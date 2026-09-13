#!/usr/bin/env python3
"""Demo: run an initiation of coverage for a company.

Live mode calls the Claude API and needs ``anthropic`` installed and
``ANTHROPIC_API_KEY`` set. Offline mode replays a small canned analysis so the
whole pipeline — evidence, state, validation, report — can be inspected without
network access or spend.

    python3 scripts/example_usage.py --workspace /tmp/ACME --offline
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_SCRIPTS = SKILL_ROOT.parent / "persistent-equity-research" / "scripts"
sys.path.insert(0, str(SKILL_ROOT))

from orchestrator import AnalystAgent  # noqa: E402


class _CannedBlock:
    def __init__(self, block_type, name=None, payload=None, identifier=None, text=None):
        self.type = block_type
        self.name = name
        self.input = payload
        self.id = identifier
        self.text = text


class _CannedResponse:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class _CannedMessages:
    def __init__(self, turns):
        self._turns = list(turns)

    def create(self, **_kwargs):
        if not self._turns:
            return _CannedResponse([_CannedBlock("text", text="Done.")], "end_turn")
        return self._turns.pop(0)


class _CannedClient:
    """Replays a fixed analysis; stands in for the Anthropic client offline."""

    def __init__(self):
        def tool(name, payload, identifier):
            return _CannedBlock("tool_use", name=name, payload=payload, identifier=identifier)

        analysis = _CannedResponse(
            [
                tool("record_assumption", {
                    "name": "Revenue CAGR 5-Year Forward", "value": "5.5%", "units": "percent",
                    "rationale": "Below guidance, reflecting distributor destocking.",
                    "source_ids": ["SRC-0001", "SRC-0002"],
                }, "t1"),
                tool("record_assumption", {
                    "name": "EBIT Margin FY2028", "value": "14.1%", "units": "percent",
                    "rationale": "Aftermarket mix offsets capacity start-up costs.",
                    "source_ids": ["SRC-0001"],
                }, "t2"),
                tool("record_assumption", {
                    "name": "Target Forward P/E", "value": "16.5x", "units": "x",
                    "rationale": "Mid-peer multiple given mid-peer ROIC.",
                    "source_ids": ["SRC-0003"],
                }, "t3"),
                tool("record_valuation", {
                    "method": "Peer Multiple (P/E)",
                    "inputs": [
                        {"name": "peer_median_pe", "value": "17.4"},
                        {"name": "target_pe", "value": "16.5"},
                        {"name": "fy2_eps", "value": "2.61"},
                    ],
                    "output": {"low": 36.5, "base": 43.1, "high": 49.8},
                }, "t4"),
                tool("record_valuation", {
                    "method": "DCF",
                    "inputs": [
                        {"name": "wacc", "value": "9.0%"},
                        {"name": "terminal_growth", "value": "2.5%"},
                    ],
                    "output": {"low": 34.0, "base": 44.6, "high": 55.2},
                }, "t5"),
                tool("record_scenario", {
                    "name": "Base",
                    "assumptions": [{"name": "revenue_cagr", "value": "5.5%"}],
                    "valuation": "Blend of 16.5x FY2 EPS and DCF at 9.0% WACC",
                    "price_target": 44.0, "weight": 0.5,
                }, "t6"),
                tool("record_scenario", {
                    "name": "Bull",
                    "assumptions": [{"name": "revenue_cagr", "value": "8.0%"}],
                    "valuation": "18.5x FY2 EPS on aftermarket re-rating",
                    "price_target": 55.0, "weight": 0.25,
                }, "t7"),
                tool("record_scenario", {
                    "name": "Bear",
                    "assumptions": [{"name": "revenue_cagr", "value": "2.0%"}],
                    "valuation": "13.0x depressed FY2 EPS",
                    "price_target": 31.0, "weight": 0.25,
                }, "t8"),
                tool("record_catalyst", {
                    "name": "FY2026 guidance reset at Q1 results", "timeframe": "next 3 months",
                    "direction": "downside", "magnitude_estimate_pct": -8.0,
                }, "t9"),
                tool("record_catalyst", {
                    "name": "New plant commissioning ahead of schedule", "timeframe": "next 9 months",
                    "direction": "upside", "magnitude_estimate_pct": 6.0,
                }, "t10"),
                tool("record_catalyst", {
                    "name": "Distributor restocking completes", "timeframe": "6-12 months",
                    "direction": "upside", "magnitude_estimate_pct": 5.0,
                }, "t11"),
                tool("flag_analysis_gap", {
                    "category": "Segment Detail",
                    "description": "No geographic revenue split; Europe exposure cannot be sized.",
                }, "t12"),
                tool("flag_contradiction", {
                    "field1": "FY2026 revenue guidance",
                    "field2": "Five-year historical revenue CAGR",
                    "description": "Guidance implies acceleration while channel checks show destocking.",
                }, "t13"),
            ],
            "tool_use",
        )
        self.messages = _CannedMessages([analysis])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run initiate_coverage for a company.")
    parser.add_argument("--workspace", required=True, help="Workspace path; created if absent")
    parser.add_argument("--ticker", default="ACME")
    parser.add_argument("--company-name", default="Acme Corp")
    parser.add_argument("--max-evidence-sources", type=int, default=10)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Replay a canned analysis instead of calling the Claude API",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace = Path(args.workspace).expanduser()

    if not workspace.exists():
        result = subprocess.run(
            [
                sys.executable, str(PERSISTENT_SCRIPTS / "init_workspace.py"),
                "--workspace", str(workspace),
                "--ticker", args.ticker,
                "--company-name", args.company_name,
                "--format", "json",
            ],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(result.stderr or result.stdout, file=sys.stderr)
            return 1
        print(f"Initialized workspace: {workspace}")

    agent = AnalystAgent(
        workspace_root=str(workspace),
        client=_CannedClient() if args.offline else None,
    )
    outcome = agent.initiate_coverage(
        ticker=args.ticker,
        company_name=args.company_name,
        max_evidence_sources=args.max_evidence_sources,
    )

    print(f"status:            {outcome['status']}")
    print(f"evidence sources:  {outcome['evidence_count']}")
    print(f"state collections: {', '.join(outcome['state_ledger_keys'])}")
    print(f"tool calls:        {outcome['tool_calls']}")
    print(f"report:            {outcome['report_path']}")
    for note in outcome["notes"]:
        print(f"note:              {note}")
    for warning in outcome["validation_warnings"]:
        print(f"validator warning: {warning}")
    for error in outcome["validation_errors"]:
        print(f"validator ERROR:   {error}", file=sys.stderr)
    return 0 if outcome["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
