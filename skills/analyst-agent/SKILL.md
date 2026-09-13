---
name: analyst-agent
description: Orchestrate automated equity-research report generation -- initiation of coverage, earnings updates, sector reports, quarterly outlooks, and trading reports -- by fetching evidence, driving a Claude tool-use analysis, writing findings into persistent research state where applicable, and rendering the report from that state. Use for programmatic, unattended report runs; use persistent-equity-research for interactive, analyst-led research and sector-primer for interactive sector work.
license: GPL-3.0-only
compatibility: Requires Python 3.9+ and filesystem read/write access. Live runs additionally require the anthropic SDK and an API key; every bundled evidence source is mock data until real providers are wired in.
metadata:
  version: "0.2.0"
---

# Analyst Agent

A thin orchestration layer over five report types. Every report type follows
the same shape: fetch evidence -> drive one Claude tool-use conversation ->
turn the resulting tool calls into structured state (a workspace ledger where
one exists, or an in-memory result otherwise) -> render a Markdown view of that
state. Nothing renders a figure that isn't traceable back to a tool call or a
function input; gaps and contradictions are surfaced, never smoothed away.

| Report type | Phase | Workspace | Entry point |
| --- | --- | --- | --- |
| Initiation of Coverage | 1 | v2 company workspace (created by this run) | `orchestrator.AnalystAgent.initiate_coverage` |
| Earnings Update | 2a | the same v2 company workspace (revised, not created) | `orchestrator.AnalystAgent.earnings_update` / `earnings_update.EarningsUpdateAgent` |
| Sector Report | 2b | sector-primer workspace (created if new) | `sector_report.SectorReportAgent.sector_report` |
| Quarterly Outlook | 2c | none (standalone) | `outlook_report.run_quarterly_outlook` |
| Trading Report | 3 | none (standalone) | `trading_report.run_trading_report` |

Three report types persist to a durable workspace and are governed by the
repository's `CLAUDE.md` research-fidelity rules (never invent a fact, keep
observations/estimates/interpretations distinct, preserve contradictions and
gaps). The other two (Quarterly Outlook, Trading Report) are tactical/ephemeral
by design -- they take no `workspace_path` and persist nothing; their evidence
and analysis are only as durable as whatever the caller does with the returned
dict.

## Shared infrastructure

- `agent_common.py`: `run_tool_loop` (the Claude tool-use conversation driver
  every report type uses), `build_client` (lazy `anthropic` import so the
  offline test suite never needs the SDK installed), `name_value_array_schema`
  / `as_mapping` (the strict-tool-schema pattern for representing an open-ended
  map), `DEFAULT_MODEL` / `DEFAULT_MAX_TOKENS` / `DEFAULT_MAX_TURNS`.
- `render_helpers.py`: `markdown_table`, `format_number`, `format_price`,
  `format_pct`, `source_label` -- the Markdown formatting every report
  generator renders through.
- `workspace_adapter.py`: `ResearchWorkspace`, the v2 company-workspace
  read/modify/atomic-write surface, plus `update_workspace_from_claude` (tool
  calls -> ledger writes). Used by Initiation of Coverage and Earnings Update.
  Not used by Sector Report (different workspace schema -- see
  `sector_workspace.py`) or by the two standalone report types.

## Initiation of Coverage (Phase 1)

```python
import sys
sys.path.insert(0, "<repo>/skills/analyst-agent")

from orchestrator import AnalystAgent

agent = AnalystAgent(workspace_root="/path/to/ACME")
result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")
print(result["status"], result["report_path"])
```

The workspace must already exist. Create one outside the installed skill first:

```text
python3 <persistent-equity-research>/scripts/init_workspace.py \
  --workspace /path/to/ACME --ticker ACME --company-name "Acme Corp"
```

`AnalystAgent(workspace_root, anthropic_api_key=None, model=..., client=None, max_turns=12)`

`initiate_coverage(ticker, company_name, max_evidence_sources=10)` returns:

| Key | Meaning |
| --- | --- |
| `workspace_path` | Absolute path to the workspace written |
| `report_markdown` | The rendered initiation |
| `evidence_count` | Sources in the registry after the run |
| `state_ledger_keys` | State collections that hold records |
| `status` | `success`, `partial`, or `failed` |
| `report_path` | Where the report was written in the workspace (`outputs/initiation-of-coverage.md`) |
| `tool_calls` | Count of each tool Claude called |
| `validation_errors` / `validation_warnings` | From the workspace validator |
| `notes` | Why a run is `partial` |

Tool vocabulary: `record_source`, `record_assumption`, `record_valuation`,
`record_scenario`, `record_catalyst`, `flag_analysis_gap`,
`flag_contradiction` (schemas in `prompts.py`, strict-validated).

### Phase 1 limits

- Evidence is mock data (`data_sources.py`). Rendered reports say so and must
  not inform a decision.
- The report covers a subset of the repository's full initiation-of-coverage
  standard; the rendered document lists the analytical lenses it does not yet
  cover rather than presenting itself as a complete initiation.
- No caching, no workspace locking, single-threaded use assumed.

## Earnings Update (Phase 2a)

