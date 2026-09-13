"""Claude system prompt and user-prompt builder for the earnings-update report type.

The tool vocabulary is unchanged from the initiation-of-coverage report type:
``prompts.TOOL_DEFINITIONS`` is reused directly (re-exported here under a
stable name) rather than redefined, because the same six tools --
``record_source``, ``record_assumption``, ``record_valuation``,
``record_catalyst``, ``flag_analysis_gap``, ``flag_contradiction`` -- fit an
earnings update unchanged. ``record_scenario`` is present in the shared
schema list but is deliberately not part of this report type's work order:
bull/bear cases are not revised on an earnings update unless a major
structural change occurred, and the Base case's price target is recalculated
by ``earnings_update.py`` from the valuation methods Claude records, not by a
Claude-authored scenario call.

Only the system prompt and user-prompt builder are new; the schemas and the
adapter that applies tool calls to workspace state are shared with Phase 1
unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

import prompts

#: Re-exported under a stable, report-type-specific name. Do not redefine --
#: see the module docstring for why the vocabulary is unchanged from Phase 1.
TOOL_DEFINITIONS_EARNINGS: List[Dict[str, Any]] = prompts.TOOL_DEFINITIONS


SYSTEM_PROMPT_EARNINGS = """\
You are an institutional equity research analyst producing a same-day earnings \
update against an existing initiation-of-coverage thesis.

Given the prior thesis (assumptions already on file and the prior Base-case \
price target) and new evidence from this quarter's release, you will:
1. Compare actual EPS and revenue to consensus, and guidance direction to the
   prior thesis.
2. Revise ONLY the assumptions that the new evidence actually changes.
3. Recalculate valuation using the workspace's existing methods with the
   revised assumptions.
4. Surface new catalysts the guidance or call revealed.
5. Flag gaps and contradictions rather than resolving them by netting them out.

## Output format

Speak in tool calls, not prose. Do not narrate your reasoning in natural
language; let the structured state carry the analysis. Any text you emit is
treated as commentary and is not persisted as research state.

## You do not decide the verdict

Do not label the outcome "thesis intact," "at risk," or "broken," and do not
state a rating change in prose. The calling code computes the verdict
deterministically from the beat/miss math and the assumption and valuation
tool calls you make. Your job is to supply accurate, well-sourced inputs to
that computation, not to name the conclusion yourself.

## Evidence handling

Treat all supplied evidence as unverified input. Where evidence conflicts --
for example, a beat on EPS alongside lowered guidance, or a guidance raise
that outruns the historical growth record -- call `flag_contradiction`
instead of averaging the two signals away. Never invent a figure that is not
derivable from the evidence.

## Required work

**Sources.** Call `record_source` for every source you rely on, before the
tool calls that depend on it. Later calls reference sources by the ids listed
in the evidence block. Sources already on file from the initiation do not
need to be re-recorded; only cite the new evidence sources supplied below.

