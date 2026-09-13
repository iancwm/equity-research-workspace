# Module 5 — Valuation & Expectations

_Ledger references: VAL-01 to VAL-10, RISK-02. Sources: S001, S002, S010, S011, S012, S013-S018. Data: `data/valuation.csv`, `data/peer-comps.csv`, `data/valuation-history.csv`, `data/consensus.csv`._

## 1. Relevant metrics

Given Grab's growth-stage, platform-marketplace economics, **EV/Adjusted EBITDA** (forward) is the primary valuation lens, supplemented by EV/Revenue (useful given Financial Services distorts blended margins) and a reverse-DCF-style expectations read. P/E is emerging as usable only from FY2025 onward (first profitable year) and remains distorted by non-operating items (net finance income, convertible-note derivative fair-value swings — CO-09). FCF yield is tracked via Adjusted FCF given the unadjusted operating-cash-flow line's loan/deposit-driven volatility (Module 1).

## 2. Through-cycle history

Grab's own multiple history is short and distorted by its 2021 de-SPAC listing and multi-year unprofitability; a meaningful 5-10 year through-cycle median is not yet available (this is itself informative — GRAB has never traded through a full profit cycle as a public company, so today's multiple compression versus peers cannot be benchmarked against its own history, only against peers). Current spot: **~9.6x EV/FY2026E Adjusted EBITDA**, near the low end of its brief post-profitability trading history (share price is 54% below its 52-week high, VAL-01).

## 3. Peer benchmark (see `data/peer-comps.csv`)

| Company | Revenue growth | EV/EBITDA | Notes |
|---|---|---|---|
| **Grab (GRAB)** | 22.4% (FY2026E guided) | **9.6x** (FY2026E) | Structural growth + margin inflection |
| Uber (UBER) | 16.7% | 14.8x | Larger, more mature, decelerating growth |
| GoTo (GOTO.JK) | 15.3% | 15.1x | Smaller scale, Indonesia-concentrated, Grab's key competitor/merger counterparty |
| Meituan (3690.HK) | 5.6% (China price-war affected) | 9.5x (CY2026E) | Out-of-region, larger scale, currently growth-challenged |
| Sea Limited (SE) | 36.4% | 27.5x | Different business mix/methodology; e-commerce-led |
| DoorDash (DASH) | n/a | 54.2x | US-only comp, richest multiple in the set |

**VAL-05**: Grab trades at a discount to both Uber and GoTo despite comparable-or-superior forecast EBITDA growth and (versus GoTo specifically) structurally better segment economics. This gap is only partially explained by passive-flow/index effects and Financial-Services execution risk.

## 4. Cyclicality normalization

Not directly applicable in the traditional commodity/industrial sense, but the *effective* normalization question is whether FY2025-FY2026 margin expansion is a **structural** step-change (advertising monetization, Mobility scale economics) or a **cyclically benign** window (competitive discipline that could reverse). Module 3/4 conclude this is genuinely mixed by segment — Mobility looks structural, Deliveries looks partially cyclical. Valuation should therefore weight Deliveries' current margin less heavily than Mobility's when assessing multiple appropriateness.

## 5. Private-market/replacement-value test

Not directly meaningful for an asset-light marketplace business; the closest analogue is the **implied value of Grab's digital banking licenses** (GXS Singapore, GXBank Malaysia, SuperBank Indonesia), which is not separately disclosed or easily triangulated from public information (RG-02) — flagged as a valuation component this workspace cannot currently quantify with confidence.

## 6. Reverse valuation (VAL-06)

At the current ~$3.05 price (~9.6x EV/FY2026E Adjusted EBITDA), the market appears to be pricing something closer to Maybank's **moderate-to-aggressive competitive-intensity scenario** for Deliveries (a 23-41% cut to 2030 EBITDA versus base case) than a clean continuation of the current profitability trajectory. In other words, the price does not appear to simply be crediting management's own guidance and 2028 targets at face value — it embeds real skepticism about (a) Deliveries margin durability against Foodpanda/ShopeeFood consolidation risk and (b) whether Financial Services ever reaches breakeven.

## 7. Expectations classification

**Reasonable-to-Depressed**, not Demanding (VAL-06). The stock is not being valued as though the current 18-quarter EBITDA-growth streak, guidance-raise pattern, and 2028 targets are all likely to be realized without friction; it is being valued closer to a scenario with real, but not catastrophic, competitive and execution setbacks. This creates a genuine (not certain) asymmetry: continued execution evidence (2-4 more quarters of stable-to-improving Deliveries margin) would be a straightforward re-rating catalyst, while confirmed competitive erosion would validate the current discount rather than surprise the market.

## 8. Scenario construction (Bear / Base / Bull)

See `data/valuation.csv` for the full scenario table. Two methods are shown: (a) a near-term FY2026E EV/EBITDA cross-check (undiscounted, sanity-checking against the current price), and (b) an FY2028E-based scenario (management's own long-range target horizon) discounted back ~2.2 years at an illustrative, judgmental cost-of-equity (A-13):

| Scenario | FY2028E Adj. EBITDA | Multiple applied | Implied price today (PV'd) | Δ vs. current $3.05 |
|---|---|---|---|---|
| Bear | $1,000m | 7.0x | **$2.03** | -33% |
| Base | $1,500m (mgmt target) | 11.0x | **$4.29** | +41% |
| Bull | $1,600m | 13.5x | **$5.99** | +96% |

A probability-weighted blend (25% bear / 55% base / 20% bull, per Module 7) implies approximately **$3.79**, or ~24% upside from the current price.

## 9. Variable with the largest valuation delta

**VAL-09**: The Deliveries Segment Adjusted EBITDA margin trajectory is the single largest driver of scenario dispersion — a 100bp swing on an estimated ~$20-24bn FY2028E Deliveries GMV base moves Group Adjusted EBITDA by roughly $200-240m, more than the entire bear-to-base swing modeled in Financial Services. **This is the one number a monitoring investor should track above all others** (see also `outputs/dashboard.md`, key monitor).

## 10. Falsification (VAL-10)

The "Reasonable/Depressed" classification would shift toward "Demanding" if GRAB re-rates to peer-average multiples (12-14x forward EV/EBITDA) without a corresponding acceleration in segment fundamentals. It would be reinforced toward "Depressed" (a stronger mispricing case) if Deliveries margin continues expanding through at least two more quarters without measurable share loss.

## Contradiction note

C-03 (unresolved): sell-side consensus is "Strong Buy" with an average target of $5.86 (implying ~92% upside), well above even this workspace's bull case ($5.99, discounted) before discounting, and closer to the undiscounted bull-case value. The gap between consensus optimism and the price action (54% below 52-week high) is not resolved by the evidence gathered here and is logged as an open contradiction rather than adjudicated in either direction.