Revises an *existing* company workspace (one created by Initiation of
Coverage, or directly by `persistent-equity-research`'s `init_workspace.py`)
within 24-48 hours of a quarterly print: compares actual results to the prior
thesis, revises only the assumptions that materially changed (superseding, not
silently overwriting, the prior record of each), recalculates valuation, and
renders a short update note.

```python
from orchestrator import AnalystAgent
# or: from earnings_update import EarningsUpdateAgent

agent = AnalystAgent(workspace_root="/path/to/ACME")
result = agent.earnings_update(
    earnings_date="2025-04-01",
    eps_actual=2.15, eps_consensus=2.10,
    revenue_actual=1200.0, revenue_consensus=1190.0,
    guidance_change="raised",  # "raised" | "lowered" | "in-line" | None
)
```

`earnings_update(earnings_date, eps_actual, eps_consensus, revenue_actual, revenue_consensus, guidance_change, earnings_call_transcript_url=None, max_evidence_sources=5)` returns:

| Key | Meaning |
| --- | --- |
| `update_note_markdown` | Short-form report (<1000 words), written to `outputs/update-note.md` |
| `assumptions_changed` | Count of assumptions actually revised this run |
| `valuation_changed_pct` | % change in the Base-case price target vs. prior |
| `verdict` | `thesis_intact` / `thesis_at_risk` / `thesis_broken` -- computed deterministically in Python from EPS/revenue surprise and guidance direction, never asserted by the model (see `earnings_update.determine_verdict`) |
| `revised_price_target` | New Base-case price target |
| `status` | `success`, `partial`, or `failed` |

Reuses `prompts.TOOL_DEFINITIONS` unchanged -- the initiation's tool vocabulary
(`record_source`, `record_assumption`, `record_valuation`, `record_catalyst`,
`flag_analysis_gap`, `flag_contradiction`) already fits this report type.

## Sector Report (Phase 2b)

Peer benchmarking, value-chain economics, structural drivers, cyclicality, and
a sector valuation verdict, persisted to a `sector-primer`-shaped workspace
(created via `sector-primer`'s own `init_sector_workspace.py` if it does not
already exist, so the two skills' file layouts never drift apart).

```python
from sector_report import SectorReportAgent

agent = SectorReportAgent(workspace_root="/path/to/semiconductors-sector")
result = agent.sector_report(sector_name="Semiconductors", geography="Global")
print(result["status"], result["peer_universe_count"])
```

`sector_report(sector_name, geography="Global", peer_universe=None, look_forward_years=3, max_evidence_sources=15)` returns:

| Key | Meaning |
| --- | --- |
| `workspace_path` | Absolute path to the sector workspace |
| `sector_report_markdown` | The rendered report, also written to `outputs/sector-primer.md` |
| `peer_universe_count` | Number of peers benchmarked |
| `valuation_spread_pct` | `(richest peer P/E / cheapest peer P/E - 1) * 100` |
| `status` | `success`, `partial`, or `failed` |

The sector-primer workspace has a different on-disk schema than the company
workspace (`state/assumptions.json` and `state/contradictions.json` are plain
JSON lists, not the company workspace's dict shape; peer data lives in
`data/company-comps.csv` / `data/sector-metrics.csv`), so it is read and
written by its own `sector_workspace.SectorWorkspace` class and validated with
`sector-primer`'s own `validate_sector_workspace.py` -- not
`workspace_adapter.ResearchWorkspace`.

## Quarterly Outlook (Phase 2c)

A standalone macro/asset-allocation view: Base/Bull/Bear scenarios, sector
tilts, relative-value calls, tail risks, and a catalyst calendar. No workspace
is read or written.

```python
from outlook_report import run_quarterly_outlook

result = run_quarterly_outlook(quarter="Q1 2025")
print(result["status"], result["sector_tilts"], result["tail_risks"])
```

`run_quarterly_outlook(quarter, macro_scenario="base", lookback_quarters=4, sector_universe=None, max_evidence_sources=20, anthropic_api_key=None, model=..., client=None, max_turns=...)` returns
`outlook_markdown`, `macro_scenario`, `sector_tilts` (a dict of sector ->
`"+2%"`/`"0%"`/`"-2%"`, a display convention derived from each sector's
recorded Base-case tilt, not a portfolio-optimizer weight), `tail_risks`,
`catalyst_calendar`, and `status`. Bull/Base/Bear probabilities must sum to
~100%; a mismatch downgrades `status` to `partial` with a note rather than
being silently renormalized.

## Trading Report (Phase 3)

A standalone, tactical catalyst-driven thesis (2-12 week horizon) with
entry/target/stop levels. No workspace is read or written. Risk/reward and
implied return are computed deterministically in Python from the given
entry/target/stop -- never delegated to the model.

```python
from trading_report import run_trading_report

result = run_trading_report(
    ticker="ACME", trade_thesis="long",
    catalyst_name="Q4 earnings", catalyst_date="2025-02-15",
    entry_price=105.0, target_price=120.0, stop_loss=98.0,
)
print(result["risk_reward_ratio"], result["conviction"])
```

`run_trading_report(ticker, trade_thesis, catalyst_name, catalyst_date, entry_price, target_price, stop_loss, time_horizon_days=60, max_evidence_sources=10, anthropic_api_key=None, model=..., client=None, max_turns=...)` returns
`trade_report_markdown`, `risk_reward_ratio`, `implied_return_pct`,
`catalyst_probability_pct`, `technical_setup` (`strong`/`moderate`/`weak`),
`conviction` (`high`/`medium`/`low`), and `status`. A risk/reward below 2:1 or
an inverted setup (target/entry/stop out of order for the stated direction)
downgrades `status` to `partial` with a prominent caution in the report,
rather than raising.

## Common limits (all report types)

- Every evidence fetcher (`data_sources.py`, `earnings_evidence.py`,
  `sector_evidence.py`, `outlook_evidence.py`, `trading_evidence.py`) is
  deterministic mock data -- no network calls. Real providers replace these
  functions later without changing their return schema or any downstream code.
- No caching, no workspace locking, single-threaded use assumed.
- Live Claude runs require `pip install anthropic` and an API key; every test
  in this skill runs with a scripted fake client and imports no such
  dependency.
