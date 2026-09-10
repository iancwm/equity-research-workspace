# Evidence normalization

Transform raw source material into atomic research-ledger records.

## Rules

- One record should express one material fact, derived metric, assumption, conclusion, risk, catalyst, falsification criterion, or research gap.
- Quantitative records should include metric, value, unit, and period.
- Sourced observations must include source IDs.
- Derived metrics must identify their dependencies.
- Analytical conclusions should identify supporting records and confidence.
- Contradictory observations remain separate records; do not average them away.
- A new datapoint that invalidates an old record should mark the old record stale or superseded rather than silently deleting it.

Write one object conforming to `schemas/ledger-record.schema.json` per line to `state/ledger.jsonl`.
