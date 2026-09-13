"""Bridge between Claude tool calls and a sector-primer workspace.

Mirrors ``workspace_adapter.py``'s design for the company workspace: sources
are applied first so later records can cite them regardless of the order
Claude emitted the calls in; a reference to an unknown source id is dropped
and reported rather than raised; an unrecognized tool name is reported rather
than raised. Exceptions from malformed payloads are not caught -- the caller
decides how to recover.

This module owns every write into sector workspace state that originates from
Claude's tool calls. Facts ingested directly from evidence (structural
drivers, cyclicality, macro lens) are written by ``sector_report.py`` before
the tool-use conversation runs, exactly as the company orchestrator ingests
``macro_context`` directly rather than routing it through a tool call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from agent_common import ToolResult
from sector_workspace import SectorWorkspace, _clean_text


@dataclass
class SectorAdapterReport:
    """What a batch of tool calls actually changed in a sector workspace."""

    applied: Dict[str, int] = field(default_factory=dict)
    source_ids: List[str] = field(default_factory=list)
    ledger_ids: List[str] = field(default_factory=list)
    dropped_source_links: List[str] = field(default_factory=list)
    unknown_tools: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when every tool call mapped into state without normalization."""

        return not self.dropped_source_links and not self.unknown_tools


def _resolve_source_ids(
    workspace: SectorWorkspace,
    requested: Any,
    report: SectorAdapterReport,
    context: str,
) -> List[str]:
    """Keep only source ids that exist in the registry, recording any dropped."""

    if not isinstance(requested, (list, tuple)):
        return []
    known = set(workspace.known_source_ids)
    resolved: List[str] = []
    for identifier in requested:
        text = _clean_text(identifier)
        if text in known:
            resolved.append(text)
        elif text:
            report.dropped_source_links.append(f"{context}: {text}")
    return resolved


def _apply_record_source(workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport) -> None:
    source_id = workspace.add_source(
        title=payload.get("title", ""),
        url=payload.get("url", ""),
        date=payload.get("date"),
        extract=payload.get("extract"),
    )
    report.source_ids.append(source_id)


def _apply_record_sector_overview(
    workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport
) -> None:
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, "sector overview")
    growth_drivers = [str(item) for item in (payload.get("growth_drivers") or []) if str(item).strip()]
    tam_size = _clean_text(payload.get("tam_size"), "not recorded")
    forward_cagr_pct = payload.get("forward_cagr_pct")

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="sector_overview",
            statement=(
                f"Sector TAM of {tam_size} with a {forward_cagr_pct}% forward CAGR, driven by "
                f"{'; '.join(growth_drivers) if growth_drivers else 'unspecified drivers'}."
            ),
            source_ids=source_ids,
            confidence="medium",
            tam_size=tam_size,
            forward_cagr_pct=forward_cagr_pct,
            growth_drivers=growth_drivers,
            capacity_cycle_note=_clean_text(payload.get("capacity_cycle_note")) or None,
        )
    )
    workspace.add_sector_metric_row(
        metric="Total addressable market",
        value=tam_size,
        unit="currency, as text",
        status="estimated",
        definition="Sector-wide total addressable market as sized in the recorded overview.",
        source_ids=source_ids,
    )
    workspace.add_sector_metric_row(
        metric="Forward revenue CAGR",
        value=forward_cagr_pct,
        unit="percent",
        status="estimated",
        definition="Forward-looking sector revenue compound annual growth rate.",
        source_ids=source_ids,
    )


