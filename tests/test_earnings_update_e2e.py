"""End-to-end integration test for the analyst-agent earnings-update report type.

No network access and no ``anthropic`` dependency: the Claude conversation is
driven by the shared scripted fake client from ``tests/analyst_agent_fakes.py``.
The workspace is a real one, created by the real ``init_workspace.py`` and
hand-seeded (via ``workspace_adapter.ResearchWorkspace``) with a prior thesis,
so this module exercises revising an existing workspace rather than creating
one.
"""

from __future__ import annotations

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
sys.path.insert(0, str(ROOT))

import earnings_evidence  # noqa: E402
from earnings_update import EarningsUpdateAgent, EarningsUpdateError, determine_verdict  # noqa: E402
from workspace_adapter import ResearchWorkspace  # noqa: E402
from workspace_lib import validate_workspace  # noqa: E402

from tests.analyst_agent_fakes import (  # noqa: E402
    FakeAnthropicClient,
    FakeBlock,
    FakeResponse,
    text,
    tool,
)

INIT = PERSISTENT_SCRIPTS / "init_workspace.py"

EARNINGS_DATE = "2026-04-15"


def _seed_prior_thesis(workspace: ResearchWorkspace) -> None:
    """Write a prior initiation-style thesis directly, without a live Claude run.

    Mirrors the state an ``AnalystAgent.initiate_coverage`` run would have
    produced: three active assumptions, two valuation methods, three
    scenarios, and one catalyst of each kind (already-occurred vs. still
    ahead), plus one open gap and one open contradiction.
    """

    source_id = workspace.add_source(
        title="Acme Corp Annual Report FY2025",
        url="https://investor.example.com/acme/annual-report",
        date="2025-06-09",
        extract="Five-year revenue CAGR of 6.1%.",
    )
    assert source_id == "SRC-0001"

    workspace.add_assumption(
        name="Revenue CAGR 5-Year Forward",
        base="5.5%",
        units="percent",
        rationale="Below guidance, reflecting distributor destocking.",
        source_ids=[source_id],
    )
    workspace.add_assumption(
        name="EBIT Margin FY2028",
        base="14.1%",
        units="percent",
        rationale="Aftermarket mix shift offsets capacity start-up costs.",
        source_ids=[source_id],
    )
    workspace.add_assumption(
        name="Target Forward P/E",
        base="16.5x",
        units="x",
        rationale="Mid-peer multiple; ROIC above Cobalt, below Meridian.",
        source_ids=[source_id],
    )

    workspace.add_valuation_row(
        scenario="base", method="Peer Multiple (P/E)", implied_price=43.1, assumption_set="base",
        notes="peer_median_pe=17.4; target_pe=16.5",
    )
    workspace.add_valuation_row(
        scenario="base", method="DCF", implied_price=44.6, assumption_set="base",
        notes="wacc=9.0%; terminal_growth=2.5%",
    )

    workspace.set_scenario_override(
        "Base",
        {
            "assumptions": {"revenue_cagr": "5.5%", "ebit_margin": "14.1%"},
            "valuation": "Blend of 16.5x FY2 EPS and DCF at 9.0% WACC",
            "price_target": 44.0,
            "weight": 0.5,
        },
    )
    workspace.set_scenario_override(
        "Bull",
        {
            "assumptions": {"revenue_cagr": "8.0%", "ebit_margin": "15.4%"},
            "valuation": "18.5x FY2 EPS on aftermarket re-rating",
            "price_target": 55.0,
            "weight": 0.25,
        },
    )
    workspace.set_scenario_override(
        "Bear",
        {
            "assumptions": {"revenue_cagr": "2.0%", "ebit_margin": "11.8%"},
            "valuation": "13.0x depressed FY2 EPS",
            "price_target": 31.0,
            "weight": 0.25,
        },
    )

    # A catalyst tied to this quarter's own release -- must be superseded.
    workspace.add_ledger_record(
        record_type="catalyst",
        statement="FY2026 guidance reset at Q1 results (downside, next 3 months).",
        confidence="medium",
        nodes=["strategist_dashboard"],
        metric="FY2026 guidance reset at Q1 results",
        value=-8.0,
        unit="percent",
        period="next 3 months",
        notes="direction=downside",
    )
    # A catalyst unrelated to this release -- should still be ahead afterwards.
    workspace.add_ledger_record(
        record_type="catalyst",
        statement="New plant commissioning ahead of schedule (upside, next 9 months).",
        confidence="medium",
        nodes=["strategist_dashboard"],
        metric="New plant commissioning ahead of schedule",
        value=6.0,
        unit="percent",
        period="next 9 months",
        notes="direction=upside",
    )

    workspace.add_ledger_record(
        record_type="research_gap",
        statement="[Segment Detail] No geographic revenue split; Europe exposure cannot be sized.",
        confidence="medium",
        status="unresolved",
        nodes=["source_ingestion"],
        metric="Segment Detail",
    )
    workspace.add_contradiction(
        summary=(
            "FY2026 revenue guidance vs Five-year historical revenue CAGR: Guidance implies "
            "acceleration while channel checks show destocking."
        ),
    )

    workspace.touch_research_update()
    workspace.save()


