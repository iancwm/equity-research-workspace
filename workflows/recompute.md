# Selective Recompute Protocol

## Principle

A change propagates through dependencies, not through file order.

## Procedure

1. Identify changed ledger IDs or assumption IDs.
2. Find nodes that directly depend on them.
3. Mark those nodes `stale` in `state/dependency-graph.yaml`.
4. Recursively mark downstream nodes stale.
5. Execute stale nodes in dependency order.
6. Mark successful nodes `fresh` and record updated outputs.
7. If a node's conclusion is unchanged, do not rewrite unrelated downstream prose unless required for consistency.

## Typical dependency graph

```text
source/evidence
  → normalized fact
      → historical financials
      → economic engine
      → cycle/structure
      → forecast
          → valuation
              → dashboard
                  → thesis
                      → publication
```

### Example: WACC changes

Recompute:

valuation → scenario table → dashboard → thesis → report valuation/conclusion

Do not recompute:

industry structure, historical financials, source extracts, pricing-power analysis.

### Example: quarterly consulting bookings fall sharply

Potentially recompute:

company overlay → cycle/structure → forecast → valuation → dashboard → thesis → update note.
