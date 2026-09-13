"""``run_quarterly_outlook``: macro evidence in, one Claude conversation, a
rendered Quarterly Outlook and a result dict out.

Unlike the initiation-of-coverage orchestrator (``orchestrator.AnalystAgent``),
this report type has **no persistent workspace**. There is no ledger, no
validator, and nothing written to disk unless the caller chooses to write the
returned ``outlook_markdown`` somewhere. This module does not import
``workspace_adapter`` at all.

Pipeline:

1. ``outlook_evidence.fetch_macro_evidence`` returns deterministic mock macro,
   rates, and sector evidence.
2. ``outlook_prompts.build_outlook_user_prompt`` turns that evidence into a
   work order.
3. ``agent_common.run_tool_loop`` drives one Claude tool-use conversation
   against ``outlook_prompts.TOOL_DEFINITIONS_OUTLOOK`` and collects every
   tool call.
4. This module applies those tool calls into an in-memory result (no
   persistence), validates the coverage minimums the spec requires
   (scenario probabilities summing to ~100%, every sector tilted for at least
   the Base case, >=3 tail risks, >=3 catalysts), and marks the run
   ``"partial"`` with explanatory notes rather than silently padding or
   rejecting the whole run.
5. ``outlook_render.render_outlook_markdown`` renders the eight-section report
   from exactly what was collected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import agent_common
import outlook_evidence
import outlook_prompts
from agent_common import AgentRunError, ToolResult
from outlook_render import (
    CatalystRecord,
    MacroScenarioRecord,
    RelativeValueRecord,
    SectorTiltRecord,
    TILT_DISPLAY_LABELS,
    TailRiskRecord,
    render_outlook_markdown,
)

#: Valid values for the ``macro_scenario`` headline-case parameter.
_VALID_HEADLINE_SCENARIOS = ("bull", "base", "bear")

#: Absolute tolerance on the three scenario probability weights summing to 1.0
#: (i.e. a 1-percentage-point tolerance, since weights are expressed on a
#: 0-1 scale). A run outside this tolerance is marked ``"partial"`` with a
#: note rather than silently renormalized or rejected outright.
PROBABILITY_SUM_TOLERANCE = 0.01

#: Minimum count thresholds the spec's acceptance criteria require.
MINIMUM_TAIL_RISKS = 3
MINIMUM_CATALYSTS = 3
MINIMUM_RELATIVE_VALUE_VIEWS = 3


class OutlookAgentError(AgentRunError):
    """Raised when a quarterly outlook run cannot complete."""


@dataclass
class _CollectedOutlook:
    """Tool calls sorted into typed records, plus everything dropped or missing."""

    macro_scenarios: Dict[str, MacroScenarioRecord] = field(default_factory=dict)
    sector_tilts: List[SectorTiltRecord] = field(default_factory=list)
    relative_value_views: List[RelativeValueRecord] = field(default_factory=list)
    catalysts: List[CatalystRecord] = field(default_factory=list)
    tail_risks: List[TailRiskRecord] = field(default_factory=list)
    unknown_tools: List[str] = field(default_factory=list)
    invalid_sector_names: List[str] = field(default_factory=list)
    duplicate_scenarios: List[str] = field(default_factory=list)
    tool_call_counts: Dict[str, int] = field(default_factory=dict)


def _resolve_sector_name(raw_sector: str, sector_universe: List[str]) -> Optional[str]:
    """Match a recorded sector name back to the canonical spelling, or None.

    Tries an exact match first, then a case/whitespace-insensitive match. A
    sector name Claude invents that matches nothing in ``sector_universe`` is
    not persisted -- the caller drops it and records the miss, the same
    pattern ``workspace_adapter.py`` uses for an unresolvable source id.
    """

    if raw_sector in sector_universe:
        return raw_sector
    normalized = raw_sector.strip().lower()
    for candidate in sector_universe:
        if candidate.strip().lower() == normalized:
            return candidate
    return None


def _collect_tool_calls(
    tool_calls: List[ToolResult], sector_universe: List[str]
) -> _CollectedOutlook:
    """Sort every collected tool call into typed records.

    Nothing is written anywhere here -- this is the deterministic, in-memory
    equivalent of ``workspace_adapter.update_workspace_from_claude`` for a
    report type that has no workspace to write into.
    """

    collected = _CollectedOutlook()

    for call in tool_calls:
        collected.tool_call_counts[call.name] = collected.tool_call_counts.get(call.name, 0) + 1
        payload = call.input or {}

        if call.name == "record_macro_scenario":
            name = str(payload.get("name", "")).strip()
            if name in collected.macro_scenarios:
                collected.duplicate_scenarios.append(name)
            collected.macro_scenarios[name] = MacroScenarioRecord(
                name=name,
                probability_weight=float(payload.get("probability_weight", 0.0)),
                gdp_growth_pct=float(payload.get("gdp_growth_pct", 0.0)),
                inflation_pct=float(payload.get("inflation_pct", 0.0)),
                fed_funds_rate_pct=float(payload.get("fed_funds_rate_pct", 0.0)),
                ten_year_yield_pct=float(payload.get("ten_year_yield_pct", 0.0)),
                eps_growth_pct=float(payload.get("eps_growth_pct", 0.0)),
                trigger_or_narrative=str(payload.get("trigger_or_narrative", "")),
                winners=[str(item) for item in (payload.get("winners") or [])],
                losers=[str(item) for item in (payload.get("losers") or [])],
            )
        elif call.name == "record_sector_tilt":
            raw_sector = str(payload.get("sector", "")).strip()
            resolved = _resolve_sector_name(raw_sector, sector_universe)
            if resolved is None:
                collected.invalid_sector_names.append(raw_sector)
                continue
            collected.sector_tilts.append(
                SectorTiltRecord(
                    sector=resolved,
                    scenario=str(payload.get("scenario", "")).strip(),
                    earnings_growth_pct=float(payload.get("earnings_growth_pct", 0.0)),
                    pe_ratio=float(payload.get("pe_ratio", 0.0)),
                    tilt=str(payload.get("tilt", "")).strip().lower(),
                    rationale=str(payload.get("rationale", "")),
                )
            )
        elif call.name == "record_relative_value_view":
            collected.relative_value_views.append(
                RelativeValueRecord(
                    pair_name=str(payload.get("pair_name", "")),
                    metric_a_label=str(payload.get("metric_a_label", "")),
                    metric_a_value=str(payload.get("metric_a_value", "")),
                    metric_b_label=str(payload.get("metric_b_label", "")),
                    metric_b_value=str(payload.get("metric_b_value", "")),
                    verdict=str(payload.get("verdict", "")),
                    rationale=str(payload.get("rationale", "")),
                )
            )
        elif call.name == "record_catalyst":
            collected.catalysts.append(
                CatalystRecord(
                    name=str(payload.get("name", "")),
                    date=str(payload.get("date", "")),
                    impact=str(payload.get("impact", "")),
                )
            )
        elif call.name == "flag_tail_risk":
            collected.tail_risks.append(
                TailRiskRecord(
                    description=str(payload.get("description", "")),
                    category=str(payload.get("category", "")),
                )
            )
        else:
            collected.unknown_tools.append(call.name)

    return collected


def _map_sector_tilts_to_display(
    sector_tilts: List[SectorTiltRecord], sector_universe: List[str]
) -> Dict[str, str]:
    """Derive the top-level ``sector_tilts`` display dict from Base-case calls.

    Per the spec, this is a fixed display convention
    (``overweight -> "+2%"``, ``neutral -> "0%"``, ``underweight -> "-2%"``)
    standing in for a real portfolio-optimizer weight -- not a derived
    number. Only sectors with a recorded Base-case tilt appear; a sector
    with no Base-case call is left out rather than defaulted to "0%", so a
    caller cannot mistake an omission for a deliberate neutral call.
    """

    base_tilt_by_sector = {
        record.sector: record.tilt for record in sector_tilts if record.scenario == "Base"
    }
    display: Dict[str, str] = {}
    for sector in sector_universe:
        tilt = base_tilt_by_sector.get(sector)
        if tilt is None:
            continue
        display[sector] = TILT_DISPLAY_LABELS.get(tilt, "0%")
    return display


def _cap_evidence_for_prompt(
    evidence: Dict[str, Any], max_evidence_sources: int
) -> Dict[str, Any]:
    """Apply ``max_evidence_sources`` to the prompt's evidence payload.

    This report type has no discrete "sources" list the way the initiation of
    coverage does; ``max_evidence_sources`` instead caps the two evidence
    collections that are not otherwise mandated by the report -- historical
    macro quarters and supplementary tail-risk headlines -- while never
    truncating the full sector universe or the catalyst-calendar grounding
    evidence, since those directly gate the report's acceptance minimums
    (every sector tilted, >=3 catalysts). The tail-risk floor of 3 keeps the
    >=3 tail-risk requirement satisfiable even at a very small cap.
    """

    if max_evidence_sources is None or max_evidence_sources <= 0:
        return evidence
    capped = dict(evidence)
    history = evidence.get("macro_history", []) or []
    if len(history) > max_evidence_sources:
        capped["macro_history"] = history[-max_evidence_sources:]
    tail_risks = evidence.get("tail_risk_evidence", []) or []
    keep = max(MINIMUM_TAIL_RISKS, min(len(tail_risks), max_evidence_sources))
    capped["tail_risk_evidence"] = tail_risks[:keep]
    return capped


def run_quarterly_outlook(
    quarter: str,
    macro_scenario: str = "base",
    lookback_quarters: int = 4,
    sector_universe: Optional[List[str]] = None,
    max_evidence_sources: int = 20,
    anthropic_api_key: Optional[str] = None,
    model: str = agent_common.DEFAULT_MODEL,
    client: Any = None,
    max_turns: int = agent_common.DEFAULT_MAX_TURNS,
) -> Dict[str, Any]:
    """Produce a standalone Quarterly Outlook asset-allocation report.

    No workspace is read or written. Evidence is fetched, one Claude tool-use
    conversation is run, the resulting tool calls are validated and rendered,
    and the result is returned in memory.

    Args:
        quarter: Quarter label, e.g. ``"Q1 2025"``.
        macro_scenario: Which case ("bull", "base", or "bear", case
            insensitive) the caller wants headlined in the executive framing.
            All three cases are still constructed and recorded in full.
        lookback_quarters: Historical quarters of macro data to fetch.
        sector_universe: Sectors to tilt. Defaults to
            :data:`outlook_evidence.DEFAULT_SECTOR_UNIVERSE`.
        max_evidence_sources: Caps the historical-macro and supplementary
            tail-risk evidence shown to Claude (see
            :func:`_cap_evidence_for_prompt`); never truncates the sector
            universe or the catalyst-calendar grounding evidence.
        anthropic_api_key: API key for a live run. Ignored if ``client`` is
            supplied.
        model: Claude model id.
        client: A pre-built Anthropic client, or any object exposing
            ``messages.create``. Supplying one skips SDK construction
            entirely and is how the offline test suite runs with no network
            access and no ``anthropic`` import.
        max_turns: Maximum tool-use round trips before the run is cut short.

    Returns:
        A dict with ``outlook_markdown``, ``macro_scenario``, ``sector_tilts``,
        ``tail_risks``, ``catalyst_calendar``, and ``status``
        (``"success"``, ``"partial"``, or ``"failed"``). Additional
        diagnostic keys: ``quarter``, ``sector_universe``, ``tool_calls``
        (per-tool call counts), ``notes`` (why the run is ``"partial"`` or
        ``"failed"``), and ``probability_weight_sum``.

    Raises:
        ValueError: If ``quarter`` is malformed or ``macro_scenario`` is not
            one of "bull", "base", or "bear".
        OutlookAgentError: If the model returns no tool calls at all.
    """

    normalized_scenario = (macro_scenario or "").strip().lower()
    if normalized_scenario not in _VALID_HEADLINE_SCENARIOS:
        raise ValueError(
            f"macro_scenario must be one of {_VALID_HEADLINE_SCENARIOS!r}, got {macro_scenario!r}"
        )

    sectors = list(sector_universe) if sector_universe else list(outlook_evidence.DEFAULT_SECTOR_UNIVERSE)

    evidence = outlook_evidence.fetch_macro_evidence(
        quarter=quarter, lookback_quarters=lookback_quarters, sector_universe=sectors
    )
    normalized_quarter = evidence["quarter"]

    prompt_evidence = _cap_evidence_for_prompt(evidence, max_evidence_sources)
    user_prompt = outlook_prompts.build_outlook_user_prompt(
        quarter=normalized_quarter,
        macro_scenario=normalized_scenario,
        lookback_quarters=lookback_quarters,
        sector_universe=sectors,
        evidence=prompt_evidence,
    )

    resolved_client = agent_common.build_client(anthropic_api_key, client)
    tool_calls = agent_common.run_tool_loop(
        client=resolved_client,
        model=model,
        system_prompt=outlook_prompts.SYSTEM_PROMPT_OUTLOOK,
        tool_definitions=outlook_prompts.TOOL_DEFINITIONS_OUTLOOK,
        user_prompt=user_prompt,
        max_turns=max_turns,
        max_tokens=agent_common.DEFAULT_MAX_TOKENS,
    )
    if not tool_calls:
        raise OutlookAgentError(
            "the model returned no tool calls; no quarterly outlook was produced"
        )

    collected = _collect_tool_calls(tool_calls, sectors)

    notes: List[str] = []
    if collected.unknown_tools:
        notes.append(
            "ignored unknown tool calls: " + ", ".join(sorted(set(collected.unknown_tools)))
        )
    if collected.invalid_sector_names:
        notes.append(
            "dropped sector tilts for names outside the requested sector universe: "
            + ", ".join(sorted(set(collected.invalid_sector_names)))
        )
    if collected.duplicate_scenarios:
        notes.append(
            "duplicate scenario recordings overwrote an earlier call for: "
            + ", ".join(sorted(set(collected.duplicate_scenarios)))
        )

    scenario_count = len(collected.macro_scenarios)
    if scenario_count < 3:
        notes.append(f"only {scenario_count} of 3 macro scenarios recorded")

    probability_sum: Optional[float] = None
    if collected.macro_scenarios:
        probability_sum = sum(
            record.probability_weight for record in collected.macro_scenarios.values()
        )
        if abs(probability_sum - 1.0) > PROBABILITY_SUM_TOLERANCE:
            notes.append(
                f"scenario probability weights sum to {probability_sum:.3f}, not 1.00 "
                f"(tolerance +/-{PROBABILITY_SUM_TOLERANCE})"
            )

    base_tilt_sectors = {
        record.sector for record in collected.sector_tilts if record.scenario == "Base"
    }
    missing_base_sectors = [sector for sector in sectors if sector not in base_tilt_sectors]
    if missing_base_sectors:
        notes.append(
            f"{len(missing_base_sectors)} of {len(sectors)} sectors have no recorded Base-case "
            "tilt: " + ", ".join(missing_base_sectors)
        )

    if len(collected.tail_risks) < MINIMUM_TAIL_RISKS:
        notes.append(
            f"only {len(collected.tail_risks)} tail risk(s) recorded, expected at least "
            f"{MINIMUM_TAIL_RISKS}"
        )
    if len(collected.catalysts) < MINIMUM_CATALYSTS:
        notes.append(
            f"only {len(collected.catalysts)} catalyst(s) recorded, expected at least "
            f"{MINIMUM_CATALYSTS}"
        )
    if len(collected.relative_value_views) < MINIMUM_RELATIVE_VALUE_VIEWS:
        notes.append(
            f"only {len(collected.relative_value_views)} relative-value view(s) recorded, "
            f"expected at least {MINIMUM_RELATIVE_VALUE_VIEWS}"
        )

    if not collected.macro_scenarios:
        status = "failed"
    elif notes:
        status = "partial"
    else:
        status = "success"

    sector_tilts_display = _map_sector_tilts_to_display(collected.sector_tilts, sectors)
    tail_risks_list = [record.description for record in collected.tail_risks]
    catalyst_calendar = [
        {"date": record.date, "catalyst": record.name, "impact": record.impact}
        for record in sorted(collected.catalysts, key=lambda record: record.date)
    ]

    outlook_markdown = render_outlook_markdown(
        quarter=normalized_quarter,
        macro_scenario_requested=normalized_scenario,
        macro_scenarios=list(collected.macro_scenarios.values()),
        sector_tilts=collected.sector_tilts,
        relative_value_views=collected.relative_value_views,
        catalysts=collected.catalysts,
        tail_risks=collected.tail_risks,
        sector_universe=sectors,
        evidence=evidence,
        notes=notes,
        status=status,
    )

    return {
        "outlook_markdown": outlook_markdown,
        "macro_scenario": normalized_scenario,
        "sector_tilts": sector_tilts_display,
        "tail_risks": tail_risks_list,
        "catalyst_calendar": catalyst_calendar,
        "status": status,
        "quarter": normalized_quarter,
        "sector_universe": sectors,
        "tool_calls": dict(collected.tool_call_counts),
        "notes": notes,
        "probability_weight_sum": probability_sum,
    }
