"""End-to-end integration test for the sector-report agent (Phase 2b).

No network access and no ``anthropic`` dependency: the Claude conversation is
driven by the shared scripted fake client from ``tests/analyst_agent_fakes``.
Workspaces are real ones, created by the real sector-primer initializer (via
``SectorWorkspace.create`` shelling out to it) and checked by the real
sector-primer validator.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYST_SKILL = ROOT / "skills" / "analyst-agent"
SECTOR_PRIMER_SCRIPTS = ROOT / "skills" / "sector-primer" / "scripts"
TESTS_DIR = ROOT / "tests"
for _path in (ANALYST_SKILL, SECTOR_PRIMER_SCRIPTS, TESTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sector_evidence  # noqa: E402
import sector_report_render  # noqa: E402
import validate_sector_workspace  # noqa: E402
from sector_report import SectorReportAgent, SectorReportError  # noqa: E402
from sector_workspace import SectorWorkspace, SectorWorkspaceError  # noqa: E402
from sector_workspace_adapter import update_sector_workspace_from_claude  # noqa: E402
from agent_common import ToolResult  # noqa: E402

from analyst_agent_fakes import (  # noqa: E402
    FakeAnthropicClient,
    FakeBlock,
    FakeResponse,
    tool,
    text,
)

SECTOR_NAME = "Semiconductors"
GEOGRAPHY = "Global"

# Source ids Claude sees in the evidence catalogue, in the fixed order
# `sector_evidence._synthesize_evidence` emits its sources list: overview,
# peer multiples, macro snapshot, capacity review, trade watch.
SRC_OVERVIEW = "SRC-0001"
SRC_PEER_MULTIPLES = "SRC-0002"
SRC_MACRO = "SRC-0003"
SRC_CAPACITY = "SRC-0004"
SRC_TRADE = "SRC-0005"


def _peer_tool(ticker, company, pe_ratio, identifier, eps_revision_trend="up"):
    return tool(
        "record_peer_benchmark",
        {
            "ticker": ticker,
            "company": company,
            "revenue": 1200.0,
            "revenue_unit": "USD m",
            "eps_growth_pct": 8.0,
            "pe_ratio": pe_ratio,
            "ev_ebitda": round(pe_ratio * 0.6, 1),
            "roic_pct": 14.0,
            "quality_tier": "Tier 2 - core holding",
            "eps_revision_trend": eps_revision_trend,
            "source_ids": [SRC_PEER_MULTIPLES],
        },
        identifier,
    )


def _scripted_turns():
    """A realistic two-turn sector analysis, then a closing turn with no tool calls."""

    first = FakeResponse(
        [
            tool(
                "record_source",
                {
                    "title": f"{SECTOR_NAME} Market Size and Forecast, {GEOGRAPHY}",
                    "url": "https://industrydata.example.com/semiconductors/market-size",
                    "date": "2026-08-23",
                    "extract": "TAM estimated with a mid-single-digit forward CAGR.",
                },
                "tu_01",
            ),
            tool(
                "record_sector_overview",
                {
                    "tam_size": "$620bn",
                    "forward_cagr_pct": 7.5,
                    "growth_drivers": [
                        "AI accelerator demand outpacing prior capex cycles",
                        "share gains by scaled foundries as sub-scale fabs exit",
                    ],
                    "capacity_cycle_note": "Leading-edge capacity remains tight through the forward window.",
                    "source_ids": [SRC_OVERVIEW],
                },
                "tu_02",
            ),
            tool(
                "record_value_chain_segment",
                {
                    "segment_name": "Equipment and materials",
                    "position": "upstream",
                    "gross_margin_pct": 45.0,
                    "operating_margin_pct": 22.0,
                    "roic_estimate_pct": 18.0,
                    "moat": "Process-tool qualification cycles lock in incumbent equipment suppliers.",
                    "key_risk": "Export-control regimes can abruptly cut off a customer segment.",
                    "source_ids": [SRC_CAPACITY],
                },
                "tu_03",
            ),
            tool(
                "record_value_chain_segment",
                {
                    "segment_name": "Foundry and fabrication",
                    "position": "core",
                    "gross_margin_pct": 52.0,
                    "operating_margin_pct": 35.0,
                    "roic_estimate_pct": 24.0,
                    "moat": "Leading-edge process scale is a multi-year, multi-billion-dollar barrier to replicate.",
                    "key_risk": "A demand air pocket after a capacity build leaves fixed costs under-absorbed.",
                    "source_ids": [SRC_CAPACITY],
                },
                "tu_04",
            ),
            tool(
                "record_value_chain_segment",
                {
                    "segment_name": "Design and IP licensing",
                    "position": "downstream",
                    "gross_margin_pct": 65.0,
                    "operating_margin_pct": 38.0,
                    "roic_estimate_pct": 40.0,
                    "moat": "Architecture licensing and software ecosystems create high switching costs for customers.",
                    "key_risk": "A well-funded challenger architecture could fragment the licensing base.",
                    "source_ids": [SRC_OVERVIEW],
                },
                "tu_05",
            ),
            _peer_tool("SEMI1", "Northgate Semiconductors", 12.0, "tu_06", "up"),
            _peer_tool("SEMI2", "Meridian Semiconductors", 15.0, "tu_07", "flat"),
            _peer_tool("SEMI3", "Vantage Semiconductors", 18.0, "tu_08", "up"),
            _peer_tool("SEMI4", "Summit Semiconductors", 20.0, "tu_09", "down"),
            _peer_tool("SEMI5", "Atlas Semiconductors", 24.0, "tu_10", "down"),
        ],
        "tool_use",
    )

    second = FakeResponse(
        [
            tool(
                "record_valuation",
                {
                    "verdict": "attractive",
                    "growth_outlook": "accelerating",
                    "risk_reward": "Asymmetric upside if AI-driven demand persists, capped downside given tight capacity.",
                    "sector_multiple": 16.0,
                    "historical_avg_multiple": 14.0,
                    "rationale": "Current multiple sits modestly above history but growth has re-accelerated.",
                    "source_ids": [SRC_PEER_MULTIPLES],
                },
                "tu_11",
            ),
            tool(
                "record_catalyst",
                {
                    "name": "Next-generation node yield ramp update",
                    "date_or_timeframe": "Q1 2027",
                    "implication": "A clean ramp would support the accelerating-growth outlook.",
                    "source_ids": [SRC_CAPACITY],
                },
                "tu_12",
            ),
            tool(
                "record_catalyst",
                {
                    "name": "Major hyperscaler capex guidance update",
                    "date_or_timeframe": "next 2 quarters",
                    "implication": "A cut to capex guidance would be the clearest signal the cycle is turning.",
                    "source_ids": [SRC_OVERVIEW],
                },
                "tu_13",
            ),
            tool(
                "record_catalyst",
                {
                    "name": "Export-control policy review",
                    "date_or_timeframe": "next 6 months",
                    "implication": "Tighter controls would pressure the equipment segment's addressable market.",
                    "source_ids": [SRC_TRADE],
                },
                "tu_14",
            ),
            tool(
                "flag_analysis_gap",
                {
                    "category": "Peer Coverage",
                    "description": "No pure-play memory peer is included; DRAM/NAND cyclicality is not separately sized.",
                },
                "tu_15",
            ),
            tool(
                "flag_contradiction",
                {
                    "field1": "Accelerating forward CAGR",
                    "field2": "High recession sensitivity recorded for the sector",
                    "description": "A cyclical downturn would contradict the accelerating growth outlook within the forward window.",
                },
                "tu_16",
            ),
        ],
        "tool_use",
    )

    return [first, second, FakeResponse([FakeBlock("text", text="Analysis complete.")], "end_turn")]


class SectorReportEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace_path = self.root / "SEMI-SECTOR"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _agent(self, turns=None) -> SectorReportAgent:
        return SectorReportAgent(
            workspace_root=str(self.workspace_path),
            anthropic_api_key="test-key-not-used",
            client=FakeAnthropicClient(turns if turns is not None else _scripted_turns()),
        )

    # ------------------------------------------------------------------
    # New-workspace end-to-end run
    # ------------------------------------------------------------------

    def test_sector_report_creates_workspace_end_to_end(self) -> None:
        self.assertFalse(self.workspace_path.exists())
        agent = self._agent()
        result = agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)

        for key in (
            "workspace_path",
            "sector_report_markdown",
            "peer_universe_count",
            "valuation_spread_pct",
            "status",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["workspace_path"], str(self.workspace_path))
        self.assertEqual(result["status"], "success", result.get("notes"))

        # Workspace was created with the sector-primer shape.
        self.assertTrue((self.workspace_path / "project.json").is_file())
        workspace = SectorWorkspace.load(self.workspace_path)
        self.assertEqual(workspace.sector_name, SECTOR_NAME)
        self.assertEqual(workspace.geography, GEOGRAPHY)

        # Acceptance criteria: >=3 segments, >=5 peers auto-detected, >=2 tailwinds,
        # a recorded verdict, >=3 catalysts, >=2 sources.
        self.assertGreaterEqual(len(workspace.ledger_by_type("value_chain_segment")), 3)
        self.assertGreaterEqual(result["peer_universe_count"], 5)
        tailwinds = [d for d in workspace.ledger_by_type("structural_driver") if d.get("kind") == "tailwind"]
        self.assertGreaterEqual(len(tailwinds), 2)
        self.assertEqual(len(workspace.ledger_by_type("sector_valuation")), 1)
        self.assertGreaterEqual(len(workspace.ledger_by_type("catalyst")), 3)
        self.assertGreaterEqual(len(workspace.sources), 2)

        # Peer P/E spread: max 24.0 / min 12.0 - 1 = 100%.
        self.assertAlmostEqual(result["valuation_spread_pct"], 100.0, places=2)

        # Structurally valid per the real sector-primer validator.
        self.assertEqual(validate_sector_workspace.validate(self.workspace_path), [])
        self.assertEqual(workspace.validate(), [])

        # The report is written to the pre-existing placeholder path.
        report_path = self.workspace_path / "outputs" / "sector-primer.md"
        self.assertTrue(report_path.is_file())
        self.assertEqual(report_path.read_text(encoding="utf-8"), result["sector_report_markdown"])

    def test_report_has_all_eight_sections_with_real_content(self) -> None:
        agent = self._agent()
        result = agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        report = result["sector_report_markdown"]

        for heading in (
            "## I. Sector Size and Growth",
            "## II. Value-Chain Economics",
            "## III. Peer Comparative Analysis",
            "## IV. Structural Drivers",
            "## V. Cyclicality and Recession Sensitivity",
            "## VI. Valuation Summary",
            "## VII. Sector Catalyst Calendar",
            "## VIII. Risk Summary",
        ):
            self.assertIn(heading, report)

        # Real content, not placeholders: recorded figures surface verbatim.
        self.assertIn("$620bn", report)
        self.assertIn("Foundry and fabrication", report)
        self.assertIn("SEMI1", report)
        self.assertIn("ATTRACTIVE", report)
        self.assertIn("Next-generation node yield ramp update", report)
        # Gaps and contradictions are surfaced, not smoothed away.
        self.assertIn("Peer Coverage", report)
        self.assertIn("recorded unresolved", report)
        self.assertIn("Accelerating forward CAGR", report)
        # Mock-data provenance is disclosed.
        self.assertIn("mock data", report)
        # Catalyst calendar is a table.
        self.assertIn("| Date / timeframe | Event | Implication |", report)
        # Per-peer derived calls appear, not asserted independently of state.
        self.assertIn("Derived call", report)

    def test_peer_comparative_table_has_at_least_five_metrics(self) -> None:
        agent = self._agent()
        result = agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        report = result["sector_report_markdown"]
        header_line = next(line for line in report.splitlines() if line.startswith("| Ticker |"))
        for metric in ("Revenue", "EPS growth", "P/E", "EV/EBITDA", "ROIC"):
            self.assertIn(metric, header_line)

    def test_verdict_is_sourced_from_recorded_tool_call_not_asserted(self) -> None:
        agent = self._agent()
        agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        workspace = agent.workspace
        valuations = workspace.ledger_by_type("sector_valuation")
        self.assertEqual(len(valuations), 1)
        self.assertEqual(valuations[0]["verdict"], "attractive")
        self.assertEqual(valuations[0]["growth_outlook"], "accelerating")

    # ------------------------------------------------------------------
    # Existing-workspace load path
    # ------------------------------------------------------------------

    def test_rerun_against_existing_workspace_loads_and_revises(self) -> None:
        first_agent = self._agent()
        first_result = first_agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        first_source_count = len(SectorWorkspace.load(self.workspace_path).sources)

        second_agent = self._agent(turns=_scripted_turns())
        second_result = second_agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)

        self.assertEqual(second_result["status"], "success", second_result.get("notes"))
        workspace = SectorWorkspace.load(self.workspace_path)
        # Sources are idempotent by title/url, so re-registering the same
        # evidence does not duplicate the registry.
        self.assertEqual(len(workspace.sources), first_source_count)
        # A second analytical pass adds a second generation of records.
        self.assertEqual(len(workspace.ledger_by_type("sector_valuation")), 2)
        self.assertEqual(validate_sector_workspace.validate(self.workspace_path), [])
        self.assertNotEqual(first_result["report_path"], None)

    def test_sector_name_mismatch_against_existing_workspace_is_refused(self) -> None:
        agent = self._agent()
        agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)

        other_agent = self._agent(turns=_scripted_turns())
        with self.assertRaises(ValueError):
            other_agent.sector_report(sector_name="Airlines", geography=GEOGRAPHY)

    # ------------------------------------------------------------------
    # Explicit peer universe (auto-detect minimum does not apply)
    # ------------------------------------------------------------------

    def test_explicit_peer_universe_smaller_than_auto_minimum_is_accepted(self) -> None:
        turns = [
            FakeResponse(
                [
                    _peer_tool("AAA", "Alpha Corp", 10.0, "tu_01"),
                    _peer_tool("BBB", "Beta Corp", 20.0, "tu_02"),
                ],
                "tool_use",
            ),
            FakeResponse([FakeBlock("text", text="done")], "end_turn"),
        ]
        agent = self._agent(turns=turns)
        result = agent.sector_report(
            sector_name=SECTOR_NAME, geography=GEOGRAPHY, peer_universe=["AAA", "BBB"]
        )
        self.assertEqual(result["peer_universe_count"], 2)
        self.assertAlmostEqual(result["valuation_spread_pct"], 100.0, places=2)
        # Not enough for a full sector report, but not a workspace-validity failure.
        self.assertIn("status", result)
        self.assertNotEqual(result["status"], "failed")

    # ------------------------------------------------------------------
    # Failure modes
    # ------------------------------------------------------------------

    def test_run_without_tool_calls_raises(self) -> None:
        agent = self._agent(turns=[FakeResponse([FakeBlock("text", text="No.")], "end_turn")])
        with self.assertRaises(SectorReportError):
            agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)

    def test_empty_sector_name_is_refused(self) -> None:
        agent = self._agent()
        with self.assertRaises(ValueError):
            agent.sector_report(sector_name="   ", geography=GEOGRAPHY)

    def test_pause_turn_is_resumed(self) -> None:
        turns = _scripted_turns()
        paused = FakeResponse([FakeBlock("text", text="working")], "pause_turn")
        agent = self._agent(turns=[paused] + turns)
        result = agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        self.assertEqual(result["status"], "success", result.get("notes"))

    def test_agent_never_imports_anthropic_when_client_supplied(self) -> None:
        sys.modules.pop("anthropic", None)
        agent = self._agent()
        agent.sector_report(sector_name=SECTOR_NAME, geography=GEOGRAPHY)
        self.assertNotIn("anthropic", sys.modules)


class SectorWorkspaceTest(unittest.TestCase):
    """Workspace-level behaviour that the happy path does not exercise."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.temporary.name) / "SEMI"
        self.workspace = SectorWorkspace.create(self.workspace_path, sector_name=SECTOR_NAME, geography=GEOGRAPHY)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_produces_a_structurally_valid_workspace(self) -> None:
        self.assertEqual(validate_sector_workspace.validate(self.workspace_path), [])
        self.assertEqual(self.workspace.assumptions, [])
        self.assertEqual(self.workspace.contradictions, [])

    def test_load_rejects_non_sector_workspace(self) -> None:
        other = Path(tempfile.mkdtemp())
        (other / "project.json").write_text('{"workspace_type": "v2"}', encoding="utf-8")
        with self.assertRaises(SectorWorkspaceError):
            SectorWorkspace.load(other)

    def test_source_registration_is_idempotent(self) -> None:
        first = self.workspace.add_source("Report", "https://example.com")
        second = self.workspace.add_source("Report", "https://example.com")
        self.assertEqual(first, second)
        self.assertEqual(len(self.workspace.sources), 1)

    def test_sources_are_applied_before_records_that_cite_them(self) -> None:
        calls = [
            ToolResult(
                "record_sector_overview",
                {
                    "tam_size": "$10bn",
                    "forward_cagr_pct": 5.0,
                    "growth_drivers": ["a", "b"],
                    "capacity_cycle_note": "note",
                    "source_ids": ["SRC-0001"],
                },
                "tu_1",
            ),
            ToolResult(
                "record_source",
                {"title": "Report", "url": "https://example.com", "date": "", "extract": "x"},
                "tu_2",
            ),
        ]
        report = update_sector_workspace_from_claude(self.workspace, calls)
        self.workspace.save()
        self.assertEqual(report.dropped_source_links, [])
        overview = self.workspace.ledger_by_type("sector_overview")[0]
        self.assertEqual(overview["source_ids"], ["SRC-0001"])

    def test_unknown_source_link_is_dropped_not_raised(self) -> None:
        calls = [
            ToolResult(
                "record_source",
                {"title": "Report", "url": "https://example.com", "date": "", "extract": "x"},
                "tu_1",
            ),
            ToolResult(
                "record_value_chain_segment",
                {
                    "segment_name": "Core",
                    "position": "core",
                    "gross_margin_pct": 30.0,
                    "operating_margin_pct": 15.0,
                    "roic_estimate_pct": 12.0,
                    "moat": "m",
                    "key_risk": "r",
                    "source_ids": ["SRC-9999"],
                },
                "tu_2",
            ),
        ]
        report = update_sector_workspace_from_claude(self.workspace, calls)
        self.workspace.save()
        self.assertEqual(len(report.dropped_source_links), 1)
        self.assertIn("SRC-9999", report.dropped_source_links[0])
        self.assertFalse(report.clean)
        self.assertEqual(validate_sector_workspace.validate(self.workspace_path), [])

    def test_unknown_tool_is_reported_not_applied(self) -> None:
        report = update_sector_workspace_from_claude(
            self.workspace, [ToolResult("record_vibe", {"mood": "bullish"}, "tu_1")]
        )
        self.assertEqual(report.unknown_tools, ["record_vibe"])
        self.assertEqual(self.workspace.ledger, [])

    def test_malformed_date_becomes_null_not_invalid_state(self) -> None:
        self.workspace.add_source("Report", "https://example.com", date="Q3 2025")
        self.workspace.save()
        self.assertIsNone(self.workspace.sources[0]["publication_date"])
        self.assertEqual(validate_sector_workspace.validate(self.workspace_path), [])


