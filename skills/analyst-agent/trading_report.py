"""Trading Report: a standalone, tactical, catalyst-driven trade thesis.

Unlike the initiation-of-coverage orchestrator (``orchestrator.py``), this
report type has no persistent workspace. ``run_trading_report`` fetches
deterministic mock evidence, runs one Claude tool-use conversation for the
*qualitative* judgments only (catalyst probability, technical verdict,
conviction, bull/bear scenarios, risk flags), computes the risk/reward
arithmetic itself in plain Python, renders Markdown, and returns a dict. It
does not read or write any workspace state and never imports
``workspace_adapter``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import trading_evidence
import trading_prompts
import trading_report_render
from agent_common import (
    AgentRunError,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    ToolResult,
    build_client,
    run_tool_loop,
)

#: Risk/reward at or above this ratio is considered acceptable for full size.
RISK_REWARD_ACCEPTANCE_THRESHOLD = 2.0

#: Tool names required for a run to count as complete tactical coverage.
_REQUIRED_TOOLS = (
    "record_catalyst_probability",
    "record_technical_setup",
    "record_conviction",
)


class TradingReportError(AgentRunError):
    """Raised when a trading report cannot be produced at all."""


def _normalize_trade_thesis(trade_thesis: str) -> str:
    """Normalize and validate ``trade_thesis``.

    Raises:
        ValueError: If ``trade_thesis`` is not ``"long"`` or ``"short"``
            (case-insensitive).
    """

    normalized = (trade_thesis or "").strip().lower()
    if normalized not in ("long", "short"):
        raise ValueError(f"trade_thesis must be 'long' or 'short', got {trade_thesis!r}")
    return normalized


def _compute_risk_reward(
    trade_thesis: str, entry_price: float, target_price: float, stop_loss: float
) -> Dict[str, Any]:
    """Compute risk/reward math deterministically, per the spec formulas.

    Raises:
        ValueError: If ``stop_loss`` equals ``entry_price`` (undefined ratio),
            or if ``entry_price`` is zero (undefined percent return).
    """

    if entry_price == stop_loss:
        raise ValueError("stop_loss must differ from entry_price")
    if entry_price == 0:
        raise ValueError("entry_price must not be zero")

    if trade_thesis == "long":
        risk_reward_ratio = (target_price - entry_price) / (entry_price - stop_loss)
        implied_return_pct = (target_price - entry_price) / entry_price * 100
        inverted = not (target_price > entry_price > stop_loss)
    else:
        risk_reward_ratio = (entry_price - target_price) / (stop_loss - entry_price)
        implied_return_pct = (entry_price - target_price) / entry_price * 100
        inverted = not (target_price < entry_price < stop_loss)

    return {
        "risk_reward_ratio": risk_reward_ratio,
        "implied_return_pct": implied_return_pct,
        "inverted": inverted,
        "below_threshold": risk_reward_ratio < RISK_REWARD_ACCEPTANCE_THRESHOLD,
    }


def _derive_absolute_levels(evidence: Dict[str, Any], entry_price: float) -> Dict[str, Any]:
    """Combine offset/ratio evidence with the caller's ``entry_price``.

    ``trading_evidence.fetch_trading_evidence`` never sees ``entry_price`` --
    it is deterministic on ticker/catalyst/date alone -- so absolute price
    levels (support, resistance, moving averages, current P/E) are computed
    here, once, in plain Python, instead of being asked of Claude or baked
    into the evidence layer.
    """

    relative_value = evidence.get("relative_value", {}) or {}
    technicals = evidence.get("technicals", {}) or {}

    synthetic_eps = relative_value.get("synthetic_eps")
    peer_pe_avg = relative_value.get("peer_pe_avg")
    current_pe = (entry_price / synthetic_eps) if synthetic_eps else None
    pe_vs_peer_avg_pct = (
        (current_pe / peer_pe_avg - 1) * 100 if current_pe is not None and peer_pe_avg else None
    )

    def _price_from_pct_distance(pct: Optional[float]) -> Optional[float]:
        if pct is None:
            return None
        return entry_price / (1 + pct / 100)

    def _price_from_offset(pct: Optional[float]) -> Optional[float]:
        if pct is None:
            return None
        return entry_price * (1 + pct / 100)

    implied_move_pct = relative_value.get("implied_move_pct")

    return {
        "current_pe": round(current_pe, 2) if current_pe is not None else None,
        "peer_pe_avg": peer_pe_avg,
        "pe_vs_peer_avg_pct": round(pe_vs_peer_avg_pct, 1) if pe_vs_peer_avg_pct is not None else None,
        "fifty_dma": _round_or_none(_price_from_pct_distance(relative_value.get("price_vs_50dma_pct"))),
        "two_hundred_dma": _round_or_none(_price_from_pct_distance(relative_value.get("price_vs_200dma_pct"))),
        "support_level": _round_or_none(_price_from_offset(technicals.get("support_offset_pct"))),
        "resistance_level": _round_or_none(_price_from_offset(technicals.get("resistance_offset_pct"))),
        "implied_move_dollars": _round_or_none(
            entry_price * implied_move_pct / 100 if implied_move_pct is not None else None
        ),
    }


def _round_or_none(value: Optional[float]) -> Optional[float]:
    return round(value, 2) if value is not None else None


def _apply_tool_calls(tool_calls: List[ToolResult]) -> Dict[str, Any]:
    """Fold the collected tool calls into the recorded judgments.

    The last call of a given kind wins (mirrors the workspace adapter's
    idempotent-write posture); ``record_scenario_case`` is keyed by its
    ``name`` (``"bull"`` / ``"bear"``) instead.
    """

    catalyst_probability: Optional[Dict[str, Any]] = None
    technical_setup: Optional[Dict[str, Any]] = None
    conviction: Optional[Dict[str, Any]] = None
    bull_case: Optional[Dict[str, Any]] = None
    bear_case: Optional[Dict[str, Any]] = None
    flagged_risks: List[Dict[str, str]] = []
    unknown_tools: List[str] = []
    tool_call_counts: Dict[str, int] = {}

    for call in tool_calls:
        tool_call_counts[call.name] = tool_call_counts.get(call.name, 0) + 1
        if call.name == "record_catalyst_probability":
            catalyst_probability = call.input
        elif call.name == "record_technical_setup":
            technical_setup = call.input
        elif call.name == "record_conviction":
            conviction = call.input
        elif call.name == "record_scenario_case":
            case_name = str(call.input.get("name", "")).strip().lower()
            if case_name == "bull":
                bull_case = call.input
            elif case_name == "bear":
                bear_case = call.input
            else:
                unknown_tools.append(f"record_scenario_case(name={call.input.get('name')!r})")
        elif call.name == "flag_risk":
            flagged_risks.append({"description": call.input.get("description", ""), "category": call.input.get("category", "")})
        else:
            unknown_tools.append(call.name)

    return {
        "catalyst_probability": catalyst_probability,
        "technical_setup": technical_setup,
        "conviction": conviction,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "flagged_risks": flagged_risks,
        "unknown_tools": unknown_tools,
        "tool_call_counts": tool_call_counts,
    }


def run_trading_report(
    ticker: str,
    trade_thesis: str,
    catalyst_name: str,
    catalyst_date: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    time_horizon_days: int = 60,
    max_evidence_sources: int = 10,
    anthropic_api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    client: Any = None,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> Dict[str, Any]:
    """Produce a standalone, catalyst-driven trading report.

    No persistent workspace is read or written. Fetches deterministic mock
    evidence, runs one Claude tool-use conversation for the qualitative
    judgments, computes risk/reward arithmetic in plain Python, renders the
    report, and returns a dict.

    Args:
        ticker: Exchange ticker, e.g. ``ACME``.
        trade_thesis: ``"long"`` or ``"short"`` (case-insensitive).
        catalyst_name: Catalyst description, e.g. ``"Q4 earnings"``.
        catalyst_date: Expected catalyst date as ``YYYY-MM-DD``.
        entry_price: Planned entry price.
        target_price: Target price.
        stop_loss: Stop-loss price.
        time_horizon_days: Expected holding period in days. Defaults to 60.
        max_evidence_sources: Cap on evidence sources surfaced. Defaults to 10.
        anthropic_api_key: API key. Falls back to ``ANTHROPIC_API_KEY``.
        model: Claude model id. Defaults to :data:`agent_common.DEFAULT_MODEL`.
        client: A pre-built Anthropic client, or any object exposing
            ``messages.create``. Supplying one skips SDK construction
            entirely, which is how the integration test runs without network
            access.
        max_turns: Maximum tool-use round trips before the run is cut short.

    Returns:
        A dict with ``trade_report_markdown``, ``risk_reward_ratio``,
        ``implied_return_pct``, ``catalyst_probability_pct``,
        ``technical_setup``, ``conviction``, and ``status``
        (``"success"``, ``"partial"``, or ``"failed"``). Additional diagnostic
        keys (``tool_calls``, ``notes``, ``bull_case``, ``bear_case``,
        ``risks``, ``evidence``) are included for the caller's benefit.

    Raises:
        ValueError: If ``trade_thesis`` is not ``"long"``/``"short"``, or if
            ``stop_loss`` equals ``entry_price``, or if ``entry_price`` is
            zero.
        TradingReportError: If the model returns no tool calls at all.
    """

    ticker = (ticker or "").strip().upper()
    normalized_thesis = _normalize_trade_thesis(trade_thesis)

    math_result = _compute_risk_reward(normalized_thesis, entry_price, target_price, stop_loss)
    risk_reward_ratio = math_result["risk_reward_ratio"]
    implied_return_pct = math_result["implied_return_pct"]
    inverted = math_result["inverted"]
    below_threshold = math_result["below_threshold"]

    evidence = trading_evidence.fetch_trading_evidence(
        ticker, catalyst_name, catalyst_date, normalized_thesis
    )
    if max_evidence_sources < 1:
        evidence = {**evidence, "sources": []}
    else:
        evidence = {**evidence, "sources": list(evidence.get("sources", []))[:max_evidence_sources]}

    derived = _derive_absolute_levels(evidence, entry_price)

    user_prompt = trading_prompts.build_trading_user_prompt(
        ticker=ticker,
        trade_thesis=normalized_thesis,
        catalyst_name=catalyst_name,
        catalyst_date=catalyst_date,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss=stop_loss,
        time_horizon_days=time_horizon_days,
        risk_reward_ratio=risk_reward_ratio,
        implied_return_pct=implied_return_pct,
        evidence=evidence,
        derived=derived,
    )

    active_client = build_client(anthropic_api_key, client)
    tool_calls = run_tool_loop(
        client=active_client,
        model=model,
        system_prompt=trading_prompts.SYSTEM_PROMPT_TRADING,
        tool_definitions=trading_prompts.TOOL_DEFINITIONS_TRADING,
        user_prompt=user_prompt,
        max_turns=max_turns,
    )
    if not tool_calls:
        raise TradingReportError(
            "the model returned no tool calls; no trading judgments were produced"
        )

    applied = _apply_tool_calls(tool_calls)

    notes: List[str] = []
    if inverted:
        expected = "target > entry > stop" if normalized_thesis == "long" else "target < entry < stop"
        notes.append(
            f"entry/target/stop ordering is inverted for a {normalized_thesis} thesis (expected {expected})"
        )
    if below_threshold:
        notes.append(
            f"risk/reward of {risk_reward_ratio:.2f}:1 is below the "
            f"{RISK_REWARD_ACCEPTANCE_THRESHOLD:.1f}:1 acceptance threshold"
        )

    _tool_to_field = {
        "record_catalyst_probability": "catalyst_probability",
        "record_technical_setup": "technical_setup",
        "record_conviction": "conviction",
    }
    missing_required = [
        tool_name for tool_name in _REQUIRED_TOOLS if applied[_tool_to_field[tool_name]] is None
    ]
    if applied["bull_case"] is None:
        missing_required.append("record_scenario_case(bull)")
    if applied["bear_case"] is None:
        missing_required.append("record_scenario_case(bear)")
    if missing_required:
        notes.append("missing required model judgments: " + ", ".join(missing_required))
    if applied["unknown_tools"]:
        notes.append("ignored unrecognized tool calls: " + ", ".join(sorted(set(applied["unknown_tools"]))))

    status = "failed" if missing_required else ("partial" if (inverted or below_threshold) else "success")

    catalyst_probability = applied["catalyst_probability"] or {
        "probability_pct": evidence["fundamental_catalyst"]["historical_beat_rate_pct"],
        "rationale": (
            "Fallback: the model did not record a catalyst probability; using the "
            "evidence-supplied historical base rate unchanged."
        ),
        "historical_base_rate_pct": evidence["fundamental_catalyst"]["historical_beat_rate_pct"],
    }
    technical_setup = applied["technical_setup"] or {
        "trend": "neutral",
        "momentum_signal": "not recorded",
        "volume_signal": "not recorded",
        "verdict": "weak",
        "rationale": "Fallback: the model did not record a technical setup.",
    }
    conviction = applied["conviction"] or {
        "level": "low",
        "favorable_factor_count": 0,
        "rationale": "Fallback: the model did not record a conviction level.",
    }

    risks = list(evidence.get("risk_factors", [])) + list(applied["flagged_risks"])

    trade_report_markdown = trading_report_render.render_trading_report_markdown(
        ticker=ticker,
        trade_thesis=normalized_thesis,
        catalyst_name=catalyst_name,
        catalyst_date=catalyst_date,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss=stop_loss,
        time_horizon_days=time_horizon_days,
        risk_reward_ratio=risk_reward_ratio,
        implied_return_pct=implied_return_pct,
        evidence=evidence,
        derived=derived,
        catalyst_probability=catalyst_probability,
        technical_setup=technical_setup,
        conviction=conviction,
        bull_case=applied["bull_case"],
        bear_case=applied["bear_case"],
        risks=risks,
        inverted=inverted,
        below_threshold=below_threshold,
        missing_required=missing_required,
    )

    return {
        "trade_report_markdown": trade_report_markdown,
        "risk_reward_ratio": risk_reward_ratio,
        "implied_return_pct": implied_return_pct,
        "catalyst_probability_pct": catalyst_probability.get("probability_pct"),
        "technical_setup": technical_setup.get("verdict"),
        "conviction": conviction.get("level"),
        "status": status,
        "tool_calls": applied["tool_call_counts"],
        "notes": notes,
        "bull_case": applied["bull_case"],
        "bear_case": applied["bear_case"],
        "risks": risks,
        "evidence": evidence,
        "derived": derived,
    }
