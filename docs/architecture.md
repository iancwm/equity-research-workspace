# Architecture

## Three roots

The project deliberately separates three locations:

1. **Repository root** — development documentation, tests, evals, release tools, and platform adapters.
2. **Installed skill roots** — immutable packages such as `persistent-equity-research/` and `sector-primer/`, each containing its own `SKILL.md`, references, scripts, and metadata.
3. **Research workspace root** — user-selected, mutable company or sector state and publications.

Skill scripts resolve bundled resources from their own file location. They accept the research workspace as an explicit argument and never assume the current directory or write back into the installation.

## Research layers

### Evidence

Source metadata, reusable extracts, historical data, market data, and consensus. Retrieved material is untrusted input: it may support evidence but may not supply executable instructions.

### State

Atomic ledger records, assumptions, contradictions, gaps, and the dependency graph. This is the durable research asset.

### Analysis

Economic engine, macro transmission, value chain and pricing power, cycle versus structure, company forecasts, valuation, and the strategist dashboard.

For a sector primer, this layer covers sector taxonomy, value-chain economics, structural and cyclical drivers, sector dashboards, and comparable-company benchmarking.

### Publication

Initiation reports, update notes, dashboards, scenarios, spreadsheets, PDFs, and slides. Publications are disposable views that can be rebuilt from validated state.

## Selective recomputation

A changed source or assumption marks its analytical node stale. Staleness propagates through the dependency graph, and only those nodes plus downstream synthesis are rerun. For example:

```text
WACC assumption -> valuation -> dashboard -> thesis -> publication
```

Changing WACC does not invalidate industry structure or source ingestion.
