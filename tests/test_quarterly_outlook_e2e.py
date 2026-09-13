"""End-to-end integration test for the analyst-agent Quarterly Outlook report type.

No network access and no ``anthropic`` dependency: the Claude conversation is
driven by the shared scripted fake client from ``tests/analyst_agent_fakes.py``.
Unlike the initiation-of-coverage tests, there is no workspace to initialize --
``run_quarterly_outlook`` is a standalone function with no persistence, so
``setUp`` here only has to build scripted Claude turns.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYST_SKILL = ROOT / "skills" / "analyst-agent"
sys.path.insert(0, str(ANALYST_SKILL))
sys.path.insert(0, str(ROOT))

import outlook_evidence  # noqa: E402
import outlook_report  # noqa: E402
from outlook_render import SectorTiltRecord  # noqa: E402
from outlook_report import OutlookAgentError, run_quarterly_outlook  # noqa: E402

from tests.analyst_agent_fakes import (  # noqa: E402
    FakeAnthropicClient,
    FakeResponse,
    text,
    tool,
)

DEFAULT_SECTORS = list(outlook_evidence.DEFAULT_SECTOR_UNIVERSE)

#: One tilt per default sector: (tilt, earnings_growth_pct, pe_ratio).
_SECTOR_TILT_FIXTURES = {
    "Technology": ("overweight", 12.0, 26.0),
    "Healthcare": ("overweight", 8.0, 18.5),
    "Financials": ("neutral", 6.0, 12.0),
    "Industrials": ("neutral", 5.0, 17.0),
    "Consumer Discretionary": ("overweight", 9.0, 21.0),
    "Consumer Staples": ("underweight", 3.0, 20.0),
    "Energy": ("neutral", 4.0, 11.0),
    "Materials": ("underweight", 2.0, 15.0),
    "Utilities": ("underweight", 3.5, 17.5),
    "Real Estate": ("neutral", 4.5, 16.0),
    "Communication Services": ("overweight", 10.0, 19.0),
}


def _macro_scenario_calls(probabilities=None):
    """Bull/Base/Bear ``record_macro_scenario`` calls.

    ``probabilities`` overrides the (Base, Bull, Bear) weights, e.g. to
    script a run whose weights do not sum to 1.0.
    """

    base_p, bull_p, bear_p = probabilities or (0.60, 0.25, 0.15)
    return [
        tool(
            "record_macro_scenario",
            {
                "name": "Base",
                "probability_weight": base_p,
                "gdp_growth_pct": 2.1,
                "inflation_pct": 2.8,
                "fed_funds_rate_pct": 3.75,
                "ten_year_yield_pct": 4.1,
                "eps_growth_pct": 7.0,
                "trigger_or_narrative": (
                    "Growth moderates gradually while the Fed holds near current levels and "
                    "inflation drifts toward target. This is the modal path given the evidence."
                ),
                "winners": ["Technology", "Healthcare"],
                "losers": ["Utilities"],
            },
            "tu_b1",
        ),
        tool(
            "record_macro_scenario",
            {
                "name": "Bull",
                "probability_weight": bull_p,
                "gdp_growth_pct": 3.2,
                "inflation_pct": 2.3,
                "fed_funds_rate_pct": 3.25,
                "ten_year_yield_pct": 3.8,
                "eps_growth_pct": 11.0,
                "trigger_or_narrative": (
                    "A soft landing takes hold, the Fed cuts faster than priced, and earnings "
                    "revisions turn broadly positive."
                ),
                "winners": ["Technology", "Consumer Discretionary", "Financials"],
                "losers": ["Consumer Staples"],
            },
            "tu_b2",
        ),
        tool(
            "record_macro_scenario",
            {
                "name": "Bear",
                "probability_weight": bear_p,
                "gdp_growth_pct": 0.4,
                "inflation_pct": 3.6,
                "fed_funds_rate_pct": 4.5,
                "ten_year_yield_pct": 4.6,
                "eps_growth_pct": -3.0,
                "trigger_or_narrative": (
                    "Sticky inflation forces the Fed to stay restrictive into a growth "
                    "slowdown, pressuring cyclical earnings."
                ),
                "winners": ["Utilities", "Consumer Staples"],
                "losers": ["Technology", "Consumer Discretionary"],
            },
            "tu_b3",
        ),
    ]


def _relative_value_calls():
    return [
        tool(
            "record_relative_value_view",
            {
                "pair_name": "Growth vs Value",
                "metric_a_label": "Growth forward P/E",
                "metric_a_value": "24.5x",
                "metric_b_label": "Value forward P/E",
                "metric_b_value": "15.2x",
                "verdict": "Stay barbelled; growth's premium is wide but earnings durability justifies part of it.",
                "rationale": "The spread sits above its 10-year average, but growth earnings revisions remain positive.",
            },
            "tu_r1",
        ),
        tool(
            "record_relative_value_view",
            {
                "pair_name": "Quality Premium",
                "metric_a_label": "High-ROIC quintile forward P/E",
                "metric_a_value": "22.0x",
                "metric_b_label": "Low-ROIC quintile forward P/E",
                "metric_b_value": "13.5x",
                "verdict": "Quality premium is justified, not stretched, given the late-cycle backdrop.",
                "rationale": "Balance-sheet stress typically rises later in the cycle, favoring high-ROIC names.",
            },
            "tu_r2",
        ),
        tool(
            "record_relative_value_view",
            {
                "pair_name": "Bonds vs Equities",
                "metric_a_label": "S&P 500 earnings yield",
                "metric_a_value": "4.9%",
                "metric_b_label": "10-year Treasury yield",
                "metric_b_value": "4.1%",
                "verdict": "The equity risk premium is thin; equities are not obviously cheap versus bonds.",
                "rationale": "An ERP below its 15-year average argues for a modest duration overweight.",
            },
            "tu_r3",
        ),
    ]


def _sector_tilt_calls(sectors):
    calls = []
    for index, sector in enumerate(sectors):
        tilt, growth, pe_ratio = _SECTOR_TILT_FIXTURES.get(sector, ("neutral", 5.0, 15.0))
        calls.append(
            tool(
                "record_sector_tilt",
                {
                    "sector": sector,
                    "scenario": "Base",
                    "earnings_growth_pct": growth,
                    "pe_ratio": pe_ratio,
                    "tilt": tilt,
                    "rationale": (
                        f"{sector} earnings growth of {growth}% against a {pe_ratio}x forward "
                        f"multiple supports a {tilt} call."
                    ),
                },
                f"tu_s{index}",
            )
        )
    return calls


def _catalyst_calls(count=4):
    all_calls = [
        tool(
            "record_catalyst",
            {"name": "Nonfarm payrolls", "date": "2025-01-05", "impact": "A weak print firms up the Base case."},
            "tu_c1",
        ),
        tool(
            "record_catalyst",
            {"name": "CPI inflation print", "date": "2025-01-12", "impact": "A hot core print delays the first cut."},
            "tu_c2",
        ),
        tool(
            "record_catalyst",
            {"name": "FOMC policy decision", "date": "2025-02-18", "impact": "A hawkish hold pressures duration-sensitive sectors."},
            "tu_c3",
        ),
        tool(
            "record_catalyst",
            {"name": "PCE inflation release", "date": "2025-03-28", "impact": "Confirms or contradicts the quarter's disinflation trend."},
            "tu_c4",
        ),
    ]
    return all_calls[:count]


def _tail_risk_calls(count=4):
    all_calls = [
        tool(
            "flag_tail_risk",
            {"description": "Escalation in Taiwan Strait tensions disrupts chip supply chains.", "category": "geopolitical"},
            "tu_t1",
        ),
        tool(
            "flag_tail_risk",
            {"description": "A central bank surprise reprices rate-cut expectations.", "category": "monetary"},
            "tu_t2",
        ),
        tool(
            "flag_tail_risk",
            {"description": "A fiscal standoff threatens a government shutdown.", "category": "fiscal"},
            "tu_t3",
        ),
        tool(
            "flag_tail_risk",
            {"description": "A regional conflict disrupts energy supply routes.", "category": "geopolitical"},
            "tu_t4",
        ),
    ]
    return all_calls[:count]


def _happy_path_turns():
    first = FakeResponse(_macro_scenario_calls() + _relative_value_calls(), "tool_use")
    second = FakeResponse(
        _sector_tilt_calls(DEFAULT_SECTORS) + _catalyst_calls() + _tail_risk_calls(),
        "tool_use",
    )
    third = FakeResponse([text("Analysis complete.")], "end_turn")
    return [first, second, third]


class QuarterlyOutlookHappyPathTest(unittest.TestCase):
    def test_full_run_tilts_all_default_sectors(self) -> None:
        result = run_quarterly_outlook(
            quarter="Q1 2025",
            macro_scenario="base",
            client=FakeAnthropicClient(_happy_path_turns()),
        )

        for key in (
            "outlook_markdown",
            "macro_scenario",
            "sector_tilts",
            "tail_risks",
            "catalyst_calendar",
            "status",
        ):
            self.assertIn(key, result)

        self.assertEqual(result["status"], "success", result.get("notes"))
        self.assertEqual(result["macro_scenario"], "base")
        self.assertEqual(result["quarter"], "Q1 2025")
        self.assertEqual(result["notes"], [])

        # All 11 default sectors are tilted and appear in the derived display dict.
        self.assertEqual(set(result["sector_tilts"].keys()), set(DEFAULT_SECTORS))

        # >=3 tail risks, >=3 dated catalyst-calendar entries.
        self.assertGreaterEqual(len(result["tail_risks"]), 3)
        self.assertGreaterEqual(len(result["catalyst_calendar"]), 3)
        for entry in result["catalyst_calendar"]:
            self.assertIn("date", entry)
            self.assertIn("catalyst", entry)
            self.assertIn("impact", entry)
        dates = [entry["date"] for entry in result["catalyst_calendar"]]
        self.assertEqual(dates, sorted(dates))

        # Probabilities sum to 1.0.
        self.assertAlmostEqual(result["probability_weight_sum"], 1.0, places=6)

        report = result["outlook_markdown"]
        self.assertTrue(report.strip())
        for heading in (
            "# Quarterly Outlook: Q1 2025",
            "## Executive Summary",
            "## I. Macro Scenario",
            "## II. Base Case",
            "## III. Bull Case",
            "## IV. Bear Case",
            "## V. Relative Value Views",
            "## VI. Sector Catalyst Calendar",
            "## VII. Key Risks to Base Case",
            "## VIII. Positioning Summary",
            "## Notes",
        ):
            self.assertIn(heading, report)

        # Relative value: three distinct recorded views, each surfaced by name.
        self.assertIn("Growth vs Value", report)
        self.assertIn("Quality Premium", report)
        self.assertIn("Bonds vs Equities", report)

        # Sector tilts reconcile: every default sector's name appears in the report.
        for sector in DEFAULT_SECTORS:
            self.assertIn(sector, report)

    def test_agent_never_imports_anthropic_when_client_supplied(self) -> None:
        sys.modules.pop("anthropic", None)
        run_quarterly_outlook(quarter="Q1 2025", client=FakeAnthropicClient(_happy_path_turns()))
        self.assertNotIn("anthropic", sys.modules)


class QuarterlyOutlookValidationTest(unittest.TestCase):
    def test_probability_mismatch_marks_run_partial_without_renormalizing(self) -> None:
        """Probabilities summing to 80% must be surfaced, not silently fixed."""

        turns = [
            FakeResponse(_macro_scenario_calls(probabilities=(0.5, 0.2, 0.1)), "tool_use"),
            FakeResponse([text("done")], "end_turn"),
        ]
        result = run_quarterly_outlook(quarter="Q2 2025", client=FakeAnthropicClient(turns))

        self.assertEqual(result["status"], "partial")
        self.assertAlmostEqual(result["probability_weight_sum"], 0.8, places=6)
        joined_notes = " ".join(result["notes"])
        self.assertIn("0.800", joined_notes)
        self.assertIn("not 1.00", joined_notes)

    def test_tail_risk_and_catalyst_shortfalls_are_reported(self) -> None:
        """Fewer than 3 tail risks / catalysts must be visible in notes, not padded."""

        turns = [
            FakeResponse(
                _macro_scenario_calls()
                + _relative_value_calls()
                + _sector_tilt_calls(DEFAULT_SECTORS)
                + _catalyst_calls(count=2)
                + _tail_risk_calls(count=2),
                "tool_use",
            ),
            FakeResponse([text("done")], "end_turn"),
        ]
        result = run_quarterly_outlook(quarter="Q3 2025", client=FakeAnthropicClient(turns))

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["tail_risks"]), 2)
        self.assertEqual(len(result["catalyst_calendar"]), 2)
        joined_notes = " ".join(result["notes"])
        self.assertIn("only 2 tail risk(s) recorded", joined_notes)
        self.assertIn("only 2 catalyst(s) recorded", joined_notes)

    def test_run_without_tool_calls_raises(self) -> None:
        turns = [FakeResponse([text("No analysis performed.")], "end_turn")]
        with self.assertRaises(OutlookAgentError):
            run_quarterly_outlook(quarter="Q1 2025", client=FakeAnthropicClient(turns))

    def test_invalid_macro_scenario_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_quarterly_outlook(
                quarter="Q1 2025",
                macro_scenario="sideways",
                client=FakeAnthropicClient(_happy_path_turns()),
            )

    def test_malformed_quarter_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_quarterly_outlook(quarter="2025-Q1", client=FakeAnthropicClient(_happy_path_turns()))

    def test_sector_tilt_outside_universe_is_dropped_not_raised(self) -> None:
        turns = [
            FakeResponse(
                _macro_scenario_calls()
                + _relative_value_calls()
                + _sector_tilt_calls(DEFAULT_SECTORS)
                + [
                    tool(
                        "record_sector_tilt",
                        {
                            "sector": "Crypto",
                            "scenario": "Base",
                            "earnings_growth_pct": 40.0,
                            "pe_ratio": 50.0,
                            "tilt": "overweight",
                            "rationale": "Not a real sector in the requested universe.",
                        },
                        "tu_bad_sector",
                    )
                ]
                + _catalyst_calls()
                + _tail_risk_calls(),
                "tool_use",
            ),
            FakeResponse([text("done")], "end_turn"),
        ]
        result = run_quarterly_outlook(quarter="Q1 2025", client=FakeAnthropicClient(turns))

        self.assertNotIn("Crypto", result["sector_tilts"])
        self.assertIn(
            "dropped sector tilts for names outside the requested sector universe",
            " ".join(result["notes"]),
        )


class SectorTiltDisplayMappingTest(unittest.TestCase):
    """Unit-level check of the overweight/neutral/underweight -> display-label convention."""

    def test_labels_match_the_documented_convention(self) -> None:
        tilts = [
            SectorTiltRecord("Technology", "Base", 12.0, 26.0, "overweight", "r"),
            SectorTiltRecord("Financials", "Base", 6.0, 12.0, "neutral", "r"),
            SectorTiltRecord("Utilities", "Base", 3.0, 17.0, "underweight", "r"),
            # A non-Base scenario call for a sector must not leak into the display dict.
            SectorTiltRecord("Energy", "Bull", 20.0, 14.0, "overweight", "r"),
        ]
        display = outlook_report._map_sector_tilts_to_display(
            tilts, ["Technology", "Financials", "Utilities", "Energy"]
        )
        self.assertEqual(
            display,
            {"Technology": "+2%", "Financials": "0%", "Utilities": "-2%"},
        )
        self.assertNotIn("Energy", display)


class MacroEvidenceDeterminismTest(unittest.TestCase):
    def test_evidence_is_deterministic_across_calls(self) -> None:
        first = outlook_evidence.fetch_macro_evidence("Q2 2025")
        second = outlook_evidence.fetch_macro_evidence("Q2 2025")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_evidence_is_deterministic_with_custom_sector_universe(self) -> None:
        universe = ["Technology", "Energy", "Financials"]
        first = outlook_evidence.fetch_macro_evidence("Q4 2026", sector_universe=universe)
        second = outlook_evidence.fetch_macro_evidence("Q4 2026", sector_universe=universe)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(set(first["sector_data"].keys()), set(universe))

    def test_evidence_has_every_required_key(self) -> None:
        evidence = outlook_evidence.fetch_macro_evidence("Q1 2025")
        for key in outlook_evidence.REQUIRED_MACRO_EVIDENCE_KEYS:
            self.assertIn(key, evidence)
        self.assertGreaterEqual(len(evidence["tail_risk_evidence"]), 3)
        self.assertGreaterEqual(len(evidence["catalyst_calendar_evidence"]), 3)

    def test_malformed_quarter_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            outlook_evidence.fetch_macro_evidence("garbage")


if __name__ == "__main__":
    unittest.main()
