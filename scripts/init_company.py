#!/usr/bin/env python3
from pathlib import Path
import argparse, shutil, datetime, yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "company"
COMPANIES = ROOT / "companies"


def main():
    p = argparse.ArgumentParser(description="Initialize a persistent equity-research company workspace.")
    p.add_argument("ticker")
    p.add_argument("company_name")
    p.add_argument("--exchange", default="")
    p.add_argument("--benchmark", default="")
    p.add_argument("--currency", default="USD")
    args = p.parse_args()

    ticker = args.ticker.upper().strip()
    dest = COMPANIES / ticker
    if dest.exists():
        raise SystemExit(f"Workspace already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE, dest)

    today = datetime.date.today().isoformat()
    project = {
        "company_name": args.company_name,
        "ticker": ticker,
        "exchange": args.exchange,
        "benchmark": args.benchmark,
        "base_currency": args.currency,
        "rating_convention": "Overweight/Equal-weight/Underweight",
        "status": "new",
        "created_at": today,
        "last_research_update": "",
        "last_publication": "",
    }
    (dest / "project.yaml").write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")

    ctx_path = dest / "state" / "research-context.yaml"
    ctx = yaml.safe_load(ctx_path.read_text(encoding="utf-8"))
    ctx.update({
        "company_name": args.company_name,
        "ticker": ticker,
        "exchange": args.exchange,
        "benchmark": args.benchmark,
        "base_currency": args.currency,
        "research_date": today,
        "existing_state": False,
    })
    ctx_path.write_text(yaml.safe_dump(ctx, sort_keys=False), encoding="utf-8")
    print(dest)

if __name__ == "__main__":
    main()
