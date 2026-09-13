"""EarningsUpdateAgent: earnings evidence in, a revised workspace and a short update note out.

Phase 2a of the analyst-agent report-type set. This report type does not
create a workspace: it loads one already produced by
``persistent-equity-research``'s ``init_workspace.py`` (optionally seeded
further by a prior ``orchestrator.AnalystAgent.initiate_coverage`` run) and
revises it against one quarter's earnings evidence.

Mirrors ``orchestrator.py``'s division of labour: evidence fetching lives in
``earnings_evidence.py``, the Claude conversation's contract lives in
``earnings_prompts.py``, workspace mutation is delegated to
``workspace_adapter`` (imported, not edited), and rendering lives in
``earnings_report.py``. This module is the thin orchestration layer that ties
them together and adds the analysis this report type owns outright: the
deterministic beat/miss-and-guidance verdict, which assumptions actually
changed, and the valuation delta from the prior Base case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import earnings_evidence
import earnings_prompts
import earnings_report
from agent_common import (
    AgentRunError,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    build_client,
    run_tool_loop,
)
from workspace_adapter import (
    ResearchWorkspace,
    SCENARIO_METHOD_PREFIX,
    ToolResult,
    update_workspace_from_claude,
)

#: Where the rendered update note is written inside the workspace, matching
#: the ``workflow-update.md`` convention and the placeholder asset already
#: shipped by ``persistent-equity-research``'s workspace template.
UPDATE_NOTE_OUTPUT = "outputs/update-note.md"

#: Deterministic verdict thresholds. See :func:`determine_verdict` for the
#: exact rule and the module docstring for the judgment call made where the
#: spec's prose left the boundary conditions ambiguous.
AT_RISK_MISS_THRESHOLD_PCT = 5.0
BROKEN_MISS_WITH_GUIDANCE_THRESHOLD_PCT = 10.0
BROKEN_OUTRIGHT_MISS_THRESHOLD_PCT = 15.0

#: Keywords that mark a prior catalyst as having already occurred once this
#: quarter's earnings have been released, and therefore due for supersession
#: rather than continuing to be reported as still ahead.
_ELAPSED_CATALYST_KEYWORDS = ("earnings", "results", "guidance")


class EarningsUpdateError(AgentRunError):
    """Raised when the earnings-update agent cannot complete a run."""


def determine_verdict(
    eps_surprise_pct: Optional[float],
    revenue_surprise_pct: Optional[float],
    guidance_change: Optional[str],
) -> str:
    """Deterministically classify a quarter's fit against the prior thesis.

    This is plain Python, not a Claude tool call, so the label is
    reproducible from the same three inputs every time -- Claude supplies the
    assumption and valuation revisions; this function supplies the verdict.

    Rule (see the spec's "Analysis flow" step 4):
        - ``thesis_broken``: guidance lowered AND a miss of 10% or worse on
          either EPS or revenue, OR a miss of 15% or worse outright on
          either metric regardless of guidance.
        - ``thesis_at_risk``: a miss of more than 5% on either metric, or
          guidance lowered (and not already ``thesis_broken``).
        - ``thesis_intact``: otherwise -- results within the miss thresholds
          above and guidance not lowered (a beat, even a large one, cannot by
          itself move the thesis to "at risk").

    Args:
        eps_surprise_pct: Percent surprise from :func:`earnings_evidence.compute_surprise_pct`,
            or ``None`` when undefined (treated as no surprise).
        revenue_surprise_pct: Same, for revenue.
        guidance_change: ``"raised"``, ``"lowered"``, ``"in-line"``, or ``None``.

    Returns:
        ``"thesis_intact"``, ``"thesis_at_risk"``, or ``"thesis_broken"``.
    """

    eps_miss = max(0.0, -(eps_surprise_pct or 0.0))
    revenue_miss = max(0.0, -(revenue_surprise_pct or 0.0))
    worst_miss = max(eps_miss, revenue_miss)
    guidance_lowered = guidance_change == "lowered"

    if worst_miss >= BROKEN_OUTRIGHT_MISS_THRESHOLD_PCT:
        return "thesis_broken"
    if guidance_lowered and worst_miss >= BROKEN_MISS_WITH_GUIDANCE_THRESHOLD_PCT:
        return "thesis_broken"
    if worst_miss > AT_RISK_MISS_THRESHOLD_PCT or guidance_lowered:
        return "thesis_at_risk"
    return "thesis_intact"


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class EarningsUpdateAgent:
    """Drives an earnings update against a persistent research workspace.

    Args:
        workspace_root: Path to a v2 workspace created by ``init_workspace.py``,
            typically already carrying a prior thesis from an
            ``initiate_coverage`` run.
        anthropic_api_key: API key. Defaults to the ``ANTHROPIC_API_KEY``
            environment variable, which the SDK also resolves on its own.
        model: Claude model id. Defaults to :data:`agent_common.DEFAULT_MODEL`.
        client: A pre-built Anthropic client, or any object exposing
            ``messages.create``. Supplying one skips SDK construction
            entirely, which is how the integration test runs without network
            access.
        max_turns: Maximum tool-use round trips before the run is cut short.

    Raises:
        WorkspaceAdapterError: If ``workspace_root`` is not a v2 workspace.
        ValueError: If the loaded workspace carries no ticker, meaning it was
            never properly initialized as a company workspace.
    """

    def __init__(
        self,
        workspace_root: str,
        anthropic_api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        client: Any = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.workspace = ResearchWorkspace.load(self.workspace_root)
        if not self.workspace.ticker:
            raise ValueError(
                f"workspace at {self.workspace_root} carries no ticker; it is not a "
                "valid company workspace to revise"
            )
        self.model = model
        self.max_turns = max_turns
        self._api_key = anthropic_api_key
        self._client = client

    @property
    def client(self) -> Any:
        """The Anthropic client, constructed on first use.

        The SDK is imported lazily so that importing this module -- and
        running the offline test suite -- never requires ``anthropic`` to be
        installed.
        """

        if self._client is None:
            self._client = build_client(self._api_key, None)
        return self._client

    # ------------------------------------------------------------------
    # Evidence ingestion
    # ------------------------------------------------------------------

    def _register_sources(
        self, evidence: Dict[str, Any], max_evidence_sources: int
    ) -> Dict[str, str]:
        """Write new evidence sources into the registry and map title -> source id."""

        registered: Dict[str, str] = {}
        for record in earnings_evidence.limit_sources(evidence, max_evidence_sources):
            title = str(record.get("title", "")).strip()
            source_id = self.workspace.add_source(
                title=title,
                url=record.get("url", ""),
                date=record.get("date"),
                extract=record.get("extract"),
                publisher=record.get("publisher"),
            )
            registered[title] = source_id
        return registered

    def _supersede_elapsed_catalysts(self) -> List[Dict[str, Any]]:
        """Mark prior catalysts that this quarter's release has now resolved.

        Runs before the tool loop, over catalysts already on file, so a new
        catalyst Claude records this run (which may itself mention
        "guidance") is never accidentally superseded by its own keyword.
        """

        superseded: List[Dict[str, Any]] = []
        for record in self.workspace.ledger_by_type("catalyst"):
            statement = str(record.get("statement", "")).lower()
            if any(keyword in statement for keyword in _ELAPSED_CATALYST_KEYWORDS):
                record["status"] = "superseded"
                superseded.append(record)
        return superseded

    # ------------------------------------------------------------------
    # Claude tool-use loop
    # ------------------------------------------------------------------

    def _run_tool_loop(self, user_prompt: str) -> List[ToolResult]:
        """Run the tool-use conversation and collect every tool call Claude makes."""

        return run_tool_loop(
            client=self.client,
            model=self.model,
            system_prompt=earnings_prompts.SYSTEM_PROMPT_EARNINGS,
            tool_definitions=earnings_prompts.TOOL_DEFINITIONS_EARNINGS,
            user_prompt=user_prompt,
            max_turns=self.max_turns,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def earnings_update(
        self,
        earnings_date: str,
        eps_actual: float,
        eps_consensus: float,
        revenue_actual: float,
        revenue_consensus: float,
        guidance_change: Optional[str],
        earnings_call_transcript_url: Optional[str] = None,
        max_evidence_sources: int = 5,
    ) -> Dict[str, Any]:
        """Produce an earnings update and persist it to the workspace.

        Fetches earnings evidence, registers it as sourced state, runs one
        Claude tool-use conversation against the prior thesis, revises only
        the assumptions that changed, recalculates valuation, computes a
        deterministic verdict, and renders the update note.

        Args:
            earnings_date: Release date as ``YYYY-MM-DD``.
            eps_actual: Reported EPS.
            eps_consensus: Prior consensus EPS estimate.
            revenue_actual: Reported revenue, in the workspace's reporting units.
            revenue_consensus: Prior consensus revenue estimate, same units.
            guidance_change: ``"raised"``, ``"lowered"``, ``"in-line"``, or ``None``.
            earnings_call_transcript_url: Transcript URL, if available.
            max_evidence_sources: Cap on new evidence sources registered.

        Returns:
            A dict with ``workspace_path``, ``update_note_markdown``,
            ``assumptions_changed``, ``valuation_changed_pct``, ``verdict``,
            ``revised_price_target``, and ``status`` (``success``,
            ``partial``, or ``failed``). Additional diagnostic keys
            (``report_path``, ``tool_calls``, ``validation_errors``,
            ``validation_warnings``, ``eps_surprise_pct``,
            ``revenue_surprise_pct``, ``notes``) are included for the
            caller's benefit, mirroring ``orchestrator.AnalystAgent``.

        Raises:
            EarningsUpdateError: If the model returns no tool calls at all.
        """

        ticker = self.workspace.ticker
        company_name = self.workspace.company_name

        evidence = earnings_evidence.fetch_earnings_evidence(
            ticker=ticker,
            company_name=company_name,
            earnings_date=earnings_date,
            eps_actual=eps_actual,
            eps_consensus=eps_consensus,
            revenue_actual=revenue_actual,
            revenue_consensus=revenue_consensus,
            guidance_change=guidance_change,
            earnings_call_transcript_url=earnings_call_transcript_url,
        )
        eps_surprise_pct = evidence["earnings_release"]["eps_surprise_pct"]
        revenue_surprise_pct = evidence["earnings_release"]["revenue_surprise_pct"]

        # ---- Snapshot prior state before anything is mutated ----
        prior_active_by_name = {
            str(record.get("name", "")).casefold(): dict(record)
            for record in self.workspace.assumptions.get("assumptions", [])
            if record.get("status") == "active"
        }
        prior_valuation_snapshot = list(self.workspace.valuation_rows)
        prior_base_override = self.workspace.assumptions.get("scenario_overrides", {}).get("Base")
        prior_base_price_target = (
            _to_float(prior_base_override.get("price_target"))
            if isinstance(prior_base_override, dict)
            else None
        )
        prior_base_weight = (
            prior_base_override.get("weight") if isinstance(prior_base_override, dict) else None
        )
        prior_base_assumptions = (
            prior_base_override.get("assumptions") if isinstance(prior_base_override, dict) else None
        )
        prior_base_valuation_desc = (
            prior_base_override.get("valuation") if isinstance(prior_base_override, dict) else None
        )

        superseded_catalysts = self._supersede_elapsed_catalysts()

        registered = self._register_sources(evidence, max_evidence_sources)

        prior_assumptions_for_prompt = [
            record
            for record in self.workspace.assumptions.get("assumptions", [])
            if record.get("status") == "active"
        ]
        user_prompt = earnings_prompts.build_earnings_user_prompt(
            ticker=ticker,
            company_name=company_name,
            earnings_date=earnings_date,
            eps_actual=eps_actual,
            eps_consensus=eps_consensus,
            revenue_actual=revenue_actual,
            revenue_consensus=revenue_consensus,
            guidance_change=guidance_change,
            evidence=evidence,
            source_ids=registered,
            prior_assumptions=prior_assumptions_for_prompt,
            prior_base_price_target=prior_base_price_target,
        )

        tool_calls = self._run_tool_loop(user_prompt)
        if not tool_calls:
            raise EarningsUpdateError(
                "the model returned no tool calls; no earnings-update state was produced"
            )

        adapter_report = update_workspace_from_claude(self.workspace, tool_calls)

        # ---- Assumption revisions: supersede the prior record of the same name ----
        assumptions_by_id = {
            record.get("id"): record for record in self.workspace.assumptions.get("assumptions", [])
        }
        assumption_changes: List[earnings_report.AssumptionChange] = []
        for assumption_id in adapter_report.assumption_ids:
            record = assumptions_by_id.get(assumption_id)
            if record is None:
                continue
            name_key = str(record.get("name", "")).casefold()
            prior_record = prior_active_by_name.get(name_key)
            revised_value = f"{record.get('base', '')} {record.get('units', '') or ''}".strip()
            if prior_record is not None and prior_record.get("id") != assumption_id:
                self.workspace.mark_assumption_stale(str(prior_record["id"]))
                prior_value = f"{prior_record.get('base', '')} {prior_record.get('units', '') or ''}".strip()
            else:
                prior_value = "n/a (new)"
            assumption_changes.append(
                earnings_report.AssumptionChange(
                    name=str(record.get("name", "")),
                    prior_value=prior_value,
                    revised_value=revised_value,
                    rationale=str(record.get("rationale") or "-"),
                )
            )

        untouched_assumption_names = {
            str(record.get("name", "")) for record in prior_assumptions_for_prompt
        } - {change.name for change in assumption_changes}

        # ---- Valuation: recompute the Base case from any recalculated methods ----
        new_valuation_rows = self.workspace.valuation_rows[len(prior_valuation_snapshot):]
        new_base_by_method = {
            str(row.get("method", "")): _to_float(row.get("implied_price"))
            for row in new_valuation_rows
            if row.get("scenario") == "base"
            and not str(row.get("method", "")).startswith(SCENARIO_METHOD_PREFIX)
        }
        prior_base_by_method = {
            str(row.get("method", "")): _to_float(row.get("implied_price"))
            for row in prior_valuation_snapshot
            if row.get("scenario") == "base"
            and not str(row.get("method", "")).startswith(SCENARIO_METHOD_PREFIX)
        }
        valuation_changes = [
            earnings_report.ValuationChange(
                method=method,
                prior_price=prior_base_by_method.get(method),
                revised_price=new_base_by_method.get(method),
            )
            for method in sorted(set(prior_base_by_method) | set(new_base_by_method))
        ]

        recomputed_prices = [price for price in new_base_by_method.values() if price is not None]
        if recomputed_prices:
            revised_price_target = sum(recomputed_prices) / len(recomputed_prices)
        else:
            revised_price_target = prior_base_price_target

        if prior_base_price_target not in (None, 0) and revised_price_target is not None:
            valuation_changed_pct = (
                (revised_price_target - prior_base_price_target) / abs(prior_base_price_target) * 100.0
            )
        else:
            valuation_changed_pct = 0.0

        self.workspace.set_scenario_override(
            "Base",
            {
                "assumptions": prior_base_assumptions if prior_base_assumptions is not None else {},
                "valuation": prior_base_valuation_desc if prior_base_valuation_desc is not None else "",
                "price_target": revised_price_target,
                "weight": prior_base_weight if prior_base_weight is not None else 0.5,
            },
        )

        # ---- Verdict ----
        verdict = determine_verdict(eps_surprise_pct, revenue_surprise_pct, guidance_change)

        # ---- What changed / didn't change ----
        what_changed: List[str] = []
        for change in assumption_changes:
            if change.prior_value == "n/a (new)":
                what_changed.append(f"{change.name}: new assumption added ({change.rationale})")
            else:
                what_changed.append(
                    f"{change.name}: {change.prior_value} -> {change.revised_value} ({change.rationale})"
                )
        if guidance_change in ("raised", "lowered"):
            what_changed.append(f"Guidance {guidance_change} versus the prior outlook.")
        if abs(valuation_changed_pct) > 0.01:
            what_changed.append(
                f"Base-case price target moved from {prior_base_price_target} to "
                f"{revised_price_target} ({valuation_changed_pct:+.1f}%)."
            )
        for record in superseded_catalysts:
            what_changed.append(
                f"Catalyst superseded (occurred this quarter): {record.get('metric') or record.get('statement')}"
            )

        what_didnt_change: List[str] = []
        for name in sorted(untouched_assumption_names):
            record = prior_active_by_name.get(name.casefold(), {})
            what_didnt_change.append(
                f"{record.get('name', name)}: unchanged at {record.get('base', '')} "
                f"{record.get('units', '') or ''}".strip()
            )
        if guidance_change in (None, "in-line"):
            what_didnt_change.append("Guidance was not revised.")
        if not valuation_changes or all(c.revised_price is None for c in valuation_changes):
            what_didnt_change.append("No valuation method was recalculated this run.")

        # ---- Catalysts ahead: still-active catalysts after supersession ----
        catalysts_ahead = self.workspace.ledger_by_type("catalyst")

        # ---- Next steps: open gaps and contradictions ----
        gaps = self.workspace.ledger_by_type("research_gap")
        open_contradictions = [
            record
            for record in self.workspace.contradictions.get("contradictions", [])
            if isinstance(record, dict) and record.get("status") == "open"
        ]
        next_steps = [str(record.get("statement", "")) for record in gaps] + [
            f"Contradiction: {record.get('summary')}" for record in open_contradictions
        ]

        # ---- Audit trail: one ledger record documenting this event ----
        surprise_text = (
            f"EPS {eps_surprise_pct:+.1f}%" if eps_surprise_pct is not None else "EPS surprise n/a"
        )
        revenue_surprise_text = (
            f"revenue {revenue_surprise_pct:+.1f}%"
            if revenue_surprise_pct is not None
            else "revenue surprise n/a"
        )
        self.workspace.add_ledger_record(
            record_type="analytical_conclusion",
            statement=(
                f"Earnings update for {earnings_date}: verdict {verdict} "
                f"({surprise_text} vs. consensus, {revenue_surprise_text} vs. consensus, "
                f"guidance {guidance_change or 'not addressed'})."
            ),
            confidence="high",
            nodes=["valuation"],
            metric="earnings_update",
            value=eps_actual,
            period=earnings_date,
            notes=f"verdict={verdict}",
        )

        self.workspace.touch_research_update()
        self.workspace.save()

        run_context = earnings_report.EarningsRunContext(
            ticker=ticker,
            company_name=company_name,
            earnings_date=earnings_date,
            eps_actual=eps_actual,
            eps_consensus=eps_consensus,
            eps_surprise_pct=eps_surprise_pct,
            revenue_actual=revenue_actual,
            revenue_consensus=revenue_consensus,
            revenue_surprise_pct=revenue_surprise_pct,
            guidance_change=guidance_change,
            verdict=verdict,
            prior_base_price_target=prior_base_price_target,
            revised_price_target=revised_price_target,
            valuation_changed_pct=valuation_changed_pct,
            assumption_changes=assumption_changes,
            valuation_changes=valuation_changes,
            what_changed=what_changed,
            what_didnt_change=what_didnt_change,
            catalysts_ahead=catalysts_ahead,
            next_steps=next_steps,
        )
        update_note_markdown = earnings_report.render_update_note_markdown(self.workspace, run_context)
        report_path = self.workspace_root / UPDATE_NOTE_OUTPUT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(update_note_markdown, encoding="utf-8")

        validation = self.workspace.validate()
        notes = self._run_notes(adapter_report, update_note_markdown)
        status = self._status(validation, notes)

        return {
            "workspace_path": str(self.workspace_root),
            "update_note_markdown": update_note_markdown,
            "assumptions_changed": adapter_report.applied.get("record_assumption", 0),
            "valuation_changed_pct": round(valuation_changed_pct, 2),
            "verdict": verdict,
            "revised_price_target": revised_price_target,
            "status": status,
            "report_path": str(report_path),
            "tool_calls": dict(adapter_report.applied),
            "validation_errors": list(validation.errors),
            "validation_warnings": list(validation.warnings),
            "eps_surprise_pct": eps_surprise_pct,
            "revenue_surprise_pct": revenue_surprise_pct,
            "notes": notes,
        }

    @staticmethod
    def _run_notes(adapter_report: Any, update_note_markdown: str) -> List[str]:
        """Describe every way the run under-delivered against a clean update."""

        notes: List[str] = []
        word_count = len(update_note_markdown.split())
        if word_count > 1000:
            notes.append(f"update note is {word_count} words, exceeds the 1000-word ceiling")
        if adapter_report.dropped_source_links:
            notes.append(
                "dropped unresolvable source links: "
                + "; ".join(adapter_report.dropped_source_links)
            )
        if adapter_report.unknown_tools:
            notes.append(
                "ignored unknown tool calls: " + ", ".join(sorted(set(adapter_report.unknown_tools)))
            )
        return notes

    @staticmethod
    def _status(validation: Any, notes: List[str]) -> str:
        """Map validation state and run notes onto the reported status."""

        if not validation.valid:
            return "failed"
        return "partial" if notes else "success"
