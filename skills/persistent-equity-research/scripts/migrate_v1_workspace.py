#!/usr/bin/env python3
"""Convert a legacy YAML/CSV workspace to v2 without changing the source."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    import yaml
except ImportError:  # pragma: no cover - exercised through the CLI environment
    yaml = None

from workspace_lib import SKILL_ROOT, validate_workspace


TEMPLATE = SKILL_ROOT / "assets" / "company-workspace"


def _read_yaml(path: Path) -> Any:
    if yaml is None:
        raise RuntimeError("migration requires PyYAML; install the development requirements and retry")
    if not path.is_file():
        raise ValueError(f"missing legacy file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_json(path: Path, value: object) -> None:
    def encode_special(item: object) -> str:
        if isinstance(item, (dt.date, dt.datetime)):
            return item.isoformat()
        raise TypeError(f"cannot encode {type(item).__name__} as JSON")

    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=encode_special) + "\n", encoding="utf-8")


def _nullable(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return None if value in (None, "") else value


def _assumption_records(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"assumptions": [], "scenario_overrides": {}}
    if isinstance(value.get("assumptions"), list):
        overrides = value.get("scenario_overrides", {})
        return {
            "assumptions": value["assumptions"],
            "scenario_overrides": overrides if isinstance(overrides, dict) else {},
        }
    if isinstance(value.get("base_case"), list):
        overrides = value.get("scenario_overrides", {})
        return {
            "assumptions": value["base_case"],
            "scenario_overrides": overrides if isinstance(overrides, dict) else {},
        }
    cases = {
        "base": value.get("base_case", {}),
        "bear": value.get("bear_case", {}),
        "bull": value.get("bull_case", {}),
    }
    names = sorted({name for case in cases.values() if isinstance(case, dict) for name in case})
    records: List[Dict[str, Any]] = []
    for index, name in enumerate(names, 1):
        record: Dict[str, Any] = {
            "id": f"ASM-{index:04d}",
            "name": str(name),
            "base": cases["base"].get(name) if isinstance(cases["base"], dict) else None,
            "units": "unspecified",
            "owner_node": "company_overlay",
            "status": "active",
        }
        for case_name in ("bear", "bull"):
            case = cases[case_name]
            if isinstance(case, dict) and name in case:
                record[case_name] = case[name]
        records.append(record)
    overrides = value.get("scenario_overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
    return {"assumptions": records, "scenario_overrides": overrides}


def _contradiction_records(value: Any) -> Dict[str, Any]:
    raw_records = value.get("contradictions", []) if isinstance(value, dict) else []
    records = []
    for index, item in enumerate(raw_records if isinstance(raw_records, list) else [], 1):
        item = item if isinstance(item, dict) else {"summary": str(item)}
        status = item.get("status", "open")
        if status not in ("open", "monitoring", "resolved"):
            status = "open"
        summary = item.get("summary") or item.get("topic") or item.get("statement") or item.get("description")
        records.append({
            "id": str(item.get("id") or f"CON-{index:04d}"),
            "summary": str(summary or json.dumps(item, sort_keys=True)),
            "ledger_ids": list(item.get("ledger_ids", [])),
            "source_ids": list(item.get("source_ids", [])),
            "status": status,
            "resolution": _nullable(item.get("resolution")),
            "last_updated": _nullable(item.get("last_updated")),
        })
    return {"contradictions": records}


def _source_records(path: Path, today: str) -> Iterable[Dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not any((value or "").strip() for value in row.values()):
                continue
            primary = (row.get("primary_source") or "").strip().lower() in ("1", "true", "yes", "y")
            try:
                tier = int((row.get("quality_tier") or "4").strip())
            except ValueError:
                tier = 4
            records.append({
                "source_id": (row.get("source_id") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "source_type": (row.get("source_type") or "").strip(),
                "publisher": (row.get("publisher") or "").strip(),
                "url_or_ref": (row.get("url_or_ref") or "").strip(),
                "publication_date": _nullable((row.get("publication_date") or "").strip()),
                "observation_period": _nullable((row.get("observation_period") or "").strip()),
                "accessed_at": (row.get("accessed_at") or "").strip() or today,
                "primary_source": primary,
                "quality_tier": max(1, min(4, tier)),
                "notes": _nullable((row.get("notes") or "").strip()),
            })
    return records


def _copy_preserved(source: Path, staging: Path) -> None:
    for directory in ("analysis", "data", "outputs"):
        candidate = source / directory
        if candidate.is_dir():
            shutil.copytree(candidate, staging / directory, dirs_exist_ok=True)
    extracts = source / "sources" / "extracts"
    if extracts.is_dir():
        shutil.copytree(extracts, staging / "sources" / "extracts", dirs_exist_ok=True)
    ledger = source / "state" / "ledger.jsonl"
    if ledger.is_file():
        shutil.copy2(ledger, staging / "state" / "ledger.jsonl")


def migrate(source: Path, destination: Path, dry_run: bool = False) -> Dict[str, Any]:
    source = source.expanduser().resolve()
    requested_destination = destination.expanduser()
    if requested_destination.exists() or requested_destination.is_symlink():
        raise ValueError(f"destination already exists: {requested_destination.resolve()}")
    destination = requested_destination.resolve()
    if not source.is_dir():
        raise ValueError(f"source workspace does not exist: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"legacy workspace contains a symlink: {path.relative_to(source).as_posix()}")
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination already exists: {destination}")
    if source == destination:
        raise ValueError("source and destination must differ")
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("destination must not be inside the source workspace")
    try:
        destination.relative_to(SKILL_ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("workspace destination must be outside the installed skill")

    today = dt.date.today().isoformat()
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}-migration-",
        dir=None if dry_run else str(destination.parent),
    ))
    try:
        shutil.copytree(TEMPLATE, staging, dirs_exist_ok=True)
        (staging / "analysis").mkdir(exist_ok=True)
        (staging / "sources" / "extracts").mkdir(parents=True, exist_ok=True)
        _copy_preserved(source, staging)

        project = _read_yaml(source / "project.yaml")
        project_v2 = {
            "schema_version": 2,
            "company_name": str(project.get("company_name") or "Unknown Company"),
            "ticker": str(project.get("ticker") or "UNKNOWN").upper(),
            "exchange": str(project.get("exchange") or ""),
            "benchmark": str(project.get("benchmark") or ""),
            "base_currency": str(project.get("base_currency") or "USD").upper(),
            "rating_convention": str(project.get("rating_convention") or "Overweight/Equal-weight/Underweight"),
            "status": project.get("status") if project.get("status") in ("new", "active", "stale", "archived") else "new",
            "created_at": str(project.get("created_at") or today),
            "last_research_update": _nullable(project.get("last_research_update")),
            "last_publication": _nullable(project.get("last_publication")),
        }
        _write_json(staging / "project.json", project_v2)

        context = _read_yaml(source / "state" / "research-context.yaml")
        context_v2 = {
            "company_name": str(context.get("company_name") or project_v2["company_name"]),
            "ticker": str(context.get("ticker") or project_v2["ticker"]).upper(),
            "exchange": str(context.get("exchange") or project_v2["exchange"]),
            "industry": _nullable(context.get("industry")),
            "geography": _nullable(context.get("geography")),
            "research_date": str(context.get("research_date") or today),
            "benchmark": str(context.get("benchmark") or project_v2["benchmark"]),
            "base_currency": str(context.get("base_currency") or project_v2["base_currency"]).upper(),
            "forecast_horizon_years": int(context.get("forecast_horizon_years") or 3),
            "rating_convention": str(context.get("rating_convention") or project_v2["rating_convention"]),
            "special_questions": list(context.get("special_questions") or []),
            "existing_state": bool(context.get("existing_state", True)),
        }
        _write_json(staging / "state" / "research-context.json", context_v2)
        _write_json(
            staging / "state" / "assumptions.json",
            _assumption_records(_read_yaml(source / "state" / "assumptions.yaml")),
        )
        _write_json(
            staging / "state" / "contradictions.json",
            _contradiction_records(_read_yaml(source / "state" / "contradictions.yaml")),
        )

        graph = _read_yaml(source / "state" / "dependency-graph.yaml")
        for node in graph.get("nodes", {}).values() if isinstance(graph, dict) else []:
            if isinstance(node, dict):
                node["outputs"] = [
                    "sources/registry.jsonl" if output == "sources/registry.csv" else output
                    for output in node.get("outputs", [])
                ]
        _write_json(staging / "state" / "dependency-graph.json", graph)

        records = list(_source_records(source / "sources" / "registry.csv", today))
        registry = staging / "sources" / "registry.jsonl"
        registry.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

        result = validate_workspace(staging)
        if not result.valid:
            raise ValueError("migrated workspace failed validation: " + "; ".join(result.errors))
        report = {
            "dry_run": dry_run,
            "source": str(source),
            "destination": str(destination),
            "source_records": len(records),
            "warnings": result.warnings,
        }
        if not dry_run:
            os.replace(str(staging), str(destination))
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate a v1 YAML workspace to v2 JSON state.")
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = migrate(Path(args.source), Path(args.destination), args.dry_run)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if args.format == "json":
            print(json.dumps({"migrated": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report["migrated"] = not args.dry_run
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        verb = "Validated migration" if args.dry_run else "Migrated workspace"
        print(f"{verb}: {report['source']} -> {report['destination']}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
