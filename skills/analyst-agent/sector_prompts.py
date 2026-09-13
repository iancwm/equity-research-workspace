"""Claude system prompt, tool schemas, and user-prompt builder for sector reports.

Mirrors ``prompts.py``'s design for the initiation of coverage: the system
prompt is the contract that turns raw sector evidence into structured
workspace state, and the tool schemas sit alongside it because prompt and
schema are one contract.

Structural drivers, cyclicality, and the macro/geopolitical lens are ingested
directly from evidence by the orchestrator (see ``sector_report.py``), the
same way the company agent ingests ``macro_context`` straight into the
ledger -- they are supplied facts, not Claude's analytical output. The tool
vocabulary here covers only the analytical judgments that must come from
Claude: sizing the opportunity, mapping value-chain economics, benchmarking
peers, forming a valuation verdict, and flagging what remains uncertain.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT_SECTOR = """\
You are an institutional equity research analyst producing a sector report:
comprehensive peer benchmarking and sector dynamics for one industry.

Given sector evidence -- market sizing, a value-chain map, peer financials,
peer earnings-revision trends, structural drivers, cyclicality, and a macro
backdrop -- you will:
1. Size the opportunity and identify what drives its forward growth.
2. Map value-chain economics across at least three segments.
3. Benchmark at least five peers on revenue, EPS growth, P/E, EV/EBITDA, and ROIC.
4. Form a sector-level valuation verdict, growth outlook, and risk/reward view.
5. Record 3-5 sector catalysts with a timeframe and stated implication.
6. Flag every material data gap and every conflicting signal.
7. Record every finding through structured tool calls.

## Output format

Speak in tool calls, not prose. Do not narrate your reasoning in natural
language; let the structured state carry the analysis. Any text you emit is
treated as commentary and is not persisted as research state.

## Evidence handling

Treat all supplied evidence as unverified input. Where evidence conflicts or
is incomplete, call `flag_analysis_gap` or `flag_contradiction` instead of
guessing. Never invent a figure that is not derivable from the evidence.

## Required work

**Sources.** Call `record_source` for every source you rely on, before the
tool calls that depend on it. Later calls reference sources by the ids listed
in the evidence block.

**Sector overview.** Call `record_sector_overview` exactly once: the total
addressable market, the forward CAGR, at least two growth drivers, and a note
on where the sector sits in its capacity cycle.

**Value-chain economics.** Call `record_value_chain_segment` once per segment,
for at least three segments (typically upstream, core, and downstream).
Each call needs a margin profile, an ROIC estimate, the segment's competitive
moat, and its key risk.

**Peer benchmarking.** Call `record_peer_benchmark` once per peer, for every
peer in the evidence (at least five). Each call needs revenue, EPS growth,
P/E, EV/EBITDA, ROIC, a quality-tier label, and the peer's consensus
EPS-revision trend.

**Sector valuation.** Call `record_valuation` exactly once with a verdict
(attractive, fair, or unattractive), a growth outlook (accelerating, flat, or
decelerating), a risk/reward characterization, the current sector multiple,
the historical average multiple, and the rationale connecting them. This
determination is yours to make from the peer table and sector overview; the
report renders it verbatim rather than asserting its own view.

**Catalysts.** Record 3-5 sector-level catalysts with `record_catalyst`, each
with a date or timeframe and a stated implication for the sector view.

**Gaps and contradictions.** Flag every material gap and every conflicting
signal. Do not resolve a contradiction by averaging it away.

## Standards

