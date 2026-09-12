# Sector analytics and comparable companies

Use this reference when the request includes broad sector data, quantitative analysis, or peer benchmarking. The objective is comparability and explanatory power, not maximum metric count.

## Sector dashboard

Select metrics that reveal demand, price, supply, economics, capital intensity, and market expectations. Typical groups are:

| Question | Useful metrics | Important qualification |
|---|---|---|
| How large and fast is demand? | Market revenue, units/volume, penetration, installed base, end-market mix, historical and forecast CAGR | Define the market perimeter and distinguish volume from price/mix growth |
| Who has power? | Market shares, concentration, capacity, utilization, backlog, churn, customer concentration | Explain whether shares are by revenue, units, capacity, or another basis |
| Can participants earn attractive economics? | Gross/EBITDA/EBIT margins, ROIC/ROE, incremental margins, pricing versus cost inflation | Use consistent accounting periods and note business-model mix |
| How cash and capital intensive is it? | Capex/sales, R&D/sales, working-capital intensity, cash conversion, FCF margin, net debt/EBITDA | Separate maintenance from growth investment when possible |
| What drives the cycle? | Price indices, volumes, inventory, capacity additions, lead times, orders, utilization, rates, FX, commodity inputs | State the transmission lag and the relevant subsector |
| What is priced in? | Absolute and relative P/E, EV/EBITDA, EV/sales, FCF yield, dividend yield, total return, estimate revisions | Mark LTM, NTM, FY, and point-in-time values explicitly |

Useful calculations include:

- CAGR: `(ending value / beginning value)^(1 / years) - 1`; state whether the endpoints are reported or estimated.
- Margin: `profit measure / stated revenue`; do not mix adjusted and reported profit without labeling both.
- ROIC: use a consistent operating-profit and invested-capital definition; disclose treatment of goodwill, leases, excess cash, and tax.
- Cash conversion: `FCF / EBITDA` or `FCF / net income`; identify the chosen denominator and unusual working-capital effects.
- Concentration: use a clearly defined measure such as top-five share or HHI; do not infer concentration from a small peer list.
- Relative valuation: compare each company with the selected peer median or a justified reference set, and show the underlying absolute multiple.

### Aggregation choices

Prefer a table with individual observations plus a transparent summary. If aggregating, label the method:

- **Market-cap weighted:** useful for investable-sector exposure and index-like economics; dominated by the largest companies.
- **Revenue weighted:** useful for sector operating scale; can overrepresent low-margin businesses.
- **Equal weighted:** useful for typical constituent experience; sensitive to small or distressed names.
- **Simple aggregate:** useful for total sector revenue or profit only when constituents have consistent perimeter and no double counting.

Do not combine these methods in one dashboard without labeling them. Remove intercompany revenue or overlapping business lines when the universe would otherwise double count the same economics.

## Peer-universe design

Build the set in layers:

1. Core peers with substantially similar products, customers, geography, and earnings drivers.
2. Leaders and challengers that reveal scale, share, or margin differences.
3. Adjacent or substitute businesses that compete for the same customer budget or scarce input.
4. Excluded names that look similar by label but differ materially in exposure, accounting, geography, or business model.

For each company, record at least:

| Field | Why it matters |
|---|---|
| Ticker, issuer, exchange, currency, market-data date | Prevents stale or ambiguous market values |
| Subsector and exposure tags | Explains why it belongs in the set and what is not comparable |
| Market cap and enterprise value | Establishes scale; document debt, leases, minority interest, and cash treatment where relevant |
| Revenue, growth, EBITDA/EBIT margin, ROIC/ROE | Frames operating quality and trajectory |
| Capex/R&D, FCF margin or yield, net debt/EBITDA | Shows reinvestment, cash generation, and balance-sheet risk |
| Valuation multiples and estimate basis | Shows expectations; identify LTM, NTM, or fiscal-year basis |
| Source, period, definition, and notes | Makes the row auditable and keeps unlike measures from appearing identical |

Use `n.m.` for not meaningful values such as a negative earnings denominator. Do not rank companies on a single multiple. Explain outliers: high growth, cyclically depressed earnings, conglomerate discount, net cash, accounting differences, or non-core assets may all matter.

## Quality checks

Before publication, verify that:

- market data share one observation date or carry explicit as-of dates;
- operating data are labeled actual, LTM, FY, or estimate and use the same forecast vintage where possible;
- the chosen currency and FX convention are stated;
- market cap, enterprise value, leverage, and yield calculations reconcile to source inputs;
- negative denominators and missing values are visible;
- sector aggregates do not double count constituents or mix incompatible perimeters;
- the narrative explains what the table changes about the sector view.
