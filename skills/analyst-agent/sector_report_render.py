"""Render the sector report as a view of sector-primer workspace state.

Every figure in the rendered report is read back out of the workspace.
Nothing here invents, averages, or smooths a value: if the state does not
contain a section's inputs, the section says so rather than filling the space
with prose -- the same discipline ``report_generators.py`` applies to the
initiation of coverage.

Per-peer buy/hold/avoid recommendations in Section VI are *derived*, not
asserted: they combine the recorded sector-level verdict with each peer's
own recorded valuation and earnings-revision trend under one fixed,
documented rule (see :func:`_derive_recommendation`). The renderer never
originates a rating on its own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from render_helpers import format_number, markdown_table, source_label
from sector_workspace import SectorWorkspace


def _source_label(workspace: SectorWorkspace, source_ids: Sequence[str]) -> str:
    return source_label(workspace.known_source_ids, source_ids or [])


def _cover(workspace: SectorWorkspace) -> str:
    project = workspace.project
    context = workspace.context
    valuations = workspace.ledger_by_type("sector_valuation")
    verdict_line = "_No sector verdict is recorded in workspace state._"
    if valuations:
        latest = valuations[-1]
        verdict_line = (
            f"**Verdict: {str(latest.get('verdict', 'n/a')).upper()}** &middot; "
            f"Growth outlook: {latest.get('growth_outlook', 'n/a')} &middot; "
            f"Risk/reward: {latest.get('risk_reward') or 'not recorded'}"
        )
    rows = [
        ("Sector", workspace.sector_name or "n/a"),
        ("Geography", workspace.geography or "n/a"),
        ("Benchmark", project.get("benchmark") or "not recorded"),
        ("As-of date", context.get("as_of_date") or "not recorded"),
        ("Created", project.get("created_at") or "n/a"),
        ("Last updated", project.get("updated_at") or "n/a"),
    ]
    return (
        f"# {workspace.sector_name or 'Untitled Sector'} Sector Report\n\n"
        + markdown_table(["Field", "Value"], [[key, str(value)] for key, value in rows])
        + f"\n\n> {verdict_line}\n\n"
        "> Generated from persisted sector-primer workspace state. Every figure below "
        "reconciles to `state/` and `data/` in this workspace. Evidence in this build is "
        "deterministic mock data (see the methodology note at the end of this report) and "
        "must not be used for an investment decision.\n"
    )


def _sector_size_and_growth(workspace: SectorWorkspace) -> str:
    overviews = workspace.ledger_by_type("sector_overview")
    if not overviews:
        return (
            "## I. Sector Size and Growth\n\n"
            "_No sector overview is recorded in workspace state._\n"
        )
    latest = overviews[-1]
    drivers = latest.get("growth_drivers") or []
    lines = [
        "## I. Sector Size and Growth\n",
        f"Total addressable market: **{latest.get('tam_size', 'not recorded')}**. "
        f"Forward CAGR: **{format_number(latest.get('forward_cagr_pct'))}%**.\n",
    ]
    if drivers:
        lines.append("Growth is underpinned by:\n")
        for driver in drivers:
            lines.append(f"- {driver}")
        lines.append("")
    else:
        lines.append("_No growth drivers are recorded alongside this overview._\n")
    if latest.get("capacity_cycle_note"):
        lines.append(f"**Capacity cycle:** {latest['capacity_cycle_note']}\n")
    lines.append(f"_Source: {_source_label(workspace, latest.get('source_ids', []))}_\n")
    return "\n".join(lines) + "\n"


def _value_chain_economics(workspace: SectorWorkspace) -> str:
    segments = workspace.ledger_by_type("value_chain_segment")
    if not segments:
        return (
            "## II. Value-Chain Economics\n\n"
            "_No value-chain segments are recorded in workspace state._\n"
        )
    lines = ["## II. Value-Chain Economics\n"]
    if len(segments) < 3:
        lines.append(
            f"> **Coverage note:** only {len(segments)} value-chain segment(s) are recorded; "
            "a complete map covers at least three.\n"
        )
    table = markdown_table(
        ["Segment", "Position", "Gross margin", "Operating margin", "ROIC", "Key risk"],
        [
            [
                segment.get("segment_name", ""),
                segment.get("position", ""),
                f"{format_number(segment.get('gross_margin_pct'))}%",
                f"{format_number(segment.get('operating_margin_pct'))}%",
                f"{format_number(segment.get('roic_estimate_pct'))}%",
                segment.get("key_risk") or "not recorded",
            ]
            for segment in segments
        ],
    )
    lines.append(table)
    lines.append("")
    lines.append("**Where the moat sits, by segment:**\n")
    for segment in segments:
        moat = segment.get("moat") or "no moat rationale recorded"
        lines.append(f"- **{segment.get('segment_name', 'Segment')}:** {moat}")
    lines.append("")
    margins = [s.get("operating_margin_pct") for s in segments if isinstance(s.get("operating_margin_pct"), (int, float))]
    if margins:
        richest = max(segments, key=lambda s: s.get("operating_margin_pct", float("-inf")))
        lines.append(
            f"Operating margin is highest in **{richest.get('segment_name')}** at "
            f"{format_number(richest.get('operating_margin_pct'))}%, consistent with where the "
            "recorded moats concentrate pricing power in this chain.\n"
        )
    return "\n".join(lines) + "\n"


def _quality_tier_summary(peers: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    tiers: Dict[str, List[str]] = {}
    for peer in peers:
        tier = str(peer.get("quality_tier") or "unrated")
        tiers.setdefault(tier, []).append(str(peer.get("ticker") or peer.get("company") or "?"))
    return tiers


def _peer_comparative_table(workspace: SectorWorkspace) -> str:
    peers = workspace.ledger_by_type("peer_benchmark")
    if not peers:
        return (
            "## III. Peer Comparative Analysis\n\n"
            "_No peer benchmarks are recorded in workspace state._\n"
        )
    lines = ["## III. Peer Comparative Analysis\n"]
    if len(peers) < 5:
        lines.append(
            f"> **Coverage note:** only {len(peers)} peer(s) are recorded; a complete "
            "benchmark set covers at least five.\n"
        )
    table = markdown_table(
        ["Ticker", "Company", "Revenue", "EPS growth", "P/E", "EV/EBITDA", "ROIC", "Quality tier", "EPS revisions"],
        [
            [
                peer.get("ticker", ""),
                peer.get("company", ""),
                f"{format_number(peer.get('revenue'))} {peer.get('revenue_unit', '')}".strip(),
                f"{format_number(peer.get('eps_growth_pct'))}%",
                f"{format_number(peer.get('pe_ratio'))}x",
                f"{format_number(peer.get('ev_ebitda'))}x",
                f"{format_number(peer.get('roic_pct'))}%",
                peer.get("quality_tier", "unrated"),
                peer.get("eps_revision_trend", "flat"),
            ]
            for peer in peers
        ],
    )
    lines.append(table)
    lines.append("")

    tiers = _quality_tier_summary(peers)
    if tiers:
        lines.append("**Reading the table by quality tier:**\n")
        for tier, tickers in tiers.items():
            lines.append(f"- **{tier}:** {', '.join(tickers)}")
        lines.append("")

    pe_values = [
        (peer.get("ticker"), float(peer["pe_ratio"]))
        for peer in peers
        if isinstance(peer.get("pe_ratio"), (int, float))
    ]
    if len(pe_values) >= 2:
        richest = max(pe_values, key=lambda item: item[1])
        cheapest = min(pe_values, key=lambda item: item[1])
        spread_pct = (richest[1] / cheapest[1] - 1.0) * 100.0 if cheapest[1] else 0.0
        lines.append(
            f"The richest peer on P/E, **{richest[0]}** at {richest[1]:.1f}x, trades at a "
            f"{spread_pct:.1f}% premium to the cheapest, **{cheapest[0]}** at {cheapest[1]:.1f}x. "
            "That spread is a starting point for relative-value work within the peer set, not a "
            "conclusion about which peer is mispriced on its own.\n"
        )
    return "\n".join(lines) + "\n"


def _structural_drivers(workspace: SectorWorkspace) -> str:
    drivers = workspace.ledger_by_type("structural_driver")
    if not drivers:
        return (
            "## IV. Structural Drivers\n\n"
            "_No structural drivers are recorded in workspace state._\n"
        )
    tailwinds = [d for d in drivers if str(d.get("kind")) == "tailwind"]
    headwinds = [d for d in drivers if str(d.get("kind")) == "headwind"]
    lines = ["## IV. Structural Drivers\n"]
    lines.append("### Tailwinds\n")
    if tailwinds:
        for driver in tailwinds:
            lines.append(f"- {driver.get('statement')} _(source: {_source_label(workspace, driver.get('source_ids', []))})_")
    else:
        lines.append("_No tailwinds are recorded._")
    lines.append("")
    lines.append("### Headwinds\n")
    if headwinds:
        for driver in headwinds:
            lines.append(f"- {driver.get('statement')} _(source: {_source_label(workspace, driver.get('source_ids', []))})_")
    else:
        lines.append("_No headwinds are recorded._")
    return "\n".join(lines) + "\n"


def _cyclicality(workspace: SectorWorkspace) -> str:
    notes = workspace.ledger_by_type("cyclicality_note")
    if not notes:
        return (
            "## V. Cyclicality and Recession Sensitivity\n\n"
            "_No cyclicality analysis is recorded in workspace state._\n"
        )
    latest = notes[-1]
    lines = [
        "## V. Cyclicality and Recession Sensitivity\n",
        f"Recession sensitivity: **{latest.get('recession_sensitivity', 'not recorded')}**. "
        f"Operating leverage: **{latest.get('operating_leverage', 'not recorded')}**.\n",
    ]
    if latest.get("statement"):
        lines.append(f"{latest['statement']}\n")
    indicators = latest.get("leading_indicators") or []
    if len(indicators) < 2:
        lines.append(
            f"> **Coverage note:** only {len(indicators)} leading indicator(s) are recorded; "
            "a complete monitoring set tracks at least two.\n"
        )
    if indicators:
        lines.append("**Leading indicators to watch:**\n")
        for indicator in indicators:
            lines.append(f"- {indicator}")
        lines.append("")
    lines.append(f"_Source: {_source_label(workspace, latest.get('source_ids', []))}_\n")
    return "\n".join(lines) + "\n"


def _derive_recommendation(peer: Dict[str, Any], valuation: Dict[str, Any]) -> str:
    """Derive a buy/hold/avoid-style call for one peer.

    A fixed, documented rule -- never an asserted opinion. It combines:
    - the recorded sector-level verdict (attractive: +1, unattractive: -1, fair: 0),
    - whether the peer's own P/E sits below (+1) or above (-1) the recorded
      historical average multiple, and
    - whether the peer's recorded EPS-revision trend is up (+1), down (-1),
      or flat (0).

    The three signals are summed; a score of +2 or higher reads "buy", -2 or
    lower reads "avoid", and anything in between reads "hold". Every input to
    this score is a value already recorded in workspace state, so the call is
    reconstructable from the report itself.
    """

    score = 0
    verdict = str(valuation.get("verdict", "fair"))
    if verdict == "attractive":
        score += 1
    elif verdict == "unattractive":
        score -= 1

    historical_avg = valuation.get("historical_avg_multiple")
    pe_ratio = peer.get("pe_ratio")
    if isinstance(historical_avg, (int, float)) and isinstance(pe_ratio, (int, float)):
        if pe_ratio < historical_avg:
            score += 1
        elif pe_ratio > historical_avg:
            score -= 1

    trend = str(peer.get("eps_revision_trend", "flat"))
    if trend == "up":
        score += 1
    elif trend == "down":
        score -= 1

    if score >= 2:
        return "buy"
    if score <= -2:
        return "avoid"
    return "hold"


def _valuation_summary(workspace: SectorWorkspace) -> str:
    valuations = workspace.ledger_by_type("sector_valuation")
    peers = workspace.ledger_by_type("peer_benchmark")
    if not valuations:
        return (
            "## VI. Valuation Summary\n\n"
            "_No sector-level valuation verdict is recorded in workspace state._\n"
        )
    latest = valuations[-1]
    lines = [
        "## VI. Valuation Summary\n",
        f"**Verdict: {str(latest.get('verdict', 'n/a')).upper()}.** Sector trades at "
        f"{format_number(latest.get('sector_multiple'))}x versus a historical average of "
        f"{format_number(latest.get('historical_avg_multiple'))}x.\n",
    ]
    if latest.get("rationale"):
        lines.append(f"{latest['rationale']}\n")
    lines.append(f"_Source: {_source_label(workspace, latest.get('source_ids', []))}_\n")

    if peers:
        lines.append(
            "\n**Per-peer calls, derived from the recorded verdict and each peer's own valuation "
            "and EPS-revision trend (see methodology note at the end of this report):**\n"
        )
        rows = []
        for peer in peers:
            rows.append(
                [
                    peer.get("ticker", ""),
                    peer.get("company", ""),
                    f"{format_number(peer.get('pe_ratio'))}x",
                    peer.get("eps_revision_trend", "flat"),
                    _derive_recommendation(peer, latest).upper(),
                ]
            )
        lines.append(markdown_table(["Ticker", "Company", "P/E", "EPS revisions", "Derived call"], rows))
        lines.append("")
    else:
        lines.append("_No peer benchmarks are recorded, so no per-peer calls can be derived._\n")
    return "\n".join(lines) + "\n"


def _catalyst_calendar(workspace: SectorWorkspace) -> str:
    catalysts = workspace.ledger_by_type("catalyst")
    if not catalysts:
        return (
            "## VII. Sector Catalyst Calendar\n\n"
            "_No catalysts are recorded in workspace state._\n"
        )
    table = markdown_table(
        ["Date / timeframe", "Event", "Implication"],
        [
            [
                catalyst.get("date_or_timeframe", "unspecified"),
                catalyst.get("name", ""),
                catalyst.get("implication") or "not recorded",
            ]
            for catalyst in catalysts
        ],
    )
    return f"## VII. Sector Catalyst Calendar\n\n{table}\n"


def _risk_summary(workspace: SectorWorkspace) -> str:
    headwinds = [d for d in workspace.ledger_by_type("structural_driver") if str(d.get("kind")) == "headwind"]
    cyclicality_notes = workspace.ledger_by_type("cyclicality_note")
    macro_notes = workspace.ledger_by_type("macro_sensitivity")
    geopolitical_notes = workspace.ledger_by_type("geopolitical_risk")
    gaps = workspace.ledger_by_type("research_gap")
    contradictions = [record for record in workspace.contradictions if isinstance(record, dict)]

    lines = ["## VIII. Risk Summary\n"]

    lines.append("### Structural risks\n")
    if headwinds:
        for driver in headwinds:
            lines.append(f"- {driver.get('statement')}")
    else:
        lines.append("_No structural headwinds are recorded._")
    lines.append("")

    lines.append("### Cyclical risks\n")
    if cyclicality_notes:
        latest = cyclicality_notes[-1]
        lines.append(
            f"- Recession sensitivity is recorded as **{latest.get('recession_sensitivity', 'not recorded')}** "
            f"with **{latest.get('operating_leverage', 'not recorded')}** operating leverage."
        )
    else:
        lines.append("_No cyclicality analysis is recorded._")
    lines.append("")

    lines.append("### Macro and geopolitical risks\n")
    any_macro = False
    for record in macro_notes:
        if record.get("statement"):
            lines.append(f"- {record['statement']}")
            any_macro = True
    for record in geopolitical_notes:
        if record.get("statement"):
            lines.append(f"- {record['statement']}")
            any_macro = True
    if not any_macro:
        lines.append("_No macro or geopolitical sensitivity notes are recorded._")
    lines.append("")

    lines.append("### Evidence gaps\n")
    if gaps:
        for record in gaps:
            lines.append(f"- {record.get('statement')}")
    else:
        lines.append("_No evidence gaps are recorded._")
    lines.append("")

    lines.append("### Contradictions in the evidence\n")
    if contradictions:
        for record in contradictions:
            lines.append(f"- **{record.get('id')}** ({record.get('status')}): {record.get('summary')}")
        lines.append(
            "\n> These conflicts are recorded unresolved. They are not averaged away, and each "
            "remains open in `state/contradictions.json`.\n"
        )
    else:
        lines.append("_No contradictions are recorded._")

    return "\n".join(lines) + "\n"


def _methodology(workspace: SectorWorkspace) -> str:
    errors = workspace.validate()
    lines = [
        "## Methodology and Research Limitations\n",
        "This document is rendered entirely from persisted sector-primer workspace state; no "
        "figure above is asserted without a backing record. Evidence in this build is "
        "deterministic mock data produced by `sector_evidence.fetch_sector_evidence` -- figures "
        "are internally consistent but are **not** real market data and must not inform an "
        "investment decision.\n",
        "Per-peer calls in the valuation summary are derived by a fixed rule from the recorded "
        "sector verdict, each peer's own P/E versus the recorded historical average multiple, "
        "and each peer's recorded EPS-revision trend -- see `_derive_recommendation` in "
        "`sector_report_render.py` for the exact scoring. They are not a second, independently "
        "asserted opinion.\n",
        f"Workspace validation at render time: {'valid' if not errors else 'INVALID'}"
        f"{'' if not errors else ' — ' + '; '.join(errors[:5])}.",
    ]
    return "\n".join(lines) + "\n"


def _source_appendix(workspace: SectorWorkspace) -> str:
    if not workspace.sources:
        return "## Source Appendix\n\n_No sources are recorded._\n"
    table = markdown_table(
        ["ID", "Title", "Publisher", "Published", "Accessed", "Reference"],
        [
            [
                record.get("source_id", ""),
                record.get("title", ""),
                record.get("publisher", ""),
                record.get("publication_date") or "n/a",
                record.get("accessed_at", ""),
                record.get("url_or_ref", ""),
            ]
            for record in workspace.sources
        ],
    )
    return f"## Source Appendix\n\n{table}\n"


def render_sector_report_markdown(workspace: SectorWorkspace) -> str:
    """Render the sector report as Markdown from workspace state.

    Args:
        workspace: A loaded workspace whose state has already been written.

    Returns:
        A Markdown document. Sections without backing state say so explicitly
        rather than being omitted silently.
    """

    sections: List[str] = [
        _cover(workspace),
        _sector_size_and_growth(workspace),
        _value_chain_economics(workspace),
        _peer_comparative_table(workspace),
        _structural_drivers(workspace),
        _cyclicality(workspace),
        _valuation_summary(workspace),
        _catalyst_calendar(workspace),
        _risk_summary(workspace),
        _methodology(workspace),
        _source_appendix(workspace),
    ]
    return "\n---\n\n".join(section.rstrip() + "\n" for section in sections)
