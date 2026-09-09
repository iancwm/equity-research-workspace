---
name: persistent-equity-research
version: 0.1.0
description: Build and maintain a persistent institutional equity-research workspace for a public company. Use for initiation of coverage, thesis formation, earnings updates, valuation work, scenario analysis, catalyst/risk monitoring, and publication. Preserve sourced evidence, assumptions, ledger conclusions, dependencies, and editable outputs so subsequent work selectively recomputes affected analysis instead of restarting from scratch.
---

# Persistent Equity Research Skill

## Objective

Maintain a living equity-research model from which initiation reports, update notes, dashboards, scenario analyses, and other publications can be generated.

The primary artifact is the **research state**. A prose report is only one rendered view of that state.

## When to use

Use this skill when the user asks to:

- initiate coverage on a listed company;
- recommend Overweight / Equal-weight / Underweight or Buy / Hold / Sell;
- analyze a company relative to a benchmark or investor debate;
- update an existing thesis after earnings, guidance, news, regulation, M&A, or valuation moves;
- stress-test a thesis or change assumptions;
- maintain a reusable company research workspace;
- produce an IOC, update note, dashboard, scenario note, or investment memo from existing research.

Do not run the complete pipeline for a narrow factual question. Use the smallest workflow that answers the request.

## Operating principles

1. **Persist before publishing.** Store important facts, sources, assumptions, conclusions, contradictions, and dependencies before producing the final report.
2. **Evidence before narrative.** Quantitative claims and material qualitative claims should map to source records where practicable.
3. **Separate observation, assumption, inference, and conclusion.** Never store them as if they were the same thing.
4. **Selective recomputation.** When new evidence or an assumption changes, identify dependent analytical nodes and rerun only those nodes plus downstream synthesis.
5. **Progressive disclosure.** Give the user an early framing before the long research run: the core debate, preliminary valuation context, and the hypotheses to test.
6. **No context dumping.** Modules receive only relevant ledger entries, assumptions, and source extracts. Do not replay all prior prose.
7. **Independent QA.** The generation pass does not certify itself. Run `prompts/05-qa-reviewer.md` before publication.
8. **Editable outputs.** Keep analysis modules and outputs in separate files so the user can revise one section without destroying the rest of the research state.

## Workspace layout

Each company lives under:

```text
companies/<TICKER>/
  project.yaml
  state/
  sources/
  data/
  analysis/
  outputs/
```

If the workspace does not exist, initialize it from `templates/company/` or run:

```bash
python scripts/init_company.py <TICKER> "<Company Name>"
```

## Workflow router

Choose exactly one primary workflow:

### Quick View
Use `workflows/quick-view.md` when the user needs a fast initial stance, debate map, or screening view.

### Full Initiation
Use `workflows/full-initiation.md` for a new IOC or when no usable company state exists.

### Update
Use `workflows/update.md` when new earnings, guidance, filings, news, or material datapoints arrive.

### Scenario
Use `workflows/scenario.md` when the user changes valuation, forecast, macro, or operating assumptions and fresh evidence is not required.

### Publish
Use `workflows/publish.md` when the analytical state is substantially complete and the task is mainly rendering or editing outputs.

## Research stages

For a full initiation, execute these stages:

1. Resolve target, benchmark, horizon, currency, rating convention, and special investor question.
2. Create/update `state/research-context.yaml`.
3. Produce a concise preliminary framing before deep work.
4. Build `sources/registry.csv`; store useful source extracts or references.
5. Normalize evidence into `state/ledger.jsonl` using `schemas/ledger-record.schema.json`.
6. Run the analytical modules in `modules/` as applicable.
7. Maintain `state/assumptions.yaml`, `state/contradictions.yaml`, and `state/dependency-graph.yaml` continuously.
8. Run company-specific forecast/IOC overlay.
9. Run valuation and strategist dashboard.
10. Synthesize using `prompts/04-final-synthesis.md`.
11. Validate with `prompts/05-qa-reviewer.md` and `scripts/validate_workspace.py`.
12. Publish the requested artifact(s) to `outputs/`.