class SectorEvidenceTest(unittest.TestCase):
    def test_evidence_has_every_required_key(self) -> None:
        evidence = sector_evidence.fetch_sector_evidence(SECTOR_NAME, GEOGRAPHY)
        for key in sector_evidence.REQUIRED_EVIDENCE_KEYS:
            self.assertIn(key, evidence)
        self.assertGreaterEqual(len(evidence["peers"]), 5)
        self.assertGreaterEqual(len(evidence["value_chain"]), 3)

    def test_evidence_is_deterministic_across_calls(self) -> None:
        import json

        first = sector_evidence.fetch_sector_evidence(SECTOR_NAME, GEOGRAPHY)
        second = sector_evidence.fetch_sector_evidence(SECTOR_NAME, GEOGRAPHY)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_empty_sector_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            sector_evidence.fetch_sector_evidence("", GEOGRAPHY)

    def test_explicit_peer_universe_is_honored(self) -> None:
        evidence = sector_evidence.fetch_sector_evidence(SECTOR_NAME, GEOGRAPHY, peer_universe=["AAA", "BBB"])
        tickers = [peer["ticker"] for peer in evidence["peers"]]
        self.assertEqual(tickers, ["AAA", "BBB"])


class SectorReportRenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.temporary.name) / "SEMI"
        self.workspace = SectorWorkspace.create(self.workspace_path, sector_name=SECTOR_NAME, geography=GEOGRAPHY)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_empty_workspace_renders_absence_explicitly(self) -> None:
        report = sector_report_render.render_sector_report_markdown(self.workspace)
        self.assertIn("## I. Sector Size and Growth", report)
        self.assertIn("No sector overview is recorded", report)
        self.assertIn("No peer benchmarks are recorded", report)
        self.assertIn("No sources are recorded", report)


if __name__ == "__main__":
    unittest.main()
