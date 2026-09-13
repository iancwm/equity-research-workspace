# Module 7 — Company Overlay & IOC Forecasts

_Ledger references: CO-01 to CO-10, VAL-01 to VAL-03. Sources: S001, S002, S011, S012. Data: `data/historical-financials.csv`, `data/forecast.csv`._

## Company architecture

- **Segment revenue mix (FY2025)**: Deliveries 53%, Mobility 36%, Financial Services 10%, Others <1%.
- **Geographic exposure**: not disclosed at the country-revenue level in the sources accessed; qualitatively, Singapore/Malaysia are the most mature/monetized markets, Indonesia is the largest population opportunity but most competitively contested, and Vietnam/Philippines/Thailand are mid-scale markets now also carrying incremental regulatory risk (Vietnam, per RISK-01/VC-05).
- **Recurring vs. transactional**: the on-demand segments are inherently transactional (per-ride, per-order), but MTU/frequency metrics (GMV per MTU, advertiser retention) function as the closest available proxy for recurring-engagement quality; Financial Services (deposits, recurring loan interest) is structurally the most recurring-revenue segment, though still small.
- **Acquisition vs. organic growth**: FY2026 guidance was explicitly raised in part due to the **consolidation of SuperBank and Stash** (Indonesian digital banking assets) — a real, disclosed acquisition/consolidation contribution to growth that should be separated from organic Deliveries/Mobility momentum when assessing quality of growth (CO-10).
- **Key company-specific advantages**: regional superapp distribution, dominant food-delivery share, first-full-year-profitable digital-bank optionality, large net-cash balance sheet ($5.4bn net cash liquidity) providing both a funding cushion and a rate-sensitive income stream.
- **Key company-specific vulnerabilities**: thin Deliveries margin base relative to competitive-intensity risk, unresolved Financial Services path-to-profitability, dual-class governance structure (RISK-03), and an unresolved large strategic shareholder (Uber, ~13.5% stake, RISK-02) that is a persistent overhang risk independent of fundamentals.

## Historical financials (see `data/historical-financials.csv` for full detail)

| Metric | FY2023 | FY2024 | FY2025 | Q2 2026 (LTM trend) |
|---|---|---|---|---|
| Revenue ($m) | 2,359 | 2,797 (+19%) | 3,370 (+20%) | Guided $4,125m FY2026E (+22% at midpoint) |
| Adjusted EBITDA ($m) | (22) | 313 | 500 (+60%) | Guided $730m FY2026E (+46% at midpoint) |
| Adjusted EBITDA margin | (0.9%) | 11.2% | 14.8% | ~17.7% implied FY2026E |
| Net income/(loss) ($m) | (485) | (158) | 200 | $235m Q2 2026 alone (vs $20m PY) |
| Adjusted FCF ($m) | (234) [tier-4 sourced] | 162 | 290 | $450m TTM disclosed at Q2 2026 |
| Diluted EPS ($) | n/a (not sourced) | (0.03) | 0.06 | $0.06 (Q2 2026 quarter alone) |
| Total ordinary shares (m) | n/a | 4,065 | 4,089 | 4,079 (Jun-2026; down on buybacks) |

Note: Adjusted EBITDA is Grab's own non-IFRS measure throughout; unadjusted IFRS operating profit was $65m FY2025 vs $(168)m FY2024 (see Module 1, Section 5, and RG-04 on methodology consistency across years).

## Forecast — base, bear, bull (see `data/forecast.csv` and `state/assumptions.json` for full assumption detail)

**Base case** assumes Grab executes toward its own disclosed targets (FY2026 guidance midpoint; 2028 Adjusted EBITDA target of $1.5bn; 80% FCF-conversion target approached but not fully reached by FY2028):

