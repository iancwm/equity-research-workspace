# Valuation and Expectations — Apple

## Current setup

The September 9, 2026 intraday snapshot places AAPL at $314.70, $4.628T market capitalization and 36.1x trailing P/E. Adjusting the June-quarter balance sheet for $62.2B of net cash gives enterprise value of approximately $4.566T. The timing mismatch between the intraday quote and quarterly balance sheet is disclosed and should be refreshed for publication. [OBS-008, OBS-012, DER-003]

## Scenario valuation

Forward P/E is the primary communication method because mature free cash flow, return of capital and EPS compounding are the dominant equity-value drivers. It is not sufficient on its own, so an illustrative DCF is shown as a duration sensitivity.

| Case | Key operating assumption | FY2027 EPS | Multiple | Implied value | Probability |
|---|---|---:|---:|---:|---:|
| Bear | 3.5% revenue growth; 31.0% EBIT margin | $8.64 | 27.5x | $237.7 | 25% |
| Base | 6.5% revenue growth; 32.1% EBIT margin | $9.33 | 34.3x | $320.0 | 50% |
| Bull | 10.0% revenue growth; 33.0% EBIT margin | $10.10 | 37.0x | $373.8 | 25% |

Probability-weighted P/E value is **$313.9 per share**, effectively the quoted price. Each revenue, margin, tax, share-count, CFO, capex and FCF driver is persisted in `data/scenario-forecast.csv`. [CON-004]

## Reverse-expectations framing

The market does not appear to be pricing a distressed hardware company. A 36.1x trailing P/E and $4.6T equity value require durable premium-multiple earnings growth, sustained cash return and confidence that Services/cycle advantages can more than offset memory and regulatory pressure. This is an inference from the price and our scenario framework, not a claim about a published consensus forecast. [OBS-012, CON-004]

## DCF cross-check

Using FY2026E-FY2030E FCF of $130.5B to $174.9B, 3.0% terminal growth, 7.5% WACC and $62.2B net cash gives about **$237.2 per share**. At 6.5% / 8.5% WACC, the output is roughly $304.8 / $194.3. This wide range says the valuation is duration-sensitive; it does not establish a superior target price to the P/E framework.

## Interpretation and limits

The P/E framework captures Apple’s cash-return profile but relies on an unvalidated premium multiple. The lower DCF outcome is sensitive to WACC and terminal growth but cannot be dismissed. The correct adjudication is **no benchmark-relative rating**: the methods bracket a wide range, and peer valuation history, independently sourced consensus and a quantified EU exposure are missing. [CON-004, G-001]
