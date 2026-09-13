"""End-to-end integration test for the analyst-agent orchestrator.

No network access and no ``anthropic`` dependency: the Claude conversation is
driven by a scripted fake client that returns the same content-block shapes the
SDK does. The workspace is a real one, created by the real initializer and
checked by the real validator.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_SCRIPTS = ROOT / "skills" / "persistent-equity-research" / "scripts"
ANALYST_SKILL = ROOT / "skills" / "analyst-agent"
sys.path.insert(0, str(ANALYST_SKILL))
sys.path.insert(0, str(PERSISTENT_SCRIPTS))

import data_sources  # noqa: E402
import report_generators  # noqa: E402
from orchestrator import AnalystAgent, AnalystAgentError  # noqa: E402
from workspace_adapter import (  # noqa: E402
    ResearchWorkspace,
    ToolResult,
    update_workspace_from_claude,
)
from workspace_lib import validate_workspace  # noqa: E402

INIT = PERSISTENT_SCRIPTS / "init_workspace.py"


# ----------------------------------------------------------------------
# Fake Anthropic client
# ----------------------------------------------------------------------


class FakeBlock:
    """Stand-in for an SDK content block."""

    def __init__(self, type, name=None, input=None, id=None, text=None):
        self.type = type
        self.name = name
        self.input = input
        self.id = id
        self.text = text


class FakeResponse:
    """Stand-in for an SDK ``Message``."""

    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._turns:
            return FakeResponse([FakeBlock("text", text="Done.")], "end_turn")
        return self._turns.pop(0)


class FakeAnthropicClient:
    """Minimal object exposing the one method the orchestrator calls."""

    def __init__(self, turns):
        self.messages = FakeMessages(turns)


def _tool(name, payload, identifier):
    return FakeBlock("tool_use", name=name, input=payload, id=identifier)


def _scripted_turns():
    """A realistic two-turn analysis, then a closing turn with no tool calls."""

    first = FakeResponse(
        [
            _tool(
                "record_source",
                {
                    "title": "Acme Corp Annual Report FY2025",
                    "url": "https://investor.example.com/acme/annual-report",
                    "date": "2025-06-09",
                    "extract": "Five-year revenue CAGR of 6.1%.",
                },
                "tu_01",
            ),
            _tool(
                "record_assumption",
                {
                    "name": "Revenue CAGR 5-Year Forward",
                    "value": "5.5%",
                    "units": "percent",
                    "rationale": "Below guidance, reflecting distributor destocking.",
                    "source_ids": ["SRC-0001", "SRC-0002"],
                },
                "tu_02",
            ),
            _tool(
                "record_assumption",
                {
                    "name": "EBIT Margin FY2028",
                    "value": "14.1%",
                    "units": "percent",
                    "rationale": "Aftermarket mix shift offsets capacity start-up costs.",
                    "source_ids": ["SRC-0001"],
                },
                "tu_03",
            ),
            _tool(
                "record_assumption",
                {
                    "name": "Target Forward P/E",
                    "value": "16.5x",
                    "units": "x",
                    "rationale": "Mid-peer multiple; ROIC above Cobalt, below Meridian.",
                    "source_ids": ["SRC-0003"],
                },
                "tu_04",
            ),
            _tool(
                "record_assumption",
                {
                    "name": "WACC",
                    "value": "9.0%",
                    "units": "percent",
                    "rationale": "3.75% policy rate plus an equity risk premium for cyclicality.",
                    "source_ids": ["SRC-0004"],
                },
                "tu_05",
            ),
            _tool(
                "record_valuation",
                {
                    "method": "Peer Multiple (P/E)",
                    "inputs": [
                        {"name": "peer_median_pe", "value": "17.4"},
                        {"name": "target_pe", "value": "16.5"},
                        {"name": "fy2_eps", "value": "2.61"},
                    ],
                    "output": {"low": 36.5, "base": 43.1, "high": 49.8},
                },
                "tu_06",
            ),
            _tool(
                "record_valuation",
                {
                    "method": "DCF",
                    "inputs": [
                        {"name": "wacc", "value": "9.0%"},
                        {"name": "terminal_growth", "value": "2.5%"},
                        {"name": "forecast_years", "value": "10"},
                    ],
                    "output": {"low": 34.0, "base": 44.6, "high": 55.2},
                },
                "tu_07",
            ),
        ],
        "tool_use",
    )

    second = FakeResponse(
        [
            _tool(
                "record_scenario",
                {
                    "name": "Base",
                    "assumptions": [
                        {"name": "revenue_cagr", "value": "5.5%"},
                        {"name": "ebit_margin", "value": "14.1%"},
                    ],
                    "valuation": "Blend of 16.5x FY2 EPS and DCF at 9.0% WACC",
                    "price_target": 44.0,
                    "weight": 0.5,
                },
                "tu_08",
            ),
            _tool(
                "record_scenario",
                {
                    "name": "Bull",
                    "assumptions": [
                        {"name": "revenue_cagr", "value": "8.0%"},
                        {"name": "ebit_margin", "value": "15.4%"},
                    ],
                    "valuation": "18.5x FY2 EPS on aftermarket re-rating",
                    "price_target": 55.0,
                    "weight": 0.25,
                },
                "tu_09",
            ),
            _tool(
                "record_scenario",
                {
                    "name": "Bear",
                    "assumptions": [
                        {"name": "revenue_cagr", "value": "2.0%"},
                        {"name": "ebit_margin", "value": "11.8%"},
                    ],
                    "valuation": "13.0x depressed FY2 EPS",
                    "price_target": 31.0,
                    "weight": 0.25,
                },
                "tu_10",
            ),
            _tool(
                "record_catalyst",
                {
                    "name": "FY2026 guidance reset at Q1 results",
                    "timeframe": "next 3 months",
                    "direction": "downside",
                    "magnitude_estimate_pct": -8.0,
                },
                "tu_11",
            ),
            _tool(
                "record_catalyst",
                {
                    "name": "New plant commissioning ahead of schedule",
                    "timeframe": "next 9 months",
                    "direction": "upside",
                    "magnitude_estimate_pct": 6.0,
                },
                "tu_12",
            ),
            _tool(
                "record_catalyst",
                {
                    "name": "Distributor restocking completes",
                    "timeframe": "6-12 months",
                    "direction": "upside",
                    "magnitude_estimate_pct": 5.0,
                },
                "tu_13",
            ),
            _tool(
                "flag_analysis_gap",
                {
                    "category": "Segment Detail",
                    "description": "No geographic revenue split; Europe exposure cannot be sized.",
                },
                "tu_14",
            ),
            _tool(
                "flag_contradiction",
                {
                    "field1": "FY2026 revenue guidance",
                    "field2": "Five-year historical revenue CAGR",
                    "description": (
                        "Guidance implies acceleration while channel checks show destocking."
                    ),
                },
                "tu_15",
            ),
        ],
        "tool_use",
    )

    return [first, second, FakeResponse([FakeBlock("text", text="Analysis complete.")], "end_turn")]


class AnalystAgentEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace_path = self.root / "ACME"
        result = subprocess.run(
            [
                sys.executable,
                str(INIT),
                "--workspace", str(self.workspace_path),
                "--ticker", "ACME",
                "--company-name", "Acme Corp",
                "--exchange", "TEST",
                "--benchmark", "Synthetic 100",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _agent(self, turns=None) -> AnalystAgent:
        return AnalystAgent(
            workspace_root=str(self.workspace_path),
            anthropic_api_key="test-key-not-used",
            client=FakeAnthropicClient(turns if turns is not None else _scripted_turns()),
        )

    def test_initiate_coverage_end_to_end(self) -> None:
        agent = self._agent()
        result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")

        # 1. Returns a dict with every key the specification requires.
        for key in (
            "workspace_path",
            "report_markdown",
            "evidence_count",
            "state_ledger_keys",
            "status",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["workspace_path"], str(self.workspace_path))
        self.assertEqual(result["status"], "success", result.get("notes"))
        self.assertEqual(result["validation_errors"], [])

        # 2. Workspace ledger thresholds: >=3 assumptions, >=1 valuation, >=2 sources.
        workspace = ResearchWorkspace.load(self.workspace_path)
        self.assertGreaterEqual(len(workspace.assumptions["assumptions"]), 3)
        self.assertGreaterEqual(result["tool_calls"]["record_valuation"], 1)
        self.assertGreaterEqual(len(workspace.sources), 2)
        self.assertEqual(result["evidence_count"], len(workspace.sources))
        self.assertEqual(len(workspace.assumptions["scenario_overrides"]), 3)

        # 3. State ledger keys reflect what was actually written.
        for key in ("sources", "ledger", "assumptions", "scenario_overrides", "valuation"):
            self.assertIn(key, result["state_ledger_keys"])

        # 4. The workspace still validates under the persistent-equity-research rules.
        validation = validate_workspace(self.workspace_path)
        self.assertTrue(validation.valid, validation.errors)

        # 5. The report is non-empty and structurally complete.
        report = result["report_markdown"]
        self.assertTrue(report.strip())
        for heading in (
            "# Acme Corp (ACME)",
            "## Initiation of Coverage",
            "## 1. Investment Thesis",
            "## 2. Company Overview and Business Model",
            "## 3. Valuation Summary",
            "## 4. Key Assumptions",
            "## 5. Bull, Base, and Bear Cases",
            "## 6. Catalysts, Risks, and Open Questions",
            "## 7. Methodology and Research Limitations",
            "## 8. Source Appendix",
        ):
            self.assertIn(heading, report)

        # 6. The report is written into the workspace as a publication view.
        report_path = self.workspace_path / "outputs" / "initiation-of-coverage.md"
        self.assertTrue(report_path.is_file())
        self.assertEqual(report_path.read_text(encoding="utf-8"), report)

    def test_report_carries_state_not_invention(self) -> None:
        agent = self._agent()
        result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")
        report = result["report_markdown"]

        # Recorded values surface verbatim.
        self.assertIn("Revenue CAGR 5-Year Forward", report)
        self.assertIn("DCF", report)
        self.assertIn("Peer Multiple (P/E)", report)
        # The contradiction is surfaced, not averaged away.
        self.assertIn("FY2026 revenue guidance", report)
        self.assertIn("recorded unresolved", report)
        # The gap is visible.
        self.assertIn("Segment Detail", report)
        # Mock-data provenance is disclosed rather than implied to be real.
        self.assertIn("mock data", report)
        # Uncovered analytical lenses are declared, not silently dropped.
        self.assertIn("Reverse expectations analysis", report)

    def test_probability_weighted_target_is_derived_from_recorded_weights(self) -> None:
        agent = self._agent()
        result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")
        # 0.5*44.0 + 0.25*55.0 + 0.25*31.0 = 43.5
        self.assertIn("43.50", result["report_markdown"])

    def test_ticker_mismatch_is_refused(self) -> None:
        agent = self._agent()
        with self.assertRaises(ValueError):
            agent.initiate_coverage(ticker="OTHER", company_name="Other Corp")

    def test_run_without_tool_calls_raises(self) -> None:
        agent = self._agent(turns=[FakeResponse([FakeBlock("text", text="No.")], "end_turn")])
        with self.assertRaises(AnalystAgentError):
            agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")

    def test_pause_turn_is_resumed(self) -> None:
        turns = _scripted_turns()
        paused = FakeResponse([FakeBlock("text", text="working")], "pause_turn")
        agent = self._agent(turns=[paused] + turns)
        result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")
        self.assertEqual(result["status"], "success", result.get("notes"))

    def test_agent_never_imports_anthropic_when_client_supplied(self) -> None:
        sys.modules.pop("anthropic", None)
        agent = self._agent()
        agent.initiate_coverage(ticker="ACME", company_name="Acme Corp")
        self.assertNotIn("anthropic", sys.modules)


class WorkspaceAdapterTest(unittest.TestCase):
    """Adapter-level behaviour that the happy path does not exercise."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.temporary.name) / "ACME"
        subprocess.run(
            [
                sys.executable, str(INIT),
                "--workspace", str(self.workspace_path),
                "--ticker", "ACME",
                "--company-name", "Acme Corp",
                "--format", "json",
            ],
            capture_output=True, text=True, check=True,
        )
        self.workspace = ResearchWorkspace.load(self.workspace_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_sources_are_applied_before_the_records_that_cite_them(self) -> None:
        """An assumption may cite a source Claude records later in the same turn."""

        calls = [
            ToolResult(
                "record_assumption",
                {
                    "name": "Revenue CAGR",
                    "value": "6%",
                    "units": "percent",
                    "rationale": "In line with history.",
                    "source_ids": ["SRC-0001"],
                },
                "tu_2",
            ),
            ToolResult(
                "record_source",
                {
                    "title": "10-K",
                    "url": "https://sec.example.gov/acme",
                    "date": "2025-02-15",
                    "extract": "5Y CAGR 6%.",
                },
                "tu_1",
            ),
        ]
        report = update_workspace_from_claude(self.workspace, calls)
        self.workspace.save()

        self.assertEqual(report.dropped_source_links, [])
        assumption = self.workspace.assumptions["assumptions"][0]
        self.assertEqual(assumption["source_ids"], ["SRC-0001"])
        self.assertTrue(validate_workspace(self.workspace_path).valid)

    def test_unknown_source_link_is_dropped_not_raised(self) -> None:
        """A hallucinated id must not make the whole workspace invalid."""

        calls = [
            ToolResult(
                "record_source",
                {"title": "10-K", "url": "https://sec.example.gov/acme", "date": "", "extract": "x"},
                "tu_1",
            ),
            ToolResult(
                "record_assumption",
                {
                    "name": "Margin",
                    "value": "14%",
                    "units": "percent",
                    "rationale": "Mix.",
                    "source_ids": ["SRC-9999"],
                },
                "tu_2",
            ),
        ]
        report = update_workspace_from_claude(self.workspace, calls)
        self.workspace.save()

        self.assertEqual(len(report.dropped_source_links), 1)
        self.assertIn("SRC-9999", report.dropped_source_links[0])
        self.assertFalse(report.clean)
        self.assertTrue(validate_workspace(self.workspace_path).valid)

    def test_source_registration_is_idempotent(self) -> None:
        first = self.workspace.add_source("10-K", "https://sec.example.gov/acme")
        second = self.workspace.add_source("10-K", "https://sec.example.gov/acme")
        self.assertEqual(first, second)
        self.assertEqual(len(self.workspace.sources), 1)

    def test_unknown_tool_is_reported_not_applied(self) -> None:
        report = update_workspace_from_claude(
            self.workspace, [ToolResult("record_vibe", {"mood": "bullish"}, "tu_1")]
        )
        self.assertEqual(report.unknown_tools, ["record_vibe"])
        self.assertEqual(self.workspace.ledger, [])

    def test_malformed_date_becomes_null_not_invalid_state(self) -> None:
        self.workspace.add_source("Report", "https://example.com", date="Q3 2025")
        self.workspace.save()
        self.assertIsNone(self.workspace.sources[0]["publication_date"])
        self.assertTrue(validate_workspace(self.workspace_path).valid)


class EvidenceTest(unittest.TestCase):
    def test_evidence_has_every_required_key(self) -> None:
        evidence = data_sources.fetch_company_evidence("ACME", "Acme Corp")
        for key in data_sources.REQUIRED_EVIDENCE_KEYS:
            self.assertIn(key, evidence)
        self.assertTrue(evidence["sources"])
        self.assertTrue(evidence["peer_universe"])

    def test_evidence_is_deterministic_across_calls(self) -> None:
        first = data_sources.fetch_company_evidence("ACME", "Acme Corp")
        second = data_sources.fetch_company_evidence("ACME", "Acme Corp")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_empty_ticker_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            data_sources.fetch_company_evidence("", "Acme Corp")

    def test_source_limit_is_applied(self) -> None:
        evidence = data_sources.fetch_company_evidence("ACME", "Acme Corp")
        self.assertEqual(len(data_sources.limit_sources(evidence, 2)), 2)
        self.assertEqual(data_sources.limit_sources(evidence, 0), [])


class ReportGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace_path = Path(self.temporary.name) / "ACME"
        subprocess.run(
            [
                sys.executable, str(INIT),
                "--workspace", str(self.workspace_path),
                "--ticker", "ACME",
                "--company-name", "Acme Corp",
                "--format", "json",
            ],
            capture_output=True, text=True, check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_empty_workspace_renders_absence_explicitly(self) -> None:
        """An empty state must say sections are missing, not fabricate them."""

        workspace = ResearchWorkspace.load(self.workspace_path)
        report = report_generators.initiation_report_markdown(workspace)
        self.assertIn("## 1. Investment Thesis", report)
        self.assertIn("No thesis is recorded in workspace state", report)
        self.assertIn("No valuation is recorded", report)
        self.assertIn("No sources are recorded", report)


if __name__ == "__main__":
    unittest.main()
