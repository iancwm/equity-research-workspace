# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Analyst agent orchestration skill (Phase 1 MVP): drives an initiation of coverage
  from evidence through a Claude tool-use analysis into persisted workspace state.
- Workspace adapter exposing a `ResearchWorkspace` read/modify/write surface over
  the v2 workspace format, and translating Claude tool calls into ledger writes.
- Mock company evidence source, initiation report generator, analyst system prompt
  and tool schemas, an offline demo script, and an end-to-end integration test.
- Analyst agent Phase 2a: Earnings Update. Revises an existing v2 company
  workspace within 24-48 hours of a quarterly print -- compares actual results
  to the prior thesis, revises only assumptions that materially changed
  (superseding the prior record of each rather than silently overwriting it),
  recalculates valuation, and renders a short (<1000-word) update note to
  `outputs/update-note.md`. Verdict (`thesis_intact`/`thesis_at_risk`/
  `thesis_broken`) is computed deterministically from EPS/revenue surprise and
  guidance direction, not asserted by the model. Reachable as
  `orchestrator.AnalystAgent.earnings_update` or standalone via
  `earnings_update.EarningsUpdateAgent`.
- Analyst agent Phase 2b: Sector Report. Peer benchmarking, value-chain
  economics, structural drivers, cyclicality, and a sector valuation verdict,
  persisted to a `sector-primer`-shaped workspace (created via that skill's
  own initializer, and validated with its own validator) via a new
  `sector_workspace.SectorWorkspace` class parallel to `ResearchWorkspace`.
  Entry point: `sector_report.SectorReportAgent`.
- Analyst agent Phase 2c: Quarterly Outlook. A standalone macro/asset-
  allocation view -- Base/Bull/Bear scenarios with probabilities validated to
  sum to ~100%, sector tilts, relative-value calls, tail risks, and a catalyst
  calendar. No persistent workspace. Entry point:
  `outlook_report.run_quarterly_outlook`.
- Analyst agent Phase 3: Trading Report. A standalone, tactical catalyst-
  driven thesis (2-12 week horizon) with entry/target/stop levels; risk/reward
  and implied return are computed deterministically in Python, never
  delegated to the model. No persistent workspace. Entry point:
  `trading_report.run_trading_report`.
- Shared analyst-agent infrastructure (`agent_common.py`, `render_helpers.py`)
  factored out of the Phase 1 orchestrator and report generator so every
  report type drives its Claude tool-use conversation and renders Markdown
  through one implementation each, plus `tests/analyst_agent_fakes.py`, a
  shared scripted-Claude-client test double reused by every report type's
  offline integration tests.

## [2.1.0] - 2026-09-12

### Added

- Sector primer skill for explaining industry structure, sector analytics, and comparable companies.
- Persistent sector workspace initializer and structural validator.
- Automated tests for sector workspace creation and validation paths.

## [2.0.0] - 2026-09-10

### Added

- Canonical Agent Skills package with Claude plugin and Codex UI metadata.
- Dependency-free workspace initialization and validation.
- Normative JSON Schemas, reproducible packaging, offline tests, and behavioral eval cases.
- Non-destructive v1 migration utility and cross-platform installation documentation.

### Changed

- Moved mutable company research outside the installed skill.
- Replaced YAML state and the CSV source registry with JSON and JSONL.
- Reworked prompts into vendor-neutral, progressively disclosed references.

### Removed

- Vendor-specific model routing and Work-mode assumptions.
- The tracked runtime AAPL workspace and root-level duplicate skill resources.
