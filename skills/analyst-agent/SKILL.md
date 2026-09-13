---
name: analyst-agent
description: Orchestrate an automated initiation of coverage by fetching company evidence, driving a Claude tool-use analysis, writing the findings into a persistent equity-research workspace, and rendering the report from that state. Use for programmatic, unattended coverage runs against an existing workspace; use persistent-equity-research for interactive, analyst-led research.
license: GPL-3.0-only
compatibility: Requires Python 3.9+ and filesystem read/write access. Live runs additionally require the anthropic SDK and an API key; the bundled evidence source is mock data until Phase 2.
metadata:
  version: "0.1.0"
---

# Analyst Agent

Phase 1 MVP: a thin orchestration layer that produces an Initiation of Coverage
from a v2 workspace created by `persistent-equity-research`.

The workspace is the source of truth. This skill writes analysis into workspace
state, validates that state with the existing validator, and renders the report
as a view of it. It never modifies the `persistent-equity-research` or
`sector-primer` skills.

## Pipeline

1. `data_sources.fetch_company_evidence` returns structured evidence.
2. The orchestrator registers evidence sources in `sources/registry.jsonl` and
   writes company context to `state/ledger.jsonl` as sourced observed facts.
3. Claude is called with the analyst system prompt and a tool vocabulary. It
   replies only in tool calls.
4. `workspace_adapter.update_workspace_from_claude` translates those calls into
   ledger, assumption, contradiction, and valuation writes.
5. The workspace is validated with `persistent-equity-research`'s validator.
6. `report_generators.initiation_report_markdown` renders the report and writes
   it to `outputs/initiation-of-coverage.md`.

## Usage

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

To see the whole pipeline without an API key or spend:

```text
python3 scripts/example_usage.py --workspace /tmp/ACME --offline
```

## Inputs and outputs

`AnalystAgent(workspace_root, anthropic_api_key=None, model=..., client=None, max_turns=12)`

`initiate_coverage(ticker, company_name, max_evidence_sources=10)` returns:

| Key | Meaning |
| --- | --- |
| `workspace_path` | Absolute path to the workspace written |
| `report_markdown` | The rendered initiation |
| `evidence_count` | Sources in the registry after the run |
| `state_ledger_keys` | State collections that hold records |
| `status` | `success`, `partial`, or `failed` |
| `report_path` | Where the report was written in the workspace |
| `tool_calls` | Count of each tool Claude called |
| `validation_errors` / `validation_warnings` | From the workspace validator |
| `notes` | Why a run is `partial` |

`status` is `failed` when the workspace does not validate, `partial` when the run
under-delivered against the coverage minimums or the adapter had to normalize
something, and `success` otherwise.

## Tool vocabulary

`record_source`, `record_assumption`, `record_valuation`, `record_scenario`,
`record_catalyst`, `flag_analysis_gap`, `flag_contradiction`. Schemas are in
`prompts.py` and run under strict validation.

## Phase 1 limits

- Evidence is mock data. Rendered reports say so and must not inform a decision.
- The report covers a subset of the repository's full initiation standard. The
  rendered document lists the analytical lenses it does not yet cover rather
  than presenting itself as a complete initiation.
- Narrative risks are not persisted as ledger records; downside is carried by
  the bear case, catalysts, contradictions, and gaps.
- No caching, no workspace locking, single-threaded use assumed.
