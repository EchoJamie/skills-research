from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_MAVEN_ARGS = ["-B", "-ntp", "-Dstyle.color=never"]
DEFAULT_THREAD_COUNT = "4C"
DEFAULT_RUNS_DIR = ".codex-runs/maven"
MAX_ARCHIVED_RUNS = 5
RUN_DIR_NAME_PATTERN = re.compile(r"^\d{8}-\d{6}-mvn-\d+(?:-\d+)?$")


@dataclass(frozen=True)
class RunResult:
    status: str
    adapter_exit_code: int
    maven_exit_code: int
    project_root: Path
    run_dir: Path
    command: list[str]
    duration_seconds: float
    next_step: str
    errors_path: Path | None
    reports_path: Path | None


@dataclass(frozen=True)
class AdapterOptions:
    threads: str | None
    runs_dir: str | None
    report_dirs: list[str] | None
    maven_args: list[str]


@dataclass(frozen=True)
class ExecutionSettings:
    threads: str | None
    enable_sdkmanrc: bool
    runs_dir: Path
    report_dirs: list[Path] | None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    try:
        result = execute(args, Path.cwd())
    except AdapterError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    summary = render_summary(result)
    (result.run_dir / "summary.txt").write_text(summary, encoding="utf-8")
    prune_old_runs(result.run_dir.parent, keep_last=MAX_ARCHIVED_RUNS)
    sys.stdout.write(summary)
    return result.adapter_exit_code


def execute(args: Sequence[str], cwd: Path) -> RunResult:
    started = time.monotonic()
    started_epoch = time.time()
    options = parse_adapter_args(args)
    project_root = find_project_root(cwd)
    settings = resolve_settings(project_root, options)
    executable = select_maven_executable(project_root)
    maven_args = build_maven_args(settings, options.maven_args)
    run_dir = allocate_run_dir(settings.runs_dir)
    command = [str(executable), *maven_args]

    completed = run_maven(command, project_root, run_dir, settings.enable_sdkmanrc)

    combined_output = f"{completed.stdout}{completed.stderr}"
    (run_dir / "mvn.log").write_text(combined_output, encoding="utf-8")
    (run_dir / "command.txt").write_text(render_command(command, project_root), encoding="utf-8")
    (run_dir / "env.txt").write_text(render_env(settings.enable_sdkmanrc), encoding="utf-8")

    duration_seconds = time.monotonic() - started
    report_dirs = discover_report_dirs(project_root, started_epoch, settings.report_dirs)
    reports_path = copy_reports(report_dirs, project_root, run_dir) if report_dirs else None

    if completed.returncode == 0:
        return RunResult(
            status="SUCCESS",
            adapter_exit_code=0,
            maven_exit_code=0,
            project_root=project_root,
            run_dir=run_dir,
            command=command,
            duration_seconds=duration_seconds,
            next_step="No deeper inspection needed.",
            errors_path=None,
            reports_path=None,
        )

    status = classify_failure(combined_output, report_dirs)
    errors_path = run_dir / "errors.txt"
    errors_path.write_text(render_errors(status, combined_output, reports_path), encoding="utf-8")

    return RunResult(
        status=status,
        adapter_exit_code=1,
        maven_exit_code=completed.returncode,
        project_root=project_root,
        run_dir=run_dir,
        command=command,
        duration_seconds=duration_seconds,
        next_step=next_step_for_status(status),
        errors_path=errors_path,
        reports_path=reports_path,
    )


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pom.xml").exists():
            return current
        if current.parent == current:
            raise AdapterError(f"Could not find pom.xml from {start}")
        current = current.parent


def select_maven_executable(project_root: Path) -> Path:
    wrapper = project_root / "mvnw"
    if wrapper.exists():
        return wrapper

    mvn_path = shutil.which("mvn")
    if mvn_path:
        return Path(mvn_path)
    raise AdapterError("Could not find mvnw or mvn")


def parse_adapter_args(args: Sequence[str]) -> AdapterOptions:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--threads")
    parser.add_argument("--runs-dir")
    parser.add_argument("--report-dir", action="append", dest="report_dirs")
    known, remaining = parser.parse_known_args(list(args))
    return AdapterOptions(
        threads=known.threads,
        runs_dir=known.runs_dir,
        report_dirs=known.report_dirs,
        maven_args=remaining,
    )


