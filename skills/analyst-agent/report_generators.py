"""Render publication views from validated workspace state.

Every figure in the rendered report is read back out of the workspace. Nothing
here invents, averages, or smooths a value: if the state does not contain a
section's inputs, the section says so rather than filling the space with prose.

Phase 1 renders the Initiation of Coverage. The workspace state populated by
this phase does not yet cover every section of the repository's full
initiation-of-coverage standard, so the rendered document declares which
sections are outstanding instead of presenting itself as a complete initiation.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Sequence

from workspace_adapter import SCENARIO_METHOD_PREFIX, ResearchWorkspace

#: Sections of the repository's full initiation standard that Phase 1 state
#: cannot yet support. Rendered into the report's limitations section so a
#: reader is never left to infer that an absent lens was judged immaterial.
PHASE_1_UNCOVERED_SECTIONS = (
    "Industry structure, value chain, and competitive landscape",
    "Asset portfolio and operating exposure",
    "Historical financial and operating analysis across multiple periods",
    "Explicit forecast build with period-by-period earnings drivers",
    "Reverse expectations analysis and valuation sensitivity grids",
)


def _format_number(value: Any, digits: int = 2) -> str:
    """Render a number for display, passing non-numeric values through as text."""

    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and abs(number) < 1e15:
        return f"{int(number):,}"
    return f"{number:,.{digits}f}"


def _format_price(value: Any) -> str:
    """Render a per-share value at fixed precision, so a column reads evenly."""

    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a GitHub-flavoured Markdown table."""

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _source_label(workspace: ResearchWorkspace, source_ids: Sequence[str]) -> str:
    known = {str(record.get("source_id")) for record in workspace.sources}
    resolved = [identifier for identifier in source_ids if identifier in known]
    return ", ".join(resolved) if resolved else "unsourced"


def _cover(workspace: ResearchWorkspace, analyst: str) -> str:
    context = workspace.context
    project = workspace.project
    rows = [
        ("Ticker", workspace.ticker or "n/a"),
        ("Exchange", context.get("exchange") or "n/a"),
        ("Industry", context.get("industry") or "not recorded in state"),
        ("Geography", context.get("geography") or "not recorded in state"),
        ("Reporting currency", workspace.base_currency),
        ("Rating convention", workspace.rating_convention or "n/a"),
        ("Research date", context.get("research_date") or dt.date.today().isoformat()),
        ("Last research update", project.get("last_research_update") or "n/a"),
        ("Analyst", analyst),
    ]
    return (
        f"# {workspace.company_name} ({workspace.ticker})\n\n"
        "## Initiation of Coverage\n\n"
        + _markdown_table(["Field", "Value"], [[key, str(value)] for key, value in rows])
        + "\n\n> Generated from persisted workspace state by the analyst-agent "
        "orchestrator. Every figure below reconciles to `state/` and `data/` in "
        "this workspace.\n"
    )


def _investment_thesis(workspace: ResearchWorkspace) -> str:
    conclusions = workspace.ledger_by_type("analytical_conclusion")
    assumptions = workspace.assumptions.get("assumptions", [])
    overrides = workspace.assumptions.get("scenario_overrides", {})

    if not conclusions and not assumptions:
        return (
            "## 1. Investment Thesis\n\n"
            "_No thesis is recorded in workspace state. The analysis step produced no "
            "assumptions or conclusions, so no thesis can be rendered._\n"
        )

    lines = ["## 1. Investment Thesis\n"]

    weighted = _weighted_price_target(overrides)
    drivers = [record for record in assumptions if record.get("rationale")][:3]
    if drivers:
        driver_text = "; ".join(
            f"{record.get('name')} at {record.get('base')}" for record in drivers
        )
        lines.append(
            f"The view rests on {len(assumptions)} recorded assumptions, led by {driver_text}. "
            "Each is carried in `state/assumptions.json` with its rationale and sources.\n"
        )
    if weighted is not None:
        lines.append(
            f"Probability-weighted 12-month price target: **{_format_number(weighted)} "
            f"{workspace.base_currency}**, derived from the recorded scenario weights "
            "(a derived figure, not a recorded one).\n"
        )
    for record in conclusions:
        lines.append(f"- {record.get('statement')}")
    return "\n".join(lines) + "\n"


def _weighted_price_target(overrides: Dict[str, Any]) -> Optional[float]:
    """Weight recorded scenario price targets; None when weights are unusable."""

    total_weight = 0.0
    total_value = 0.0
    for payload in overrides.values():
        if not isinstance(payload, dict):
            continue
        try:
            weight = float(payload.get("weight"))
            target = float(payload.get("price_target"))
        except (TypeError, ValueError):
            continue
        total_weight += weight
        total_value += weight * target
    if total_weight <= 0:
        return None
    return total_value / total_weight