## Model / reasoning routing

Do not use the highest-cost reasoning setting for every task.

- **Fast / low reasoning:** ticker resolution, formatting, table reshaping, obvious field extraction, source registry updates.
- **Medium reasoning:** filing extraction, evidence normalization, peer grouping, historical financial normalization, ordinary forecast maintenance.
- **High reasoning:** economic-engine identification, cycle-vs-structure, AI/technology disruption, reverse valuation, variant perception, contradictions, recommendation adjudication, QA.
- **Highest available reasoning:** only for genuinely difficult unresolved conflicts or final adjudication where a wrong conclusion would materially change the rating.

If operating in an agentic Work environment, use it for long-running browsing, file manipulation, model building, and multi-artifact publication. Use ordinary chat for framing, steering, review, and narrow edits.

## Ledger contract

Every material ledger record should identify:

- `id`;
- `record_type`: `observed_fact`, `derived_metric`, `assumption`, `analytical_conclusion`, `risk`, `catalyst`, `falsification`, `research_gap`;
- `statement`;
- period/date where relevant;
- value/unit where quantitative;
- source IDs for sourced observations;
- confidence;
- affected analytical nodes;
- status.

Never overwrite history silently. If a fact or conclusion changes, supersede it or preserve enough provenance to understand what changed.

## Dependency / recomputation rule

When a source fact or assumption changes:

1. locate the record in `state/ledger.jsonl` or `state/assumptions.yaml`;
2. consult `state/dependency-graph.yaml`;
3. mark affected nodes stale;
4. rerun only affected nodes and their downstream dependents;
5. update dashboard and thesis if recommendation-relevant;
6. record material changes in the update note.

Example:

```text
WACC assumption
   → valuation
   → scenario table
   → strategist dashboard
   → investment thesis
```

A WACC edit should not rerun industry structure or source ingestion.

## Publication standard

For initiation of coverage, the rendered report should ordinarily include:

- Investment Thesis;
- Company Overview;
- Industry & Competitive Landscape;
- Financial Analysis;
- Forecasts & Key Assumptions;
- Valuation;
- Catalysts;
- Risks;
- Conclusion / Recommendation.

The recommendation must be internally consistent with forecast and valuation assumptions. Include explicit falsification criteria and distinguish market expectations from the analyst's variant view.

## Rating logic

Do not choose a rating merely from upside to a price target. Consider:

- earnings revision direction;
- valuation expectations;
- quality/durability of cash flows;
- balance-sheet and capital-allocation risk;
- credible catalysts within the horizon;
- probability-weighted downside;
- benchmark-relative opportunity cost.

If evidence is insufficient, preserve ambiguity rather than force a high-conviction rating.

## User interaction

Expose useful intermediate state. Do not make the user wait for the complete IOC before seeing anything.

At minimum, after target resolution provide:

- the principal investor debate;
- what appears to be priced in;
- 2–4 hypotheses the research will test;
- any material ambiguity that could change the workflow.

During a long research run, surface major findings or contradictions as they emerge.

## Source discipline

Use primary sources for company-reported financials and guidance where available. Use secondary sources for market estimates, industry context, channel evidence, or triangulation. Record publication date, observation period, and access date when material.

Do not cite a secondary summary when the primary source directly supports the same quantitative claim unless there is a reason to do so.

## Completion criteria

A full initiation is not complete until:

- material quantitative claims have provenance;
- earnings equations and key sensitivities are identified;
- cycle and structural effects are separated;
- forecast assumptions are explicit;
- valuation is normalized where needed;
- current market expectations are reverse-engineered;
- bear/base/bull cases are internally consistent;
- recommendation has explicit falsification criteria;
- contradictions and research gaps are visible;
- QA passes or unresolved exceptions are disclosed.
