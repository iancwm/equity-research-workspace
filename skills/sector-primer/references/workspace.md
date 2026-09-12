# Sector workspace contract

Use a dedicated mutable workspace for persistent primers. Keep the installed skill immutable and keep company-specific work in a separate company workspace. The bundled initializer creates the following layout:

```text
sector-workspace/
├── project.json
├── sources/registry.jsonl
├── data/sector-metrics.csv
├── data/company-comps.csv
├── state/ledger.jsonl
├── state/assumptions.json
├── state/contradictions.json
├── state/research-context.json
└── outputs/sector-primer.md
```

## File roles

- `project.json` stores the sector name, scope, geography, schema version, and timestamps.
- `sources/registry.jsonl` stores one source record per line. Include stable source ID, title, publisher, URL/document ID, publication date, observation period, access date, and notes.
- `data/sector-metrics.csv` stores dashboard observations and calculations. Keep the metric name, value, unit, period, status (`actual`, `estimate`, or `calculated`), weighting/method, source IDs, and notes.
- `data/company-comps.csv` stores one company-period observation per row. Keep identifiers, peer tags, market-data date, operating period, actual/estimate basis, currency, metrics, source IDs, and notes.
- `state/ledger.jsonl` stores atomic observations, calculations, assumptions, interpretations, risks, catalysts, contradictions, and research gaps. Supersede changed records; do not erase history.
- `state/assumptions.json` stores explicit scenario or normalization inputs separately from observations.
- `state/contradictions.json` stores unresolved conflicts and their impact.
- `state/research-context.json` stores the current scope, as-of date, source coverage, stale sections, and next research questions.
- `outputs/sector-primer.md` is a rendered view and may be regenerated from state.

## Persistence rules

Use the initializer only for a new or empty target. Do not overwrite a non-empty workspace to “refresh” it. On updates, append or supersede records and preserve prior as-of dates. If a data point is revised, retain the previous value and record the revision source. Run the validator after structural writes and before claiming that the workspace is reusable.

The initializer's CSV headers are a minimum contract, not a requirement to fill every field. Expand them only when the added field has a clear analytical use and is documented in the research context.