def _company_overview(workspace: ResearchWorkspace) -> str:
    facts = workspace.ledger_by_type("observed_fact")
    if not facts:
        return (
            "## 2. Company Overview and Business Model\n\n"
            "_No company-context facts are recorded in workspace state._\n"
        )
    lines = ["## 2. Company Overview and Business Model\n"]
    for record in facts:
        source = _source_label(workspace, record.get("source_ids", []))
        lines.append(f"- {record.get('statement')} _(source: {source})_")
    return "\n".join(lines) + "\n"


def _valuation_summary(workspace: ResearchWorkspace) -> str:
    rows = [row for row in workspace.valuation_rows if row.get("method")]
    method_rows = [
        row for row in rows if not str(row.get("method", "")).startswith(SCENARIO_METHOD_PREFIX)
    ]
    scenario_rows = [
        row for row in rows if str(row.get("method", "")).startswith(SCENARIO_METHOD_PREFIX)
    ]
    if not rows:
        return (
            "## 3. Valuation Summary\n\n"
            "_No valuation is recorded in `data/valuation.csv`._\n"
        )

    methods = sorted({str(row.get("method", "")) for row in method_rows})
    lines = ["## 3. Valuation Summary\n"]
    if methods:
        lines.append(
            f"{len(methods)} valuation method(s) are recorded: {', '.join(methods)}.\n"
        )
        lines.append(
            _markdown_table(
                ["Method", "Band", "Implied price", "Inputs"],
                [
                    [
                        row.get("method", ""),
                        row.get("scenario", ""),
                        _format_price(row.get("implied_price")),
                        row.get("notes", "") or "-",
                    ]
                    for row in method_rows
                ],
            )
        )
        lines.append("")
    else:
        lines.append(
            "_No valuation method output is recorded; only scenario targets are present._\n"
        )

    if scenario_rows:
        lines.append("### Scenario price targets\n")
        lines.append(
            _markdown_table(
                ["Case", "Valuation basis", "Price target", "Weight"],
                [
                    [
                        row.get("scenario", ""),
                        str(row.get("method", ""))[len(SCENARIO_METHOD_PREFIX):],
                        _format_price(row.get("implied_price")),
                        str(row.get("notes", "")).replace("weight=", "") or "n/a",
                    ]
                    for row in scenario_rows
                ],
            )
        )
        lines.append("")

    lines.append(
        f"All values are per share in {workspace.base_currency} and reconcile to "
        "`data/valuation.csv`."
    )
    return "\n".join(lines) + "\n"


def _key_assumptions(workspace: ResearchWorkspace) -> str:
    assumptions = workspace.assumptions.get("assumptions", [])
    if not assumptions:
        return "## 4. Key Assumptions\n\n_No assumptions are recorded in workspace state._\n"
    table = _markdown_table(
        ["ID", "Assumption", "Base", "Units", "Rationale", "Sources"],
        [
            [
                record.get("id", ""),
                record.get("name", ""),
                str(record.get("base", "")),
                record.get("units", "") or "-",
                record.get("rationale") or "_no rationale recorded_",
                _source_label(workspace, record.get("source_ids", [])),
            ]
            for record in assumptions
        ],
    )
    unsourced = [
        record.get("name")
        for record in assumptions
        if not record.get("source_ids")
    ]
    note = ""
    if unsourced:
        note = (
            "\n> **Evidence quality:** the following assumptions carry no source link "
            f"and are judgemental: {', '.join(str(name) for name in unsourced)}.\n"
        )
    return f"## 4. Key Assumptions\n\n{table}\n{note}"


def _scenarios(workspace: ResearchWorkspace) -> str:
    overrides = workspace.assumptions.get("scenario_overrides", {})
    if not overrides:
        return (
            "## 5. Bull, Base, and Bear Cases\n\n"
            "_No scenarios are recorded in workspace state._\n"
        )

    order = {"bull": 0, "base": 1, "bear": 2}
    names = sorted(overrides, key=lambda name: order.get(str(name).lower(), 99))
    table = _markdown_table(
        ["Case", "Weight", "12m price target", "Valuation basis"],
        [
            [
                name,
                _format_number(overrides[name].get("weight")),
                _format_price(overrides[name].get("price_target")),
                str(overrides[name].get("valuation") or "-"),
            ]
            for name in names
            if isinstance(overrides[name], dict)
        ],
    )

    lines = ["## 5. Bull, Base, and Bear Cases\n", table, ""]
    for name in names:
        payload = overrides[name]
        if not isinstance(payload, dict):
            continue
        case_assumptions = payload.get("assumptions") or {}
        if not case_assumptions:
            continue
        lines.append(f"### {name} case drivers\n")
        for key, value in case_assumptions.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    total_weight = sum(
        float(payload.get("weight", 0) or 0)
        for payload in overrides.values()
        if isinstance(payload, dict)
    )
    if abs(total_weight - 1.0) > 0.01:
        lines.append(
            f"> **Caveat:** recorded scenario weights sum to {total_weight:.2f}, not 1.00. "
            "The probability-weighted target is normalized by the recorded weights.\n"
        )
    return "\n".join(lines) + "\n"


