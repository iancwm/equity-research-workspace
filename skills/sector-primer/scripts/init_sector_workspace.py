#!/usr/bin/env python3
"""Create a minimal, portable workspace for a persistent sector primer."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_workspace(workspace: Path, sector_name: str, geography: str, benchmark: Optional[str]) -> None:
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"workspace is not empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    created_at = now()
    project = {
        "schema_version": "1.0",
        "workspace_type": "sector-primer",
        "sector_name": sector_name,
        "geography": geography,
        "benchmark": benchmark,
        "created_at": created_at,
        "updated_at": created_at,
    }
    write_text(workspace / "project.json", json.dumps(project, indent=2) + "\n")
    write_text(workspace / "sources/registry.jsonl", "")
    write_text(
        workspace / "data/sector-metrics.csv",
        "metric,subsector,value,unit,period,as_of_date,status,definition,numerator,denominator,weighting,source_ids,notes\n",
    )
    write_text(
        workspace / "data/company-comps.csv",
        "issuer,ticker,exchange,peer_tag,subsector,currency,market_data_date,operating_period,basis,market_cap,enterprise_value,revenue,revenue_growth,ebitda_margin,ebit_margin,roic,roe,capex_sales,rd_sales,fcf_margin,cash_conversion,net_debt_ebitda,pe,ev_ebitda,fcf_yield,dividend_yield,total_return,estimate_vintage,source_ids,notes\n",
    )
    write_text(workspace / "state/ledger.jsonl", "")
    write_text(workspace / "state/assumptions.json", "[]\n")
    write_text(workspace / "state/contradictions.json", "[]\n")
    write_text(
        workspace / "state/research-context.json",
        json.dumps(
            {
                "scope": {"sector_name": sector_name, "geography": geography},
                "as_of_date": None,
                "source_ids": [],
                "stale_sections": [],
                "research_gaps": [],
                "next_questions": [],
            },
            indent=2,
        )
        + "\n",
    )
    write_text(workspace / "outputs/sector-primer.md", f"# {sector_name} sector primer\n\nStatus: initialized; research not yet completed.\n")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, type=Path)
    p.add_argument("--sector-name", required=True)
    p.add_argument("--geography", default="Not specified")
    p.add_argument("--benchmark", default=None)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        build_workspace(args.workspace.expanduser().resolve(), args.sector_name.strip(), args.geography.strip(), args.benchmark)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Initialized sector workspace: {args.workspace.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
