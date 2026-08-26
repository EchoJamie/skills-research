#!/usr/bin/env python3
"""管理开发资源晋级、正式集合同步、设备资源纳管与 QA 软链接。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 及更早版本
    tomllib = None


SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESOURCE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MANIFEST_VERSION = 2


class ManagerError(RuntimeError):
    """可向用户直接展示的管理错误。"""


@dataclass(frozen=True)
class InstallPaths:
    skills_home: Path
    agents_home: Path
    state_home: Path
    codex_home: Path

    @classmethod
    def from_environment(cls) -> "InstallPaths":
        user_home = Path.home()
        codex_home = Path(
            os.environ.get("CODEX_HOME", str(user_home / ".codex"))
        ).expanduser()
        return cls(
            skills_home=Path(
                os.environ.get(
                    "SKILLS_RESEARCH_SKILLS_HOME",
                    str(user_home / ".agents" / "skills"),
                )
            ).expanduser(),
            agents_home=Path(
                os.environ.get(
                    "SKILLS_RESEARCH_AGENTS_HOME", str(codex_home / "agents")
                )
            ).expanduser(),
            state_home=Path(
                os.environ.get(
                    "SKILLS_RESEARCH_STATE_HOME",
                    str(codex_home / ".skills-research"),
                )
            ).expanduser(),
            codex_home=codex_home,
        )


@dataclass(frozen=True)
class Resource:
    area: str
    kind: str
    name: str
    source: Path
    target: Path

    @property
    def selector(self) -> str:
        return f"{self.kind}:{self.name}"

    @property
    def key(self) -> str:
        return f"{self.area}:{self.selector}"


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    external_validator: Optional[Path] = None

    @property
    def ok(self) -> bool:
        return not self.errors


def path_present(path: Path) -> bool:
    """同时识别普通路径和悬空符号链接。"""
    return path.exists() or path.is_symlink()


def absolute_path(path: Path) -> Path:
    """返回绝对路径，但不跟随路径末端已有的符号链接。"""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def resolved_link(path: Path) -> Optional[Path]:
    if not path.is_symlink():
        return None
    raw_target = Path(os.readlink(path))
    if not raw_target.is_absolute():
        raw_target = path.parent / raw_target
    return raw_target.resolve(strict=False)


def same_link(target: Path, source: Path) -> bool:
    linked = resolved_link(target)
    return linked is not None and linked == source.resolve(strict=False)


def same_resource_content(left: Path, right: Path) -> bool:
    """比较资源内容、文件模式和符号链接目标，不跟随符号链接。"""
    if left.is_symlink() or right.is_symlink():
        return (
            left.is_symlink()
            and right.is_symlink()
            and os.readlink(left) == os.readlink(right)
        )
    if left.is_file():
        if (
            not right.is_file()
            or (left.stat().st_mode & 0o777) != (right.stat().st_mode & 0o777)
            or left.stat().st_size != right.stat().st_size
        ):
            return False
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            while True:
                left_chunk = left_handle.read(1024 * 1024)
                right_chunk = right_handle.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    if left.is_dir():
        if not right.is_dir():
            return False
        left_items = {item.name: item for item in left.iterdir()}
        right_items = {item.name: item for item in right.iterdir()}
        return left_items.keys() == right_items.keys() and all(
            same_resource_content(item, right_items[name])
            for name, item in left_items.items()
        )
    return False


def remove_path(path: Path) -> None:
    """删除一个已精确解析的资源路径，用于失败回滚。"""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


class ResourceManager:
    def __init__(self, repo_root: Path, paths: InstallPaths):
        self.repo_root = repo_root.resolve()
        self.paths = paths
        self.skills_source = self.repo_root / "skills"
        self.agents_source = self.repo_root / "agents"
        self.installed_root = self.repo_root / "installed"
        self.installed_skills_source = self.installed_root / "skills"
        self.installed_agents_source = self.installed_root / "agents"
        self.manifest_path = self.paths.state_home / "manifest.json"
        self.backup_root = self.paths.state_home / "backups"
        self._backup_stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")

    def _discover_area(
        self, area: str, skills_source: Path, agents_source: Path
    ) -> list[Resource]:
        resources: list[Resource] = []
        if skills_source.is_dir():
            for source in sorted(skills_source.iterdir()):
                if source.name.startswith(".") or not source.is_dir():
                    continue
                if (source / "SKILL.md").is_file():
                    resources.append(
                        Resource(
                            area,
                            "skill",
                            source.name,
                            source.resolve(),
                            absolute_path(self.paths.skills_home / source.name),
                        )
                    )
        if agents_source.is_dir():
            for source in sorted(agents_source.glob("*.toml")):
                resources.append(
                    Resource(
                        area,
                        "agent",
                        source.stem,
                        source.resolve(),
                        absolute_path(self.paths.agents_home / source.name),
                    )
                )
        return resources

    def discover_development(self) -> list[Resource]:
        return self._discover_area(
            "development", self.skills_source, self.agents_source
        )

    def discover_installed(self) -> list[Resource]:
        return self._discover_area(
            "installed", self.installed_skills_source, self.installed_agents_source
        )

    def discover(self) -> list[Resource]:
        return self.discover_development() + self.discover_installed()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": MANIFEST_VERSION, "resources": []}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManagerError(f"无法读取管理清单 {self.manifest_path}：{exc}") from exc
        if data.get("version") != MANIFEST_VERSION or not isinstance(
            data.get("resources"), list
        ):
            raise ManagerError(f"不支持的管理清单格式：{self.manifest_path}")
        return data

    def _save_manifest(self, entries: list[dict[str, Any]]) -> None:
        self.paths.state_home.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": MANIFEST_VERSION,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "resources": sorted(entries, key=lambda item: (item["kind"], item["name"])),
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.manifest_path)

    def _quick_validator(self) -> Optional[Path]:
        candidates = [
            self.paths.codex_home
            / "skills"
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py",
            Path.home()
            / ".codex"
            / "skills"
            / ".system"
            / "skill-creator"
            / "scripts"
            / "quick_validate.py",
        ]
        return next((path for path in candidates if path.is_file()), None)

    def validate(self, use_external: bool = True) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        required = ["README.md", "AGENTS.md", ".gitignore", "skills", "agents", "research"]
        for relative in required:
            if not (self.repo_root / relative).exists():
                errors.append(f"缺少仓库基础路径：{relative}")

        skill_dirs: list[Path] = []
        areas = [
            ("开发区", self.skills_source, self.agents_source),
            ("正式集合", self.installed_skills_source, self.installed_agents_source),
        ]
        for area_label, skills_source, agents_source in areas:
            if skills_source.is_dir():
                for skill_dir in sorted(skills_source.iterdir()):
                    if skill_dir.name.startswith("."):
                        continue
                    if not skill_dir.is_dir():
                        relative = skills_source.relative_to(self.repo_root)
                        errors.append(f"{relative}/ 只允许 Skill 目录：{skill_dir.name}")
                        continue
                    skill_dirs.append(skill_dir)
                    self._validate_skill(skill_dir, errors)

            agent_files = (
                sorted(agents_source.glob("*.toml"))
                if agents_source.is_dir()
                else []
            )
            seen_agent_names: dict[str, Path] = {}
            for agent_file in agent_files:
                parsed_name = self._validate_agent(agent_file, errors, warnings)
                if parsed_name:
                    previous = seen_agent_names.get(parsed_name)
                    if previous:
                        errors.append(
                            f"{area_label} Agent name 重复：{parsed_name}"
                            f"（{previous.name}、{agent_file.name}）"
                        )
                    seen_agent_names[parsed_name] = agent_file

        external = self._quick_validator() if use_external and skill_dirs else None
        if external:
            for skill_dir in skill_dirs:
                completed = subprocess.run(
                    [sys.executable, str(external), str(skill_dir)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if completed.returncode != 0:
                    detail = (completed.stdout + completed.stderr).strip()
                    errors.append(
                        f"官方 quick_validate 未通过：{skill_dir.name}"
                        + (f"：{detail}" if detail else "")
                    )

        return ValidationResult(errors, warnings, external)

    def _validate_skill(self, skill_dir: Path, errors: list[str]) -> None:
        if not SKILL_NAME_RE.fullmatch(skill_dir.name):
            errors.append(f"Skill 目录名不合法：{skill_dir.name}")
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"Skill 缺少 SKILL.md：{skill_dir.relative_to(self.repo_root)}")
            return
        lines = skill_file.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            errors.append(f"SKILL.md 缺少 YAML frontmatter：{skill_dir.name}")
            return
        try:
            closing = next(
                index
                for index, line in enumerate(lines[1:], 1)
                if line.strip() == "---"
            )
        except StopIteration:
            errors.append(f"SKILL.md frontmatter 未闭合：{skill_dir.name}")
            return
        fields: dict[str, str] = {}
        for line in lines[1:closing]:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
            if match:
                fields[match.group(1)] = match.group(2).strip().strip("'\"")
        skill_name = fields.get("name", "")
        if not skill_name:
            errors.append(f"SKILL.md 缺少 name：{skill_dir.name}")
        elif skill_name != skill_dir.name:
            errors.append(
                f"Skill 名称不一致：目录 {skill_dir.name}，frontmatter {skill_name}"
            )
        if "description" not in fields or not fields["description"]:
            errors.append(f"SKILL.md 缺少 description：{skill_dir.name}")

    def _validate_agent(
        self, agent_file: Path, errors: list[str], warnings: list[str]
    ) -> Optional[str]:
        if not RESOURCE_FILE_RE.fullmatch(agent_file.stem):
            errors.append(f"Agent 文件名不合法：{agent_file.name}")
        if tomllib is None:
            errors.append("校验 Agent TOML 需要 Python 3.11 或更高版本")
            return None
        try:
            with agent_file.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"Agent TOML 无法解析：{agent_file.name}：{exc}")
            return None
        for field in ("name", "description", "developer_instructions"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                errors.append(f"Agent 缺少非空 {field}：{agent_file.name}")
        name = data.get("name") if isinstance(data.get("name"), str) else None
        if name and agent_file.stem.replace("-", "_") != name:
            warnings.append(
                f"Agent 文件名与 name 不完全对应：{agent_file.name} -> {name}"
            )
        return name

    def print_validation(self, result: ValidationResult) -> None:
        for warning in result.warnings:
            print(f"警告：{warning}")
        for error in result.errors:
            print(f"错误：{error}", file=sys.stderr)
        development = self.discover_development()
        installed = self.discover_installed()
        development_skills = sum(resource.kind == "skill" for resource in development)
        development_agents = sum(resource.kind == "agent" for resource in development)
        installed_skills = sum(resource.kind == "skill" for resource in installed)
        installed_agents = sum(resource.kind == "agent" for resource in installed)
        if result.ok:
            suffix = (
                f"；已调用 {result.external_validator}"
                if result.external_validator
                else ""
            )
            print(
                "校验通过（"
                f"开发区 {development_skills} Skill/{development_agents} Agent，"
                f"正式集合 {installed_skills} Skill/{installed_agents} Agent）{suffix}"
            )

    def _backup(self, resource: Resource) -> Path:
        backup = self.backup_root / self._backup_stamp / resource.kind / resource.target.name
        candidate = backup
        counter = 1
        while path_present(candidate):
            counter += 1
            candidate = backup.with_name(f"{backup.name}.{counter}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resource.target), str(candidate))
        return candidate

    @staticmethod
    def _entry_key(entry: dict[str, Any]) -> str:
        return (
            f"{entry.get('channel')}:{entry.get('kind')}:{entry.get('name')}"
        )

    def _entry_for_resource(
        self,
        resource: Resource,
        channel: str,
        restore: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "channel": channel,
            "kind": resource.kind,
            "name": resource.name,
            "source": str(resource.source),
            "target": str(resource.target),
            "mode": "symlink",
            "repository": str(self.repo_root),
        }
        if restore:
            entry["restore"] = restore
        return entry

    def _select_development(
        self, selectors: Iterable[str], operation: str = "QA 接入"
    ) -> list[Resource]:
        requested = list(dict.fromkeys(selectors))
        if not requested:
            raise ManagerError(
                f"{operation}必须显式指定资源，"
                "例如 skill:demo-skill 或 agent:demo-agent"
            )
        resources = {
            resource.selector: resource for resource in self.discover_development()
        }
        unknown = [selector for selector in requested if selector not in resources]
        if unknown:
            raise ManagerError("开发区中不存在资源：" + "、".join(unknown))
        return [resources[selector] for selector in requested]

    def promote(self, selectors: Iterable[str], force: bool = False) -> None:
        """把显式指定的开发资源复制到正式集合，不修改设备安装。"""
        result = self.validate()
        if not result.ok:
            self.print_validation(result)
            raise ManagerError("仓库校验失败，未晋级正式资源")
        resources = self._select_development(selectors, "正式晋级")
        planned: list[tuple[Resource, Path, bool]] = []
        conflicts: list[str] = []
        for resource in resources:
            if resource.kind == "skill":
                target = self.installed_skills_source / resource.name
            else:
                target = self.installed_agents_source / f"{resource.name}.toml"
            if target.is_symlink():
                raise ManagerError(f"正式集合目标是软链接，未晋级：{target}")
            exists = path_present(target)
            if exists and same_resource_content(resource.source, target):
                continue
            if exists and not force:
                conflicts.append(resource.selector)
            planned.append((resource, target, exists))
        if conflicts:
            raise ManagerError(
                "正式集合中存在内容不同的资源，未做任何修改："
                + "、".join(conflicts)
                + "；确认更新后可使用 --force"
            )
        if not planned:
            for resource in resources:
                print(f"正式资源内容一致，无需晋级 {resource.selector}")
            return

        self.installed_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".promote-", dir=self.installed_root
        ) as temporary:
            staging_root = Path(temporary)
            staged_resources: list[tuple[Resource, Path, Path, bool]] = []
            for resource, target, exists in planned:
                relative = target.relative_to(self.installed_root)
                staged = staging_root / "next" / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                if resource.source.is_dir():
                    shutil.copytree(resource.source, staged, symlinks=True)
                else:
                    shutil.copy2(resource.source, staged, follow_symlinks=False)
                staged_resources.append((resource, target, staged, exists))

            applied: list[tuple[Path, Optional[Path]]] = []
            try:
                for resource, target, staged, exists in staged_resources:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    backup: Optional[Path] = None
                    if exists:
                        relative = target.relative_to(self.installed_root)
                        backup = staging_root / "previous" / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        target.rename(backup)
                    try:
                        staged.rename(target)
                    except Exception:
                        if backup and not path_present(target):
                            backup.rename(target)
                        raise
                    applied.append((target, backup))
                    action = "更新" if exists else "晋级"
                    print(f"已{action}正式资源 {resource.selector} -> {target}")
            except Exception as exc:
                for target, backup in reversed(applied):
                    remove_path(target)
                    if backup:
                        backup.rename(target)
                raise ManagerError(f"正式资源晋级失败，已尝试回滚：{exc}") from exc

    def sync(self, force: bool = False) -> None:
        result = self.validate()
        if not result.ok:
            self.print_validation(result)
            raise ManagerError("仓库校验失败，未同步正式已安装集合")
        resources = self.discover_installed()
        if not resources:
            print("正式已安装集合为空，无需同步。")
            return

        manifest = self._load_manifest()
        entries = {
            self._entry_key(item): item for item in manifest["resources"]
        }
        qa_entries = {
            f"{item.get('kind')}:{item.get('name')}": item
            for item in entries.values()
            if item.get("repository") == str(self.repo_root)
            and item.get("channel") == "qa"
        }

        conflicts: list[Resource] = []
        blocked_by_backup: list[str] = []
        for resource in resources:
            qa_entry = qa_entries.get(resource.selector)
            if qa_entry:
                restore = qa_entry.get("restore")
                if isinstance(restore, dict) and restore.get("type") == "backup":
                    blocked_by_backup.append(resource.selector)
                continue
            if not path_present(resource.target) or same_link(
                resource.target, resource.source
            ):
                continue
            conflicts.append(resource)
        if blocked_by_backup:
            raise ManagerError(
                "以下资源正在 QA，且覆盖前存在设备资源；请先解除 QA："
                + "、".join(blocked_by_backup)
            )
        if conflicts and not force:
            raise ManagerError(
                "设备中存在同名资源，未同步正式集合："
                + "、".join(resource.selector for resource in conflicts)
                + "；确认接管后可使用 --force"
            )

        conflict_keys = {resource.key for resource in conflicts}
        for resource in resources:
            qa_entry = qa_entries.get(resource.selector)
            if qa_entry:
                previous_restore = qa_entry.get("restore")
                next_restore: dict[str, str] = {
                    "type": "managed",
                    "source": str(resource.source),
                }
                if (
                    isinstance(previous_restore, dict)
                    and previous_restore.get("type") == "managed"
                    and previous_restore.get("fallback_backup")
                ):
                    next_restore["fallback_backup"] = str(
                        previous_restore["fallback_backup"]
                    )
                qa_entry["restore"] = next_restore
                entries[f"qa:{resource.selector}"] = qa_entry
                print(f"QA 结束后将恢复正式资源 {resource.selector}")
                continue
            if resource.key in conflict_keys:
                backup = self._backup(resource)
                print(f"已备份设备资源 {resource.selector} -> {backup}")
                restore: Optional[dict[str, str]] = {
                    "type": "backup",
                    "path": str(backup),
                }
            else:
                existing = entries.get(f"installed:{resource.selector}")
                existing_restore = existing.get("restore") if existing else None
                restore = existing_restore if isinstance(existing_restore, dict) else None
            resource.target.parent.mkdir(parents=True, exist_ok=True)
            if not path_present(resource.target):
                resource.target.symlink_to(
                    resource.source, target_is_directory=resource.source.is_dir()
                )
                print(f"已同步正式资源 {resource.selector} -> {resource.target}")
            else:
                print(f"正式资源已同步，无需变更 {resource.selector}")
            entries[f"installed:{resource.selector}"] = self._entry_for_resource(
                resource, "installed", restore=restore
            )
        self._save_manifest(list(entries.values()))

    def qa_link(self, selectors: Iterable[str], force: bool = False) -> None:
        result = self.validate()
        if not result.ok:
            self.print_validation(result)
            raise ManagerError("仓库校验失败，未执行 QA 接入")
        resources = self._select_development(selectors)
        installed = {
            resource.selector: resource for resource in self.discover_installed()
        }
        manifest = self._load_manifest()
        entries = {
            self._entry_key(item): item for item in manifest["resources"]
        }

        conflicts: list[Resource] = []
        for resource in resources:
            if not path_present(resource.target):
                continue
            if same_link(resource.target, resource.source):
                continue
            installed_resource = installed.get(resource.selector)
            if installed_resource and same_link(
                resource.target, installed_resource.source
            ):
                continue
            conflicts.append(resource)
        if conflicts and not force:
            names = "、".join(resource.selector for resource in conflicts)
            raise ManagerError(
                f"设备中存在同名资源，未做任何修改：{names}；"
                "确认接管后可使用 --force，原资源会先备份"
            )

        conflict_keys = {resource.key for resource in conflicts}
        for resource in resources:
            qa_key = f"qa:{resource.selector}"
            existing_qa = entries.get(qa_key)
            if existing_qa and same_link(resource.target, resource.source):
                print(f"已接入 QA，无需变更 {resource.selector}")
                continue

            restore: Optional[dict[str, str]] = None
            installed_resource = installed.get(resource.selector)
            installed_entry = entries.get(f"installed:{resource.selector}")
            if installed_resource and (
                not path_present(resource.target)
                or same_link(resource.target, installed_resource.source)
                or same_link(resource.target, resource.source)
            ):
                restore = {
                    "type": "managed",
                    "source": str(installed_resource.source),
                }
                installed_restore = (
                    installed_entry.get("restore") if installed_entry else None
                )
                if (
                    isinstance(installed_restore, dict)
                    and installed_restore.get("type") == "backup"
                ):
                    restore["fallback_backup"] = str(installed_restore.get("path", ""))
            if resource.key in conflict_keys:
                backup = self._backup(resource)
                restore = {"type": "backup", "path": str(backup)}
                print(f"已备份设备资源 {resource.selector} -> {backup}")
            elif path_present(resource.target) and not same_link(
                resource.target, resource.source
            ):
                resource.target.unlink()
                entries.pop(f"installed:{resource.selector}", None)
            resource.target.parent.mkdir(parents=True, exist_ok=True)
            if not path_present(resource.target):
                resource.target.symlink_to(
                    resource.source, target_is_directory=resource.source.is_dir()
                )
                print(f"已接入 QA {resource.selector} -> {resource.target}")
            else:
                print(f"已接入 QA，无需变更 {resource.selector}")
            entries.pop(f"installed:{resource.selector}", None)
            entries[qa_key] = self._entry_for_resource(
                resource, "qa", restore=restore
            )
        self._save_manifest(list(entries.values()))

    def _expected_target(self, entry: dict[str, Any]) -> Optional[Path]:
        kind = entry.get("kind")
        name = entry.get("name")
        if not isinstance(name, str) or not RESOURCE_FILE_RE.fullmatch(name):
            return None
        if kind == "skill":
            return absolute_path(self.paths.skills_home / name)
        if kind == "agent":
            return absolute_path(self.paths.agents_home / f"{name}.toml")
        return None

    def qa_unlink(self, selectors: Iterable[str]) -> None:
        manifest = self._load_manifest()
        selected = set(selectors)
        if not selected:
            raise ManagerError(
                "解除 QA 接入必须显式指定资源，例如 skill:demo-skill 或 agent:demo-agent"
            )
        entries = manifest["resources"]
        current_entries = [
            entry
            for entry in entries
            if entry.get("repository") == str(self.repo_root)
            and entry.get("channel") == "qa"
        ]
        known = {
            f"{entry.get('kind')}:{entry.get('name')}" for entry in current_entries
        }
        unknown = selected - known
        if unknown:
            raise ManagerError("未找到已登记的 QA 接入：" + "、".join(sorted(unknown)))
        candidates = [
            entry
            for entry in current_entries
            if f"{entry.get('kind')}:{entry.get('name')}" in selected
        ]

        installed = {
            resource.selector: resource for resource in self.discover_installed()
        }
        remaining = list(entries)
        refused: list[str] = []
        for entry in candidates:
            key = f"{entry.get('kind')}:{entry.get('name')}"
            expected = self._expected_target(entry)
            recorded_target = absolute_path(Path(str(entry.get("target", ""))))
            if expected is None or expected != recorded_target:
                refused.append(f"{key}（清单目标异常）")
                continue
            target = expected
            source = Path(str(entry.get("source", ""))).resolve(strict=False)
            if path_present(target) and not same_link(target, source):
                refused.append(f"{key}（设备目标已不是登记的仓库软链接）")
                continue
            restore = entry.get("restore")
            if isinstance(restore, dict) and restore.get("type") == "managed":
                restore_source = Path(str(restore.get("source", "")))
                if not restore_source.exists():
                    refused.append(f"{key}（待恢复的正式资源不存在）")
            elif isinstance(restore, dict) and restore.get("type") == "backup":
                backup = Path(str(restore.get("path", "")))
                if not path_present(backup):
                    refused.append(f"{key}（待恢复的设备备份不存在）")
        if refused:
            raise ManagerError("以下资源未解除：" + "、".join(refused))

        for entry in candidates:
            key = f"{entry.get('kind')}:{entry.get('name')}"
            target = self._expected_target(entry)
            assert target is not None
            if path_present(target):
                target.unlink()
            restore = entry.get("restore")
            if isinstance(restore, dict) and restore.get("type") == "managed":
                restore_source = Path(str(restore["source"])).resolve(strict=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(
                    restore_source, target_is_directory=restore_source.is_dir()
                )
                installed_resource = installed.get(key)
                if installed_resource:
                    fallback = str(restore.get("fallback_backup", ""))
                    installed_restore = (
                        {"type": "backup", "path": fallback} if fallback else None
                    )
                    remaining.append(
                        self._entry_for_resource(
                            installed_resource,
                            "installed",
                            restore=installed_restore,
                        )
                    )
                print(f"已解除 QA 并恢复正式资源 {key} -> {target}")
            elif isinstance(restore, dict) and restore.get("type") == "backup":
                backup = Path(str(restore["path"]))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(target))
                print(f"已解除 QA 并恢复设备资源 {key} -> {target}")
            else:
                print(f"已解除 QA 接入 {key} -> {target}")
            remaining.remove(entry)
        self._save_manifest(remaining)

    def unsync(self, selectors: Iterable[str]) -> None:
        selected = set(selectors)
        if not selected:
            raise ManagerError(
                "解除正式同步必须显式指定资源，例如 skill:demo-skill"
            )
        installed = {
            resource.selector: resource for resource in self.discover_installed()
        }
        unknown = selected - installed.keys()
        if unknown:
            raise ManagerError("正式集合中不存在资源：" + "、".join(sorted(unknown)))

        manifest = self._load_manifest()
        entries = {
            self._entry_key(item): item for item in manifest["resources"]
        }
        refused: list[str] = []
        for selector in sorted(selected):
            resource = installed[selector]
            qa_entry = entries.get(f"qa:{selector}")
            if qa_entry:
                continue
            if path_present(resource.target) and not same_link(
                resource.target, resource.source
            ):
                refused.append(f"{selector}（设备目标不是正式集合软链接）")
                continue
            installed_entry = entries.get(f"installed:{selector}")
            restore = installed_entry.get("restore") if installed_entry else None
            if isinstance(restore, dict) and restore.get("type") == "backup":
                backup = Path(str(restore.get("path", "")))
                if not path_present(backup):
                    refused.append(f"{selector}（待恢复的设备备份不存在）")
        if refused:
            raise ManagerError("以下资源未解除正式同步：" + "、".join(refused))

        for selector in sorted(selected):
            resource = installed[selector]
            qa_entry = entries.get(f"qa:{selector}")
            if qa_entry:
                restore = qa_entry.get("restore")
                if isinstance(restore, dict) and restore.get("type") == "managed":
                    qa_entry.pop("restore", None)
                    entries[f"qa:{selector}"] = qa_entry
                    print(f"已取消 QA 结束后的正式恢复 {selector}")
                continue
            installed_entry = entries.get(f"installed:{selector}")
            restore = installed_entry.get("restore") if installed_entry else None
            had_target = path_present(resource.target)
            if had_target:
                resource.target.unlink()
            if isinstance(restore, dict) and restore.get("type") == "backup":
                backup = Path(str(restore["path"]))
                resource.target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(resource.target))
                print(f"已解除正式同步并恢复设备资源 {selector}")
            elif had_target:
                print(f"已解除正式同步 {selector} -> {resource.target}")
            else:
                print(f"正式链接已不存在，清理登记 {selector}")
            entries.pop(f"installed:{selector}", None)
        self._save_manifest(list(entries.values()))

    def status(self) -> None:
        development = self.discover_development()
        installed = self.discover_installed()
        manifest = self._load_manifest()
        registered = {
            self._entry_key(entry): entry
            for entry in manifest["resources"]
            if entry.get("repository") == str(self.repo_root)
        }
        if not development and not installed and not registered:
            print("仓库没有开发资源、正式已安装资源或管理登记。")
            return
        installed_by_selector = {
            resource.selector: resource for resource in installed
        }
        print("开发与 QA 资源")
        for resource in development:
            entry = registered.get(f"qa:{resource.selector}")
            if not path_present(resource.target):
                state = "未接入 QA"
            elif same_link(resource.target, resource.source):
                state = "QA 已接入" if entry else "已链接未登记"
            elif entry:
                state = "QA 链接漂移"
            elif resource.selector in installed_by_selector and same_link(
                resource.target, installed_by_selector[resource.selector].source
            ):
                state = "正式集合生效"
            else:
                state = "同名设备资源"
            print(f"{resource.selector:<32} {state:<12} {resource.target}")

        print("\n正式已安装集合")
        if not installed:
            print("（空）")
        development_by_selector = {
            resource.selector: resource for resource in development
        }
        for resource in installed:
            installed_entry = registered.get(f"installed:{resource.selector}")
            qa_entry = registered.get(f"qa:{resource.selector}")
            if qa_entry and resource.selector in development_by_selector and same_link(
                resource.target, development_by_selector[resource.selector].source
            ):
                state = "QA 临时覆盖"
            elif not path_present(resource.target):
                state = "未同步"
            elif same_link(resource.target, resource.source):
                state = "已同步" if installed_entry else "已链接未登记"
            elif installed_entry:
                state = "正式链接漂移"
            else:
                state = "同名设备资源"
            print(f"{resource.selector:<32} {state:<12} {resource.target}")

        known_keys = {f"qa:{resource.selector}" for resource in development}
        known_keys.update(f"installed:{resource.selector}" for resource in installed)
        for key, entry in sorted(registered.items()):
            if key not in known_keys:
                print(f"{key:<32} 仓库源已移除   {entry.get('target')}")

    def device_list(self) -> None:
        """只读盘点设备目录；不把结果写入仓库或管理清单。"""
        development_targets = {
            resource.target: resource for resource in self.discover_development()
        }
        installed_targets = {
            resource.target: resource for resource in self.discover_installed()
        }
        skill_roots = [
            ("用户目录", absolute_path(self.paths.skills_home), False),
            ("旧版目录", absolute_path(self.paths.codex_home / "skills"), True),
            ("系统目录", absolute_path(self.paths.codex_home / "skills" / ".system"), False),
        ]
        seen_roots: set[Path] = set()
        skill_rows: list[tuple[str, str, str, Path]] = []
        for origin, root, skip_system in skill_roots:
            if root in seen_roots or not root.is_dir():
                continue
            seen_roots.add(root)
            for item in sorted(root.iterdir()):
                if skip_system and item.name == ".system":
                    continue
                if item.name.startswith(".") or not (item / "SKILL.md").is_file():
                    continue
                target = absolute_path(item)
                development_resource = development_targets.get(target)
                installed_resource = installed_targets.get(target)
                if development_resource and same_link(
                    target, development_resource.source
                ):
                    ownership = "仓库 QA 接入"
                elif installed_resource and same_link(
                    target, installed_resource.source
                ):
                    ownership = "仓库正式同步"
                elif origin == "系统目录":
                    ownership = "系统管理"
                else:
                    ownership = "设备既有"
                skill_rows.append((origin, item.name, ownership, target))

        print("设备 Skill（只读盘点）")
        if skill_rows:
            for origin, name, ownership, path in skill_rows:
                print(f"{origin:<8} {name:<32} {ownership:<12} {path}")
        else:
            print("未发现目录型 Skill。")

        agent_rows: list[tuple[str, str, Path]] = []
        if self.paths.agents_home.is_dir():
            for item in sorted(self.paths.agents_home.glob("*.toml")):
                target = absolute_path(item)
                development_resource = development_targets.get(target)
                installed_resource = installed_targets.get(target)
                if development_resource and same_link(
                    target, development_resource.source
                ):
                    ownership = "仓库 QA 接入"
                elif installed_resource and same_link(
                    target, installed_resource.source
                ):
                    ownership = "仓库正式同步"
                else:
                    ownership = "设备既有"
                agent_rows.append((item.stem, ownership, target))
        print("\n设备自定义 Agent（只读盘点）")
        if agent_rows:
            for name, ownership, path in agent_rows:
                print(f"{name:<32} {ownership:<12} {path}")
        else:
            print("未发现自定义 Agent。")
        print("\n插件 Skill 由 Codex 插件机制管理，不由本仓库接管。")

    def adopt(self, selector: str) -> None:
        """把一个显式指定的设备资源迁入正式集合，并改为软链接。"""
        if ":" not in selector:
            raise ManagerError("纳管资源必须写成 skill:name 或 agent:name")
        kind, name = selector.split(":", 1)
        pattern = SKILL_NAME_RE if kind == "skill" else RESOURCE_FILE_RE
        if kind not in {"skill", "agent"} or not pattern.fullmatch(name):
            raise ManagerError(f"资源选择器不合法：{selector}")

        if kind == "skill":
            candidates = [
                absolute_path(self.paths.skills_home / name),
                absolute_path(self.paths.codex_home / "skills" / name),
            ]
            repository_target = self.installed_skills_source / name
            device_target = absolute_path(self.paths.skills_home / name)
        else:
            candidates = [absolute_path(self.paths.agents_home / f"{name}.toml")]
            repository_target = self.installed_agents_source / f"{name}.toml"
            device_target = candidates[0]

        present = list(dict.fromkeys(path for path in candidates if path_present(path)))
        if not present:
            raise ManagerError(f"设备中未找到资源：{selector}")
        if len(present) > 1:
            raise ManagerError(
                f"设备中存在多个同名来源，无法自动纳管：{selector} -> "
                + "、".join(str(path) for path in present)
            )
        source = present[0]
        if source.is_symlink():
            raise ManagerError(f"设备资源已经是软链接，未纳管：{source}")
        if path_present(repository_target):
            raise ManagerError(f"正式集合中已存在资源，未覆盖：{repository_target}")
        if kind == "skill" and not source.is_dir():
            raise ManagerError(f"Skill 设备资源不是目录：{source}")
        if kind == "agent" and not source.is_file():
            raise ManagerError(f"Agent 设备资源不是文件：{source}")
        if kind == "skill" and not (source / "SKILL.md").is_file():
            raise ManagerError(f"设备 Skill 缺少 SKILL.md：{source}")
        if kind == "skill" and (source / ".git").exists():
            raise ManagerError(
                f"设备 Skill 含嵌套 Git 仓库，未直接迁入：{source}；"
                "应先明确上游版本管理方式"
            )

        errors: list[str] = []
        warnings: list[str] = []
        if kind == "skill":
            self._validate_skill(source, errors)
            external = self._quick_validator()
            if external and not errors:
                completed = subprocess.run(
                    [sys.executable, str(external), str(source)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if completed.returncode != 0:
                    detail = (completed.stdout + completed.stderr).strip()
                    errors.append(
                        "官方 quick_validate 未通过"
                        + (f"：{detail}" if detail else "")
                    )
        else:
            self._validate_agent(source, errors, warnings)
        if errors:
            raise ManagerError("设备资源校验失败，未纳管：" + "；".join(errors))
        for warning in warnings:
            print(f"警告：{warning}")

        repository_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.rename(repository_target)
            device_target.parent.mkdir(parents=True, exist_ok=True)
            device_target.symlink_to(
                repository_target,
                target_is_directory=repository_target.is_dir(),
            )
            resource = Resource(
                "installed",
                kind,
                name,
                repository_target.resolve(),
                device_target,
            )
            manifest = self._load_manifest()
            entries = {
                self._entry_key(item): item for item in manifest["resources"]
            }
            entries[f"installed:{selector}"] = self._entry_for_resource(
                resource, "installed"
            )
            self._save_manifest(list(entries.values()))
        except Exception as exc:
            if device_target.is_symlink() and same_link(
                device_target, repository_target
            ):
                device_target.unlink()
            if path_present(repository_target) and not path_present(source):
                repository_target.rename(source)
            raise ManagerError(f"纳管失败，已尝试恢复原位置：{exc}") from exc
        print(f"已纳管正式资源 {selector}：{source} -> {repository_target}")

    def doctor(self) -> bool:
        print(f"仓库：{self.repo_root}")
        print(f"Python：{sys.version.split()[0]}")
        print(f"Codex：{shutil.which('codex') or '未在 PATH 中发现'}")
        print(f"Skill 设备挂载目录：{self.paths.skills_home}")
        print(f"Agent 设备挂载目录：{self.paths.agents_home}")
        print(f"管理状态目录：{self.paths.state_home}")
        if sys.version_info < (3, 11):
            print("错误：资源管理器需要 Python 3.11 或更高版本。", file=sys.stderr)
            return False
        result = self.validate()
        self.print_validation(result)
        return result.ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="校验仓库中的全部资源")
    subparsers.add_parser("doctor", help="检查本机运行条件和目录")
    subparsers.add_parser("status", help="查看开发资源与正式集合的设备状态")
    subparsers.add_parser("device-list", help="只读盘点设备已有 Skill 与 Agent")

    sync_parser = subparsers.add_parser(
        "sync", help="把正式已安装集合软链接到设备"
    )
    sync_parser.add_argument(
        "--force", action="store_true", help="备份并接管设备中的同名目标"
    )

    unsync_parser = subparsers.add_parser(
        "unsync", help="解除显式指定的正式集合设备软链接"
    )
    unsync_parser.add_argument(
        "selectors",
        nargs="+",
        metavar="KIND:NAME",
        help="指定 skill:name 或 agent:name，可同时指定多项",
    )

    adopt_parser = subparsers.add_parser(
        "adopt", help="把一个设备既有资源迁入正式集合并改为软链接"
    )
    adopt_parser.add_argument(
        "selector", metavar="KIND:NAME", help="指定一个 skill:name 或 agent:name"
    )

    promote_parser = subparsers.add_parser(
        "promote", help="把显式指定的开发资源复制到正式集合"
    )
    promote_parser.add_argument(
        "selectors",
        nargs="+",
        metavar="KIND:NAME",
        help="指定 skill:name 或 agent:name，可同时指定多项",
    )
    promote_parser.add_argument(
        "--force", action="store_true", help="更新正式集合中的不同版本"
    )

    link_parser = subparsers.add_parser(
        "qa-link", help="把显式指定的仓库资源软链接到设备用于 QA"
    )
    link_parser.add_argument(
        "selectors",
        nargs="+",
        metavar="KIND:NAME",
        help="指定 skill:name 或 agent:name，可同时指定多项",
    )
    link_parser.add_argument(
        "--force", action="store_true", help="备份并接管设备中的同名目标"
    )

    unlink_parser = subparsers.add_parser(
        "qa-unlink", help="解除显式指定且由本仓库登记的 QA 软链接"
    )
    unlink_parser.add_argument(
        "selectors",
        nargs="+",
        metavar="KIND:NAME",
        help="指定 skill:name 或 agent:name，可同时指定多项",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    manager = ResourceManager(repo_root, InstallPaths.from_environment())
    try:
        if args.command == "validate":
            result = manager.validate()
            manager.print_validation(result)
            return 0 if result.ok else 1
        if args.command == "doctor":
            return 0 if manager.doctor() else 1
        if args.command == "status":
            manager.status()
            return 0
        if args.command == "device-list":
            manager.device_list()
            return 0
        if args.command == "sync":
            manager.sync(args.force)
            return 0
        if args.command == "unsync":
            manager.unsync(args.selectors)
            return 0
        if args.command == "adopt":
            manager.adopt(args.selector)
            return 0
        if args.command == "promote":
            manager.promote(args.selectors, args.force)
            return 0
        if args.command == "qa-link":
            manager.qa_link(args.selectors, args.force)
            return 0
        if args.command == "qa-unlink":
            manager.qa_unlink(args.selectors)
            return 0
    except ManagerError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
