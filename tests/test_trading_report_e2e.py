"""End-to-end integration tests for the Trading Report agent.

No network access and no ``anthropic`` dependency: the Claude conversation is
driven by the shared scripted fake client from ``tests/analyst_agent_fakes.py``.
Trading Report has no persistent workspace, so setup here is far lighter than
``test_analyst_agent_e2e.py``'s: no ``init_workspace.py`` subprocess is needed.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYST_SKILL = ROOT / "skills" / "analyst-agent"
TESTS_DIR = ROOT / "tests"
for _path in (ANALYST_SKILL, TESTS_DIR, ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from analyst_agent_fakes import FakeAnthropicClient, FakeBlock, FakeResponse, tool, text  # noqa: E402

import trading_evidence  # noqa: E402
from trading_evidence import TradingEvidenceError  # noqa: E402
import trading_report  # noqa: E402
from trading_report import TradingReportError, run_trading_report  # noqa: E402


# ----------------------------------------------------------------------
# Scripted tool-use turns
# ----------------------------------------------------------------------


def _full_turns(catalyst_probability_pct=70.0, verdict="strong", conviction_level="high"):
    """A complete, well-formed set of tool calls: every required judgment present."""

    return [
        FakeResponse(
            [
                tool(
                    "record_catalyst_probability",
                    {
                        "probability_pct": catalyst_probability_pct,
                        "rationale": "Above the historical base rate given accelerating bookings.",
                        "historical_base_rate_pct": 55.0,
                    },
                    "tu_01",
                ),
                tool(
                    "record_technical_setup",
                    {
                        "trend": "uptrend",
                        "momentum_signal": "RSI 58, MACD bullish",
                        "volume_signal": "accumulation",
                        "verdict": verdict,
                        "rationale": "Uptrend with accumulation volume and a bullish MACD cross.",
                    },
                    "tu_02",
                ),
                tool(
                    "record_conviction",
                    {
                        "level": conviction_level,
                        "favorable_factor_count": 3,
                        "rationale": "Catalyst, technical, and valuation are all favorable.",
                    },
                    "tu_03",
                ),
                tool(
                    "record_scenario_case",
                    {
                        "name": "bull",
                        "trigger": "Beat and raise guidance with margin upside",
                        "resulting_price_estimate": 145.0,
                        "rationale": "Bigger beat with re-rating on peer multiple convergence.",
                    },
                    "tu_04",
                ),
                tool(
                    "record_scenario_case",
                    {
                        "name": "bear",
                        "trigger": "Miss and guide down amid demand softness",
                        "resulting_price_estimate": 78.0,
                        "rationale": "Miss with de-rating toward the trough multiple.",
                    },
                    "tu_05",
                ),
                tool(
                    "flag_risk",
                    {
                        "description": "A peer's pre-announcement could move the stock ahead of the print.",
                        "category": "event",
                    },
                    "tu_06",
                ),
            ],
            "tool_use",
        ),
        FakeResponse([FakeBlock("text", text="Analysis complete.")], "end_turn"),
    ]


class TradingReportEndToEndTest(unittest.TestCase):
    def test_long_thesis_happy_path(self) -> None:
        client = FakeAnthropicClient(_full_turns())
        result = run_trading_report(
            ticker="acme",
            trade_thesis="Long",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=130.0,
            stop_loss=90.0,
            time_horizon_days=45,
            anthropic_api_key="test-key-not-used",
            client=client,
        )

        for key in (
            "trade_report_markdown",
            "risk_reward_ratio",
            "implied_return_pct",
            "catalyst_probability_pct",
            "technical_setup",
            "conviction",
            "status",
        ):
            self.assertIn(key, result)

        # Arithmetic: (130-100)/(100-90) = 3.0 ; (130-100)/100*100 = 30.0
        self.assertAlmostEqual(result["risk_reward_ratio"], 3.0)
        self.assertAlmostEqual(result["implied_return_pct"], 30.0)
        self.assertEqual(result["catalyst_probability_pct"], 70.0)
        self.assertEqual(result["technical_setup"], "strong")
        self.assertEqual(result["conviction"], "high")
        self.assertEqual(result["status"], "success", result.get("notes"))
        self.assertEqual(result["notes"], [])

        report = result["trade_report_markdown"]
        self.assertTrue(report.strip())

        # Ticker/catalyst/date/entry/target/stop are echoed from the inputs.
        self.assertIn("ACME", report)
        self.assertIn("Q4 earnings", report)
        self.assertIn("2026-01-15", report)
        self.assertIn("100.00", report)
        self.assertIn("130.00", report)
        self.assertIn("90.00", report)

        # Recorded tool-call fields surface verbatim.
        self.assertIn("accumulation", report)
        self.assertIn("Beat and raise guidance with margin upside", report)
        self.assertIn("Miss with de-rating toward the trough multiple.", report)
        self.assertIn("A peer's pre-announcement could move the stock ahead of the print.", report)

        # Structural sections all present.
        for heading in (
            "## I. Fundamental Catalyst",
            "## II. Valuation & Relative Value",
            "## III. Technical Setup",
            "## IV. Risk Management",
            "## V. Execution Plan",
            "## VI. Alternative Views",
            "## VII. Final Checklist",
        ):
            self.assertIn(heading, report)

        # Final one-line verdict, direction-aware, no reduced-size caveat.
        self.assertIn("INITIATE LONG ACME @ 100.00 | Target 130.00 | Stop 90.00.", report)
        self.assertNotIn("REDUCED SIZE", report)
        self.assertNotIn("DO NOT INITIATE", report)
        self.assertNotIn("Fallback:", report)

        # Short-form: stays well within a 2-4 page budget.
        self.assertLess(len(report), 9000, "report is longer than the 2-4 page short-form budget")

    def test_short_thesis_has_different_math_and_wording(self) -> None:
        client = FakeAnthropicClient(_full_turns())
        result = run_trading_report(
            ticker="ACME",
            trade_thesis="short",
            catalyst_name="FDA approval decision",
            catalyst_date="2026-02-01",
            entry_price=100.0,
            target_price=70.0,
            stop_loss=110.0,
            client=client,
        )

        # Arithmetic: (100-70)/(110-100) = 3.0 ; (100-70)/100*100 = 30.0
        self.assertAlmostEqual(result["risk_reward_ratio"], 3.0)
        self.assertAlmostEqual(result["implied_return_pct"], 30.0)
        self.assertEqual(result["status"], "success", result.get("notes"))

        report = result["trade_report_markdown"]
        self.assertIn("SHORT", report)
        self.assertIn("INITIATE SHORT ACME @ 100.00 | Target 70.00 | Stop 110.00.", report)

    def test_below_threshold_risk_reward_is_flagged_not_hard_failed(self) -> None:
        client = FakeAnthropicClient(_full_turns())
        result = run_trading_report(
            ticker="ACME",
            trade_thesis="long",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=110.0,
            stop_loss=90.0,
            client=client,
        )
        # (110-100)/(100-90) = 1.0 -- below the 2:1 acceptance threshold.
        self.assertAlmostEqual(result["risk_reward_ratio"], 1.0)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("2.0:1 acceptance threshold" in note for note in result["notes"]))
        self.assertIn("REDUCED SIZE", result["trade_report_markdown"])

    def test_inverted_setup_is_flagged_not_hard_failed(self) -> None:
        client = FakeAnthropicClient(_full_turns())
        result = run_trading_report(
            ticker="ACME",
            trade_thesis="long",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=90.0,   # target below entry for a long -- nonsensical
            stop_loss=110.0,     # stop above entry for a long -- nonsensical
            client=client,
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any("inverted" in note for note in result["notes"]))
        self.assertIn("inverted setup", result["trade_report_markdown"])
        # The function still returns (does not raise) for a merely nonsensical,
        # not undefined, setup.
        self.assertIn("trade_report_markdown", result)

    def test_missing_required_judgments_fail_status_with_explicit_absence(self) -> None:
        """Claude records some but not all required judgments."""

        partial_turns = [
            FakeResponse(
                [
                    tool(
                        "record_catalyst_probability",
                        {
                            "probability_pct": 60.0,
                            "rationale": "In line with the historical base rate.",
                            "historical_base_rate_pct": 58.0,
                        },
                        "tu_01",
                    ),
                    tool(
                        "record_scenario_case",
                        {
                            "name": "bull",
                            "trigger": "Beat and raise",
                            "resulting_price_estimate": 140.0,
                            "rationale": "Upside on margin beat.",
                        },
                        "tu_02",
                    ),
                ],
                "tool_use",
            ),
            FakeResponse([FakeBlock("text", text="Done.")], "end_turn"),
        ]
        client = FakeAnthropicClient(partial_turns)
        result = run_trading_report(
            ticker="ACME",
            trade_thesis="long",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=130.0,
            stop_loss=90.0,
            client=client,
        )
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("missing required model judgments" in note for note in result["notes"]))
        report = result["trade_report_markdown"]
        self.assertIn("DO NOT INITIATE", report)
        self.assertIn("Fallback:", report)
        # The bear case was never recorded -- rendered as an explicit absence,
        # not a fabricated number.
        self.assertIn("_Not recorded by the model._", report)

    def test_no_tool_calls_raises(self) -> None:
        client = FakeAnthropicClient([FakeResponse([text("No analysis.")], "end_turn")])
        with self.assertRaises(TradingReportError):
            run_trading_report(
                ticker="ACME",
                trade_thesis="long",
                catalyst_name="Q4 earnings",
                catalyst_date="2026-01-15",
                entry_price=100.0,
                target_price=130.0,
                stop_loss=90.0,
                client=client,
            )

    def test_bad_trade_thesis_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            run_trading_report(
                ticker="ACME",
                trade_thesis="bullish",
                catalyst_name="Q4 earnings",
                catalyst_date="2026-01-15",
                entry_price=100.0,
                target_price=130.0,
                stop_loss=90.0,
                client=FakeAnthropicClient([]),
            )

    def test_case_insensitive_trade_thesis_is_normalized(self) -> None:
        client = FakeAnthropicClient(_full_turns())
        result = run_trading_report(
            ticker="ACME",
            trade_thesis="LONG",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=130.0,
            stop_loss=90.0,
            client=client,
        )
        self.assertIn("INITIATE LONG", result["trade_report_markdown"])

    def test_entry_equals_stop_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            run_trading_report(
                ticker="ACME",
                trade_thesis="long",
                catalyst_name="Q4 earnings",
                catalyst_date="2026-01-15",
                entry_price=100.0,
                target_price=130.0,
                stop_loss=100.0,
                client=FakeAnthropicClient([]),
            )

    def test_entry_price_zero_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            run_trading_report(
                ticker="ACME",
                trade_thesis="long",
                catalyst_name="Q4 earnings",
                catalyst_date="2026-01-15",
                entry_price=0.0,
                target_price=10.0,
                stop_loss=-5.0,
                client=FakeAnthropicClient([]),
            )

    def test_agent_never_imports_anthropic_when_client_supplied(self) -> None:
        sys.modules.pop("anthropic", None)
        client = FakeAnthropicClient(_full_turns())
        run_trading_report(
            ticker="ACME",
            trade_thesis="long",
            catalyst_name="Q4 earnings",
            catalyst_date="2026-01-15",
            entry_price=100.0,
            target_price=130.0,
            stop_loss=90.0,
            client=client,
        )
        self.assertNotIn("anthropic", sys.modules)


class RiskRewardArithmeticTest(unittest.TestCase):
    """Dedicated unit tests for the risk/reward math -- no Claude call needed."""

    def test_long_math(self) -> None:
        result = trading_report._compute_risk_reward("long", entry_price=100.0, target_price=130.0, stop_loss=90.0)
        self.assertAlmostEqual(result["risk_reward_ratio"], 3.0)
        self.assertAlmostEqual(result["implied_return_pct"], 30.0)
        self.assertFalse(result["inverted"])
        self.assertFalse(result["below_threshold"])

    def test_short_math(self) -> None:
        result = trading_report._compute_risk_reward("short", entry_price=100.0, target_price=70.0, stop_loss=110.0)
        self.assertAlmostEqual(result["risk_reward_ratio"], 3.0)
        self.assertAlmostEqual(result["implied_return_pct"], 30.0)
        self.assertFalse(result["inverted"])
        self.assertFalse(result["below_threshold"])

    def test_long_inverted_setup_detected(self) -> None:
        result = trading_report._compute_risk_reward("long", entry_price=100.0, target_price=90.0, stop_loss=110.0)
        self.assertTrue(result["inverted"])

    def test_short_inverted_setup_detected(self) -> None:
        result = trading_report._compute_risk_reward("short", entry_price=100.0, target_price=110.0, stop_loss=90.0)
        self.assertTrue(result["inverted"])

    def test_below_threshold_detected(self) -> None:
        result = trading_report._compute_risk_reward("long", entry_price=100.0, target_price=110.0, stop_loss=90.0)
        self.assertAlmostEqual(result["risk_reward_ratio"], 1.0)
        self.assertTrue(result["below_threshold"])

    def test_zero_width_stop_raises(self) -> None:
        with self.assertRaises(ValueError):
            trading_report._compute_risk_reward("long", entry_price=100.0, target_price=130.0, stop_loss=100.0)

    def test_bad_trade_thesis_normalization_raises(self) -> None:
        with self.assertRaises(ValueError):
            trading_report._normalize_trade_thesis("sideways")

    def test_trade_thesis_normalization_is_case_insensitive(self) -> None:
        self.assertEqual(trading_report._normalize_trade_thesis("ShOrT"), "short")


class TradingEvidenceTest(unittest.TestCase):
    def test_evidence_has_every_required_key(self) -> None:
        evidence = trading_evidence.fetch_trading_evidence("ACME", "Q4 earnings", "2026-01-15", "long")
        for key in trading_evidence.REQUIRED_TRADING_EVIDENCE_KEYS:
            self.assertIn(key, evidence)
        self.assertGreaterEqual(len(evidence["risk_factors"]), trading_evidence.MINIMUM_RISK_FACTORS)

    def test_evidence_is_deterministic_across_calls(self) -> None:
        first = trading_evidence.fetch_trading_evidence("ACME", "Q4 earnings", "2026-01-15", "long")
        second = trading_evidence.fetch_trading_evidence("ACME", "Q4 earnings", "2026-01-15", "long")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_evidence_deterministic_regardless_of_trade_thesis_numbers(self) -> None:
        """trade_thesis changes risk framing text, never the seeded market data."""

        long_evidence = trading_evidence.fetch_trading_evidence("ACME", "Q4 earnings", "2026-01-15", "long")
        short_evidence = trading_evidence.fetch_trading_evidence("ACME", "Q4 earnings", "2026-01-15", "short")
        self.assertEqual(long_evidence["technicals"], short_evidence["technicals"])
        self.assertEqual(long_evidence["relative_value"], short_evidence["relative_value"])

    def test_empty_ticker_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            trading_evidence.fetch_trading_evidence("", "Q4 earnings", "2026-01-15", "long")

    def test_empty_catalyst_name_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            trading_evidence.fetch_trading_evidence("ACME", "", "2026-01-15", "long")

    def test_incomplete_payload_is_refused_by_validator(self) -> None:
        with self.assertRaises(TradingEvidenceError):
            trading_evidence.validate_trading_evidence({"catalyst_type": "earnings"})

    def test_catalyst_type_classification(self) -> None:
        self.assertEqual(trading_evidence._classify_catalyst("Q4 earnings"), "earnings")
        self.assertEqual(trading_evidence._classify_catalyst("FDA approval decision"), "regulatory")
        self.assertEqual(trading_evidence._classify_catalyst("Pending acquisition close"), "m&a")
        self.assertEqual(trading_evidence._classify_catalyst("Investor day"), "event")


if __name__ == "__main__":
    unittest.main()
