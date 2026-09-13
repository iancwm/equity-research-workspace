"""SectorReportAgent: sector evidence in, validated workspace state and a
sector report out.

Mirrors ``orchestrator.AnalystAgent``'s design for the sector-report report
type: fetch evidence, ingest facts that are supplied rather than analyzed
(structural drivers, cyclicality, macro/geopolitical lens) directly into the
ledger, drive one Claude tool-use conversation for the analytical judgments
(sector sizing, value-chain economics, peer benchmarking, valuation verdict,
catalysts, gaps, contradictions), hand the resulting tool calls to the sector
workspace adapter, validate with the sector-primer validator, and render a
publication view. Analysis lives in the prompt; persistence lives in the
adapter; rendering lives in ``sector_report_render``.

Exceptions propagate. The caller decides how to recover.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import sector_evidence
import sector_prompts
import sector_report_render
from agent_common import (
    AgentRunError,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    ToolResult,
    build_client,
    run_tool_loop,
)
from sector_workspace import SectorWorkspace
from sector_workspace_adapter import update_sector_workspace_from_claude

#: Minimum structured output for a run to count as complete coverage.
MINIMUM_VALUE_CHAIN_SEGMENTS = 3
MINIMUM_PEERS_WHEN_AUTO_DETECTED = 5
MINIMUM_STRUCTURAL_TAILWINDS = 2
MINIMUM_LEADING_INDICATORS = 2
MINIMUM_CATALYSTS = 3
MINIMUM_SOURCES = 2

#: Where the rendered sector report is written inside the workspace. This is
#: the pre-existing placeholder filename ``init_sector_workspace.py`` creates;
#: this agent overwrites it with the full rendered report.
SECTOR_REPORT_OUTPUT = "outputs/sector-primer.md"


class SectorReportError(AgentRunError):
    """Raised when the sector-report agent cannot complete a run."""


class SectorReportAgent:
    """Drives a sector report against a persistent sector-primer workspace.

    Args:
        workspace_root: Path to a sector-primer workspace. Created via
            :meth:`SectorWorkspace.create` on first use if it does not exist.
        anthropic_api_key: API key. Defaults to the ``ANTHROPIC_API_KEY``
            environment variable, which the SDK also resolves on its own.
        model: Claude model id. Defaults to :data:`agent_common.DEFAULT_MODEL`.
        client: A pre-built Anthropic client, or any object exposing
            ``messages.create``. Supplying one skips SDK construction entirely,
            which is how the integration test runs without network access.
        max_turns: Maximum tool-use round trips before the run is cut short.
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
        self.model = model
        self.max_turns = max_turns
        self._api_key = anthropic_api_key
        self._client = client
        # Loaded (or created) lazily inside sector_report(), because whether an
        # existing directory is a valid sector workspace, and what sector name
        # and geography to create one with, are only known at call time.
        self.workspace: Optional[SectorWorkspace] = None

    # ------------------------------------------------------------------
    # Claude client
    # ------------------------------------------------------------------

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
    # Workspace load-or-create
    # ------------------------------------------------------------------

    def _load_or_create_workspace(self, sector_name: str, geography: str) -> SectorWorkspace:
        has_project = (self.workspace_root / "project.json").is_file()
        if has_project:
            workspace = SectorWorkspace.load(self.workspace_root)
            existing = workspace.sector_name
            if existing and sector_name and existing.strip().casefold() != sector_name.strip().casefold():
                raise ValueError(
                    f"sector_name {sector_name!r} does not match workspace sector "
                    f"{existing!r}; initialize a workspace per sector"
                )
            return workspace
        return SectorWorkspace.create(self.workspace_root, sector_name=sector_name, geography=geography)

    # ------------------------------------------------------------------
    # Evidence ingestion
    # ------------------------------------------------------------------

    def _register_sources(self, workspace: SectorWorkspace, evidence: Dict[str, Any], max_evidence_sources: int) -> Dict[str, str]:
        """Write evidence sources into the registry and map title -> source id.

        Sources are registered before the model is called so that Claude can
        cite stable ids rather than inventing them.
        """

        registered: Dict[str, str] = {}
        for record in sector_evidence.limit_sources(evidence, max_evidence_sources):
            title = str(record.get("title", "")).strip()
            source_id = workspace.add_source(
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

    def _ingest_supplied_facts(self, workspace: SectorWorkspace, evidence: Dict[str, Any], registered: Dict[str, str]) -> None:
        """Persist structural, cyclicality, and macro/geopolitical evidence directly.

        These are supplied facts, not analytical judgments: exactly like the
        company orchestrator's ``_ingest_observed_facts`` writing
        ``macro_context`` straight into the ledger, they are ingested here
        rather than routed through a Claude tool call, so a reader can trust
        them even before the analytical pass runs.
        """

        capacity_source = self._pick_source(registered, "capacity")
        macro_source = self._pick_source(registered, "macro")
        trade_source = self._pick_source(registered, "trade")

        for driver in evidence.get("structural_drivers", []) or []:
            if not isinstance(driver, dict) or not driver.get("statement"):
                continue
            workspace.add_ledger_record(
                record_type="structural_driver",
                statement=str(driver["statement"]),
                source_ids=capacity_source,
                confidence="medium",
                kind=str(driver.get("kind", "tailwind")),
            )

        cyclicality = evidence.get("cyclicality", {}) or {}
        if cyclicality:
            workspace.add_ledger_record(
                record_type="cyclicality_note",
                statement=str(cyclicality.get("note", "")) or "Cyclicality note not recorded.",
                source_ids=macro_source,
                confidence="medium",
                recession_sensitivity=cyclicality.get("recession_sensitivity"),
                operating_leverage=cyclicality.get("operating_leverage"),
                leading_indicators=list(cyclicality.get("leading_indicators", []) or []),
            )

        macro_lens = evidence.get("macro_lens", {}) or {}
        if macro_lens.get("statement"):
            workspace.add_ledger_record(
                record_type="macro_sensitivity",
                statement=str(macro_lens["statement"]),
                source_ids=macro_source,
                confidence="medium",
                dominant_factor=macro_lens.get("dominant_factor"),
            )

        geopolitical_risk = evidence.get("geopolitical_risk", {}) or {}
        if geopolitical_risk.get("statement"):
            workspace.add_ledger_record(
                record_type="geopolitical_risk",
                statement=str(geopolitical_risk["statement"]),
                source_ids=trade_source,
                confidence="medium",
            )

    # ------------------------------------------------------------------
    # Claude tool-use loop
    # ------------------------------------------------------------------

    def _run_tool_loop(self, user_prompt: str) -> List[ToolResult]:
        """Run the tool-use conversation and collect every tool call Claude makes.

        Tool results are acknowledgements only: the workspace write happens
        after the conversation, in one deterministic pass, so a mid-conversation
        failure cannot leave the ledger half-written.
        """

        return run_tool_loop(
            client=self.client,
            model=self.model,
            system_prompt=sector_prompts.SYSTEM_PROMPT_SECTOR,
            tool_definitions=sector_prompts.TOOL_DEFINITIONS_SECTOR,
            user_prompt=user_prompt,
            max_turns=self.max_turns,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sector_report(
        self,
        sector_name: str,
        geography: str = "Global",
        peer_universe: Optional[List[str]] = None,
        look_forward_years: int = 3,
        max_evidence_sources: int = 15,
    ) -> Dict[str, Any]:
        """Produce a sector report and persist it to the workspace.

        Fetches sector evidence, registers it as sourced state, ingests
        supplied structural/cyclicality/macro facts directly, runs one Claude
        tool-use conversation for the analytical judgments, writes the
        resulting findings to the workspace, validates, and renders the
        sector report.

        Args:
            sector_name: e.g. ``"Semiconductors"``. Used to create the
                workspace if it does not yet exist; must match the existing
                workspace's sector if it does.
            geography: e.g. ``"Global"``.
            peer_universe: Explicit peer tickers; auto-detected (at least
                five) when ``None``.
            look_forward_years: Forward window for the analysis.
            max_evidence_sources: Cap on evidence sources registered.

        Returns:
            A dict with ``workspace_path``, ``sector_report_markdown``,
            ``peer_universe_count``, ``valuation_spread_pct``, and ``status``
            (``success``, ``partial``, or ``failed``). Additional diagnostic
            keys (``validation_errors``, ``tool_calls``, ``report_path``,
            ``notes``) are included for the caller's benefit.

        Raises:
            ValueError: If ``sector_name`` does not match an existing workspace.
            SectorReportError: If the model returns no tool calls at all.
        """

        sector_name = (sector_name or "").strip()
        if not sector_name:
            raise ValueError("sector_name must not be empty")
        geography = (geography or "Global").strip() or "Global"

        self.workspace = self._load_or_create_workspace(sector_name, geography)
        workspace = self.workspace

        evidence = sector_evidence.fetch_sector_evidence(
            sector_name=sector_name,
            geography=geography,
            peer_universe=peer_universe,
            look_forward_years=look_forward_years,
        )
        registered = self._register_sources(workspace, evidence, max_evidence_sources)
        self._ingest_supplied_facts(workspace, evidence, registered)

        user_prompt = sector_prompts.build_sector_user_prompt(
            sector_name, geography, evidence, registered, look_forward_years
        )
        tool_calls = self._run_tool_loop(user_prompt)
        if not tool_calls:
            raise SectorReportError(
                "the model returned no tool calls; no research state was produced"
            )

        adapter_report = update_sector_workspace_from_claude(workspace, tool_calls)

        workspace.touch_research_update()
        workspace.save()

        report_markdown = sector_report_render.render_sector_report_markdown(workspace)
        report_path = self.workspace_root / SECTOR_REPORT_OUTPUT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown, encoding="utf-8")

        validation_errors = workspace.validate()
        peer_universe_count = len(workspace.ledger_by_type("peer_benchmark"))
        valuation_spread_pct = self._valuation_spread_pct(workspace)
        notes = self._coverage_notes(adapter_report, workspace, peer_universe is None)
        status = self._status(validation_errors, notes)

        return {
            "workspace_path": str(self.workspace_root),
            "sector_report_markdown": report_markdown,
            "peer_universe_count": peer_universe_count,
            "valuation_spread_pct": valuation_spread_pct,
            "status": status,
            "report_path": str(report_path),
            "evidence_count": len(workspace.sources),
            "tool_calls": dict(adapter_report.applied),
            "validation_errors": list(validation_errors),
            "notes": notes,
        }

    @staticmethod
    def _valuation_spread_pct(workspace: SectorWorkspace) -> float:
        """Richest peer's P/E vs. cheapest peer's P/E, as a percent premium.

        ``(max_pe / min_pe - 1) * 100``. Requires at least two peers with a
        numeric ``pe_ratio``; otherwise there is no spread to compute and this
        returns ``0.0``.
        """

        pe_values = [
            float(peer["pe_ratio"])
            for peer in workspace.ledger_by_type("peer_benchmark")
            if isinstance(peer.get("pe_ratio"), (int, float))
        ]
        if len(pe_values) < 2 or min(pe_values) <= 0:
            return 0.0
        return round((max(pe_values) / min(pe_values) - 1.0) * 100.0, 2)

    def _coverage_notes(
        self, adapter_report: Any, workspace: SectorWorkspace, peers_auto_detected: bool
    ) -> List[str]:
        """Describe every way the run fell short of complete structured coverage."""

        notes: List[str] = []
        segment_count = len(workspace.ledger_by_type("value_chain_segment"))
        peer_count = len(workspace.ledger_by_type("peer_benchmark"))
        tailwind_count = len(
            [d for d in workspace.ledger_by_type("structural_driver") if str(d.get("kind")) == "tailwind"]
        )
        cyclicality_notes = workspace.ledger_by_type("cyclicality_note")
        leading_indicator_count = (
            len(cyclicality_notes[-1].get("leading_indicators") or []) if cyclicality_notes else 0
        )
        catalyst_count = len(workspace.ledger_by_type("catalyst"))
        valuation_count = adapter_report.applied.get("record_valuation", 0)
        overview_count = adapter_report.applied.get("record_sector_overview", 0)

        if overview_count < 1:
            notes.append("no sector overview was recorded")
        if segment_count < MINIMUM_VALUE_CHAIN_SEGMENTS:
            notes.append(
                f"only {segment_count} value-chain segment(s) recorded, expected at least "
                f"{MINIMUM_VALUE_CHAIN_SEGMENTS}"
            )
        if peers_auto_detected and peer_count < MINIMUM_PEERS_WHEN_AUTO_DETECTED:
            notes.append(
                f"only {peer_count} peer(s) recorded, expected at least "
                f"{MINIMUM_PEERS_WHEN_AUTO_DETECTED} when auto-detected"
            )
        elif not peers_auto_detected and peer_count < 1:
            notes.append("no peer benchmarks were recorded")
        if tailwind_count < MINIMUM_STRUCTURAL_TAILWINDS:
            notes.append(
                f"only {tailwind_count} structural tailwind(s) recorded, expected at least "
                f"{MINIMUM_STRUCTURAL_TAILWINDS}"
            )
        if not cyclicality_notes:
            notes.append("no cyclicality analysis was recorded")
        elif leading_indicator_count < MINIMUM_LEADING_INDICATORS:
            notes.append(
                f"only {leading_indicator_count} leading indicator(s) recorded, expected at least "
                f"{MINIMUM_LEADING_INDICATORS}"
            )
        if valuation_count < 1:
            notes.append("no sector-level valuation verdict was recorded")
        if catalyst_count < MINIMUM_CATALYSTS:
            notes.append(
                f"only {catalyst_count} catalyst(s) recorded, expected at least {MINIMUM_CATALYSTS}"
            )
        if len(workspace.sources) < MINIMUM_SOURCES:
            notes.append(
                f"only {len(workspace.sources)} sources recorded, expected at least {MINIMUM_SOURCES}"
            )
        if adapter_report.dropped_source_links:
            notes.append(
                "dropped unresolvable source links: " + "; ".join(adapter_report.dropped_source_links)
            )
        if adapter_report.unknown_tools:
            notes.append(
                "ignored unknown tool calls: " + ", ".join(sorted(set(adapter_report.unknown_tools)))
            )
        return notes

    @staticmethod
    def _status(validation_errors: List[str], notes: List[str]) -> str:
        """Map validation state and coverage notes onto the reported status."""

        if validation_errors:
            return "failed"
        return "partial" if notes else "success"