def _apply_record_value_chain_segment(
    workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport
) -> None:
    segment_name = _clean_text(payload.get("segment_name"), "Unnamed segment")
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, f"segment {segment_name}")
    gross_margin_pct = payload.get("gross_margin_pct")
    operating_margin_pct = payload.get("operating_margin_pct")
    roic_estimate_pct = payload.get("roic_estimate_pct")

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="value_chain_segment",
            statement=(
                f"{segment_name} ({payload.get('position', 'unspecified')}): gross margin "
                f"{gross_margin_pct}%, operating margin {operating_margin_pct}%, ROIC "
                f"{roic_estimate_pct}%."
            ),
            source_ids=source_ids,
            confidence="medium",
            segment_name=segment_name,
            position=_clean_text(payload.get("position"), "unspecified"),
            gross_margin_pct=gross_margin_pct,
            operating_margin_pct=operating_margin_pct,
            roic_estimate_pct=roic_estimate_pct,
            moat=_clean_text(payload.get("moat")) or None,
            key_risk=_clean_text(payload.get("key_risk")) or None,
        )
    )
    workspace.add_sector_metric_row(
        metric=f"{segment_name} ROIC",
        subsector=segment_name,
        value=roic_estimate_pct,
        unit="percent",
        status="estimated",
        definition=f"Estimated return on invested capital for the {segment_name.lower()} value-chain segment.",
        source_ids=source_ids,
    )


def _apply_record_peer_benchmark(
    workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport
) -> None:
    ticker = _clean_text(payload.get("ticker"), "UNKNOWN")
    company = _clean_text(payload.get("company"), ticker)
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, f"peer {ticker}")
    revenue = payload.get("revenue")
    revenue_unit = _clean_text(payload.get("revenue_unit"), "unspecified unit")
    pe_ratio = payload.get("pe_ratio")
    ev_ebitda = payload.get("ev_ebitda")
    roic_pct = payload.get("roic_pct")
    eps_growth_pct = payload.get("eps_growth_pct")
    quality_tier = _clean_text(payload.get("quality_tier"), "unrated")
    eps_revision_trend = _clean_text(payload.get("eps_revision_trend"), "flat")

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="peer_benchmark",
            statement=(
                f"{company} ({ticker}): revenue {revenue} {revenue_unit}, EPS growth "
                f"{eps_growth_pct}%, P/E {pe_ratio}x, EV/EBITDA {ev_ebitda}x, ROIC {roic_pct}%, "
                f"{quality_tier}, EPS revisions trending {eps_revision_trend}."
            ),
            source_ids=source_ids,
            confidence="medium",
            ticker=ticker,
            company=company,
            revenue=revenue,
            revenue_unit=revenue_unit,
            eps_growth_pct=eps_growth_pct,
            pe_ratio=pe_ratio,
            ev_ebitda=ev_ebitda,
            roic_pct=roic_pct,
            quality_tier=quality_tier,
            eps_revision_trend=eps_revision_trend,
        )
    )
    workspace.add_company_comp_row(
        issuer=company,
        ticker=ticker,
        subsector="",
        basis="peer benchmark",
        revenue=revenue,
        roic=roic_pct,
        pe=pe_ratio,
        ev_ebitda=ev_ebitda,
        source_ids=source_ids,
        notes=f"quality_tier={quality_tier}; eps_revision_trend={eps_revision_trend}",
    )


def _apply_record_valuation(
    workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport
) -> None:
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, "sector valuation")
    verdict = _clean_text(payload.get("verdict"), "fair")
    growth_outlook = _clean_text(payload.get("growth_outlook"), "flat")
    risk_reward = _clean_text(payload.get("risk_reward")) or None
    sector_multiple = payload.get("sector_multiple")
    historical_avg_multiple = payload.get("historical_avg_multiple")

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="sector_valuation",
            statement=(
                f"Sector verdict: {verdict}; growth outlook: {growth_outlook}. Current multiple "
                f"{sector_multiple}x vs. historical average {historical_avg_multiple}x."
            ),
            source_ids=source_ids,
            confidence="medium",
            verdict=verdict,
            growth_outlook=growth_outlook,
            risk_reward=risk_reward,
            sector_multiple=sector_multiple,
            historical_avg_multiple=historical_avg_multiple,
            rationale=_clean_text(payload.get("rationale")) or None,
        )
    )
    workspace.add_sector_metric_row(
        metric="Sector multiple vs. historical average",
        value=sector_multiple,
        unit="x",
        status="estimated",
        definition="Current representative sector multiple, for comparison against its historical average.",
        numerator=str(sector_multiple) if sector_multiple is not None else "",
        denominator=str(historical_avg_multiple) if historical_avg_multiple is not None else "",
        source_ids=source_ids,
        notes=f"verdict={verdict}",
    )


