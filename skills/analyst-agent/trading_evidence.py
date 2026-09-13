"""Evidence sourcing for the Trading Report agent.

Mirrors the spirit of ``data_sources.py`` (Phase 1's evidence module) but is a
separate, standalone module: Trading Report has no persistent workspace, and
its evidence shape is tactical rather than fundamental -- a catalyst, a
relative-value snapshot, a technical setup, and a short list of risk
sensitivities, instead of a full company dossier.

This module is deliberately offline: :func:`fetch_trading_evidence` returns
deterministic mock evidence. A later phase can replace the synthesis internals
with real market-data and options-analytics providers while keeping the
returned schema unchanged, exactly as ``data_sources.py`` documents for its own
mock-to-real transition.

Nothing here knows about dollar price levels: :func:`fetch_trading_evidence`
takes no entry/target/stop price, so it returns *offsets* and *ratios* rather
than absolute levels. The caller (``trading_report.py``) combines these with
the user-supplied ``entry_price`` to produce concrete support/resistance
levels, moving averages, and multiples -- so the same evidence call is valid
however the trade is priced.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

#: Keys every trading-evidence payload must carry.
REQUIRED_TRADING_EVIDENCE_KEYS = (
    "catalyst_type",
    "fundamental_catalyst",
    "relative_value",
    "technicals",
    "risk_factors",
    "sources",
)

#: Minimum number of risk sensitivities the evidence must supply, per spec.
MINIMUM_RISK_FACTORS = 2


class TradingEvidenceError(ValueError):
    """Raised when a trading-evidence payload is missing required keys."""


def _stable_seed(key: str) -> int:
    """Return a deterministic, platform-independent seed for an arbitrary key.

    ``hash()`` is salted per process in Python 3, so it cannot be used where
    repeat runs must agree. This mirrors ``data_sources._stable_seed`` but
    accepts a single composite string so it can be seeded off
    ``ticker + catalyst_name + catalyst_date`` together.
    """

    total = 0
    for position, character in enumerate(key.upper()):
        total += (position + 1) * ord(character)
    return total % 97


def _classify_catalyst(catalyst_name: str) -> str:
    """Classify a catalyst name into a broad type used to shape mock context.

    Falls back to a generic "event" bucket rather than guessing specifics for
    a catalyst name the evidence layer does not recognize.
    """

    lowered = catalyst_name.lower()
    if any(token in lowered for token in ("earnings", "quarter", "q1", "q2", "q3", "q4", "results")):
        return "earnings"
    if any(token in lowered for token in ("fda", "approval", "regulatory", "pdufa", "cms", "ruling")):
        return "regulatory"
    if any(token in lowered for token in ("merger", "acquisition", "m&a", "takeover", "deal", "buyout")):
        return "m&a"
    return "event"


def _fundamental_catalyst(catalyst_type: str, catalyst_name: str, seed: int) -> Dict[str, Any]:
    """Build catalyst context appropriate to the catalyst's classified type."""

    historical_beat_rate_pct = round(45.0 + (seed % 41), 1)  # 45-85
    if catalyst_type == "earnings":
        revision_pct = round(-3.0 + (seed % 13) * 0.6, 1)  # roughly -3.0 to +4.2
        consensus_summary = (
            f"Consensus models a print in line with trend; the last four quarters beat "
            f"consensus EPS {historical_beat_rate_pct:.0f}% of the time, with an average "
            f"estimate revision of {revision_pct:+.1f}% into the print."
        )
        context = (
            f"'{catalyst_name}' is a scheduled earnings release; the relevant history is "
            "the beat/miss and guidance-revision record over the last four quarters."
        )
    elif catalyst_type == "regulatory":
        historical_beat_rate_pct = round(35.0 + (seed % 51), 1)  # 35-85, wider range
        consensus_summary = (
            f"Base rate for comparable regulatory decisions in this category is "
            f"approximately {historical_beat_rate_pct:.0f}%, based on prior review-cycle "
            "outcomes for similar filings."
        )
        context = (
            f"'{catalyst_name}' is a binary regulatory/approval-style event; there is no "
            "consensus EPS to beat or miss, so the relevant probability is a base rate "
            "drawn from comparable prior decisions."
        )
    elif catalyst_type == "m&a":
        historical_beat_rate_pct = round(55.0 + (seed % 36), 1)  # 55-90
        consensus_summary = (
            f"Deal-spread-implied completion probability is approximately "
            f"{historical_beat_rate_pct:.0f}%, based on the current spread to the announced "
            "terms and the regulatory posture in this sector."
        )
        context = (
            f"'{catalyst_name}' is an M&A/deal-timing catalyst; the relevant probability is "
            "the market-implied odds of completion on the stated terms and timeline."
        )
    else:
        consensus_summary = (
            f"No standardized consensus metric applies to '{catalyst_name}'; the base rate "
            f"below reflects comparable prior events of this type "
            f"({historical_beat_rate_pct:.0f}% historical favorable-outcome rate)."
        )
        context = f"'{catalyst_name}' is treated as a generic scheduled event."

    return {
        "historical_beat_rate_pct": historical_beat_rate_pct,
        "consensus_summary": consensus_summary,
        "context": context,
    }


