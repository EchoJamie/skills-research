#!/usr/bin/env python3
"""Compute a stable SHA-256 digest for one file or a directory tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_regular_files(root: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []

    def visit(directory: Path) -> None:
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
        for entry in entries:
            entry_path = Path(entry.path)
            mode = entry.stat(follow_symlinks=False).st_mode
            relative = entry_path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise ValueError(f"目标包含符号链接，无法形成稳定摘要: {relative}")
            if stat.S_ISDIR(mode):
                visit(entry_path)
            elif stat.S_ISREG(mode):
                files.append((relative, entry_path))
            else:
                raise ValueError(f"目标包含特殊文件，无法形成稳定摘要: {relative}")

    visit(root)
    return files


def aggregate_digest(entries: Iterable[tuple[str, str]]) -> str:
    """Hash length-prefixed UTF-8 relative paths and raw file digest bytes."""
    digest = hashlib.sha256()
    for relative, file_digest in entries:
        path_bytes = relative.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(bytes.fromhex(file_digest))
    return digest.hexdigest()


def inspect_target(target: Path) -> dict[str, object]:
    absolute = target.resolve(strict=True)
    original_mode = target.lstat().st_mode
    if stat.S_ISLNK(original_mode):
        raise ValueError("被审核对象本身不能是符号链接")

    if absolute.is_file():
        file_digest = sha256_file(absolute)
        return {
            "algorithm": "sha256",
            "kind": "file",
            "path": str(target),
            "file_count": 1,
            "digest": file_digest,
            "files": [{"path": absolute.name, "sha256": file_digest}],
        }

    if not absolute.is_dir():
        raise ValueError("被审核对象必须是普通文件或目录")

    paths = collect_regular_files(absolute)
    file_entries = [
        {"path": relative, "sha256": sha256_file(path)}
        for relative, path in paths
    ]
    tree_digest = aggregate_digest(
        (str(item["path"]), str(item["sha256"])) for item in file_entries
    )
    return {
        "algorithm": "sha256-tree-v1",
        "encoding": "每项依次写入 8 字节大端路径长度、UTF-8 相对路径、32 字节文件 SHA-256；按相对路径排序",
        "kind": "directory",
        "path": str(target),
        "file_count": len(file_entries),
        "digest": tree_digest,
        "files": file_entries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="计算单文件或目录全部普通文件的稳定 SHA-256 摘要。"
    )
    parser.add_argument("target", type=Path, help="要计算摘要的文件或目录")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = inspect_target(args.target)
    except (OSError, ValueError) as error:
        print(f"摘要计算失败: {error}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
