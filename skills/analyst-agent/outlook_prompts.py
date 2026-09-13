"""Claude system prompt, tool schemas, and the user-prompt builder for the
Quarterly Outlook report type.

Mirrors the shape of ``prompts.py`` (Phase 1's initiation-of-coverage prompt):
the system prompt is the contract that turns macro evidence into structured,
tool-call-only output, and the tool schemas sit alongside it because the two
are one contract.

Unlike ``prompts.py``, the sector tool (`record_sector_tilt`) cannot bake the
allowed sector names into a static JSON-Schema ``enum`` -- ``sector_universe``
is chosen per call by the caller of ``run_quarterly_outlook``, not fixed at
import time. Instead the system/user prompt spells out the exact allowed
sector list for this run, and ``outlook_report.py`` reconciles the tool calls
Claude actually made against that list afterwards (dropping, not fabricating,
any sector name that does not match -- the same pattern
``workspace_adapter.py`` uses for unresolvable source links).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT_OUTLOOK = """\
You are an institutional macro strategist producing a quarterly asset-allocation \
outlook for portfolio managers and systematic allocators.

Given macro data, economic indicators, sector performance and valuation data, \
rates/FX evidence, and a set of tail-risk headlines, you will:
1. Construct three macro scenarios (Bull, Base, Bear) with explicit probability
   weights that sum to 1.0 (100%).
2. Tilt every sector in the requested sector universe (overweight, neutral, or
   underweight), grounded in each sector's earnings growth versus its
   valuation, for at least the Base scenario.
3. Record explicit relative-value views: growth vs value, the quality premium,
   and bonds vs equities.
4. Flag at least three tail risks and record a dated catalyst calendar of at
   least three entries.

## Output format

Speak in tool calls, not prose. Do not narrate your reasoning in natural
language; let the structured tool calls carry the analysis. Any text you emit
outside a tool call is treated as commentary and is not part of the report.

## Evidence handling

Treat all supplied evidence as unverified mock input. Where evidence is thin
or ambiguous, say so inside the relevant tool call's rationale field rather
than inventing a number the evidence does not support. Every quantitative
field you fill in (growth rates, yields, multiples) should be traceable to,
or a reasoned extrapolation of, the evidence block.

## Required work

**Macro scenarios.** Call `record_macro_scenario` exactly once per case
(Bull, Base, Bear). Probability weights must sum to 1.0 within a small
tolerance: approximately 0.60 Base, 0.25 Bull, 0.15 Bear, adjusted to the
evidence rather than copied blindly. Each case needs its own GDP growth,
inflation, Fed funds rate, 10-year yield, and S&P 500 EPS growth path, plus a
one-paragraph trigger/narrative and explicit winner and loser sectors drawn
from the sector universe.

**Sector tilts.** Call `record_sector_tilt` once per sector, per scenario, for
every sector in the sector universe listed below -- at minimum, tilt every
sector for the Base case. Sector names must be copied exactly as given in the
universe list. Ground each tilt in the sector's recorded earnings growth and
P/E versus its own history; a rationale is required.

**Relative value.** Call `record_relative_value_view` three times, covering:
`"Growth vs Value"`, `"Quality Premium"`, and `"Bonds vs Equities"`. Each call
needs the two metrics being compared, a verdict, and a one-sentence rationale.

**Catalyst calendar.** Call `record_catalyst` at least three times for dated,
market-moving events in the quarter (FOMC, CPI, jobs report, PCE, or a
company/sector-specific event visible in the evidence).

**Tail risks.** Call `flag_tail_risk` at least three times, each in one of the
categories geopolitical, monetary, fiscal, or other.

## Standards

- Institutional tone: no marketing language, no cheerleading.
- Skeptical: show the counter-argument to the Base case, not just its logic.
- Quantify uncertainty: probability weights and ranges, not adjectives alone.
- Conviction is not certainty: the scenario weights carry the uncertainty, not
  the prose.
