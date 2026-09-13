# Module 2 — Macro Transmission

_Ledger references: MT-01 to MT-06. Sources: S001, S002, S010._

## Rates

**Macro variable → Operational KPI → Revenue → Margin → FCF**

Interest rates → Net cash liquidity yield (Grab holds $7.4bn gross / $5.4bn net cash liquidity in cash, time deposits and marketable securities) → **Net finance income** (not revenue; sits below operating profit) → **Reported net income** (not Adjusted EBITDA) → cash balance itself.

- FY2025 net finance income was $203m ($240m finance income vs $71m finance costs), a substantial contributor to the swing from a $168m FY2024 net loss to $200m FY2025 net profit (MT-02).
- **Lag**: near-immediate — most of the balance sits in short-term deposits/marketable securities that reprice within one to a few quarters.
- **±100bp sensitivity**: an estimated $50-55m annualized effect on net finance income (MT-03) — small relative to Group revenue ($4.1bn+ FY2026E) but material relative to reported net income (~15-20% of a plausible FY2026E net income base), and therefore relevant to EPS-based valuation approaches even though it barely touches Adjusted EBITDA.
- On the funding side, GXS Bank/GXBank/SuperBank's loan book (gross $2.3bn at Jun-2026, +197% YoY) is a rate-sensitive **beneficiary** of higher net interest margins as long as funding costs (deposit rates) do not rise proportionally — a genuine, if small-scale today, natural offset to the cash-side sensitivity above.
- **WACC/DCF effect**: a ±100bp move in the risk-free rate has an outsized effect on Grab's valuation precisely because so much of its equity story (per the reverse-valuation framework in Module 5) is embedded in FY2027-FY2030 EBITDA growth rather than current cash flow — see illustrative discount-rate sensitivity in `data/valuation.csv` (A-13: 9.5%/11%/13% bull/base/bear).

## Inflation

- **Input inflation** (fuel, food commodity costs for grocery/Jaya Grocer, driver cost-of-living) does not flow through Grab's own cost of revenue in a simple pass-through way, because drivers and merchants — not Grab — bear most direct input costs. Instead, inflation transmits via **partner-incentive requirements**: if fuel or living costs rise faster than driver earnings, Grab must raise incentives (or fares) to retain driver supply, which is exactly what management flagged in Q2 2026 ("elevated fuel prices," MT-05) even as MTUs hit a record.
- **Consumer-side inflation** affects discretionary delivery-order frequency (a demand-side transmission channel) and is one reason management explicitly frames its strategy around "greater affordability" (Grab's own Q4 2025 letter to shareholders, S002) rather than price increases.
- **Lag**: partner-incentive adjustments tend to show up within 1-2 quarters of a sustained fuel-price move; consumer order-frequency effects can lag further given loyalty and habit formation.
- **Margin effect**: modest and manageable to date — Mobility margin actually *expanded* slightly in Q2 2026 (8.6% vs prior year, though down marginally sequentially per Maybank, S010) despite fuel headwinds, suggesting Grab has some ability to offset via GMV growth and mix.

## FX and commodities

- Grab reports in USD but earns and spends almost entirely in ASEAN local currencies (IDR, MYR, THB, VND, PHP, SGD). This creates **translation exposure** (reported USD growth vs constant-currency growth diverges with FX moves) more than transaction exposure, since most segments are naturally matched (local revenue, local driver/merchant payouts).
- FY2025 reported growth (20%) modestly *exceeded* constant-currency growth (18%), implying regional currencies appreciated against the US dollar over the year (MT-04) — a tailwind that will not necessarily persist.
- Maybank (S010) flagged an expected **3-4 percentage point FX headwind** to Q3 2026 reported GMV growth — a reversal signal worth monitoring closely, since it would be the first negative FX print in the recent trend and could unsettle investors focused on headline reported growth even if constant-currency execution remains intact.
- **Natural hedges**: local-currency revenue against local-currency costs (driver/merchant payouts, regional offices) provides a reasonable operating hedge; the **convertible notes** ($1.5bn, issued FY2025, MT-01) are USD-denominated, meaning Grab has taken on USD financial liabilities against a local-currency-earning asset base — a modest, deliberate financial-currency mismatch that increases sensitivity to a broad USD-strength cycle beyond the pure translation effect on revenue.
- **Commodity exposure**: minimal direct exposure; the main commodity linkage is indirect, through fuel prices and their effect on driver-partner economics (see Inflation above and MT-05).

## Falsification

MT-06: the macro-transmission thesis would be falsified if net finance income declines faster than the net-cash-liquidity trend implies (a signal of FX losses or yield deterioration beyond simple rate moves), or if the reported-vs-constant-currency growth spread turns persistently and materially negative beyond the ~3-4pp already flagged for Q3 2026, indicating a structural FX headwind rather than a single-quarter effect.

## Dependencies

Feeds into: Module 3 (fuel/incentive linkage to pricing power), Module 5 (discount-rate and net-cash assumptions in valuation), Module 7 (net finance income in the profit bridge).
