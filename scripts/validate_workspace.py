#!/usr/bin/env python3
from pathlib import Path
import argparse, csv, json, sys, yaml

REQUIRED = [
    "project.yaml",
    "state/research-context.yaml",
    "state/ledger.jsonl",
    "state/assumptions.yaml",
    "state/contradictions.yaml",
    "state/dependency-graph.yaml",
    "sources/registry.csv",
]


def fail(msg, errors):
    errors.append(msg)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("workspace")
    args = p.parse_args()
    ws = Path(args.workspace)
    errors, warnings = [], []

    if not ws.exists():
        raise SystemExit(f"Missing workspace: {ws}")

    for rel in REQUIRED:
        if not (ws / rel).exists():
            fail(f"Missing required file: {rel}", errors)

    # Basic YAML readability
    for rel in ["project.yaml", "state/research-context.yaml", "state/assumptions.yaml", "state/contradictions.yaml", "state/dependency-graph.yaml"]:
        path = ws / rel
        if path.exists():
            try:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as e:
                fail(f"Invalid YAML {rel}: {e}", errors)

    # Basic ledger validity
    ledger = ws / "state/ledger.jsonl"
    if ledger.exists():
        for n, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                for key in ["id", "record_type", "statement", "confidence", "status"]:
                    if key not in obj:
                        fail(f"ledger line {n}: missing {key}", errors)
            except json.JSONDecodeError as e:
                fail(f"ledger line {n}: invalid JSON: {e}", errors)

    # Source registry duplicate IDs
    reg = ws / "sources/registry.csv"
    if reg.exists():
        with reg.open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        ids = [r.get('source_id','') for r in rows if r.get('source_id','')]
        if len(ids) != len(set(ids)):
            fail("Duplicate source_id values in sources/registry.csv", errors)
        if not rows:
            warnings.append("Source registry is empty.")

    print(f"Workspace: {ws}")
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        sys.exit(1)
    print("PASS: structural workspace validation")

if __name__ == "__main__":
    main()
