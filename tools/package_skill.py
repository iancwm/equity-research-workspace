#!/usr/bin/env python3
"""Build a deterministic, host-neutral skill archive."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "persistent-equity-research"
SKILL_ROOT = REPOSITORY_ROOT / "skills" / SKILL_NAME
MAX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _version() -> str:
    return (REPOSITORY_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _skill_metadata_version() -> str:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^metadata:\s*\n(?:^[ \t]+.*\n)*?^[ \t]+version:\s*[\"']([^\"']+)[\"']\s*$", text)
    if not match:
        raise ValueError("SKILL.md metadata.version is missing")
    return match.group(1)


def _check_versions(version: str) -> None:
    plugin = json.loads((REPOSITORY_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    versions = {
        "SKILL.md": _skill_metadata_version(),
        "plugin.json": plugin.get("version"),
        "marketplace.json": marketplace.get("plugins", [{}])[0].get("version"),
    }
    mismatches = [f"{name}={value!r}" for name, value in versions.items() if value != version]
    if mismatches:
        raise ValueError(f"version {version!r} does not match " + ", ".join(mismatches))
    changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise ValueError(f"CHANGELOG.md has no release entry for {version}")


def _files() -> Iterable[Tuple[Path, str]]:
    if SKILL_ROOT.name != SKILL_NAME or not (SKILL_ROOT / "SKILL.md").is_file():
        raise ValueError("canonical skill directory is missing or misnamed")
    for path in sorted(SKILL_ROOT.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"skill archive cannot contain symlink: {path}")
        if not path.is_file():
            continue
        if path.suffix in (".pyc", ".pyo") or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(SKILL_ROOT).as_posix()
        yield path, f"{SKILL_NAME}/{relative}"


def build_archive(output: Path) -> dict:
    version = _version()
    _check_versions(version)
    output = output.expanduser().resolve()
    try:
        output.relative_to(SKILL_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("archive output must be outside the canonical skill directory")
    entries = list(_files())
    uncompressed_size = sum(path.stat().st_size for path, _ in entries)
    if uncompressed_size >= MAX_UNCOMPRESSED_BYTES:
        raise ValueError(f"uncompressed skill size is {uncompressed_size} bytes; limit is below {MAX_UNCOMPRESSED_BYTES}")

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}-", dir=str(output.parent))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, archive_name in entries:
                info = zipfile.ZipInfo(archive_name, FIXED_TIMESTAMP)
                info.create_system = 3
                executable = path.name in {
                    "init_workspace.py",
                    "migrate_v1_workspace.py",
                    "validate_workspace.py",
                }
                info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(str(temporary), str(output))
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "archive": str(output),
        "files": len(entries),
        "skill": SKILL_NAME,
        "uncompressed_bytes": uncompressed_size,
        "version": version,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the portable persistent-equity-research ZIP.")
    parser.add_argument("--output", help="Archive path; defaults to dist/<skill>-<version>.zip")
    parser.add_argument("--expected-tag", help="Require this release tag to equal v<VERSION>")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    version = _version()
    output = Path(args.output) if args.output else REPOSITORY_ROOT / "dist" / f"{SKILL_NAME}-{version}.zip"
    try:
        if args.expected_tag and args.expected_tag != f"v{version}":
            raise ValueError(f"release tag {args.expected_tag!r} must equal v{version}")
        report = build_archive(output)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        if args.format == "json":
            print(json.dumps({"built": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report["built"] = True
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Built {report['archive']} ({report['files']} files, {report['uncompressed_bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
