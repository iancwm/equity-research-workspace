"""Render the earnings-update publication view from a run's computed context.

Mirrors ``report_generators.py``'s discipline: every figure in the rendered
note is read back out of ``run_context`` (itself built from workspace state
by ``earnings_update.py``), never invented or smoothed here. This module only
formats; it does not decide what changed or what the verdict is.

The report structure is short-form by design (tables and bullets, minimal
prose) so that it reliably stays under the 1000-word ceiling the report type
requires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from render_helpers import format_number, format_price, markdown_table

#: Verdict machine label -> human-readable heading.
VERDICT_LABELS = {
    "thesis_intact": "Thesis Intact",
    "thesis_at_risk": "Thesis At Risk",
    "thesis_broken": "Thesis Broken",
}


@dataclass
class AssumptionChange:
    """One row of the "Updated Assumptions" table."""

    name: str
    prior_value: str
    revised_value: str
    rationale: str


@dataclass
class ValuationChange:
    """One row of the "Valuation Impact" table (excluding the Base Case row)."""

    method: str
    prior_price: Optional[float]
    revised_price: Optional[float]


@dataclass
class EarningsRunContext:
    """Everything :func:`render_update_note_markdown` needs, precomputed.

    Built by ``earnings_update.EarningsUpdateAgent.earnings_update`` from the
    workspace's prior state and this run's tool calls, so the renderer never
    has to re-derive figures from the workspace itself.
    """

    ticker: str
    company_name: str
    earnings_date: str
    eps_actual: float
    eps_consensus: float
    eps_surprise_pct: Optional[float]
    revenue_actual: float
    revenue_consensus: float
    revenue_surprise_pct: Optional[float]
    guidance_change: Optional[str]
    verdict: str
    prior_base_price_target: Optional[float]
    revised_price_target: Optional[float]
    valuation_changed_pct: float
    assumption_changes: List[AssumptionChange] = field(default_factory=list)
    valuation_changes: List[ValuationChange] = field(default_factory=list)
    what_changed: List[str] = field(default_factory=list)
    what_didnt_change: List[str] = field(default_factory=list)
    catalysts_ahead: List[Dict[str, Any]] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    evidence_note: str = (
        "Evidence in this build is mock/deterministic data (Phase 2 will swap in real "
        "providers); figures are internally consistent but must not inform a live decision."
    )


def _surprise_text(surprise_pct: Optional[float]) -> str:
    if surprise_pct is None:
        return "n/a"
    sign = "+" if surprise_pct >= 0 else ""
    return f"{sign}{surprise_pct:.1f}%"


def _the_numbers(context: EarningsRunContext) -> str:
    table = markdown_table(
        ["Metric", "Actual", "Consensus", "Surprise"],
        [
            [
                "EPS",
                format_price(context.eps_actual),
                format_price(context.eps_consensus),
                _surprise_text(context.eps_surprise_pct),
            ],
            [
                "Revenue",
                format_number(context.revenue_actual),
                format_number(context.revenue_consensus),
                _surprise_text(context.revenue_surprise_pct),
            ],
        ],
    )
    guidance = context.guidance_change or "not addressed"
    return f"### The Numbers\n\n{table}\n\n**Guidance:** {guidance}.\n"


def _updated_assumptions(context: EarningsRunContext) -> str:
    if not context.assumption_changes:
        return (
            "### Updated Assumptions\n\n"
            "_No assumptions were revised this quarter; results and guidance were "
            "consistent with the prior thesis._\n"
        )
    table = markdown_table(
        ["Assumption", "Prior", "Revised", "Rationale"],
        [
            [change.name, change.prior_value, change.revised_value, change.rationale]
            for change in context.assumption_changes
        ],
    )
    return f"### Updated Assumptions\n\n{table}\n"


def _valuation_impact(context: EarningsRunContext) -> str:
    rows = [
        [
            change.method,
            format_price(change.prior_price),
            format_price(change.revised_price),
            _delta_pct_text(change.prior_price, change.revised_price),
        ]
        for change in context.valuation_changes
    ]
    rows.append(
        [
            "**Base Case**",
            format_price(context.prior_base_price_target),
            format_price(context.revised_price_target),
            f"{'+' if context.valuation_changed_pct >= 0 else ''}{context.valuation_changed_pct:.1f}%",
        ]
    )
    table = markdown_table(["Method", "Prior", "Revised", "Change"], rows)
    summary = (
        f"{format_price(context.prior_base_price_target)} -> "
        f"{format_price(context.revised_price_target)} "
        f"({'+' if context.valuation_changed_pct >= 0 else ''}{context.valuation_changed_pct:.1f}%)"
    )
    return f"### Valuation Impact\n\n{table}\n\n**Base case: {summary}.**\n"


def _delta_pct_text(prior: Optional[float], revised: Optional[float]) -> str:
    try:
        prior_f = float(prior)
        revised_f = float(revised)
    except (TypeError, ValueError):
        return "n/a"
    if prior_f == 0:
        return "n/a"
    delta = (revised_f - prior_f) / abs(prior_f) * 100.0
    return f"{'+' if delta >= 0 else ''}{delta:.1f}%"


def _bulleted(title: str, items: Sequence[str], empty_text: str) -> str:
    if not items:
        return f"### {title}\n\n_{empty_text}_\n"
    return f"### {title}\n\n" + "\n".join(f"- {item}" for item in items) + "\n"


def _catalysts_ahead(context: EarningsRunContext) -> str:
    if not context.catalysts_ahead:
        return "### Catalysts Ahead\n\n_No active catalysts are recorded._\n"
    table = markdown_table(
        ["Catalyst", "Timeframe", "Direction"],
        [
            [
                record.get("metric") or record.get("statement", ""),
                record.get("period") or "n/a",
                str(record.get("notes", "")).replace("direction=", "") or "n/a",
            ]
            for record in context.catalysts_ahead
        ],
    )
    return f"### Catalysts Ahead\n\n{table}\n"


def render_update_note_markdown(workspace: Any, run_context: EarningsRunContext) -> str:
    """Render the earnings update as Markdown from a precomputed run context.

    Args:
        workspace: The loaded, already-mutated ``ResearchWorkspace``. Used
            only for identity fields already carried on ``run_context``'s
            source (``company_name``/``ticker``); passed through for API
            symmetry with ``report_generators.initiation_report_markdown``
            and so future sections can read workspace state directly without
            a signature change.
        run_context: An :class:`EarningsRunContext` built by the caller.

    Returns:
        A Markdown document, short-form by construction (tables and bullets),
        reliably under 1000 words.
    """

    del workspace  # not needed today; kept for signature symmetry, see docstring.
    context = run_context
    verdict_label = VERDICT_LABELS.get(context.verdict, context.verdict)

    header = (
        f"# {context.company_name} ({context.ticker}) -- Earnings Update\n\n"
        f"**{context.earnings_date} | Verdict: {verdict_label}**\n\n"
        f"> {context.evidence_note}\n"
    )

    sections = [
        header,
        _the_numbers(context),
        _updated_assumptions(context),
        _valuation_impact(context),
        _bulleted(
            "What Changed",
            context.what_changed,
            "Nothing material changed relative to the prior thesis.",
        ),
        _bulleted(
            "What Didn't Change",
            context.what_didnt_change,
            "No unaffected drivers were recorded for this run.",
        ),
        _catalysts_ahead(context),
        _bulleted(
            "Next Steps",
            context.next_steps,
            "No open gaps or contradictions are recorded.",
        ),
    ]
    return "\n".join(section.rstrip() + "\n" for section in sections)
