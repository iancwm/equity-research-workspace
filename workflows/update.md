# Workflow — Update

Use after earnings, guidance, investor day, filing, M&A, regulation, management change, major competitor datapoint, or material market move.

## Steps

1. Ingest only new/revised sources.
2. Append new evidence to the ledger.
3. Mark superseded facts appropriately.
4. Compare new facts with prior assumptions and conclusions.
5. Consult dependency graph and mark affected nodes stale.
6. Recompute stale nodes and all downstream dependents.
7. Re-run strategist dashboard and thesis only if recommendation-relevant nodes changed.
8. Produce `outputs/update-note.md` containing:
   - what changed;
   - estimate changes;
   - valuation changes;
   - thesis/rating impact;
   - new catalyst/risk/falsification status;
   - what did **not** change.

Do not rerun stable industry work without a dependency-based reason.
