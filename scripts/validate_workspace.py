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

    # Basic ledger validity and source provenance
    ledger = ws / "state/ledger.jsonl"
    ledger_ids = set()
    source_references = []
    if ledger.exists():
        for n, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                for key in ["id", "record_type", "statement", "confidence", "status"]:
                    if key not in obj:
                        fail(f"ledger line {n}: missing {key}", errors)
                record_id = obj.get("id")
                if record_id:
                    if record_id in ledger_ids:
                        fail(f"ledger line {n}: duplicate id {record_id}", errors)
                    ledger_ids.add(record_id)
                for source_id in obj.get("source_ids", []):
                    source_references.append((n, source_id))
            except json.JSONDecodeError as e:
                fail(f"ledger line {n}: invalid JSON: {e}", errors)

    # Source registry duplicate IDs and ledger references
    reg = ws / "sources/registry.csv"
    if reg.exists():
        with reg.open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        ids = [r.get('source_id','') for r in rows if r.get('source_id','')]
        if len(ids) != len(set(ids)):
            fail("Duplicate source_id values in sources/registry.csv", errors)
        if not rows:
            warnings.append("Source registry is empty.")
        known_source_ids = set(ids)
        for line_number, source_id in source_references:
            if source_id not in known_source_ids:
                fail(f"ledger line {line_number}: unknown source_id {source_id}", errors)

    # Fresh dependency nodes must have their declared artifacts. A new workspace
    # can retain not_run nodes without outputs; stale nodes are deliberately
    # retained pending selective recomputation.
    graph_path = ws / "state/dependency-graph.yaml"
    if graph_path.exists():
        graph = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}
        nodes = graph.get("nodes") if isinstance(graph, dict) else None
        if not isinstance(nodes, dict):
            fail("state/dependency-graph.yaml: nodes must be a mapping", errors)
        else:
            for name, node in nodes.items():
                if not isinstance(node, dict):
                    fail(f"dependency node {name}: must be a mapping", errors)
                    continue
                for dependency in node.get("depends_on", []):
                    if dependency not in nodes:
                        fail(f"dependency node {name}: unknown dependency {dependency}", errors)
                status = node.get("status", "not_run")
                if status == "fresh":
                    for output in node.get("outputs", []):
                        if not (ws / output).exists():
                            fail(f"fresh dependency node {name}: missing output {output}", errors)
                elif status == "stale":
                    warnings.append(f"dependency node {name} is stale.")
                elif status != "not_run":
                    fail(f"dependency node {name}: invalid status {status}", errors)

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