def _relative_value(seed: int) -> Dict[str, Any]:
    """Build a small synthesized peer set and price-vs-technical-average snapshot."""

    peer_set: List[Dict[str, Any]] = [
        {"ticker": "PEER1", "company": "Comparable One Inc.", "pe_ratio": round(14.5 + (seed % 6) * 0.5, 1)},
        {"ticker": "PEER2", "company": "Comparable Two Corp.", "pe_ratio": round(17.0 + (seed % 5) * 0.6, 1)},
        {"ticker": "PEER3", "company": "Comparable Three Ltd.", "pe_ratio": round(20.0 + (seed % 4) * 0.7, 1)},
    ]
    peer_pe_avg = round(sum(peer["pe_ratio"] for peer in peer_set) / len(peer_set), 1)

    return {
        "synthetic_eps": round(1.10 + (seed % 23) * 0.09, 2),
        "peer_set": peer_set,
        "peer_pe_avg": peer_pe_avg,
        # Signed pct distance of the current price from each moving average.
        "price_vs_50dma_pct": round(-6.0 + (seed % 25) * 0.7, 1),
        "price_vs_200dma_pct": round(-4.0 + (seed % 19) * 0.9, 1),
        # Options-style implied move over the catalyst window, always positive.
        "implied_move_pct": round(3.0 + (seed % 13) * 0.55, 1),
    }


