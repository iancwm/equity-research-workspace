#!/usr/bin/env python3
"""Validate the structural contract of a sector-primer workspace."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Set


REQUIRED_FILES = (
    "project.json",
    "sources/registry.jsonl",
    "data/sector-metrics.csv",
    "data/company-comps.csv",
    "state/ledger.jsonl",
    "state/assumptions.json",
    "state/contradictions.json",
    "state/research-context.json",
    "outputs/sector-primer.md",
)
METRIC_HEADERS = {"metric", "value", "unit", "period", "status", "definition", "source_ids"}
COMP_HEADERS = {"issuer", "ticker", "currency", "market_data_date", "operating_period", "basis", "source_ids"}


def json_lines(path: Path) -> None:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}: line {line_number} must be a JSON object")


def json_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc.msg}") from exc


def csv_headers(path: Path) -> Set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            return {item.strip() for item in next(reader)}
        except StopIteration as exc:
            raise ValueError(f"{path}: missing CSV header") from exc


def validate(workspace: Path) -> List[str]:
    errors: List[str] = []
    for relative in REQUIRED_FILES:
        path = workspace / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
    if errors:
        return errors

    try:
        project = json_document(workspace / "project.json")
        if not isinstance(project, dict):
            errors.append("project.json must contain an object")
        else:
            for key in ("schema_version", "workspace_type", "sector_name", "geography"):
                if not project.get(key):
                    errors.append(f"project.json missing non-empty field: {key}")
            if project.get("workspace_type") != "sector-primer":
                errors.append("project.json workspace_type must be 'sector-primer'")
        context = json_document(workspace / "state/research-context.json")
        if not isinstance(context, dict):
            errors.append("research-context.json must contain an object")
        for relative in ("state/assumptions.json", "state/contradictions.json"):
            value = json_document(workspace / relative)
            if not isinstance(value, list):
                errors.append(f"{relative} must contain a JSON array")
        json_lines(workspace / "sources/registry.jsonl")
        json_lines(workspace / "state/ledger.jsonl")
        metric_headers = csv_headers(workspace / "data/sector-metrics.csv")
        if not METRIC_HEADERS <= metric_headers:
            errors.append("sector-metrics.csv is missing required headers: " + ", ".join(sorted(METRIC_HEADERS - metric_headers)))
        comp_headers = csv_headers(workspace / "data/company-comps.csv")
        if not COMP_HEADERS <= comp_headers:
            errors.append("company-comps.csv is missing required headers: " + ", ".join(sorted(COMP_HEADERS - comp_headers)))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("workspace", type=Path)
    args = p.parse_args()
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        print(f"ERROR: workspace directory not found: {workspace}", file=sys.stderr)
        return 1
    errors = validate(workspace)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Sector workspace is structurally valid: {workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