def _beat_and_raise_turns():
    """A beat quarter with raised guidance: revise one assumption, both valuation methods."""

    first = FakeResponse(
        [
            tool(
                "record_assumption",
                {
                    "name": "Revenue CAGR 5-Year Forward",
                    "value": "7.0%",
                    "units": "percent",
                    "rationale": "Guidance raised vs. prior +5.5% -> revised to +7.0% on backlog conversion.",
                    "source_ids": ["SRC-0001"],
                },
                "tu_01",
            ),
            tool(
                "record_valuation",
                {
                    "method": "Peer Multiple (P/E)",
                    "inputs": [
                        {"name": "peer_median_pe", "value": "17.6"},
                        {"name": "target_pe", "value": "16.7"},
                    ],
                    "output": {"low": 39.0, "base": 46.0, "high": 52.0},
                },
                "tu_02",
            ),
            tool(
                "record_valuation",
                {
                    "method": "DCF",
                    "inputs": [
                        {"name": "wacc", "value": "9.0%"},
                        {"name": "terminal_growth", "value": "2.5%"},
                    ],
                    "output": {"low": 40.0, "base": 47.0, "high": 54.0},
                },
                "tu_03",
            ),
            tool(
                "record_catalyst",
                {
                    "name": "Backlog conversion accelerates into H2",
                    "timeframe": "next 6 months",
                    "direction": "upside",
                    "magnitude_estimate_pct": 4.0,
                },
                "tu_04",
            ),
            tool(
                "flag_analysis_gap",
                {
                    "category": "New Guidance Basis",
                    "description": "Raised guidance does not disclose the new backlog conversion rate assumed.",
                },
                "tu_05",
            ),
        ],
        "tool_use",
    )
    return [first, FakeResponse([text("Analysis complete.")], "end_turn")]


