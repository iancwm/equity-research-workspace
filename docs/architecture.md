# Architecture

## Four layers

### 1. Evidence layer
Sources, extracts, historical data, market data, consensus.

### 2. State layer
Atomic ledger records, assumptions, contradictions, research gaps, dependencies.

### 3. Analysis layer
Economic engine, macro transmission, value chain, cycle/structure, company forecasts, valuation, strategist dashboard.

### 4. Publication layer
IOC, update note, dashboard, scenario note, spreadsheet, PDF, slides.

The publication layer is disposable/rebuildable. The state layer is the durable research asset.

## Why JSONL for the ledger

JSONL allows append-friendly atomic records, easy diffing, selective retrieval, schema validation, and simple indexing without requiring a database for the first implementation.

A later implementation can migrate the same logical schema to SQLite/Postgres/vector search without changing analytical contracts.
