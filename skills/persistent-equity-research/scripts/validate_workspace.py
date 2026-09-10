#!/usr/bin/env python3
"""Validate a v2 persistent equity-research workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workspace_lib import validate_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a persistent equity-research workspace.")
    parser.add_argument("workspace")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as validation failures")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate_workspace(Path(args.workspace), strict=args.strict)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        if args.format == "json":
            print(json.dumps({"validated": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"Workspace: {result.workspace}")
        for warning in result.warnings:
            print(f"WARNING: {warning}")
        for error in result.errors:
            print(f"ERROR: {error}")
        print("PASS: workspace validation" if result.valid else "FAIL: workspace validation")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