class EarningsUpdateEndToEndTest(unittest.TestCase):
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
        workspace = ResearchWorkspace.load(self.workspace_path)
        _seed_prior_thesis(workspace)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _agent(self, turns=None) -> EarningsUpdateAgent:
        return EarningsUpdateAgent(
            workspace_root=str(self.workspace_path),
            anthropic_api_key="test-key-not-used",
            client=FakeAnthropicClient(turns if turns is not None else _beat_and_raise_turns()),
        )

    def test_earnings_update_end_to_end(self) -> None:
        agent = self._agent()
        result = agent.earnings_update(
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )

        # 1. Returns a dict with every key the specification requires.
        for key in (
            "workspace_path",
            "update_note_markdown",
            "assumptions_changed",
            "valuation_changed_pct",
            "verdict",
            "revised_price_target",
            "status",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["workspace_path"], str(self.workspace_path))
        self.assertEqual(result["status"], "success", result.get("notes"))
        self.assertEqual(result["validation_errors"], [])

        # 2. Beat + guidance raised -> thesis intact.
        self.assertEqual(result["verdict"], "thesis_intact")

        # 3. Exactly one assumption was revised.
        self.assertEqual(result["assumptions_changed"], 1)

        # 4. Valuation recalculated: (46.0 + 47.0) / 2 = 46.5, up from 44.0 (+5.68%).
        self.assertAlmostEqual(result["revised_price_target"], 46.5)
        self.assertAlmostEqual(result["valuation_changed_pct"], 5.68, places=2)

        # 5. The rendered note is short-form.
        word_count = len(result["update_note_markdown"].split())
        self.assertLess(word_count, 1000, f"update note is {word_count} words")

        # 6. The report is written into the workspace as a publication view.
        report_path = self.workspace_path / "outputs" / "update-note.md"
        self.assertTrue(report_path.is_file())
        self.assertEqual(report_path.read_text(encoding="utf-8"), result["update_note_markdown"])

        # 7. Workspace state: revised assumption supersedes the prior one; the
        #    other two assumptions are provably left alone.
        workspace = ResearchWorkspace.load(self.workspace_path)
        assumptions = workspace.assumptions["assumptions"]
        by_name_active = {
            a["name"]: a for a in assumptions if a["status"] == "active"
        }
        stale = [a for a in assumptions if a["status"] == "stale"]

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["name"], "Revenue CAGR 5-Year Forward")
        self.assertEqual(stale[0]["base"], "5.5%")

        self.assertIn("Revenue CAGR 5-Year Forward", by_name_active)
        self.assertEqual(by_name_active["Revenue CAGR 5-Year Forward"]["base"], "7.0%")

        # Untouched assumptions keep their original id, base value, and active status.
        self.assertEqual(by_name_active["EBIT Margin FY2028"]["id"], "ASM-0002")
        self.assertEqual(by_name_active["EBIT Margin FY2028"]["base"], "14.1%")
        self.assertEqual(by_name_active["Target Forward P/E"]["id"], "ASM-0003")
        self.assertEqual(by_name_active["Target Forward P/E"]["base"], "16.5x")

        # 8. Base scenario price target updated; weight/assumptions untouched.
        base_override = workspace.assumptions["scenario_overrides"]["Base"]
        self.assertAlmostEqual(base_override["price_target"], 46.5)
        self.assertEqual(base_override["weight"], 0.5)
        self.assertEqual(base_override["assumptions"], {"revenue_cagr": "5.5%", "ebit_margin": "14.1%"})
        # Bull/Bear are untouched (spec: do not revise unless structural change).
        self.assertEqual(workspace.assumptions["scenario_overrides"]["Bull"]["price_target"], 55.0)
        self.assertEqual(workspace.assumptions["scenario_overrides"]["Bear"]["price_target"], 31.0)

        # 9. Catalysts: the already-occurred one is superseded; the unrelated
        #    one and the new one both remain ahead.
        catalysts = [r for r in workspace.ledger if r["record_type"] == "catalyst"]
        by_metric = {c["metric"]: c for c in catalysts}
        self.assertEqual(by_metric["FY2026 guidance reset at Q1 results"]["status"], "superseded")
        self.assertEqual(by_metric["New plant commissioning ahead of schedule"]["status"], "active")
        self.assertEqual(by_metric["Backlog conversion accelerates into H2"]["status"], "active")

        # 10. Audit trail: one ledger record documents this event.
        audits = [
            r for r in workspace.ledger
            if r["record_type"] == "analytical_conclusion" and r.get("metric") == "earnings_update"
        ]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["value"], 2.75)
        self.assertEqual(audits[0]["period"], EARNINGS_DATE)
        self.assertIn("thesis_intact", audits[0]["notes"])

        # 11. The revised workspace still validates.
        validation = validate_workspace(self.workspace_path)
        self.assertTrue(validation.valid, validation.errors)

        # 12. Report structure: verdict header and required subsections.
        note = result["update_note_markdown"]
        self.assertIn("Verdict: Thesis Intact", note)
        self.assertIn("### The Numbers", note)
        self.assertIn("### Updated Assumptions", note)
        self.assertIn("### Valuation Impact", note)
        self.assertIn("### What Changed", note)
        self.assertIn("### What Didn't Change", note)
        self.assertIn("### Catalysts Ahead", note)
        self.assertIn("### Next Steps", note)
        self.assertIn("Segment Detail", note)  # prior open gap surfaced under Next Steps

    def test_ticker_mismatch_raises_on_bad_workspace(self) -> None:
        missing = self.root / "DOES-NOT-EXIST"
        with self.assertRaises(Exception):
            EarningsUpdateAgent(workspace_root=str(missing), client=FakeAnthropicClient([]))

    def test_run_without_tool_calls_raises(self) -> None:
        agent = self._agent(turns=[FakeResponse([text("No.")], "end_turn")])
        with self.assertRaises(EarningsUpdateError):
            agent.earnings_update(
                earnings_date=EARNINGS_DATE,
                eps_actual=2.75,
                eps_consensus=2.60,
                revenue_actual=620.0,
                revenue_consensus=600.0,
                guidance_change="raised",
            )

    def test_agent_never_imports_anthropic_when_client_supplied(self) -> None:
        sys.modules.pop("anthropic", None)
        agent = self._agent()
        agent.earnings_update(
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )
        self.assertNotIn("anthropic", sys.modules)

    def test_assumption_left_untouched_when_not_revised(self) -> None:
        """A dedicated check that only the named assumption is superseded.

        Runs a scripted turn that revises a single assumption and asserts the
        other two keep their id, base value, rationale, and active status
        completely unchanged -- not merely "still present."
        """

        before = ResearchWorkspace.load(self.workspace_path)
        ebit_before = next(
            a for a in before.assumptions["assumptions"] if a["name"] == "EBIT Margin FY2028"
        )
        pe_before = next(
            a for a in before.assumptions["assumptions"] if a["name"] == "Target Forward P/E"
        )

        agent = self._agent()
        agent.earnings_update(
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )

        after = ResearchWorkspace.load(self.workspace_path)
        ebit_after = next(
            a for a in after.assumptions["assumptions"] if a["name"] == "EBIT Margin FY2028"
        )
        pe_after = next(
            a for a in after.assumptions["assumptions"] if a["name"] == "Target Forward P/E"
        )
        self.assertEqual(ebit_before, ebit_after)
        self.assertEqual(pe_before, pe_after)


