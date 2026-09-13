# QA Review — Grab Holdings (GRAB) Initiation of Coverage

_Reviewed 2026-09-13 against `skills/persistent-equity-research/references/qa-review.md`. This is a same-session self-review using only the persisted state, data, and draft — not an independent-agent review; disclosed per the skill's capability-boundary requirement._

## Evidence

- Material quantitative claims sourced? **PASS.** All financial figures trace to ledger records with source_ids (EE-01 to EE-05, CO-01 to CO-04) and to `sources/registry.jsonl`.
- Source dates and observation periods current enough? **PASS**, with one caveat: FY2022 figures (RG-01) are secondary-sourced and flagged as lower confidence; used only for long-run trend context, not in any forecast or valuation input.
- Primary sources used for reported financials? **PASS** for FY2023-Q2 2026 (S001-S004, direct SEC 6-K filings and Grab IR earnings releases). **PARTIAL** for FY2022 (secondary only, RG-01, disclosed).
- Contradictory datapoints preserved? **PASS.** Four open contradictions logged in `state/contradictions.json` (C-01 to C-04) rather than resolved by narrative convenience, including the sell-side-consensus-vs-price-action divergence (C-03) and the GXS Group loss reconciliation gap (C-04).

## Economics

- Company/industry earnings equations explicit? **PASS** (Module 1, Section 5).
- 2-3 most important sensitivities quantified? **PASS** — Deliveries margin identified and quantified as the dominant driver (VAL-09, $200-240m per 100bp).
- Operating leverage addressed? **PASS** (Module 1, Section 8; Section 5 of the IOC).
- Maintenance vs. growth capex separated? **PARTIAL.** Grab does not disclose this split; the report notes overall capex intensity (5.6% of revenue) without a maintenance/growth breakdown. Logged as an implicit limitation rather than a separate research gap, since the company itself does not provide the split.
- Pricing power tested rather than asserted? **PASS** (Module 3, Section on "Pricing-power stress test," VC-04), including an explicit statement that the test has not yet been run against a well-funded competitive response.

## Forecasting

- Do revenue, margins, tax, share count, capex, working capital, and FCF assumptions reconcile? **PASS**, with the explicit caveat that the EBIT/net-income bridge is a derived, lower-confidence overlay on top of company-guided revenue/EBITDA figures (CO-06 to CO-08), clearly labeled as such in Section 6 of the IOC.
- Does scenario logic vary the variables that actually drive the business? **PASS** — bear/base/bull vary Deliveries margin, Financial Services losses, and revenue growth, i.e., the same variables identified in Modules 1 and 3 as the true earnings drivers, not arbitrary multiple changes alone.
- Are acquisitions separated from organic growth when material? **PASS** — SuperBank/Stash consolidation flagged explicitly as a distinct contributor to the FY2026 guidance raise (CO-10), not blended silently into "organic" commentary.

## Valuation

- Is the methodology economically appropriate? **PASS** — EV/Adjusted EBITDA is appropriate for a platform marketplace business without a long profitable history; P/E and DCF are used only as secondary cross-checks given data limitations (RG-03).
- Cyclicality normalized where spot multiples mislead? **PASS (qualitative)** — Module 4 explicitly separates Mobility's more structural margin position from Deliveries' more cyclical/provisional one, and valuation weights this distinction in the "Reasonable-to-Depressed" classification.
- Does reverse valuation explain what the price embeds? **PASS** (Section 7.3 of the IOC, VAL-06).
- Does the price target reconcile with the published forecast? **PASS** — the base-case price target ($4.29) is built directly from the same FY2028E Adjusted EBITDA figure ($1,500m) used in Section 6's forecast table, not a separately-derived number.
- Is the recommendation benchmark-relative where required? **PASS** (Section 7.2 peer comparison; Module 7 "benchmark-relative opportunity cost").

## Thesis

- Credible variant perception rather than generic quality argument? **PASS** — the variant perception (Section 8, DASH-06/DASH-07) is specific: a quantified multiple gap versus named peers, not a generic "good company" argument.
- Catalyst and bear risk measurable? **PASS** — both tied to a specific, trackable metric (Deliveries segment margin threshold) and a specific, dated regulatory process (Vietnam National Competition Commission review).
- Falsification criteria explicit? **PASS** (Section 8.4, plus MT-06, VAL-10, DASH-04/DASH-05 in the ledger).
- Does the conclusion preserve unresolved ambiguity? **PASS** — the rating is explicitly framed as "constructive, not maximum-conviction" with a real, quantified bear case (-33%), and four contradictions remain open rather than resolved for narrative tidiness.

## Overall assessment

1. **Critical failures requiring correction before publication:** None identified.
2. **Material weaknesses that reduce conviction:** (a) FY2022 historicals and all market-share figures rely on secondary sources (RG-01, VC-07); (b) the EBIT/net-income/EPS forecast bridge is a judgmental overlay, not a fully sourced bottom-up build (CO-06 to CO-08); (c) Financial Services' true credit quality cannot be independently verified from public disclosure (CS-04, RG-02).
3. **Optional improvements:** ingest Grab's FY2025 Form 20-F once filed (RG-02); obtain a subscription-grade market-share dataset (VC-07); obtain a primary regional macro/TAM source such as e-Conomy SEA (RG-03).
4. **Overall publication status: READY**, subject to the disclosed limitations above being carried into the published report (they are — see IOC Section 10).
