#!/usr/bin/env python3
"""Initialize a v2 persistent equity-research workspace atomically."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = SKILL_ROOT / "assets" / "company-workspace"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_new_destination(value: str) -> Path:
    requested = Path(value).expanduser()
    if requested.exists() or requested.is_symlink():
        raise ValueError(f"destination already exists: {requested.resolve()}")
    destination = requested.resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination already exists: {destination}")
    try:
        destination.relative_to(SKILL_ROOT)
    except ValueError:
        return destination
    raise ValueError("workspace destination must be outside the installed skill")


def initialize_workspace(args: argparse.Namespace) -> Path:
    destination = _resolve_new_destination(args.workspace)
    if not TEMPLATE.is_dir():
        raise RuntimeError(f"bundled workspace template is missing: {TEMPLATE}")

    ticker = args.ticker.upper().strip()
    company_name = args.company_name.strip()
    currency = args.currency.upper().strip()
    if not ticker:
        raise ValueError("ticker must not be empty")
    if re.fullmatch(r"[A-Z0-9._-]+", ticker) is None:
        raise ValueError("ticker may contain only letters, numbers, dots, underscores, and hyphens")
    if not company_name:
        raise ValueError("company name must not be empty")
    if len(currency) < 3:
        raise ValueError("currency must contain at least three characters")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=str(destination.parent)))
    try:
        shutil.copytree(TEMPLATE, temporary, dirs_exist_ok=True)
        (temporary / "analysis").mkdir(exist_ok=True)
        (temporary / "sources" / "extracts").mkdir(parents=True, exist_ok=True)

        today = dt.date.today().isoformat()
        project_path = temporary / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update({
            "company_name": company_name,
            "ticker": ticker,
            "exchange": args.exchange.strip(),
            "benchmark": args.benchmark.strip(),
            "base_currency": currency,
            "rating_convention": args.rating_convention,
            "created_at": today,
        })
        _write_json(project_path, project)

        context_path = temporary / "state" / "research-context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context.update({
            "company_name": company_name,
            "ticker": ticker,
            "exchange": args.exchange.strip(),
            "benchmark": args.benchmark.strip(),
            "base_currency": currency,
            "research_date": today,
            "forecast_horizon_years": args.forecast_horizon,
            "rating_convention": args.rating_convention,
        })
        _write_json(context_path, context)
        os.replace(str(temporary), str(destination))
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize a persistent equity-research workspace.")
    parser.add_argument("--workspace", required=True, help="New workspace directory to create")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--exchange", default="")
    parser.add_argument("--benchmark", default="")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--forecast-horizon", type=int, choices=range(1, 11), default=3)
    parser.add_argument(
        "--rating-convention",
        choices=("Overweight/Equal-weight/Underweight", "Buy/Hold/Sell"),
        default="Overweight/Equal-weight/Underweight",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        destination = initialize_workspace(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        if args.format == "json":
            print(json.dumps({"created": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps({"created": True, "workspace": str(destination)}, sort_keys=True))
    else:
        print(f"Created workspace: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