def _apply_record_catalyst(workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport) -> None:
    name = _clean_text(payload.get("name"), "Unnamed catalyst")
    date_or_timeframe = _clean_text(payload.get("date_or_timeframe"), "unspecified")
    implication = _clean_text(payload.get("implication")) or None
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, f"catalyst {name}")

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="catalyst",
            statement=f"{name} ({date_or_timeframe}): {implication or 'implication not recorded'}.",
            source_ids=source_ids,
            confidence="medium",
            name=name,
            date_or_timeframe=date_or_timeframe,
            implication=implication,
        )
    )


def _apply_flag_analysis_gap(workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport) -> None:
    category = _clean_text(payload.get("category"), "general")
    description = _clean_text(payload.get("description"), "Unspecified gap.")
    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="research_gap",
            statement=f"[{category}] {description}",
            status="unresolved",
            confidence="medium",
            category=category,
        )
    )
    workspace.record_context_gap(f"[{category}] {description}")


def _apply_flag_contradiction(workspace: SectorWorkspace, payload: Dict[str, Any], report: SectorAdapterReport) -> None:
    field1 = _clean_text(payload.get("field1"), "signal A")
    field2 = _clean_text(payload.get("field2"), "signal B")
    description = _clean_text(payload.get("description"), "Conflicting evidence.")
    workspace.add_contradiction(summary=f"{field1} vs {field2}: {description}")


#: Tool name -> handler. Ordering of application is fixed by ``_APPLY_ORDER``.
_HANDLERS = {
    "record_source": _apply_record_source,
    "record_sector_overview": _apply_record_sector_overview,
    "record_value_chain_segment": _apply_record_value_chain_segment,
    "record_peer_benchmark": _apply_record_peer_benchmark,
    "record_valuation": _apply_record_valuation,
    "record_catalyst": _apply_record_catalyst,
    "flag_analysis_gap": _apply_flag_analysis_gap,
    "flag_contradiction": _apply_flag_contradiction,
}

#: Sources are written first so later records can reference their ids regardless
#: of the order in which Claude emitted the tool calls.
_APPLY_ORDER = (
    "record_source",
    "record_sector_overview",
    "record_value_chain_segment",
    "record_peer_benchmark",
    "record_valuation",
    "record_catalyst",
    "flag_analysis_gap",
    "flag_contradiction",
)


def update_sector_workspace_from_claude(
    workspace: SectorWorkspace,
    claude_tool_results: Sequence[ToolResult],
) -> SectorAdapterReport:
    """Translate Claude ``tool_use`` blocks into sector workspace writes.

    Tool calls are applied grouped by type in :data:`_APPLY_ORDER` (sources
    first), so a reference to a source recorded later in the same response
    still resolves. Within a group, Claude's original ordering is preserved.

    Exceptions from malformed payloads are not caught; the caller decides how
    to recover. References to unknown source ids are dropped rather than
    raised, and reported in :attr:`SectorAdapterReport.dropped_source_links`,
    so that one bad link cannot invalidate an otherwise complete workspace.

    Args:
        workspace: The workspace to mutate in memory. Call ``save()`` afterwards.
        claude_tool_results: Tool-use blocks in the order Claude emitted them.

    Returns:
        A :class:`SectorAdapterReport` describing what was written and normalized.
    """

    report = SectorAdapterReport()
    grouped: Dict[str, List[ToolResult]] = {name: [] for name in _APPLY_ORDER}
    for result in claude_tool_results:
        if result.name in grouped:
            grouped[result.name].append(result)
        else:
            report.unknown_tools.append(result.name)

    for name in _APPLY_ORDER:
        handler = _HANDLERS[name]
        for result in grouped[name]:
            payload = result.input if isinstance(result.input, dict) else {}
            handler(workspace, payload, report)
            report.applied[name] = report.applied.get(name, 0) + 1

    return report
