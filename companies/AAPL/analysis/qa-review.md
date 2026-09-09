# Independent QA Review — AAPL preliminary initiation

**Review mode:** Independent forward test of the persisted workspace, followed by correction of the mechanical defects it identified.
**Overall publication status:** **NOT READY for external investment-grade publication.**

## Structural state

| Check | Status | Evidence |
|---|---|---|
| Required workspace state and fresh outputs | PASS | `scripts/validate_workspace.py companies/AAPL` passes; all fresh dependency outputs exist. |
| Ledger/source provenance | PASS | Ledger source IDs resolve to `sources/registry.csv`; material reported financials use S-001 to S-003. |
| Contradictions and research gaps preserved | PASS | C-001 to C-004 and G-001 retain tariff, industry, DMA and valuation conflicts. |

## Findings corrected after independent review

| Original finding | Correction | Status |
|---|---|---|
| Bear/base/bull EPS and share counts were not linked to operating cases | Persisted all 15 FY2026E-FY2030E rows in `data/scenario-forecast.csv`; P/E valuation now calculates from those linked rows | PASS |
| DCF years and drivers were not persisted | Persisted revenue, EBIT margin, tax, diluted shares, CFO, capex and FCF through FY2030E, plus formulas, WACC, terminal growth and net cash | PASS |
| FQ4 gross-margin monitor did not normalize guidance | Ingested complete FQ4 guidance: 47%-48% reported GM including about 1 point of tariff refunds, or 46%-47% adjusted; reset monitor/F-002 | PASS |
| Equal-weight call lacked benchmark support and did not reconcile P/E/DCF divergence | Replaced the rating with no benchmark-relative rating and preserved C-004 | PASS |

## Remaining publication blockers

| Check | Status | Finding |
|---|---|---|
| Primary verification of forward guidance | FAIL | S-008 is a secondary transcript. It now supplies the complete guidance record but must be replaced or confirmed against a durable Apple primary record. |
| Consensus, peers and valuation history | FAIL | `data/consensus.csv`, `data/peer-comps.csv` and `data/valuation-history.csv` remain empty. A relative valuation premium/discount cannot be validated. |
| DMA exposure | FAIL | Apple does not disclose the EU App Store / Services revenue affected by alternate distribution and payment rules, so the economic exposure is not quantified or bounded. |
| Benchmark-relative recommendation | FAIL | No S&P 500 opportunity-cost or peer return framework exists; the workspace correctly remains unrated. |
| Market-data freshness | FAIL | S-004 is an intraday September 9 snapshot without a provider timestamp in the registry; refresh all market-derived values on publication day. |
| Organic versus acquired growth | FAIL | No source or model decomposition exists; the report must not imply an organic-growth conclusion. |

## Required work before publication

1. Verify S-008 from Apple’s earnings-call recording or an equivalent primary record.
2. Add independently sourced consensus, a focused peer set and valuation history; then decide whether an S&P 500-relative rating is warranted.
3. Quantify or bound the EU Services/App Store exposure and add a scenario sensitivity.
4. Refresh market data and rerun valuation, dashboard, synthesis and QA on the publication date.

**Conclusion:** The forward test demonstrates durable state, dependency tracking, source provenance, linked forecast arithmetic, scenario recomputation and honest QA gating. It deliberately stops short of an external recommendation because the remaining data gaps are material.
