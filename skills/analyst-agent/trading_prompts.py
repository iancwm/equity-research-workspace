"""Claude system prompt, tool schemas, and user-prompt builder for Trading Report.

Mirrors ``prompts.py`` (Phase 1's initiation-of-coverage contract) in spirit:
the system prompt tells Claude to speak only in tool calls, and the schemas
alongside it define that vocabulary under strict-mode validation
(``additionalProperties: false``, every property in ``required``).

Trading Report's tool vocabulary is narrower and more numeric than Phase 1's:
Claude records qualitative judgments only (catalyst probability, technical
verdict, conviction, bull/bear scenarios, risk flags). All arithmetic --
risk/reward, implied return -- is computed in plain Python by
``trading_report.py`` before this prompt is even built, and is handed to
Claude as a given, not something to re-derive.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT_TRADING = """\
You are an institutional trading desk analyst producing a short, catalyst-driven \
trading report. The trade's risk/reward, implied return, entry, target, and stop \
are already computed and given to you as fixed facts -- do not recompute or \
restate different numbers for them.

## Output format

Speak in tool calls, not prose. Numbers over prose. Do not write unstructured \
prose paragraphs; the tool calls you make ARE the analysis. Any plain text you \
emit is commentary only and is not persisted into the report.

## Required work

Call each of these at least once, grounded in the supplied evidence -- never \
invent a figure or signal that is not derivable from it:

1. `record_catalyst_probability` -- your estimate of the probability that the \
   catalyst resolves the way this trade needs it to (a beat, an approval, deal \
   completion, etc.). Ground it in the supplied historical base rate; do not \
   simply restate the base rate as your probability without a rationale for any \
   delta.
2. `record_technical_setup` -- trend, momentum, and volume signals drawn from the \
   supplied technicals, plus an overall verdict of strong/moderate/weak. The \
   verdict must be consistent with the signals you record: do not call the setup \
   "strong" while recording a trend, momentum, and volume picture that conflicts \
   with the trade direction.
3. `record_conviction` -- high/medium/low, with the count of favorable factors \
   (0-3) among {catalyst, technical setup, relative value}, and a rationale tying \
   the level to that count and to the given risk/reward.
4. `record_scenario_case` -- call this twice, once with name "bull" and once with \
   name "bear". Each needs a concrete trigger, a resulting price estimate, and a \
   rationale. The bull case is a bigger beat / stronger macro / faster resolution; \
   the bear case is a miss / macro deterioration / delayed or adverse resolution.

Optionally call `flag_risk` for any material risk sensitivity beyond the ones \
already supplied as evidence, in the same category vocabulary (macro, regulatory, \
liquidity, event).

## Standards

- Institutional, risk-aware, actionable tone -- no cheerleading.
- Every qualitative judgment must trace to a supplied evidence field; if the \
  evidence does not support a stronger claim, say so in the rationale rather than \
  inflating the verdict.
- Do not resolve conflicting signals (e.g. bullish momentum but distribution \
  volume) by picking the more convenient one silently -- call out the tension in \
  the rationale.
