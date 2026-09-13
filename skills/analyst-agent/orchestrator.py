"""AnalystAgent: evidence in, validated workspace state and a report out.

The orchestrator is deliberately thin. It fetches evidence, drives one Claude
tool-use conversation, hands the resulting tool calls to the workspace adapter,
validates through the existing ``persistent-equity-research`` validator, and
renders a publication view. Analysis lives in the prompt; persistence lives in
the adapter; rendering lives in the report generator.

Exceptions propagate. The caller decides how to recover.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import data_sources
import prompts
import report_generators
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
    SOURCE_INGESTION_NODE,
    ToolResult,
    update_workspace_from_claude,
)

#: Minimum structured output for a run to count as complete coverage.
MINIMUM_ASSUMPTIONS = 3
MINIMUM_VALUATIONS = 1
MINIMUM_SOURCES = 2

#: Where the rendered initiation is written inside the workspace.
INITIATION_OUTPUT = "outputs/initiation-of-coverage.md"


class AnalystAgentError(AgentRunError):
    """Raised when the orchestrator cannot complete a coverage run."""


def _display_metric(value: Any, unit: str) -> str:
    """Render a metric for a ledger statement, showing ratios as percentages.

    The ledger keeps the raw value in its ``value`` field; only the human-readable
    statement is reformatted.
    """

    if unit == "ratio":
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return f"{value}"
    return f"{value} {unit}".strip()


class AnalystAgent:
    """Drives an initiation of coverage against a persistent research workspace.

    Args:
        workspace_root: Path to a workspace created by ``init_workspace.py``.
        anthropic_api_key: API key. Defaults to the ``ANTHROPIC_API_KEY``
            environment variable, which the SDK also resolves on its own.
        model: Claude model id. Defaults to :data:`DEFAULT_MODEL`.
        client: A pre-built Anthropic client, or any object exposing
            ``messages.create``. Supplying one skips SDK construction entirely,
            which is how the integration test runs without network access.
        max_turns: Maximum tool-use round trips before the run is cut short.

    Raises:
        WorkspaceAdapterError: If ``workspace_root`` is not a v2 workspace.
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
        self.model = model
        self.max_turns = max_turns
        self._api_key = anthropic_api_key
        self._client = client

    # ------------------------------------------------------------------
    # Claude client
    # ------------------------------------------------------------------

    @property
    def client(self) -> Any:
        """The Anthropic client, constructed on first use.

        The SDK is imported lazily so that importing this module — and running
        the offline test suite — never requires ``anthropic`` to be installed.
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
        """Write evidence sources into the registry and map title -> source id.

        Sources are registered before the model is called so that Claude can cite
        stable ids rather than inventing them.
        """

        registered: Dict[str, str] = {}
        for record in data_sources.limit_sources(evidence, max_evidence_sources):
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

    @staticmethod
    def _pick_source(registered: Dict[str, str], *keywords: str) -> List[str]:
        """Return the id of the first registered source whose title matches."""

        for title, source_id in registered.items():
            lowered = title.lower()
            if all(keyword.lower() in lowered for keyword in keywords):
                return [source_id]
        return [next(iter(registered.values()))] if registered else []

    def _ingest_observed_facts(
        self, evidence: Dict[str, Any], registered: Dict[str, str]
    ) -> None:
        """Persist company context and headline financials as sourced ledger facts.

        Without this the report would have no company-overview section backed by
        state, and a reader unfamiliar with the company could not follow the
        valuation.
        """

        overview = evidence.get("company_overview", {}) or {}
        metrics = evidence.get("financial_metrics", {}) or {}
        macro = evidence.get("macro_context", {}) or {}

        filing_source = self._pick_source(registered, "annual report")
        market_source = self._pick_source(registered, "multiples")
        macro_source = self._pick_source(registered, "macro")

        if overview.get("business_model"):
            self.workspace.add_ledger_record(
                record_type="observed_fact",
                statement=str(overview["business_model"]),
                confidence="high",
                source_ids=filing_source,
                nodes=["economic_engine"],
            )
        if overview.get("competitive_position"):
            self.workspace.add_ledger_record(
                record_type="observed_fact",
                statement=str(overview["competitive_position"]),
                confidence="medium",
                source_ids=filing_source,
                nodes=["value_chain_pricing_power"],
            )
        for segment in overview.get("segments", []) or []:
            if not isinstance(segment, dict):
                continue
            self.workspace.add_ledger_record(
                record_type="observed_fact",
                statement=(
                    f"Segment {segment.get('name')} contributes "
                    f"{_display_metric(segment.get('revenue_share'), 'ratio')} of revenue "
                    f"at an EBIT margin of "
                    f"{_display_metric(segment.get('ebit_margin'), 'ratio')}."
                ),
                confidence="high",
                source_ids=filing_source,
                nodes=["economic_engine"],
                metric=str(segment.get("name")),
                value=segment.get("revenue_share"),
                unit="share of revenue",
            )

        headline = (
            ("revenue", "revenue", metrics.get("currency", "USD") + "m"),
            ("ebit_margin", "EBIT margin", "ratio"),
            ("eps", "EPS", metrics.get("currency", "USD")),
            ("roic", "ROIC", "ratio"),
            ("pe_ratio", "trailing P/E", "x"),
        )
        for key, label, unit in headline:
            if metrics.get(key) is None:
                continue
            self.workspace.add_ledger_record(
                record_type="observed_fact",
                statement=(
                    f"{metrics.get('period', 'latest period')} {label} of "
                    f"{_display_metric(metrics[key], unit)}."
                ),
                confidence="high",
                source_ids=filing_source if key != "pe_ratio" else market_source,
                nodes=["economic_engine"],
                metric=key,
                value=metrics[key],
                unit=unit,
                period=str(metrics.get("period", "")),
            )

        if macro.get("sector_note"):
            self.workspace.add_ledger_record(
                record_type="observed_fact",
                statement=str(macro["sector_note"]),
                confidence="medium",
                source_ids=macro_source,
                nodes=["macro_transmission"],
            )

    # ------------------------------------------------------------------
    # Claude tool-use loop
    # ------------------------------------------------------------------

    def _run_tool_loop(self, user_prompt: str) -> List[ToolResult]:
        """Run the tool-use conversation and collect every tool call Claude makes.

        Tool results are acknowledgements only: the workspace write happens after
        the conversation, in one deterministic pass, so a mid-conversation failure
        cannot leave the ledger half-written.
        """

        return run_tool_loop(
            client=self.client,
            model=self.model,
            system_prompt=prompts.SYSTEM_PROMPT,
            tool_definitions=prompts.TOOL_DEFINITIONS,
            user_prompt=user_prompt,
            max_turns=self.max_turns,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initiate_coverage(
        self,
        ticker: str,
        company_name: str,
        max_evidence_sources: int = 10,
    ) -> Dict[str, Any]:
        """Produce an initiation of coverage and persist it to the workspace.

        Fetches evidence, registers it as sourced state, runs one Claude tool-use
        conversation, writes the resulting findings to the workspace ledger,
        validates, and renders the initiation report.

        Args:
            ticker: Exchange ticker; must match the workspace's ticker.
            company_name: Display name used on the report cover.
            max_evidence_sources: Cap on evidence sources registered.

        Returns:
            A dict with ``workspace_path``, ``report_markdown``,
            ``evidence_count``, ``state_ledger_keys``, and ``status``
            (``success``, ``partial``, or ``failed``). Additional diagnostic keys
            (``validation_errors``, ``validation_warnings``, ``tool_calls``,
            ``report_path``, ``notes``) are included for the caller's benefit.

        Raises:
            ValueError: If ``ticker`` does not match the loaded workspace.
            AnalystAgentError: If the model returns no tool calls at all.
        """

        ticker = (ticker or "").strip().upper()
        if self.workspace.ticker and ticker != self.workspace.ticker:
            raise ValueError(
                f"ticker {ticker!r} does not match workspace ticker "
                f"{self.workspace.ticker!r}; initialize a workspace per company"
            )

        evidence = data_sources.fetch_company_evidence(ticker, company_name)
        registered = self._register_sources(evidence, max_evidence_sources)
        self._ingest_observed_facts(evidence, registered)

        user_prompt = prompts.build_user_prompt(ticker, company_name, evidence, registered)
        tool_calls = self._run_tool_loop(user_prompt)
        if not tool_calls:
            raise AnalystAgentError(
                "the model returned no tool calls; no research state was produced"
            )

        adapter_report = update_workspace_from_claude(self.workspace, tool_calls)

        self.workspace.touch_research_update()
        self.workspace.save()
        self.workspace.mark_node_fresh(SOURCE_INGESTION_NODE)
        self.workspace.save()

        report_markdown = report_generators.initiation_report_markdown(self.workspace)
        report_path = self.workspace_root / INITIATION_OUTPUT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown, encoding="utf-8")

        validation = self.workspace.validate()
        notes = self._coverage_notes(adapter_report)
        status = self._status(validation, notes)

        return {
            "workspace_path": str(self.workspace_root),
            "report_markdown": report_markdown,
            "evidence_count": len(self.workspace.sources),
            "state_ledger_keys": self.workspace.state_ledger_keys(),
            "status": status,
            "report_path": str(report_path),
            "tool_calls": dict(adapter_report.applied),
            "validation_errors": list(validation.errors),
            "validation_warnings": list(validation.warnings),
            "notes": notes,
        }

    def _coverage_notes(self, adapter_report: Any) -> List[str]:
        """Describe every way the run fell short of complete structured coverage."""

        notes: List[str] = []
        applied = adapter_report.applied
        assumption_count = len(self.workspace.assumptions.get("assumptions", []))
        valuation_count = applied.get("record_valuation", 0)
        scenario_count = len(self.workspace.assumptions.get("scenario_overrides", {}))

        if assumption_count < MINIMUM_ASSUMPTIONS:
            notes.append(
                f"only {assumption_count} assumptions recorded, expected at least "
                f"{MINIMUM_ASSUMPTIONS}"
            )
        if valuation_count < MINIMUM_VALUATIONS:
            notes.append(
                f"only {valuation_count} valuation methods recorded, expected at least "
                f"{MINIMUM_VALUATIONS}"
            )
        if len(self.workspace.sources) < MINIMUM_SOURCES:
            notes.append(
                f"only {len(self.workspace.sources)} sources recorded, expected at least "
                f"{MINIMUM_SOURCES}"
            )
        if scenario_count < 3:
            notes.append(f"{scenario_count} of 3 scenarios recorded")
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
        """Map validation state and coverage notes onto the reported status."""

        if not validation.valid:
            return "failed"
        return "partial" if notes else "success"

    # ------------------------------------------------------------------
    # Other report types
    # ------------------------------------------------------------------
    #
    # Sector Report, Quarterly Outlook, and Trading Report are not company-
    # workspace-bound the way an initiation or its earnings update are (a
    # sector report has its own sector-primer workspace; an outlook and a
    # trading report have none at all), so they are not wrapped here. Call
    # ``sector_report.SectorReportAgent``, ``outlook_report.run_quarterly_outlook``,
    # and ``trading_report.run_trading_report`` directly. See SKILL.md.

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
        """Revise this same company workspace after a quarterly earnings release.

        A thin delegation to :class:`earnings_update.EarningsUpdateAgent`,
        reusing this agent's workspace, model, client, and API key so that a
        caller already holding an ``AnalystAgent`` for a company (e.g. from a
        prior :meth:`initiate_coverage` run) can chain straight into an
        earnings update without re-supplying connection details.

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
            See :meth:`earnings_update.EarningsUpdateAgent.earnings_update`.
        """

        # Imported here, not at module scope, to keep earnings_update.py from
        # having to be present for callers who only ever run initiate_coverage.
        from earnings_update import EarningsUpdateAgent

        agent = EarningsUpdateAgent(
            workspace_root=str(self.workspace_root),
            anthropic_api_key=self._api_key,
            model=self.model,
            client=self._client,
            max_turns=self.max_turns,
        )
        return agent.earnings_update(
            earnings_date=earnings_date,
            eps_actual=eps_actual,
            eps_consensus=eps_consensus,
            revenue_actual=revenue_actual,
            revenue_consensus=revenue_consensus,
            guidance_change=guidance_change,
            earnings_call_transcript_url=earnings_call_transcript_url,
            max_evidence_sources=max_evidence_sources,
        )
