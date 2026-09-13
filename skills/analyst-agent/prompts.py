"""Claude system prompt, tool schemas, and user-prompt builders.

The system prompt is load-bearing: it is the contract that turns raw evidence
into structured workspace state. It lives here, apart from the orchestration
code, so it can be iterated and diffed on its own.

Tool schemas sit alongside it because the prompt and the schemas are one
contract — the prompt tells Claude to speak only in tool calls, and these
schemas define that vocabulary.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from agent_common import name_value_array_schema

SYSTEM_PROMPT = """\
You are an institutional equity research analyst producing an initiation of coverage.

Given company evidence, industry context, and a macro backdrop, you will:
1. Synthesize the evidence into a coherent investment thesis.
2. Develop a valuation using multiple methods.
3. Construct bull, base, and bear scenarios.
4. Identify key catalysts, data gaps, and contradictions.
5. Record every finding through structured tool calls.

## Output format

Speak in tool calls, not prose. Do not narrate your reasoning in natural
language; let the structured state carry the analysis. Any text you emit is
treated as commentary and is not persisted as research state.

## Evidence handling

Treat all supplied evidence as unverified input. Where evidence conflicts or is
incomplete, call `flag_analysis_gap` or `flag_contradiction` instead of guessing.
Never invent a figure that is not derivable from the evidence.

## Required work

**Sources.** Call `record_source` for every source you rely on, before the tool
calls that depend on it. Later calls reference sources by the ids listed in the
evidence block.

**Assumptions.** Record 5-8 critical assumptions with `record_assumption`:
revenue CAGR, margin trajectory, multiple expansion or compression, market share,
capital allocation. Every assumption needs a one-sentence rationale and at least
one source id.

**Valuation.** Use at least two methods with `record_valuation`:
- Multiples-based: peer median multiple, a target multiple justified by relative
  company quality, and the implied price.
- DCF or earnings power: terminal growth of 2.5-3% where free cash flow is
  visible, otherwise a multiple on terminal earnings.
Show the inputs that produce the output. Outputs are a low/base/high range.

**Scenarios.** Record exactly three cases with `record_scenario`, tied to
variance in the assumptions you recorded, not to sentiment:
- Base (weight 0.5): assumptions at mid-range.
- Bull (weight 0.25): revenue acceleration, margin expansion, or re-rating.
- Bear (weight 0.25): slower growth, margin pressure, or de-rating.
Each case needs an explicit 12-month price target.

**Catalysts.** Record 3-5 near-term (6-12 month) catalysts with
`record_catalyst`, each with a timeframe, a direction, and a magnitude estimate.

**Gaps and contradictions.** Flag every material gap and every conflicting
signal. A guidance figure that is inconsistent with historical performance is a
contradiction, not something to average away.

## Standards