"""


TOOL_DEFINITIONS_OUTLOOK: List[Dict[str, Any]] = [
    {
        "name": "record_macro_scenario",
        "description": (
            "Record one of the three macro cases (Bull, Base, Bear). Call this "
            "exactly once per case; the three probability_weight values must sum "
            "to approximately 1.0."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Scenario name.",
                    "enum": ["Bull", "Base", "Bear"],
                },
                "probability_weight": {
                    "type": "number",
                    "description": "Probability weight in [0, 1]. The three cases must sum to ~1.0.",
                },
                "gdp_growth_pct": {
                    "type": "number",
                    "description": "Real GDP growth, year over year, in percent, under this case.",
                },
                "inflation_pct": {
                    "type": "number",
                    "description": "Headline CPI inflation, year over year, in percent, under this case.",
                },
                "fed_funds_rate_pct": {
                    "type": "number",
                    "description": "Policy rate at quarter-end under this case, in percent.",
                },
                "ten_year_yield_pct": {
                    "type": "number",
                    "description": "10-year Treasury yield at quarter-end under this case, in percent.",
                },
                "eps_growth_pct": {
                    "type": "number",
                    "description": "S&P 500 EPS growth, year over year, in percent, under this case.",
                },
                "trigger_or_narrative": {
                    "type": "string",
                    "description": "What would need to happen for this case to play out, and why.",
                },
                "winners": {
                    "type": "array",
                    "description": "Sectors (from the sector universe) that outperform under this case.",
                    "items": {"type": "string"},
                },
                "losers": {
                    "type": "array",
                    "description": "Sectors (from the sector universe) that underperform under this case.",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "name",
                "probability_weight",
                "gdp_growth_pct",
                "inflation_pct",
                "fed_funds_rate_pct",
                "ten_year_yield_pct",
                "eps_growth_pct",
                "trigger_or_narrative",
                "winners",
                "losers",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_sector_tilt",
        "description": (
            "Record one sector's positioning call under one scenario. Call once "
            "per sector, per scenario, for every sector in the requested sector "
            "universe -- at minimum for the Base scenario."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": (
                        "Sector name, copied exactly from the sector universe "
                        "listed in the user prompt."
                    ),
                },
                "scenario": {
                    "type": "string",
                    "description": "Which case this tilt applies to.",
                    "enum": ["Bull", "Base", "Bear"],
                },
                "earnings_growth_pct": {
                    "type": "number",
                    "description": "Consensus or scenario-consistent EPS growth for this sector, in percent.",
                },
                "pe_ratio": {
                    "type": "number",
                    "description": "Forward P/E for this sector under this scenario.",
                },
                "tilt": {
                    "type": "string",
                    "description": "The positioning call.",
                    "enum": ["overweight", "neutral", "underweight"],
                },
                "rationale": {
                    "type": "string",
                    "description": "One sentence grounding the tilt in earnings growth versus valuation.",
                },
            },
            "required": [
                "sector",
                "scenario",
                "earnings_growth_pct",
                "pe_ratio",
                "tilt",
                "rationale",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_relative_value_view",
        "description": (
            "Record one explicit relative-value call (e.g. Growth vs Value, "
            "Quality Premium, Bonds vs Equities). Call three times, one per pair."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "pair_name": {
                    "type": "string",
                    "description": "Name of the pair being compared, e.g. 'Growth vs Value'.",
                },
                "metric_a_label": {"type": "string", "description": "Label for the first metric."},
                "metric_a_value": {"type": "string", "description": "Value of the first metric, as text."},
                "metric_b_label": {"type": "string", "description": "Label for the second metric."},
                "metric_b_value": {"type": "string", "description": "Value of the second metric, as text."},
                "verdict": {
                    "type": "string",
                    "description": "The call this comparison implies, e.g. 'Value screens cheap; stay barbelled.'",
                },
                "rationale": {"type": "string", "description": "One sentence explaining the verdict."},
            },
            "required": [
                "pair_name",
                "metric_a_label",
                "metric_a_value",
                "metric_b_label",
                "metric_b_value",
                "verdict",
                "rationale",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_catalyst",
        "description": (
            "Record one dated, market-moving event for the sector catalyst "
            "calendar. Call at least three times."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Catalyst name, e.g. 'FOMC policy decision'."},
                "date": {"type": "string", "description": "Expected date, as YYYY-MM-DD."},
                "impact": {
                    "type": "string",
                    "description": "What this event means for the outlook if it surprises hawkish/dovish or beats/misses.",
                },
            },
            "required": ["name", "date", "impact"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_tail_risk",
        "description": "Flag one low-probability, high-impact risk to the base case. Call at least three times.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the risk is and how it would transmit to markets."},
                "category": {
                    "type": "string",
                    "description": "Risk category.",
                    "enum": ["geopolitical", "monetary", "fiscal", "other"],
                },
            },
            "required": ["description", "category"],
            "additionalProperties": False,
        },
    },
]


def _render_section(title: str, payload: Any) -> str:
    return f"### {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=False, default=str)}\n```\n"


def build_outlook_user_prompt(
    quarter: str,
    macro_scenario: str,
    lookback_quarters: int,
    sector_universe: List[str],
    evidence: Dict[str, Any],
) -> str:
    """Build the user turn carrying macro evidence and the work order.

    Args:
        quarter: Quarter label, e.g. ``"Q1 2025"``.
        macro_scenario: Which case the caller wants headlined ("bull", "base",
            or "bear"). All three cases are still required in full.
        lookback_quarters: Historical quarters of macro data supplied.
        sector_universe: Sectors Claude must tilt.
        evidence: Payload from ``outlook_evidence.fetch_macro_evidence``.

    Returns:
        The user message text.
    """

    sections = [
        f"# Quarterly Outlook: {quarter}\n",
        (
            f"Produce the quarterly asset-allocation outlook for {quarter} using the "
            "tools provided. The requesting portfolio team wants the "
            f"**{macro_scenario.strip().lower() or 'base'}** case headlined in the "
            "executive framing, but you must still construct and record all three "
            "scenarios in full -- headlining one case is a presentation choice, not "
            "a license to skip the others.\n"
        ),
        (
            "## Sector universe (tilt every one of these, exactly as spelled here)\n\n"
            + "\n".join(f"- {sector}" for sector in sector_universe)
            + "\n"
        ),
        _render_section(
            f"Macro history (last {lookback_quarters} quarters)",
            evidence.get("macro_history", []),
        ),
        _render_section("Macro forward estimate", evidence.get("macro_forward_estimate", {})),
        _render_section("Economic indicators", evidence.get("economic_indicators", {})),
        _render_section("Sector performance and valuation data", evidence.get("sector_data", {})),
        _render_section("Rates and FX", evidence.get("rates_fx", {})),
        _render_section("Tail-risk headline evidence", evidence.get("tail_risk_evidence", [])),
        _render_section(
            "Macro calendar evidence for this quarter (ground your catalyst calendar in these)",
            evidence.get("catalyst_calendar_evidence", []),
        ),
        (
            "## Work order\n\n"
            "1. Call `record_macro_scenario` once for Bull, once for Base, once for "
            "Bear. Probability weights must sum to ~1.0 (approximately 0.60/0.25/0.15 "
            "Base/Bull/Bear, adjusted to the evidence).\n"
            "2. Call `record_sector_tilt` for every sector listed above, for at "
            "least the Base scenario (ideally for all three).\n"
            "3. Call `record_relative_value_view` three times: Growth vs Value, "
            "Quality Premium, and Bonds vs Equities.\n"
            "4. Call `record_catalyst` at least three times with real dates inside "
            f"{quarter}.\n"
            "5. Call `flag_tail_risk` at least three times.\n\n"
            "Stop calling tools when the analysis is complete."
        ),
    ]
    return "\n".join(sections)
