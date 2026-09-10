# Workspace v2

Version 2 moves mutable research outside the skill package and uses JSON, JSONL, and CSV. The runtime scripts have no third-party Python dependencies.

## Required files

```text
<workspace>/
├── project.json
├── state/
│   ├── research-context.json
│   ├── ledger.jsonl
│   ├── assumptions.json
│   ├── contradictions.json
│   └── dependency-graph.json
├── sources/
│   └── registry.jsonl
├── data/
├── analysis/
└── outputs/
```

`project.json` contains integer `schema_version: 2`. Unsupported versions fail validation rather than being guessed.

The ledger and source registry contain one JSON object per nonblank line. Tabular financial data remains CSV so it is easy to inspect and import into spreadsheets. Schemas under the installed skill's `schemas/` directory are normative.

## Validation

```bash
python3 <skill-root>/scripts/validate_workspace.py <workspace>
python3 <skill-root>/scripts/validate_workspace.py <workspace> --strict --format json
```

Normal validation permits warnings such as an empty new ledger. Strict mode promotes warnings—including stale analytical nodes—to failures. Exit status is `0` for valid, `1` for invalid, and `2` for command-line usage or environment errors.

## Migrating v1

Migration never modifies its source and refuses an existing destination:

```bash
python3 -m pip install -r requirements-dev.txt
python3 skills/persistent-equity-research/scripts/migrate_v1_workspace.py \
  old-workspace new-workspace --dry-run
python3 skills/persistent-equity-research/scripts/migrate_v1_workspace.py \
  old-workspace new-workspace
```

The utility converts YAML state and the CSV source registry, preserves analysis, data, outputs, reusable extracts, and ledger history, then validates the destination before publishing it atomically. Review generated assumption metadata such as units and owner nodes when the v1 files did not encode them.
