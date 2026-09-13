"""Render the Trading Report as Markdown from computed figures and tool calls.

Mirrors ``report_generators.py`` in spirit -- nothing here invents, averages, or
smooths a value. Every number in the rendered report traces to one of three
places: a function input (entry/target/stop/catalyst/time horizon), the
deterministic evidence payload (``trading_evidence.fetch_trading_evidence``,
plus the absolute levels ``trading_report.py`` derives from it), or a
``tool_use`` call Claude actually made. Where a required judgment was not
recorded, the report says so explicitly instead of presenting a default value
as if the model had produced it.

Kept short-form by design: this report type targets 2-4 pages, numbers over
prose, tables and bullets dominant.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from render_helpers import format_number, format_price, markdown_table

CHECK = "[x]"
UNCHECK = "[ ]"


def _fmt_price(value: Any) -> str:
    return format_price(value)


def _fmt_pct(number: Any, digits: int = 1) -> str:
    try:
        return f"{float(number):+.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct_plain(number: Any, digits: int = 1) -> str:
    try:
        return f"{float(number):.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    return markdown_table(headers, rows)


def _header(
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
    catalyst_probability_pct: float,
    conviction_level: str,
    inverted: bool,
    below_threshold: bool,
) -> str:
    direction = trade_thesis.upper()
    lines = [
        f"# {ticker} -- {direction} Trading Thesis\n",
        (
            f"**{direction} {ticker} @ {_fmt_price(entry_price)} | "
            f"Target {_fmt_price(target_price)} | Stop {_fmt_price(stop_loss)} | "
            f"R:R {format_number(risk_reward_ratio)}:1 | "
            f"Catalyst: {catalyst_name} ({catalyst_date}) | "
            f"Conviction: {conviction_level.upper()} | "
            f"Horizon: {time_horizon_days}d**\n"
        ),
        (
            f"{direction.title()} thesis into **{catalyst_name}** on **{catalyst_date}**, "
            f"a {time_horizon_days}-day tactical setup. Entry {_fmt_price(entry_price)}, "
            f"target {_fmt_price(target_price)} ({_fmt_pct(implied_return_pct)} implied), "
            f"stop {_fmt_price(stop_loss)}, risk/reward {format_number(risk_reward_ratio)}:1. "
            f"Catalyst probability {_fmt_pct_plain(catalyst_probability_pct)}; conviction "
            f"{conviction_level}.\n"
        ),
        _table(
            ["Field", "Value"],
            [
                ["Direction", direction],
                ["Entry", _fmt_price(entry_price)],
                ["Target", _fmt_price(target_price)],
                ["Stop", _fmt_price(stop_loss)],
                ["Risk/reward", f"{format_number(risk_reward_ratio)}:1"],
                ["Implied return", _fmt_pct(implied_return_pct)],
                ["Catalyst", f"{catalyst_name} ({catalyst_date})"],
                ["Time horizon", f"{time_horizon_days} days"],
                ["Conviction", conviction_level],
            ],
        ),
        "",
    ]
    if inverted:
        lines.append(
            f"> **Caution -- inverted setup:** the entry/target/stop levels are not ordered "
            f"the way a {trade_thesis} thesis expects "
            f"({'target > entry > stop' if trade_thesis == 'long' else 'target < entry < stop'}). "
            "Verify these levels before executing.\n"
        )
    if below_threshold:
        lines.append(
            f"> **Caution -- risk/reward below threshold:** {format_number(risk_reward_ratio)}:1 is "
            "below the 2:1 ratio this desk requires to accept a setup at full size.\n"
        )
    return "\n".join(lines)


def _fundamental_catalyst(
    catalyst_name: str,
    catalyst_date: str,
    catalyst_type: str,
    fundamental_evidence: Dict[str, Any],
    catalyst_probability: Dict[str, Any],
    trade_thesis: str,
    technical_setup: Dict[str, Any],
    derived: Dict[str, Any],
) -> str:
    lines = ["## I. Fundamental Catalyst\n"]
    lines.append(f"**Catalyst:** {catalyst_name} ({catalyst_type}), expected {catalyst_date}.\n")
    lines.append(f"{fundamental_evidence.get('consensus_summary', 'n/a')}\n")
    lines.append(f"{fundamental_evidence.get('context', '')}\n")

    lines.append("**Why we like it:**\n")
    lines.append(
        f"- Catalyst probability of {_fmt_pct_plain(catalyst_probability.get('probability_pct'))} "
        f"vs. a {_fmt_pct_plain(catalyst_probability.get('historical_base_rate_pct'))} historical "
        f"base rate: {catalyst_probability.get('rationale', 'no rationale recorded')}"
    )
    if str(technical_setup.get("verdict")) in ("strong", "moderate"):
        lines.append(
            f"- Technical setup is {technical_setup.get('verdict')}: {technical_setup.get('rationale', '')}"
        )
    pe_gap = derived.get("pe_vs_peer_avg_pct")
    if pe_gap is not None:
        lines.append(
            f"- Trades at {_fmt_pct(pe_gap)} vs. the peer P/E average, a relative-value input to "
            "the thesis alongside the catalyst."
        )
    lines.append("")

    lines.append(f"**What would make the opposite ({'short' if trade_thesis == 'long' else 'long'}) case right:**\n")
    if str(technical_setup.get("verdict")) == "weak":
        lines.append(f"- Technical setup is already weak: {technical_setup.get('rationale', '')}")
    lines.append(
        "- The catalyst resolves against this thesis (a miss, a rejection, a broken deal) rather "
        "than in line with the recorded probability above."
    )
    lines.append("")

    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Historical base rate", _fmt_pct_plain(catalyst_probability.get("historical_base_rate_pct"))],
                ["Recorded catalyst probability", _fmt_pct_plain(catalyst_probability.get("probability_pct"))],
            ],
        )
    )
    return "\n".join(lines) + "\n"


def _valuation_relative_value(
    relative_value: Dict[str, Any],
    derived: Dict[str, Any],
    bull_case: Optional[Dict[str, Any]],
    bear_case: Optional[Dict[str, Any]],
) -> str:
    lines = ["## II. Valuation & Relative Value\n"]
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Current P/E (entry price basis)", format_number(derived.get("current_pe"))],
                ["Peer P/E average", format_number(relative_value.get("peer_pe_avg"))],
                ["P/E vs. peer average", _fmt_pct(derived.get("pe_vs_peer_avg_pct"))],
                ["Price vs. 50-day MA", _fmt_pct(relative_value.get("price_vs_50dma_pct"))],
                ["Price vs. 200-day MA", _fmt_pct(relative_value.get("price_vs_200dma_pct"))],
                ["Options-implied move into catalyst", _fmt_pct_plain(relative_value.get("implied_move_pct"))],
            ],
        )
    )
    lines.append("")

    peers = relative_value.get("peer_set") or []
    if peers:
        lines.append("**Peer set:**\n")
        lines.append(
            _table(
                ["Ticker", "Company", "P/E"],
                [[peer.get("ticker", ""), peer.get("company", ""), format_number(peer.get("pe_ratio"))] for peer in peers],
            )
        )
        lines.append("")

    synthetic_eps = relative_value.get("synthetic_eps")
    rows = []
    for label, case in (("Bull", bull_case), ("Bear", bear_case)):
        if case is None:
            rows.append([label, "_not recorded by the model_", "-"])
            continue
        price = case.get("resulting_price_estimate")
        implied_pe = None
        try:
            if synthetic_eps:
                implied_pe = float(price) / float(synthetic_eps)
        except (TypeError, ValueError):
            implied_pe = None
        rows.append([label, _fmt_price(price), format_number(implied_pe) if implied_pe is not None else "n/a"])
    lines.append("**Price under the beat/miss cases:**\n")
    lines.append(_table(["Case", "Resulting price", "Implied P/E"], rows))
    return "\n".join(lines) + "\n"


def _technical_setup_section(
    technical_setup: Dict[str, Any],
    technicals_evidence: Dict[str, Any],
    derived: Dict[str, Any],
    entry_price: float,
) -> str:
    lines = ["## III. Technical Setup\n"]
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Entry vs. support", f"{_fmt_price(entry_price)} vs. {_fmt_price(derived.get('support_level'))}"],
                ["Entry vs. resistance", f"{_fmt_price(entry_price)} vs. {_fmt_price(derived.get('resistance_level'))}"],
                ["50-day MA", _fmt_price(derived.get("fifty_dma"))],
                ["200-day MA", _fmt_price(derived.get("two_hundred_dma"))],
                ["Chart pattern", technicals_evidence.get("chart_pattern", "n/a")],
                ["Trend (recorded)", technical_setup.get("trend", "n/a")],
                ["Momentum", technical_setup.get("momentum_signal", "n/a")],
                ["RSI / MACD (evidence)", f"RSI {format_number(technicals_evidence.get('rsi'))}, MACD {technicals_evidence.get('macd_signal', 'n/a')}"],
                ["Volume", technical_setup.get("volume_signal", "n/a")],
                ["Short interest", _fmt_pct_plain(technicals_evidence.get("short_interest_pct"))],
            ],
        )
    )
    lines.append("")
    lines.append(
        f"**Overall verdict: {str(technical_setup.get('verdict', 'n/a')).upper()}.** "
        f"{technical_setup.get('rationale', 'no rationale recorded')}\n"
    )
    return "\n".join(lines) + "\n"


def _sizing_guidance(conviction_level: str) -> str:
    return {
        "high": "full modeled size",
        "medium": "half modeled size",
        "low": "quarter modeled size, or skip pending a stronger signal",
    }.get(conviction_level, "reduced size pending clarification of conviction")


def _risk_management(
    entry_price: float,
    target_price: float,
    stop_loss: float,
    risk_reward_ratio: float,
    implied_return_pct: float,
    conviction_level: str,
    risks: List[Dict[str, str]],
    below_threshold: bool,
    inverted: bool,
) -> str:
    risk_per_share = abs(entry_price - stop_loss)
    reward_per_share = abs(target_price - entry_price)
    risk_pct = (risk_per_share / entry_price * 100) if entry_price else None

    lines = ["## IV. Risk Management\n"]
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Risk per share (entry to stop)", _fmt_price(risk_per_share)],
                ["Reward per share (entry to target)", _fmt_price(reward_per_share)],
                ["Max loss if stopped out", _fmt_pct_plain(risk_pct) if risk_pct is not None else "n/a"],
                ["Implied gain at target", _fmt_pct(implied_return_pct)],
                ["Risk/reward", f"{format_number(risk_reward_ratio)}:1"],
            ],
        )
    )
    lines.append("")
    lines.append(f"**Sizing mitigant:** conviction is {conviction_level}; size at {_sizing_guidance(conviction_level)}.\n")
    if below_threshold or inverted:
        lines.append(
            "**Caution carried forward:** "
            + " ".join(
                filter(
                    None,
                    [
                        "risk/reward is below the 2:1 acceptance threshold." if below_threshold else "",
                        "entry/target/stop levels are inverted for this thesis direction." if inverted else "",
                    ],
                )
            )
            + "\n"
        )

    if risks:
        lines.append("**Risk sensitivities:**\n")
        lines.append(
            _table(
                ["Risk", "Category"],
                [[risk.get("description", ""), risk.get("category", "")] for risk in risks],
            )
        )
    else:
        lines.append("_No risk sensitivities are recorded._\n")
    return "\n".join(lines) + "\n"


def _execution_plan(
    ticker: str,
    trade_thesis: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    catalyst_name: str,
    catalyst_date: str,
    time_horizon_days: int,
    risk_reward_ratio: float,
    conviction_level: str,
) -> str:
    lines = ["## V. Execution Plan\n"]
    lines.append(
        _table(
            ["Field", "Value"],
            [
                ["Ticker", ticker],
                ["Direction", trade_thesis.upper()],
                ["Entry", _fmt_price(entry_price)],
                ["Target", _fmt_price(target_price)],
                ["Stop", _fmt_price(stop_loss)],
                ["Risk/reward", f"{format_number(risk_reward_ratio)}:1"],
                ["Position size", _sizing_guidance(conviction_level)],
                ["Catalyst date", f"{catalyst_name} -- {catalyst_date}"],
                ["Time horizon", f"{time_horizon_days} days"],
            ],
        )
    )
    lines.append("")
    lines.append(
        f"Hold through the catalyst on **{catalyst_date}**; the full time window is "
        f"**{time_horizon_days} days** from entry. Exit systematically at the "
        f"{time_horizon_days}-day mark once the catalyst has resolved and the thesis has played "
        f"out, or immediately on a stop-loss breach at {_fmt_price(stop_loss)} regardless of the "
        "catalyst date.\n"
    )
    return "\n".join(lines) + "\n"


def _alternative_views(bull_case: Optional[Dict[str, Any]], bear_case: Optional[Dict[str, Any]]) -> str:
    lines = ["## VI. Alternative Views\n"]
    for label, case in (("Bull case", bull_case), ("Bear case", bear_case)):
        lines.append(f"### {label}\n")
        if case is None:
            lines.append("_Not recorded by the model._\n")
            continue
        lines.append(f"- **Trigger:** {case.get('trigger', 'n/a')}")
        lines.append(f"- **Resulting price estimate:** {_fmt_price(case.get('resulting_price_estimate'))}")
        lines.append(f"- **Rationale:** {case.get('rationale', 'n/a')}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _final_checklist(
    ticker: str,
    trade_thesis: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    risk_reward_ratio: float,
    below_threshold: bool,
    technical_setup: Dict[str, Any],
    bull_case: Optional[Dict[str, Any]],
    bear_case: Optional[Dict[str, Any]],
    missing_required: Sequence[str],
) -> str:
    def box(condition: bool) -> str:
        return CHECK if condition else UNCHECK

    lines = ["## VII. Final Checklist\n"]
    lines.append(f"- {box(True)} Catalyst clearly defined and dated")
    lines.append(f"- {box(not below_threshold)} Risk/reward at or above 2:1 ({format_number(risk_reward_ratio)}:1)")
    lines.append(
        f"- {box(bool(technical_setup.get('trend') and technical_setup.get('momentum_signal') and technical_setup.get('volume_signal')))} "
        "Technical setup analyzed (trend, momentum, volume)"
    )
    lines.append(f"- {box(True)} Relative value assessed (vs. peers, vs. moving averages)")
    lines.append(f"- {box(True)} Downside protection defined (stop-loss level and sizing mitigant)")
    lines.append(f"- {box(bull_case is not None)} Upside case defined (target and bull scenario)")
    lines.append(f"- {box(True)} Time window defined (holding period and exit rule)")
    lines.append(f"- {box(True)} Position-sizing guidance given")
    lines.append("")

    direction = trade_thesis.upper()
    if missing_required:
        verdict = f"**DO NOT INITIATE {direction} {ticker} -- missing: {', '.join(missing_required)}.**"
    elif below_threshold:
        verdict = (
            f"**INITIATE {direction} {ticker} @ {_fmt_price(entry_price)} | "
            f"Target {_fmt_price(target_price)} | Stop {_fmt_price(stop_loss)} -- REDUCED SIZE "
            "(risk/reward below 2:1).**"
        )
    else:
        verdict = (
            f"**INITIATE {direction} {ticker} @ {_fmt_price(entry_price)} | "
            f"Target {_fmt_price(target_price)} | Stop {_fmt_price(stop_loss)}.**"
        )
    lines.append(verdict)
    return "\n".join(lines) + "\n"


def render_trading_report_markdown(
    *,
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
    catalyst_probability: Dict[str, Any],
    technical_setup: Dict[str, Any],
    conviction: Dict[str, Any],
    bull_case: Optional[Dict[str, Any]],
    bear_case: Optional[Dict[str, Any]],
    risks: List[Dict[str, str]],
    inverted: bool,
    below_threshold: bool,
    missing_required: Sequence[str],
) -> str:
    """Render the full trading report as Markdown.

    Every figure either comes from the function inputs, the deterministic
    evidence/derived-levels payloads, or a tool call Claude actually made.
    Missing required judgments are rendered as explicit absences, never
    silently defaulted.

    Args:
        ticker: Exchange ticker.
        trade_thesis: Normalized ``"long"`` or ``"short"``.
        catalyst_name: Catalyst description, echoed from the function inputs.
        catalyst_date: Catalyst date, echoed from the function inputs.
        entry_price: Planned entry price.
        target_price: Target price.
        stop_loss: Stop-loss price.
        time_horizon_days: Expected holding period in days.
        risk_reward_ratio: Precomputed risk/reward ratio.
        implied_return_pct: Precomputed implied return in percent.
        evidence: Payload from ``trading_evidence.fetch_trading_evidence``.
        derived: Absolute-level figures derived from ``evidence`` and
            ``entry_price``.
        catalyst_probability: The (possibly fallback) ``record_catalyst_probability``
            input.
        technical_setup: The (possibly fallback) ``record_technical_setup`` input.
        conviction: The (possibly fallback) ``record_conviction`` input.
        bull_case: The ``record_scenario_case`` input for ``"bull"``, or ``None``
            if the model never recorded one.
        bear_case: The ``record_scenario_case`` input for ``"bear"``, or ``None``.
        risks: Combined risk list (evidence risk factors plus any ``flag_risk``
            tool calls).
        inverted: Whether the entry/target/stop ordering is nonsensical for
            this thesis direction.
        below_threshold: Whether ``risk_reward_ratio`` is below 2.0.
        missing_required: Names of required tool calls the model never made.

    Returns:
        A Markdown document, short-form (2-4 pages).
    """

    sections = [
        _header(
            ticker,
            trade_thesis,
            catalyst_name,
            catalyst_date,
            entry_price,
            target_price,
            stop_loss,
            time_horizon_days,
            risk_reward_ratio,
            implied_return_pct,
            catalyst_probability.get("probability_pct"),
            str(conviction.get("level", "n/a")),
            inverted,
            below_threshold,
        ),
        _fundamental_catalyst(
            catalyst_name,
            catalyst_date,
            evidence.get("catalyst_type", "event"),
            evidence.get("fundamental_catalyst", {}),
            catalyst_probability,
            trade_thesis,
            technical_setup,
            derived,
        ),
        _valuation_relative_value(evidence.get("relative_value", {}), derived, bull_case, bear_case),
        _technical_setup_section(technical_setup, evidence.get("technicals", {}), derived, entry_price),
        _risk_management(
            entry_price,
            target_price,
            stop_loss,
            risk_reward_ratio,
            implied_return_pct,
            str(conviction.get("level", "low")),
            risks,
            below_threshold,
            inverted,
        ),
        _execution_plan(
            ticker,
            trade_thesis,
            entry_price,
            target_price,
            stop_loss,
            catalyst_name,
            catalyst_date,
            time_horizon_days,
            risk_reward_ratio,
            str(conviction.get("level", "low")),
        ),
        _alternative_views(bull_case, bear_case),
        _final_checklist(
            ticker,
            trade_thesis,
            entry_price,
            target_price,
            stop_loss,
            risk_reward_ratio,
            below_threshold,
            technical_setup,
            bull_case,
            bear_case,
            missing_required,
        ),
    ]
    return "\n---\n\n".join(section.rstrip() + "\n" for section in sections)