- Institutional tone: no marketing language, no cheerleading.
- Skeptical: challenge management guidance against the historical record.
- Transparent: the inputs you record must reconstruct the output you claim.
- Conviction is not certainty: scenario weights carry the uncertainty.
"""


def _name_value_array(description: str) -> Dict[str, Any]:
    """Schema for a list of name/value pairs.

    Used instead of a free-form object because every tool here runs under
    ``strict`` schema validation, which needs fully specified shapes.
    """

    return name_value_array_schema(description)


#: Tool vocabulary handed to Claude. Every property is required so that strict
#: schema validation produces fully populated, directly persistable inputs.
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "record_source",
        "description": (
            "Record a source before citing any fact drawn from it. Call this first for "
            "every source you use."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Source title."},
                "url": {"type": "string", "description": "URL or reference identifier."},
                "date": {
                    "type": "string",
                    "description": "Publication date as YYYY-MM-DD, or an empty string if unknown.",
                },
                "extract": {
                    "type": "string",
                    "description": "The specific fact or passage relied upon.",
                },
            },
            "required": ["title", "url", "date", "extract"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_assumption",
        "description": (
            "Record one key driver underpinning the thesis. One assumption per call; "
            "every assumption needs a rationale and a source."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Assumption name, e.g. Revenue CAGR 5-Year Forward.",
                },
                "value": {
                    "type": "string",
                    "description": "Base-case value as text, e.g. 6% or 14.2x.",
                },
                "units": {
                    "type": "string",
                    "description": "Units, e.g. percent, x, USD. Empty string if unitless.",
                },
                "rationale": {
                    "type": "string",
                    "description": "One sentence explaining why this value, from the evidence.",
                },
                "source_ids": {
                    "type": "array",
                    "description": "Source ids from the evidence block supporting this assumption.",
                    "items": {"type": "string"},
                },
            },
            "required": ["name", "value", "units", "rationale", "source_ids"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_valuation",
        "description": (
            "Record one valuation method and its output range. Call once per method; "
            "use at least two methods."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "Method name, e.g. Peer Multiple (P/E) or DCF.",
                },
                "inputs": _name_value_array("Every input that produces the output range."),
                "output": {
                    "type": "object",
                    "description": "Implied per-share value range in the reporting currency.",
                    "properties": {
                        "low": {"type": "number"},
                        "base": {"type": "number"},
                        "high": {"type": "number"},
                    },
                    "required": ["low", "base", "high"],
                    "additionalProperties": False,
                },
            },
            "required": ["method", "inputs", "output"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_scenario",
        "description": (
            "Record one of the three cases. Each case must be tied to variance in the "
            "assumptions already recorded."
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
                "assumptions": _name_value_array(
                    "Assumption values specific to this case, keyed by assumption name."
                ),
                "valuation": {
                    "type": "string",
                    "description": "How the case is valued, e.g. DCF at 9.5% WACC, or 18x FY2 EPS.",
                },
                "price_target": {
                    "type": "number",
                    "description": "12-month price target in the reporting currency.",
                },
                "weight": {
                    "type": "number",
                    "description": "Probability weight: 0.5 Base, 0.25 Bull, 0.25 Bear.",
                },
            },
            "required": ["name", "assumptions", "valuation", "price_target", "weight"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_catalyst",
        "description": "Record one near-term event (6-12 months) that could move the stock.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Catalyst description."},
                "timeframe": {
                    "type": "string",
                    "description": "When it is expected, e.g. Q2 FY2026 or next 6 months.",
                },
                "direction": {
                    "type": "string",
                    "description": "Whether it helps or hurts the thesis.",
                    "enum": ["upside", "downside", "uncertain"],
                },
                "magnitude_estimate_pct": {
                    "type": "number",
                    "description": "Estimated share-price impact in percent.",
                },
            },
            "required": ["name", "timeframe", "direction", "magnitude_estimate_pct"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_analysis_gap",
        "description": (
            "Flag missing data or a methodological limit. Use this instead of guessing "
            "at a value you cannot support."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Gap category, e.g. Segment Detail or Growth Drivers.",
                },
                "description": {
                    "type": "string",
                    "description": "What is missing and why it matters to the conclusion.",
                },
            },
            "required": ["category", "description"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_contradiction",
        "description": "Flag two pieces of evidence that conflict. Do not resolve them by averaging.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "field1": {"type": "string", "description": "First conflicting signal."},
                "field2": {"type": "string", "description": "Second conflicting signal."},
                "description": {
                    "type": "string",
                    "description": "Why the two conflict and what it would take to resolve.",
                },
            },
            "required": ["field1", "field2", "description"],
            "additionalProperties": False,
        },
    },
]


def _render_section(title: str, payload: Any) -> str:
    return f"### {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=False, default=str)}\n```\n"


def build_user_prompt(
    ticker: str,
    company_name: str,
    evidence: Dict[str, Any],
    source_ids: Dict[str, str],
) -> str:
    """Build the user turn carrying evidence and the work order.

    Args:
        ticker: Exchange ticker.
        company_name: Display name.
        evidence: Payload from ``data_sources.fetch_company_evidence``.
        source_ids: Map of source title to the id Claude should cite.

    Returns:
        The user message text.
    """

    catalogue = [
        {"source_id": identifier, "title": title}
        for title, identifier in source_ids.items()
    ]

    sections = [
        f"# Initiation of coverage: {company_name} ({ticker})\n",
        (
            "Produce the initiation of coverage for this company using the tools "
            "provided. Record every finding as a tool call.\n"
        ),
        _render_section("Company overview", evidence.get("company_overview", {})),
        _render_section("Financial metrics", evidence.get("financial_metrics", {})),
        _render_section("Peer universe", evidence.get("peer_universe", [])),
        _render_section("Latest news and developments", evidence.get("latest_news", [])),
        _render_section("Macro context", evidence.get("macro_context", {})),
        _render_section("Source catalogue (cite these ids)", catalogue),
        (
            "## Work order\n\n"
            "1. Call `record_source` for each source you rely on.\n"
            "2. Record 5-8 assumptions, each with a rationale and source ids from the "
            "catalogue above.\n"
            "3. Record at least two valuation methods with their inputs and output ranges.\n"
            "4. Record the Bull, Base, and Bear cases with explicit price targets and weights.\n"
            "5. Record 3-5 catalysts.\n"
            "6. Flag every material gap and contradiction.\n\n"
            "Stop calling tools when the analysis is complete."
        ),
    ]
    return "\n".join(sections)