**Assumptions.** Only call `record_assumption` for a driver whose value the
new evidence actually changes -- a name that exactly matches a prior
assumption on file supersedes it; a new name is added alongside the
untouched ones. Do not re-record an assumption that this quarter's evidence
does not bear on. Every revision needs a rationale that names the delta
(e.g. "guidance raised vs. prior +6% -> revised to +8% on backlog
conversion") and at least one source id.

**Valuation.** Recalculate using the SAME methods already on file for this
company (do not introduce a new valuation method) with `record_valuation`,
carrying through only the assumptions you revised. Show the inputs that
produce the output. Outputs are a low/base/high range.

**Catalysts.** Record any new near-term (6-12 month) catalyst the guidance or
call surfaced with `record_catalyst`, each with a timeframe, a direction, and
a magnitude estimate. Do not re-record a catalyst that already fired this
quarter -- the calling code marks those superseded.

**Gaps and contradictions.** Flag every material gap and every conflicting
signal, especially a beat/miss that runs counter to the guidance direction.

## Standards

- Institutional tone: no marketing language, no cheerleading.
- Skeptical: challenge management's framing of the quarter against the
  historical record and the prior thesis.
- Transparent: the inputs you record must reconstruct the output you claim.
- Conservative: leave an assumption untouched rather than revise it on weak
  evidence.
"""


def _render_section(title: str, payload: Any) -> str:
    return f"### {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=False, default=str)}\n```\n"


def _render_prior_assumptions(prior_assumptions: Sequence[Dict[str, Any]]) -> str:
    if not prior_assumptions:
        return "_No active assumptions are on file for this workspace yet._\n"
    lines = ["| Name | Base | Units | Rationale |", "| --- | --- | --- | --- |"]
    for record in prior_assumptions:
        lines.append(
            f"| {record.get('name', '')} | {record.get('base', '')} | "
            f"{record.get('units', '') or '-'} | {record.get('rationale') or '-'} |"
        )
    return "\n".join(lines) + "\n"


def build_earnings_user_prompt(
    ticker: str,
    company_name: str,
    earnings_date: str,
    eps_actual: float,
    eps_consensus: float,
    revenue_actual: float,
    revenue_consensus: float,
    guidance_change: Optional[str],
    evidence: Dict[str, Any],
    source_ids: Dict[str, str],
    prior_assumptions: Sequence[Dict[str, Any]],
    prior_base_price_target: Optional[float],
) -> str:
    """Build the user turn carrying the prior thesis, new evidence, and work order.

    Args:
        ticker: Exchange ticker.
        company_name: Display name.
        earnings_date: Release date, ``YYYY-MM-DD``.
        eps_actual: Reported EPS.
        eps_consensus: Prior consensus EPS estimate.
        revenue_actual: Reported revenue.
        revenue_consensus: Prior consensus revenue estimate.
        guidance_change: ``"raised"``, ``"lowered"``, ``"in-line"``, or ``None``.
        evidence: Payload from ``earnings_evidence.fetch_earnings_evidence``.
        source_ids: Map of new-evidence source title to the id Claude should cite.
        prior_assumptions: Active assumption records already on file, as loaded
            from the workspace before this run.
        prior_base_price_target: The prior Base scenario's 12-month price
            target, or ``None`` when no prior Base case is on file.

    Returns:
        The user message text.
    """

    catalogue = [
        {"source_id": identifier, "title": title}
        for title, identifier in source_ids.items()
    ]

    sections = [
        f"# Earnings update: {company_name} ({ticker}) -- {earnings_date}\n",
        (
            "Produce the earnings update for this company using the tools provided. "
            "Record every finding as a tool call.\n"
        ),
        "## Prior thesis\n",
        _render_prior_assumptions(prior_assumptions),
        (
            f"Prior Base-case 12-month price target: "
            f"{'n/a (no prior Base case on file)' if prior_base_price_target is None else prior_base_price_target}\n"
        ),
        "## New data\n",
        (
            f"EPS actual {eps_actual} vs. consensus {eps_consensus}; "
            f"revenue actual {revenue_actual} vs. consensus {revenue_consensus}; "
            f"guidance change: {guidance_change or 'not addressed'}.\n"
        ),
        _render_section("Earnings release", evidence.get("earnings_release", {})),
        _render_section("Earnings call transcript", evidence.get("call_transcript", {})),
        _render_section("Consensus revisions", evidence.get("consensus_revisions", {})),
        _render_section("Street commentary", evidence.get("street_commentary", [])),
        _render_section("Stock reaction", evidence.get("stock_reaction", {})),
        _render_section("Source catalogue (cite these ids)", catalogue),
        (
            "## Work order\n\n"
            "1. Call `record_source` for each new-evidence source you rely on.\n"
            "2. Call `record_assumption` only for drivers this evidence actually changes, "
            "naming the prior value and the revised value in the rationale.\n"
            "3. Recalculate valuation with `record_valuation` using the same methods already "
            "on file, carrying through only the revised assumptions.\n"
            "4. Record any new catalyst the guidance or call surfaced with `record_catalyst`.\n"
            "5. Flag every material gap and contradiction, especially a beat/miss that runs "
            "counter to the guidance direction.\n\n"
            "Do not state a verdict or rating in prose. Stop calling tools when the analysis "
            "is complete."
        ),
    ]
    return "\n".join(sections)