| | FY2026E | FY2027E | FY2028E |
|---|---|---|---|
| Revenue ($m) | 4,125 | 4,826 | 5,550 |
| Revenue growth | 22.4% | 17.0% | 15.0% |
| Adjusted EBITDA ($m) | 730 | 1,025 | 1,500 |
| EBIT ($m, derived bridge) | 235 | 470 | 889 |
| Net income attributable to owners ($m, derived) | 386 | 570 | 893 |
| EPS ($, derived) | 0.094 | 0.140 | 0.220 |
| Adjusted FCF ($m) | 475 | 738 | 1,170 |

The EBIT and net-income lines are **derived bridges**, not company-guided figures: EBIT is built by assuming the historical EBITDA-to-EBIT bridge (D&A + share-based compensation + restructuring/M&A costs, ~12.9% of revenue in FY2025) gradually narrows toward ~11% of revenue as share-based compensation normalizes with scale; net income assumes net finance income drifts modestly with the net-cash base and an effective tax rate near 22%. **These are explicitly lower-confidence, judgmental reconciliations (CO-06, CO-07, CO-08) — decision-useful for order-of-magnitude EPS/FCF framing, not a substitute for a full bottom-up model.**

**Bear case (FY2028E)**: revenue $4,752m (cumulative growth path 8-10% p.a. in the outer years, reflecting Deliveries share loss to a well-funded competitor), Adjusted EBITDA only $1,000m (a ~33% shortfall to the management target, consistent with Maybank's "aggressive competition" scenario magnitude), EPS $0.115, Adjusted FCF $550m.

**Bull case (FY2028E)**: revenue $6,019m (continued mid-to-high-teens growth), Adjusted EBITDA $1,600m (modestly exceeding the management target on Deliveries margin upside and Financial Services reaching breakeven), EPS $0.260, Adjusted FCF $1,312m.

## Reconciliation chain

Revenue → Segment Adjusted EBITDA (Deliveries/Mobility/Financial Services/Others) → less Regional Corporate Costs → Group Adjusted EBITDA → less D&A/SBC/restructuring bridge → Operating Profit (EBIT) → plus Net Finance Income → less Tax → Profit for Period → less/plus Non-Controlling Interest → Profit Attributable to Owners → ÷ Diluted Shares → EPS. Cash side: Adjusted EBITDA → Adjusted FCF (via disclosed conversion-rate assumption, since unadjusted operating cash flow is dominated by loan/deposit working-capital swings not indicative of platform cash generation — see Module 1, Section 5 and RG-04).

## Recommendation inputs

- **Earnings direction**: Positive (DASH-02) — guidance was raised, not cut, at the most recent print, and the beat-and-raise pattern has now held for multiple consecutive quarters.
- **Valuation expectations**: Reasonable-to-Depressed relative to peers (see Module 5) — the market is not yet crediting Grab with re-rating toward Uber/GoTo multiples despite comparable-or-better fundamental momentum.
- **Balance-sheet/capital-allocation risk**: Low-to-moderate — net cash liquidity is large and buybacks are being funded from FCF, but the Financial Services segment represents a real, disclosed-but-not-fully-transparent capital commitment (RG-02) and a genuine tail risk if regional credit conditions deteriorate (RISK-04).
- **Probability-weighted outcome**: applying illustrative subjective weights (25% bear / 55% base / 20% bull) to the FY2028E-based valuation scenarios in `data/valuation.csv` (bear $2.03, base $4.29, bull $5.99) yields a probability-weighted price of approximately **$3.79**, roughly 24% above the current $3.05 price — supportive of a constructive but not maximum-conviction stance (see final synthesis and rating).
- **Catalysts within 12-24 months**: continued guidance beats (CAT-01), Grab-GoTo resolution in either direction (CAT-02), Vietnam regulatory resolution (A-14), Foodpanda ownership resolution (VC-03).
- **Benchmark-relative opportunity cost**: against Uber (steadier but slower-growing, richer multiple) and GoTo (cheaper on some metrics but smaller scale, weaker segment mix, and the more directly GoTo-exposed name if a merger narrative resolves unfavorably for non-Grab shareholders), Grab offers the more balanced combination of scale, segment-margin quality, and unresolved re-rating potential within this specific regional comp set.
