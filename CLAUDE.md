# Repository Instructions for Research Publications

## Purpose

This repository stores durable, evidence-backed equity research and the publications generated from it. Agents may use ReportKit, document generators, presentation systems, AI publication tools, or other rendering software to produce finished artifacts.

Publication tooling is a presentation and composition layer. It must not silently become a summarization layer or materially change the intended nature, scope, analytical depth, or audience of the source deliverable.

## Preserve the requested publication type

Before drafting or rendering, identify the requested artifact: full initiation of coverage, sector primer, research update, scenario note, monitoring dashboard, investment-committee brief, presentation, source appendix, or another format.

- Preserve that artifact type unless the user explicitly asks to change it.
- Do not turn a full initiation of coverage into an executive brief, dashboard, tear sheet, or presentation-style summary merely to fit a template.
- Do not treat a publication tool's example, default template, page count, or layout density as an editorial length constraint.
- A short executive summary does not imply that the body of the report should be short.
- When a tool has pagination or layout constraints, add pages, restructure sections, or split exhibits instead of deleting substantive content.
- If the user explicitly requests a condensed version, state what was omitted or provide the full report as a companion artifact when appropriate.

## Research state and source hierarchy

The workspace is the research record; publications are views of that record. Follow [docs/state-vs-report.md](docs/state-vs-report.md).

For a company workspace under `research/<TICKER>/`:

- `state/` contains durable facts, assumptions, contradictions, dependencies, gaps, and research context.
- `data/` contains normalized quantitative inputs and model outputs.
- `analysis/` contains substantive analytical modules. These are not disposable scratch notes and must not be ignored merely because a shorter file exists under `outputs/`.
- `outputs/` contains publication-ready views that may already be deliberately compressed for a particular use case.
- `sources/` contains provenance and source-quality information.

For a sector workspace created by `skills/sector-primer/`:

- `state/` contains the sector scope, ledger, assumptions, contradictions, research gaps, and current context.
- `data/` contains sector dashboard metrics and company comparable observations with periods, definitions, and source IDs.
- `outputs/` contains the rendered sector primer, which is a view of the persisted state.
- `sources/` contains source metadata and provenance for market, industry, and company evidence.

When producing a new full report, synthesize the relevant validated state, data, and analytical modules. Do not simply restyle the shortest existing output unless the user specifically asks to render that output without expansion.

## Fidelity requirements

Reformatting, typesetting, or adapting research for another publication system may improve organization and remove genuine repetition, but it must preserve all material analytical content. In particular, retain:

- the company and business-model context needed to understand how the company makes money;
- industry structure, value-chain position, competitive landscape, pricing power, and cyclicality;
- asset mix, geographic exposure, operating structure, and important segment differences;
- historical financial development, forecasts, key assumptions, and model methodology;
- the investment thesis, variant perception, supporting evidence, and counterarguments;
- valuation methodology, scenario construction, sensitivities, and reverse expectations;
- catalysts, risks, contradictions, evidence gaps, uncertainty, and falsification criteria;
- source attribution, evidence quality, dates, units, and distinctions between reported, derived, estimated, and judgemental values;
- conclusions, rating logic, and the conditions that would change the view.

Do not remove an entire analytical lens, section, qualification, or data series solely to make the artifact shorter or visually cleaner. Do not introduce unsupported facts, resolve documented contradictions by averaging them away, or change a rating, forecast, assumption, or conclusion for narrative convenience.

Substantive analytical changes must update the research state first and then regenerate affected publication sections. Wording and layout changes may remain publication-only changes.

## Full initiation-of-coverage standard

A full initiation is a long-form institutional research product, not a company tear sheet. Unless the user requests a different structure, it should include:

1. Investment Thesis and Executive Summary
2. Company Overview and Business Model
3. Industry, Value Chain, and Competitive Landscape
4. Asset Portfolio, Operating Exposure, and Strategic Position
5. Historical Financial and Operating Analysis
6. Forecasts, Earnings Drivers, and Key Assumptions
7. Valuation, Reverse Expectations, Scenarios, and Sensitivities
8. Catalysts, Risks, Debate Map, and Decision Rules
9. Conclusion, Rating, and What Would Change the View
10. Methodology, Research Limitations, and Source Appendix where material

The precise ordering may change to improve the argument, but the underlying coverage should not disappear. A full initiation should normally devote several pages to company context and business economics before relying on valuation conclusions.

The default IOC structure in [the publish workflow](skills/persistent-equity-research/references/workflow-publish.md) is a minimum coverage checklist, not a maximum length.

## Exhibits and data

Use exhibits to deepen the analysis rather than replace necessary explanation.

- Convert material quantitative evidence into readable charts, tables, bridges, or sensitivity exhibits where useful.
- Provide surrounding prose that explains what an exhibit measures, why it matters, and how it affects the investment conclusion.
- Include adequate historical and forecast periods for the reader to understand direction, cyclicality, and estimate formation.
- Reconcile displayed figures to the workspace data and identify the source or derivation.
- Preserve material tables even when a publication template offers only a small number of example exhibits.
- Do not use visual density as a substitute for analytical context.

## Publication workflow

For a substantial publication:

1. Inventory the relevant research files, analytical modules, datasets, and existing outputs.
2. Build a coverage map from source topics to planned report sections and exhibits.
3. Identify whether an existing output is a complete source manuscript or only a compressed synthesis.
4. Draft the full narrative at the depth implied by the requested publication type and audience.
5. Apply the publication system's typography, layout, and visual grammar without allowing the template to dictate scope.
6. Reconcile forecasts, valuation, scenarios, and exhibits to validated workspace state.
7. Compare the finished artifact with the coverage map and restore any material topic lost during composition.
8. Inspect every rendered page for readability, clipping, bad page breaks, and misleading visual emphasis.

## Final publication gate

Before declaring a publication complete, verify that:

- the output is still the document type the user requested;
- all material source themes are represented or any exclusions are explicitly justified;
- company background and business-model context are sufficient for a reader unfamiliar with the company;
- analysis and exhibits support one another rather than competing for space;
- facts, interpretations, assumptions, uncertainties, and recommendations remain distinct;
- material caveats, contradictory evidence, research gaps, and falsification tests remain visible;
- conclusions and numbers reconcile to the durable research state;
- compression has removed repetition, not unique analysis;
- the report has not been shortened merely to resemble an example or satisfy an arbitrary page target.

If these conditions cannot be met within the selected publication format, expand or change the format while preserving the requested deliverable's nature. Ask the user before making a materially different artifact.