def _risks_and_catalysts(workspace: ResearchWorkspace) -> str:
    catalysts = workspace.ledger_by_type("catalyst")
    gaps = workspace.ledger_by_type("research_gap")
    contradictions = [
        record
        for record in workspace.contradictions.get("contradictions", [])
        if isinstance(record, dict)
    ]

    lines = ["## 6. Catalysts, Risks, and Open Questions\n"]

    if catalysts:
        lines.append("### Catalysts\n")
        lines.append(
            _markdown_table(
                ["Catalyst", "Timeframe", "Direction", "Estimated impact"],
                [
                    [
                        record.get("metric") or record.get("statement", ""),
                        record.get("period") or "n/a",
                        str(record.get("notes", "")).replace("direction=", "") or "n/a",
                        f"{_format_number(record.get('value'))}%",
                    ]
                    for record in catalysts
                ],
            )
        )
        lines.append("")
    else:
        lines.append("_No catalysts are recorded in workspace state._\n")

    lines.append("### Risks and downside drivers\n")
    bear = workspace.assumptions.get("scenario_overrides", {}).get("Bear")
    downside = [
        record
        for record in catalysts
        if "downside" in str(record.get("notes", "")).lower()
    ]
    if isinstance(bear, dict) and bear.get("assumptions"):
        lines.append(
            "The bear case is the workspace's structured statement of downside risk. "
            "It assumes:\n"
        )
        for key, value in bear["assumptions"].items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    for record in downside:
        lines.append(f"- {record.get('statement')}")
    if not isinstance(bear, dict) and not downside:
        lines.append(
            "_No structured downside drivers are recorded. Phase 1 does not persist "
            "narrative risks as ledger records; see the limitations section._"
        )
    lines.append("")

    lines.append("### Contradictions in the evidence\n")
    if contradictions:
        for record in contradictions:
            lines.append(
                f"- **{record.get('id')}** ({record.get('status')}): {record.get('summary')}"
            )
        lines.append(
            "\n> These conflicts are recorded unresolved. They are not averaged away, "
            "and each remains open in `state/contradictions.json`.\n"
        )
    else:
        lines.append("_No contradictions are recorded._\n")

    lines.append("### Evidence gaps\n")
    if gaps:
        for record in gaps:
            lines.append(f"- {record.get('statement')}")
    else:
        lines.append("_No evidence gaps are recorded._")

    return "\n".join(lines) + "\n"


def _limitations(workspace: ResearchWorkspace) -> str:
    validation = workspace.validate()
    lines = [
        "## 7. Methodology and Research Limitations\n",
        "This document is a **Phase 1 initiation**: it is rendered from the subset of "
        "research state that the analyst-agent orchestrator persists today. It is not "
        "yet the full initiation-of-coverage product described in the repository "
        "research standard.\n",
        "Material analytical lenses **not** covered by current state:\n",
    ]
    for section in PHASE_1_UNCOVERED_SECTIONS:
        lines.append(f"- {section}")
    lines.append(
        "\nEvidence in this Phase 1 build is mock data produced by "
        "`data_sources.fetch_company_evidence`. Figures are internally consistent but "
        "are **not** real market data and must not be used for an investment decision.\n"
    )
    lines.append(
        f"Workspace validation at render time: "
        f"{'valid' if validation.valid else 'INVALID'}"
        f"{'' if validation.valid else ' — ' + '; '.join(validation.errors[:5])}."
    )
    if validation.warnings:
        lines.append(f"Validator warnings: {'; '.join(validation.warnings[:5])}.")
    return "\n".join(lines) + "\n"


def _appendix(workspace: ResearchWorkspace) -> str:
    if not workspace.sources:
        return "## 8. Source Appendix\n\n_No sources are recorded._\n"
    table = _markdown_table(
        ["ID", "Title", "Publisher", "Published", "Accessed", "Tier", "Reference"],
        [
            [
                record.get("source_id", ""),
                record.get("title", ""),
                record.get("publisher", ""),
                record.get("publication_date") or "n/a",
                record.get("accessed_at", ""),
                str(record.get("quality_tier", "")),
                record.get("url_or_ref", ""),
            ]
            for record in workspace.sources
        ],
    )
    return (
        "## 8. Source Appendix\n\n"
        f"{table}\n\n"
        "Quality tier 1 is a primary filing; tier 4 is unverified commentary.\n"
    )


def initiation_report_markdown(
    workspace: ResearchWorkspace,
    analyst: str = "analyst-agent orchestrator",
) -> str:
    """Render the initiation of coverage as Markdown from workspace state.

    Args:
        workspace: A loaded workspace whose state has already been written.
        analyst: Name credited on the cover.

    Returns:
        A Markdown document. Sections without backing state say so explicitly
        rather than being omitted silently.
    """

    sections: List[str] = [
        _cover(workspace, analyst),
        _investment_thesis(workspace),
        _company_overview(workspace),
        _valuation_summary(workspace),
        _key_assumptions(workspace),
        _scenarios(workspace),
        _risks_and_catalysts(workspace),
        _limitations(workspace),
        _appendix(workspace),
    ]
    return "\n---\n\n".join(section.rstrip() + "\n" for section in sections)