class DetermineVerdictTest(unittest.TestCase):
    """Focused unit tests for the deterministic verdict function."""

    def test_beat_with_guidance_raised_is_intact(self) -> None:
        self.assertEqual(determine_verdict(5.8, 3.3, "raised"), "thesis_intact")

    def test_large_beat_is_still_intact_not_at_risk(self) -> None:
        # A beat, however large, cannot by itself demote the thesis.
        self.assertEqual(determine_verdict(25.0, 20.0, "in-line"), "thesis_intact")

    def test_moderate_miss_alone_is_at_risk(self) -> None:
        self.assertEqual(determine_verdict(-7.0, -1.0, "in-line"), "thesis_at_risk")

    def test_guidance_lowered_with_small_miss_is_at_risk(self) -> None:
        self.assertEqual(determine_verdict(-1.0, -1.0, "lowered"), "thesis_at_risk")

    def test_guidance_lowered_with_small_beat_is_at_risk(self) -> None:
        # Guidance direction alone is enough to flag risk, even without a miss.
        self.assertEqual(determine_verdict(1.0, 1.0, "lowered"), "thesis_at_risk")

    def test_guidance_lowered_and_large_miss_is_broken(self) -> None:
        self.assertEqual(determine_verdict(-12.0, -3.0, "lowered"), "thesis_broken")

    def test_outright_large_miss_is_broken_regardless_of_guidance(self) -> None:
        self.assertEqual(determine_verdict(-16.0, 2.0, "in-line"), "thesis_broken")

    def test_none_surprise_is_treated_as_no_surprise(self) -> None:
        self.assertEqual(determine_verdict(None, None, None), "thesis_intact")

    def test_boundary_at_risk_threshold_is_exclusive(self) -> None:
        # Exactly 5% is not ">5%".
        self.assertEqual(determine_verdict(-5.0, 0.0, "in-line"), "thesis_intact")

    def test_boundary_broken_threshold_is_inclusive(self) -> None:
        self.assertEqual(determine_verdict(-15.0, 0.0, "in-line"), "thesis_broken")


class EarningsEvidenceTest(unittest.TestCase):
    def test_evidence_has_every_required_key(self) -> None:
        evidence = earnings_evidence.fetch_earnings_evidence(
            ticker="ACME",
            company_name="Acme Corp",
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )
        for key in earnings_evidence.REQUIRED_EARNINGS_EVIDENCE_KEYS:
            self.assertIn(key, evidence)
        self.assertTrue(evidence["sources"])

    def test_evidence_is_deterministic_across_calls(self) -> None:
        kwargs = dict(
            ticker="ACME",
            company_name="Acme Corp",
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )
        first = earnings_evidence.fetch_earnings_evidence(**kwargs)
        second = earnings_evidence.fetch_earnings_evidence(**kwargs)
        self.assertEqual(first, second)

    def test_transcript_included_only_when_url_supplied(self) -> None:
        kwargs = dict(
            ticker="ACME",
            company_name="Acme Corp",
            earnings_date=EARNINGS_DATE,
            eps_actual=2.75,
            eps_consensus=2.60,
            revenue_actual=620.0,
            revenue_consensus=600.0,
            guidance_change="raised",
        )
        without = earnings_evidence.fetch_earnings_evidence(**kwargs)
        self.assertFalse(without["call_transcript"]["available"])

        with_url = earnings_evidence.fetch_earnings_evidence(
            earnings_call_transcript_url="https://investor.example.com/acme/q1-transcript", **kwargs
        )
        self.assertTrue(with_url["call_transcript"]["available"])
        self.assertIn("qa_highlights", with_url["call_transcript"])

    def test_bad_earnings_date_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            earnings_evidence.fetch_earnings_evidence(
                ticker="ACME",
                company_name="Acme Corp",
                earnings_date="not-a-date",
                eps_actual=1.0,
                eps_consensus=1.0,
                revenue_actual=1.0,
                revenue_consensus=1.0,
                guidance_change=None,
            )

    def test_bad_guidance_change_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            earnings_evidence.fetch_earnings_evidence(
                ticker="ACME",
                company_name="Acme Corp",
                earnings_date=EARNINGS_DATE,
                eps_actual=1.0,
                eps_consensus=1.0,
                revenue_actual=1.0,
                revenue_consensus=1.0,
                guidance_change="bullish",
            )

    def test_surprise_pct_handles_zero_consensus(self) -> None:
        self.assertIsNone(earnings_evidence.compute_surprise_pct(1.0, 0.0))


if __name__ == "__main__":
    unittest.main()