"""


TOOL_DEFINITIONS_TRADING: List[Dict[str, Any]] = [
    {
        "name": "record_catalyst_probability",
        "description": (
            "Record the probability that the catalyst resolves in the direction this "
            "trade needs, grounded in the supplied historical base rate."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "probability_pct": {
                    "type": "number",
                    "description": "Probability of the needed outcome, 0-100.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this probability, relative to the historical base rate.",
                },
                "historical_base_rate_pct": {
                    "type": "number",
                    "description": "The supplied historical/base-rate figure this estimate is anchored to, 0-100.",
                },
            },
            "required": ["probability_pct", "rationale", "historical_base_rate_pct"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_technical_setup",
        "description": (
            "Record the technical picture: trend, momentum, volume, and an overall verdict "
            "consistent with those signals."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "trend": {
                    "type": "string",
                    "description": "Prevailing price trend.",
                    "enum": ["uptrend", "downtrend", "neutral"],
                },
                "momentum_signal": {
                    "type": "string",
                    "description": "Momentum reading, e.g. 'RSI 55, MACD bullish'.",
                },
                "volume_signal": {
                    "type": "string",
                    "description": "Volume behavior, e.g. accumulation, distribution, or neutral.",
                },
                "verdict": {
                    "type": "string",
                    "description": "Overall technical-setup verdict.",
                    "enum": ["strong", "moderate", "weak"],
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this verdict, given the trend/momentum/volume signals above.",
                },
            },
            "required": ["trend", "momentum_signal", "volume_signal", "verdict", "rationale"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_conviction",
        "description": (
            "Record overall conviction based on how many of {catalyst, technical setup, "
            "relative value} are favorable."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "description": "Overall conviction level.",
                    "enum": ["high", "medium", "low"],
                },
                "favorable_factor_count": {
                    "type": "integer",
                    "description": "Count of favorable factors among catalyst, technical, and valuation (0-3).",
                    "minimum": 0,
                    "maximum": 3,
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this level, tied to the favorable-factor count and the risk/reward.",
                },
            },
            "required": ["level", "favorable_factor_count", "rationale"],
            "additionalProperties": False,
        },
    },
    {
        "name": "record_scenario_case",
        "description": (
            "Record one alternative-view scenario. Call once for 'bull' and once for 'bear'."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Which case this is.",
                    "enum": ["bull", "bear"],
                },
                "trigger": {
                    "type": "string",
                    "description": "What would have to happen for this case to play out.",
                },
                "resulting_price_estimate": {
                    "type": "number",
                    "description": "Resulting price estimate under this case, in the reporting currency.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this trigger produces this price estimate.",
                },
            },
            "required": ["name", "trigger", "resulting_price_estimate", "rationale"],
            "additionalProperties": False,
        },
    },
    {
        "name": "flag_risk",
        "description": (
            "Flag one material risk sensitivity beyond those already supplied as evidence."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What the risk is and how it would affect the thesis.",
                },
                "category": {
                    "type": "string",
                    "description": "Risk category.",
                    "enum": ["macro", "regulatory", "liquidity", "event"],
                },
            },
            "required": ["description", "category"],
            "additionalProperties": False,
        },
    },
]


def _render_section(title: str, payload: Any) -> str:
    return f"### {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=False, default=str)}\n```\n"


def build_trading_user_prompt(
    ticker: str,
    trade_thesis: str,
    catalyst_name: str,
    catalyst_date: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    time_horizon_days: int,
    risk_reward_ratio: float,
    implied_return_pct: float,
    evidence: Dict[str, Any],
    derived: Dict[str, Any],
) -> str:
    """Build the user turn carrying the trade setup, evidence, and work order.

    Args:
        ticker: Exchange ticker.
        trade_thesis: Normalized ``"long"`` or ``"short"``.
        catalyst_name: Catalyst description.
        catalyst_date: Catalyst date as ``YYYY-MM-DD``.
        entry_price: Planned entry price.
        target_price: Target price.
        stop_loss: Stop-loss price.
        time_horizon_days: Expected holding period in days.
        risk_reward_ratio: Precomputed risk/reward ratio (Python, not Claude).
        implied_return_pct: Precomputed implied return in percent.
        evidence: Payload from ``trading_evidence.fetch_trading_evidence``.
        derived: Absolute-level figures derived from ``evidence`` and
            ``entry_price`` by ``trading_report.py`` (support/resistance
            levels, moving averages, current P/E, etc.).

    Returns:
        The user message text.
    """

    sections = [
        f"# Trading report: {ticker} -- {trade_thesis.upper()}\n",
        (
            "Produce the qualitative judgments for this trading report using the tools "
            "provided. The numbers below are already computed; treat them as fixed facts.\n"
        ),
        _render_section(
            "Trade setup (fixed -- do not recompute)",
            {
                "ticker": ticker,
                "trade_thesis": trade_thesis,
                "catalyst_name": catalyst_name,
                "catalyst_date": catalyst_date,
                "entry_price": entry_price,
                "target_price": target_price,
                "stop_loss": stop_loss,
                "time_horizon_days": time_horizon_days,
                "risk_reward_ratio": round(risk_reward_ratio, 2),
                "implied_return_pct": round(implied_return_pct, 2),
            },
        ),
        _render_section("Fundamental catalyst evidence", evidence.get("fundamental_catalyst", {})),
        _render_section("Relative value evidence", evidence.get("relative_value", {})),
        _render_section("Technical evidence", evidence.get("technicals", {})),
        _render_section("Risk factors already on file (do not duplicate)", evidence.get("risk_factors", [])),
        _render_section("Derived absolute levels (evidence + entry price)", derived),
        (
            "## Work order\n\n"
            "1. Call `record_catalyst_probability` once.\n"
            "2. Call `record_technical_setup` once.\n"
            "3. Call `record_conviction` once.\n"
            "4. Call `record_scenario_case` twice: name \"bull\" and name \"bear\".\n"
            "5. Optionally call `flag_risk` for any material risk not already on file.\n\n"
            "Stop calling tools when the analysis is complete."
        ),
    ]
    return "\n".join(sections)