- Institutional tone: no marketing language, no cheerleading.
- Skeptical: challenge sector narratives against the peer data.
- Transparent: the inputs you record must reconstruct the conclusions you claim.
- Conviction is not certainty: state uncertainty rather than smoothing over it.
"""


TOOL_DEFINITIONS_SECTOR: List[Dict[str, Any]] = [
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
        "name": "record_sector_overview",
        "description": (
            "Record the sector's size and forward growth profile. Call this exactly once."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "tam_size": {
                    "type": "string",
                    "description": "Total addressable market as text, e.g. '$78.4bn'.",
                },
                "forward_cagr_pct": {
                    "type": "number",
                    "description": "Forward revenue CAGR for the sector, in percent, e.g. 6.5 for 6.5%.",
                },
                "growth_drivers": {
                    "type": "array",
                    "description": "At least two structural drivers of forward growth.",
                    "items": {"type": "string"},
                },
                "capacity_cycle_note": {
                    "type": "string",
                    "description": "Where the sector sits in its capacity cycle and why it matters.",
                },
                "source_ids": {
                    "type": "array",
                    "description": "Source ids supporting this overview.",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "tam_size",
                "forward_cagr_pct",
                "growth_drivers",
                "capacity_cycle_note",
                "source_ids",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_value_chain_segment",
        "description": (
            "Record one value-chain segment's economics. Call once per segment; use at "
            "least three segments across the chain."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "segment_name": {"type": "string", "description": "Segment name."},
                "position": {
                    "type": "string",
                    "description": "Where this segment sits in the value chain.",
                    "enum": ["upstream", "core", "downstream"],
                },
                "gross_margin_pct": {"type": "number", "description": "Gross margin, in percent."},
                "operating_margin_pct": {"type": "number", "description": "Operating margin, in percent."},
                "roic_estimate_pct": {"type": "number", "description": "Estimated ROIC, in percent."},
                "moat": {"type": "string", "description": "The segment's competitive moat."},
                "key_risk": {"type": "string", "description": "The segment's key risk."},
                "source_ids": {
                    "type": "array",
                    "description": "Source ids supporting this segment's figures.",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "segment_name",
                "position",
                "gross_margin_pct",
                "operating_margin_pct",
                "roic_estimate_pct",
                "moat",
                "key_risk",
                "source_ids",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_peer_benchmark",
        "description": (
            "Record one peer's comparative financials. Call once per peer, for every peer "
            "in the evidence (at least five)."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Peer ticker."},
                "company": {"type": "string", "description": "Peer company name."},
                "revenue": {"type": "number", "description": "Revenue in the evidence's reporting unit."},
                "revenue_unit": {"type": "string", "description": "Unit for revenue, e.g. 'USD m'."},
                "eps_growth_pct": {"type": "number", "description": "EPS growth, in percent."},
                "pe_ratio": {"type": "number", "description": "Price/earnings ratio."},
                "ev_ebitda": {"type": "number", "description": "EV/EBITDA ratio."},
                "roic_pct": {"type": "number", "description": "ROIC, in percent."},
                "quality_tier": {
                    "type": "string",
                    "description": "Free-text quality label, e.g. 'Tier 1 - premium compounder'.",
                },
                "eps_revision_trend": {
                    "type": "string",
                    "description": "Consensus EPS-revision trend direction.",
                    "enum": ["up", "flat", "down"],
                },
                "source_ids": {
                    "type": "array",
                    "description": "Source ids supporting this peer's figures.",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "ticker",
                "company",
                "revenue",
                "revenue_unit",
                "eps_growth_pct",
                "pe_ratio",
                "ev_ebitda",
                "roic_pct",
                "quality_tier",
                "eps_revision_trend",
                "source_ids",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_valuation",
        "description": (
            "Record the sector-level valuation verdict. Call this exactly once. This is a "
            "sector-wide judgment, distinct from a single company's valuation."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "description": "Sector valuation verdict.",
                    "enum": ["attractive", "fair", "unattractive"],
                },
                "growth_outlook": {
                    "type": "string",
                    "description": "Direction of the sector's growth outlook.",
                    "enum": ["accelerating", "flat", "decelerating"],
                },
                "risk_reward": {
                    "type": "string",
                    "description": "One-sentence characterization of the sector's risk/reward.",
                },
                "sector_multiple": {
                    "type": "number",
                    "description": "Current representative sector multiple (e.g. median forward P/E).",
                },
                "historical_avg_multiple": {
                    "type": "number",
                    "description": "Historical average multiple for the same measure.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why the current multiple versus history supports the verdict.",
                },
                "source_ids": {
                    "type": "array",
                    "description": "Source ids supporting the valuation verdict.",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "verdict",
                "growth_outlook",
                "risk_reward",
                "sector_multiple",
                "historical_avg_multiple",
                "rationale",
                "source_ids",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_catalyst",
        "description": "Record one sector-level catalyst calendar entry.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Catalyst or event description."},
                "date_or_timeframe": {
                    "type": "string",
                    "description": "When it is expected, e.g. 2026-11-15 or Q2 next year.",
                },
                "implication": {
                    "type": "string",
                    "description": "What it would mean for the sector view if it occurs as expected.",
                },
                "source_ids": {
                    "type": "array",
                    "description": "Source ids supporting this catalyst.",
                    "items": {"type": "string"},
                },
            },
            "required": ["name", "date_or_timeframe", "implication", "source_ids"],
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
                    "description": "Gap category, e.g. Peer Coverage or Segment Data.",
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


def build_sector_user_prompt(
    sector_name: str,
    geography: str,
    evidence: Dict[str, Any],
    source_ids: Dict[str, str],
    look_forward_years: int = 3,
) -> str:
    """Build the user turn carrying sector evidence and the work order.

    Args:
        sector_name: e.g. ``"Semiconductors"``.
        geography: e.g. ``"Global"``.
        evidence: Payload from ``sector_evidence.fetch_sector_evidence``.
        source_ids: Map of source title to the id Claude should cite.
        look_forward_years: Forward window the analysis should reason over.

    Returns:
        The user message text.
    """

    catalogue = [{"source_id": identifier, "title": title} for title, identifier in source_ids.items()]
    peer_count = len(evidence.get("peers") or [])
    segment_count = len(evidence.get("value_chain") or [])

    sections = [
        f"# Sector report: {sector_name} ({geography})\n",
        (
            f"Produce a sector report over a {look_forward_years}-year forward window using the "
            "tools provided. Record every finding as a tool call.\n"
        ),
        _render_section("Sector overview evidence", evidence.get("sector_overview", {})),
        _render_section("Value-chain evidence", evidence.get("value_chain", [])),
        _render_section("Peer financials", evidence.get("peers", [])),
        _render_section("Structural drivers (already recorded as workspace facts)", evidence.get("structural_drivers", [])),
        _render_section("Cyclicality (already recorded as workspace facts)", evidence.get("cyclicality", {})),
        _render_section("Macro lens (already recorded as workspace facts)", evidence.get("macro_lens", {})),
        _render_section("Source catalogue (cite these ids)", catalogue),
        (
            "## Work order\n\n"
            "1. Call `record_source` for each source you rely on.\n"
            "2. Call `record_sector_overview` exactly once.\n"
            f"3. Call `record_value_chain_segment` once per segment ({segment_count} segments in evidence).\n"
            f"4. Call `record_peer_benchmark` once per peer ({peer_count} peers in evidence).\n"
            "5. Call `record_valuation` exactly once with the sector verdict, growth outlook, and "
            "risk/reward characterization.\n"
            "6. Record 3-5 catalysts with `record_catalyst`.\n"
            "7. Flag every material gap and contradiction.\n\n"
            "Note: structural drivers, cyclicality, and the macro/geopolitical lens are supplied "
            "facts already persisted directly into workspace state by the orchestrator -- they do "
            "not need a tool call; use them to inform your valuation rationale and catalysts.\n\n"
            "Stop calling tools when the analysis is complete."
        ),
    ]
    return "\n".join(sections)