def resolve_settings(project_root: Path, options: AdapterOptions) -> ExecutionSettings:
    threads = first_non_none(
        options.threads,
        os.environ.get("CODEX_MVN_THREADS"),
    )
    runs_dir_raw = first_non_none(
        options.runs_dir,
        os.environ.get("CODEX_MVN_RUNS_DIR"),
        DEFAULT_RUNS_DIR,
    )
    report_dirs_raw = first_non_none(
        options.report_dirs,
        env_list("CODEX_MVN_REPORT_DIRS"),
        None,
    )

    return ExecutionSettings(
        threads=threads,
        enable_sdkmanrc=True,
        runs_dir=resolve_path(project_root, runs_dir_raw),
        report_dirs=[resolve_path(project_root, item) for item in report_dirs_raw] if report_dirs_raw else None,
    )


def first_non_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def env_list(name: str) -> list[str] | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_path(project_root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (project_root / candidate).resolve()


def build_maven_args(settings: ExecutionSettings, maven_args: Sequence[str]) -> list[str]:
    args = list(maven_args)
    command = [*DEFAULT_MAVEN_ARGS]
    if settings.threads:
        return [*command, "-T", settings.threads, *args]
    if contains_explicit_maven_threads(args):
        return [*command, *args]
    return [*command, "-T", DEFAULT_THREAD_COUNT, *args]


def contains_explicit_maven_threads(args: Sequence[str]) -> bool:
    for index, arg in enumerate(args):
        if arg == "-T" and index + 1 < len(args):
            return True
        if arg == "--threads" and index + 1 < len(args):
            return True
        if arg.startswith("--threads="):
            return True
    return False


def run_maven(
    command: Sequence[str],
    project_root: Path,
    run_dir: Path,
    enable_sdkmanrc: bool,
) -> subprocess.CompletedProcess[str]:
    if enable_sdkmanrc and (project_root / ".sdkmanrc").exists() and os.environ.get("SDKMAN_DIR"):
        shell_script = (
            'log_path="$1"; shift; '
            'source "$SDKMAN_DIR/bin/sdkman-init.sh"; '
            'sdk env >"$log_path" 2>&1; '
            'sdk_status=$?; '
            'printf "\\nexit_code=%s\\n" "$sdk_status" >>"$log_path"; '
            '"$@"'
        )
        return subprocess.run(
            ["/bin/bash", "-c", shell_script, "codex-mvn-sdk", str(run_dir / "sdkman-env.log"), *command],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
    return subprocess.run(
        list(command),
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )


def allocate_run_dir(runs_root: Path) -> Path:
    runs_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{timestamp}-mvn-{os.getpid()}"
    candidate = runs_root / base_name
    index = 2

    while candidate.exists():
        candidate = runs_root / f"{base_name}-{index}"
        index += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def prune_old_runs(runs_root: Path, keep_last: int) -> None:
    run_dirs = sorted(
        (path for path in runs_root.iterdir() if path.is_dir() and RUN_DIR_NAME_PATTERN.match(path.name)),
        key=lambda path: path.name,
    )
    for path in run_dirs[:-keep_last]:
        shutil.rmtree(path)


def discover_report_dirs(project_root: Path, started_epoch: float, configured_dirs: list[Path] | None) -> list[Path]:
    if configured_dirs is not None:
        return [path for path in configured_dirs if path.is_dir() and report_dir_has_recent_files(path, started_epoch)]

    ordered: list[Path] = []

    for relative in ("target/surefire-reports", "target/failsafe-reports"):
        candidate = project_root / relative
        if candidate.is_dir():
            ordered.append(candidate)

    for glob_pattern in ("**/target/surefire-reports", "**/target/failsafe-reports"):
        for candidate in sorted(project_root.glob(glob_pattern)):
            if candidate not in ordered and candidate.is_dir():
                ordered.append(candidate)

    return [path for path in ordered if report_dir_has_recent_files(path, started_epoch)]


def report_dir_has_recent_files(report_dir: Path, started_epoch: float) -> bool:
    for child in report_dir.rglob("*"):
        if child.is_file() and child.stat().st_mtime >= started_epoch - 1:
            return True
    return False


def copy_reports(report_dirs: Sequence[Path], project_root: Path, run_dir: Path) -> Path | None:
    if not report_dirs:
        return None

    reports_root = run_dir / "reports"
    for report_dir in report_dirs:
        destination = reports_root / report_dir.relative_to(project_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(report_dir, destination)
    return reports_root


def classify_failure(output: str, report_dirs: Sequence[Path]) -> str:
    if report_dirs or "There are test failures." in output or "<<< FAILURE!" in output:
        return "TEST_FAILURE"
    if looks_like_compile_failure(output):
        return "COMPILE_FAILURE"
    return "EXECUTION_ERROR"


def looks_like_compile_failure(output: str) -> bool:
    compile_markers = (
        "COMPILATION ERROR",
        "cannot find symbol",
        "package does not exist",
        "maven-compiler-plugin",
    )
    if any(marker in output for marker in compile_markers):
        return True
    return bool(re.search(r"\[ERROR\]\s+/.+:\[\d+,\d+\]", output))


def next_step_for_status(status: str) -> str:
    if status == "COMPILE_FAILURE":
        return "Inspect errors.txt for compiler diagnostics."
    if status == "TEST_FAILURE":
        return "Inspect errors.txt, then reports/ for failing test evidence."
    if status == "EXECUTION_ERROR":
        return "Inspect errors.txt, then mvn.log if more context is needed."
    return "No deeper inspection needed."


def render_command(command: Sequence[str], project_root: Path) -> str:
    lines = [
        f"cwd={project_root}",
        "command=" + " ".join(command),
        "",
    ]
    return "\n".join(lines)


def render_env(enable_sdkmanrc: bool) -> str:
    lines = [f"timestamp={datetime.now().isoformat()}"]
    for key in ("JAVA_HOME", "MAVEN_HOME", "MAVEN_OPTS", "SDKMAN_DIR"):
        value = os.environ.get(key)
        if value:
            lines.append(f"{key}={value}")
    lines.append(f"sdkmanrc_enabled={'true' if enable_sdkmanrc else 'false'}")
    lines.append("")
    return "\n".join(lines)


def render_summary(result: RunResult) -> str:
    lines = [
        f"status: {result.status}",
        f"project_root: {result.project_root}",
        f"run_dir: {result.run_dir}",
        "command: " + " ".join(result.command),
        f"exit_code: {result.maven_exit_code}",
        f"duration: {result.duration_seconds:.3f}s",
        f"errors: {result.errors_path if result.errors_path else 'none'}",
        f"reports: {result.reports_path if result.reports_path else 'none'}",
        f"next_step: {result.next_step}",
        "",
    ]
    return "\n".join(lines)


def render_errors(status: str, output: str, reports_path: Path | None) -> str:
    if status == "COMPILE_FAILURE":
        excerpt = extract_compile_errors(output)
    elif status == "TEST_FAILURE":
        excerpt = extract_test_errors(output, reports_path)
    else:
        excerpt = extract_execution_errors(output)

    lines = [
        f"status: {status}",
        "",
        excerpt.strip(),
        "",
    ]
    return "\n".join(lines)


def extract_compile_errors(output: str) -> str:
    selected = collect_matching_lines(
        output.splitlines(),
        lambda line: any(
            marker in line
            for marker in ("COMPILATION ERROR", "cannot find symbol", "symbol:", "location:", "package does not exist")
        )
        or bool(re.search(r"\[ERROR\]\s+/.+:\[\d+,\d+\]", line)),
    )
    return "\n".join(selected) if selected else fallback_excerpt(output)


def extract_test_errors(output: str, reports_path: Path | None) -> str:
    blocks: list[str] = []
    if reports_path:
        for report_file in sorted(reports_path.rglob("*.txt")):
            report_text = report_file.read_text(encoding="utf-8").strip()
            if not report_text or not report_text_has_failures(report_text):
                continue
            blocks.append(f"report: {report_file}")
            blocks.append(report_text)
            blocks.append("")
    if blocks:
        return "\n".join(blocks).strip()
    return fallback_excerpt(output)


def extract_execution_errors(output: str) -> str:
    selected = collect_matching_lines(
        output.splitlines(),
        lambda line: any(token in line for token in ("Exception", "Caused by:", "FAILURE", "[ERROR]")),
    )
    return "\n".join(selected) if selected else fallback_excerpt(output)


def collect_matching_lines(lines: Sequence[str], predicate: Callable[[str], bool]) -> list[str]:
    selected: list[str] = []
    for line in lines:
        if predicate(line) and line not in selected:
            selected.append(line)
    return selected


def fallback_excerpt(output: str) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return "No additional failure details were captured."
    return "\n".join(lines[-20:])


def report_text_has_failures(report_text: str) -> bool:
    if "<<< FAILURE!" in report_text or "<<< ERROR!" in report_text:
        return True
    return bool(re.search(r"Failures:\s*[1-9]\d*|Errors:\s*[1-9]\d*", report_text))


class AdapterError(RuntimeError):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