def _technicals(seed: int) -> Dict[str, Any]:
    """Build a chart/technical snapshot as offsets from the (unknown-here) current price."""

    volume_signals = ["accumulation", "distribution", "neutral"]
    macd_signals = ["bullish", "bearish", "neutral"]
    patterns = [
        "higher-low base building above the prior consolidation range",
        "range-bound drift between well-tested support and resistance",
        "descending channel with lower highs into the catalyst",
        "breakout attempt from a multi-month base, not yet confirmed on volume",
    ]

    return {
        "support_offset_pct": round(-8.0 - (seed % 9) * 0.5, 1),
        "resistance_offset_pct": round(6.0 + (seed % 11) * 0.5, 1),
        "chart_pattern": patterns[seed % len(patterns)],
        "volume_signal": volume_signals[seed % len(volume_signals)],
        "rsi": round(38.0 + (seed % 41), 1),  # 38-78
        "macd_signal": macd_signals[(seed // 3) % len(macd_signals)],
        "short_interest_pct": round(1.5 + (seed % 21) * 0.6, 1),
    }


def _risk_factors(catalyst_type: str, trade_thesis: str, seed: int) -> List[Dict[str, str]]:
    """Build at least :data:`MINIMUM_RISK_FACTORS` sensitivities, framed to the thesis direction."""

    thesis = trade_thesis.strip().lower()
    adverse = "a sharp reversal against the position" if thesis == "long" else "a squeeze against the short"

    macro_desc = (
        "A broad risk-off move in rates or credit spreads compresses the multiple this thesis "
        f"depends on, independent of the catalyst outcome, risking {adverse}."
    )
    liquidity_desc = (
        "Average daily volume is thin enough that a fast market around the catalyst print could "
        "widen the effective entry/exit spread beyond the modeled stop distance."
    )
    regulatory_desc = (
        "A parallel regulatory or policy action in the sector could overwhelm the idiosyncratic "
        "catalyst, moving the stock on a factor unrelated to the thesis."
    )
    event_desc = (
        "The catalyst date itself is subject to slippage; a delayed announcement extends the "
        "holding period and time-decays the setup without invalidating the thesis."
    )

    factors = [
        {"description": macro_desc, "category": "macro"},
        {"description": liquidity_desc, "category": "liquidity"},
    ]
    # Deterministically add one of the two remaining categories so every
    # payload carries at least three, biased toward whichever is most relevant
    # to the catalyst type.
    if catalyst_type in ("regulatory", "m&a") or seed % 2 == 0:
        factors.append({"description": regulatory_desc, "category": "regulatory"})
    else:
        factors.append({"description": event_desc, "category": "event"})
    return factors


def _sources(ticker: str, catalyst_name: str, catalyst_date: str, seed: int) -> List[Dict[str, Any]]:
    """Build a short provenance list for the mock evidence, dated off ``catalyst_date``."""

    try:
        anchor = dt.date.fromisoformat(catalyst_date)
    except (TypeError, ValueError):
        anchor = dt.date.today()

    return [
        {
            "title": f"{ticker} options-implied move snapshot",
            "url": f"https://marketdata.example.com/{ticker.lower()}/implied-move",
            "date": (anchor - dt.timedelta(days=1)).isoformat(),
            "publisher": "Market Data Service",
            "extract": "Front-month implied move and peer multiple snapshot ahead of the catalyst.",
        },
        {
            "title": f"{ticker} technical chart snapshot",
            "url": f"https://charting.example.com/{ticker.lower()}/technicals",
            "date": (anchor - dt.timedelta(days=2)).isoformat(),
            "publisher": "Charting Service",
            "extract": "Support/resistance, moving averages, RSI, MACD, and short interest.",
        },
        {
            "title": f"{ticker} prior-period catalyst history",
            "url": f"https://research.example.com/{ticker.lower()}/{catalyst_name.lower().replace(' ', '-')}",
            "date": (anchor - dt.timedelta(days=7)).isoformat(),
            "publisher": "Research Data Service",
            "extract": "Historical base rate and revision pattern for this catalyst type.",
        },
    ]


def validate_trading_evidence(evidence: Dict[str, Any]) -> None:
    """Check that a trading-evidence payload carries every required key.

    Raises:
        TradingEvidenceError: If a required key is missing, or fewer than
            :data:`MINIMUM_RISK_FACTORS` risk factors are present.
    """

    missing = [key for key in REQUIRED_TRADING_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise TradingEvidenceError(f"evidence is missing required keys: {', '.join(missing)}")
    if len(evidence.get("risk_factors") or []) < MINIMUM_RISK_FACTORS:
        raise TradingEvidenceError(
            f"evidence must supply at least {MINIMUM_RISK_FACTORS} risk factors"
        )


def fetch_trading_evidence(
    ticker: str,
    catalyst_name: str,
    catalyst_date: str,
    trade_thesis: str,
) -> Dict[str, Any]:
    """Fetch structured, deterministic tactical evidence for one trade idea.

    Mock/deterministic only: no network call is made. The same
    ``ticker`` + ``catalyst_name`` + ``catalyst_date`` combination always
    produces byte-identical evidence, so repeat runs (and tests) can rely on
    exact values. ``trade_thesis`` only affects how risk sensitivities are
    *framed* (long vs. short exposure), never the underlying seed, so flipping
    the thesis for the same catalyst does not change the market backdrop.

    Args:
        ticker: Exchange ticker, e.g. ``ACME``.
        catalyst_name: Human-readable catalyst description, e.g. ``Q4 earnings``.
        catalyst_date: Expected catalyst date as ``YYYY-MM-DD``.
        trade_thesis: ``"long"`` or ``"short"`` (case-insensitive).

    Returns:
        A dict with ``catalyst_type``, ``fundamental_catalyst``,
        ``relative_value``, ``technicals``, ``risk_factors``, and ``sources``.

    Raises:
        ValueError: If ``ticker`` or ``catalyst_name`` is empty.
        TradingEvidenceError: If the synthesized payload is incomplete.
    """

    ticker = (ticker or "").strip().upper()
    catalyst_name = (catalyst_name or "").strip()
    if not ticker:
        raise ValueError("ticker must not be empty")
    if not catalyst_name:
        raise ValueError("catalyst_name must not be empty")

    seed = _stable_seed(f"{ticker}|{catalyst_name}|{catalyst_date}")
    catalyst_type = _classify_catalyst(catalyst_name)

    evidence = {
        "catalyst_type": catalyst_type,
        "fundamental_catalyst": _fundamental_catalyst(catalyst_type, catalyst_name, seed),
        "relative_value": _relative_value(seed),
        "technicals": _technicals(seed),
        "risk_factors": _risk_factors(catalyst_type, trade_thesis, seed),
        "sources": _sources(ticker, catalyst_name, catalyst_date, seed),
    }
    validate_trading_evidence(evidence)
    return evidence
