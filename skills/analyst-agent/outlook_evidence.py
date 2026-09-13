"""Evidence sourcing for the Quarterly Outlook report type.

Like ``data_sources.py`` for the initiation of coverage, this module is
deliberately offline: :func:`fetch_macro_evidence` returns deterministic mock
macro, rates, and sector data so the report can be driven and tested end to
end with no network access and no vendor credentials. A later phase replaces
the synthesis in this module with real macro/market data providers while
keeping the returned schema unchanged.

Determinism contract: for a given ``quarter`` and ``sector_universe``, the
returned payload is byte-identical across calls and across processes. No
``random`` module and no wall-clock read (``datetime.now``/``date.today``)
feed any value here -- every number is derived from a stable hash of the
``quarter`` string (and, for sector rows, of ``quarter`` combined with the
sector name), exactly as ``data_sources._stable_seed`` derives numbers from a
ticker. Dates that appear in the payload are computed from the quarter label
itself (e.g. "Q2 2025" implies calendar months April-June), never from
today's date.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: Default sector coverage when the caller does not narrow the universe.
DEFAULT_SECTOR_UNIVERSE: Tuple[str, ...] = (
    "Technology",
    "Healthcare",
    "Financials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Materials",
    "Utilities",
    "Real Estate",
    "Communication Services",
)

#: Keys every macro evidence payload must carry, whatever the backing provider.
REQUIRED_MACRO_EVIDENCE_KEYS = (
    "quarter",
    "macro_history",
    "macro_forward_estimate",
    "economic_indicators",
    "sector_data",
    "rates_fx",
    "tail_risk_evidence",
    "catalyst_calendar_evidence",
)

#: Rotating pool of tail-risk headlines. Selection from this pool is a
#: deterministic function of the quarter's stable hash (see
#: :func:`_select_tail_risks`), not a random draw.
_TAIL_RISK_POOL: Tuple[Dict[str, str], ...] = (
    {
        "description": (
            "Escalation in Taiwan Strait tensions disrupts semiconductor supply "
            "chains and broad risk sentiment."
        ),
        "category": "geopolitical",
    },
    {
        "description": (
            "A new round of reciprocal tariffs reignites a trade dispute with a "
            "major trading partner."
        ),
        "category": "geopolitical",
    },
    {
        "description": (
            "A central bank surprises with an off-cycle policy move, repricing "
            "the market's rate-cut path."
        ),
        "category": "monetary",
    },
    {
        "description": (
            "High-yield credit spreads widen sharply, signalling funding stress "
            "in a leveraged corner of the market."
        ),
        "category": "monetary",
    },
    {
        "description": (
            "A fiscal standoff over the budget or debt ceiling threatens a "
            "government shutdown or a sovereign rating action."
        ),
        "category": "fiscal",
    },
    {
        "description": (
            "Shelter or services inflation reaccelerates unexpectedly, forcing a "
            "hawkish repricing of the policy path."
        ),
        "category": "monetary",
    },
    {
        "description": (
            "A regional conflict disrupts energy supply routes and pushes crude "
            "oil sharply higher."
        ),
        "category": "geopolitical",
    },
    {
        "description": (
            "A systemically important bank or non-bank lender discloses an "
            "unexpected solvency or liquidity shock."
        ),
        "category": "other",
    },
)

_FED_GUIDANCE_POOL: Tuple[str, ...] = (
    "signalling a prolonged hold as inflation proves stickier than expected",
    "leaning toward gradual cuts as growth and labor-market data cool",
    "keeping full optionality, describing policy as data-dependent meeting by meeting",
)

_REVISIONS_POOL: Tuple[str, ...] = ("improving", "stable", "deteriorating")


class MacroEvidenceSchemaError(ValueError):
    """Raised when a macro evidence payload is missing required keys."""


def _stable_seed(text: str) -> int:
    """Return a deterministic, platform-independent seed for a text key.

    ``hash()`` is salted per process in Python 3, so it cannot be used where
    repeat runs must agree. Mirrors ``data_sources._stable_seed``'s method
    (position-weighted character codes) so the two mock evidence sources stay
    consistent in style; duplicated rather than imported so this module never
    depends on ``data_sources`` internals.
    """

    total = 0
    for position, character in enumerate(text.upper()):
        total += (position + 1) * ord(character)
    return total % 97


def _parse_quarter(quarter: str) -> Tuple[int, int]:
    """Parse a ``"Q1 2025"``-style label into ``(quarter_number, year)``.

    Raises:
        ValueError: If ``quarter`` is empty or not in the expected shape.
    """

    match = re.match(r"^\s*Q([1-4])\s+(\d{4})\s*$", quarter or "", re.IGNORECASE)
    if not match:
        raise ValueError(
            f"quarter must look like 'Q1 2025', got {quarter!r}"
        )
    return int(match.group(1)), int(match.group(2))


def _shift_quarter(quarter_number: int, year: int, delta: int) -> Tuple[int, int]:
    """Return the quarter ``delta`` steps away from ``(quarter_number, year)``."""

    absolute_index = year * 4 + (quarter_number - 1) + delta
    new_year, zero_based_quarter = divmod(absolute_index, 4)
    return zero_based_quarter + 1, new_year


def _quarter_label(quarter_number: int, year: int) -> str:
    return f"Q{quarter_number} {year}"


def _macro_point(label: str, base_seed: int, offset: int) -> Dict[str, Any]:
    """Build one quarter's macro data point.

    ``offset`` is the point's position relative to the requested quarter
    (negative for history, 0 for the requested quarter, positive for a
    forward forecast quarter). ``base_seed`` sets the overall macro regime for
    the run (drawn from the requested quarter, so the whole path is
    internally consistent); ``label``'s own hash adds quarter-to-quarter
    variation on top of that regime.
    """

    seed_q = _stable_seed(label)
    regime = (base_seed % 10) - 5  # -5..4: negative = late-cycle/slowing, positive = expansion

    gdp_growth_yoy_pct = round(2.4 + regime * 0.15 - offset * 0.05 + (seed_q % 7) * 0.03, 2)
    gdp_growth_qoq_annualized_pct = round(gdp_growth_yoy_pct - 0.3 + (seed_q % 5) * 0.04, 2)
    unemployment_pct = round(4.0 + (base_seed % 6) * 0.1 + max(0, -regime) * 0.1 - offset * 0.03, 2)
    cpi_headline_pct = round(2.8 + (base_seed % 8) * 0.08 - offset * 0.04 + (seed_q % 4) * 0.03, 2)
    cpi_core_pct = round(cpi_headline_pct - 0.3 + (seed_q % 3) * 0.02, 2)
    fed_funds_rate_pct = round(3.5 + (base_seed % 10) * 0.1 - offset * 0.05, 2)
    ten_year_yield_pct = round(fed_funds_rate_pct + 0.3 + (seed_q % 5) * 0.05, 2)
    two_year_yield_pct = round(fed_funds_rate_pct + 0.1 + (seed_q % 4) * 0.04, 2)
    hy_oas_bps = round(320 + (base_seed % 15) * 6 - offset * 4 + (seed_q % 6) * 5)
    ig_oas_bps = round(110 + (base_seed % 10) * 3 - offset * 2 + (seed_q % 5) * 2)
    sp500_eps_growth_yoy_pct = round(5.0 + regime * 0.3 + offset * 0.15 + (seed_q % 6) * 0.25, 2)

    return {
        "quarter": label,
        "gdp_growth_yoy_pct": gdp_growth_yoy_pct,
        "gdp_growth_qoq_annualized_pct": gdp_growth_qoq_annualized_pct,
        "unemployment_pct": unemployment_pct,
        "cpi_headline_pct": cpi_headline_pct,
        "cpi_core_pct": cpi_core_pct,
        "fed_funds_rate_pct": fed_funds_rate_pct,
        "ten_year_yield_pct": ten_year_yield_pct,
        "two_year_yield_pct": two_year_yield_pct,
        "two_year_ten_year_spread_bps": round((ten_year_yield_pct - two_year_yield_pct) * 100),
        "hy_oas_bps": hy_oas_bps,
        "ig_oas_bps": ig_oas_bps,
        "sp500_eps_growth_yoy_pct": sp500_eps_growth_yoy_pct,
    }


def _economic_indicators(base_seed: int, current_point: Dict[str, Any]) -> Dict[str, Any]:
    pmi_manufacturing = round(48.0 + (base_seed % 10) * 0.4, 1)
    pmi_services = round(51.0 + (base_seed % 8) * 0.3, 1)
    consumer_confidence_index = round(95.0 + (base_seed % 20) * 1.1, 1)
    forward_pe_sp500 = round(19.0 + (base_seed % 6) * 0.5, 1)
    earnings_yield_pct = round(100.0 / forward_pe_sp500, 2)
    equity_risk_premium_pct = round(
        earnings_yield_pct - current_point["ten_year_yield_pct"], 2
    )
    return {
        "pmi_manufacturing": pmi_manufacturing,
        "pmi_services": pmi_services,
        "consumer_confidence_index": consumer_confidence_index,
        "sp500_earnings_revisions_trend": _REVISIONS_POOL[base_seed % len(_REVISIONS_POOL)],
        "sp500_forward_pe": forward_pe_sp500,
        "sp500_earnings_yield_pct": earnings_yield_pct,
        "equity_risk_premium_pct": equity_risk_premium_pct,
    }


def _sector_data(quarter: str, sector_universe: List[str]) -> Dict[str, Dict[str, Any]]:
    sector_rows: Dict[str, Dict[str, Any]] = {}
    for sector in sector_universe:
        sector_seed = _stable_seed(f"{quarter}|{sector}")
        forward_pe = round(12.0 + (sector_seed % 20) * 0.9, 1)
        historical_avg_pe = round(forward_pe - 2.0 + (sector_seed % 5) * 0.4, 1)
        pe_vs_history_pct = (
            round((forward_pe - historical_avg_pe) / historical_avg_pe * 100, 1)
            if historical_avg_pe
            else 0.0
        )
        sector_rows[sector] = {
            "trailing_return_pct": round(-5.0 + (sector_seed % 30) * 0.8, 1),
            "forward_pe": forward_pe,
            "historical_avg_pe": historical_avg_pe,
            "forward_pe_vs_history_pct": pe_vs_history_pct,
            "consensus_eps_growth_pct": round(2.0 + (sector_seed % 25) * 0.6, 1),
            "earnings_revisions_direction": _REVISIONS_POOL[sector_seed % len(_REVISIONS_POOL)],
        }
    return sector_rows


def _rates_fx(quarter_number: int, year: int, base_seed: int) -> Dict[str, Any]:
    path = []
    for step in range(1, 5):
        future_q, future_year = _shift_quarter(quarter_number, year, step)
        label = _quarter_label(future_q, future_year)
        point = _macro_point(label, base_seed, step)
        path.append({"quarter": label, "implied_fed_funds_rate_pct": point["fed_funds_rate_pct"]})
    usd_index = round(95.0 + (base_seed % 16) * 0.6, 1)
    current = _macro_point(_quarter_label(quarter_number, year), base_seed, 0)
    return {
        "fed_funds_futures_implied_path": path,
        "two_year_ten_year_spread_bps": current["two_year_ten_year_spread_bps"],
        "usd_index": usd_index,
    }


def _select_tail_risks(base_seed: int) -> List[Dict[str, str]]:
    """Deterministically rotate 3-5 tail risks from the fixed pool.

    ``step=3`` is coprime with the 8-entry pool, so successive picks cycle
    through every entry before repeating; the starting point and count are
    both derived from ``base_seed`` so the same quarter always yields the
    same selection.
    """

    count = 3 + (base_seed % 3)  # 3, 4, or 5
    pool_size = len(_TAIL_RISK_POOL)
    picks = []
    for i in range(count):
        picks.append(_TAIL_RISK_POOL[(base_seed + i * 3) % pool_size])
    return list(picks)


def _catalyst_calendar_evidence(quarter_number: int, year: int) -> List[Dict[str, str]]:
    """Build a plausible, quarter-derived macro-data calendar for grounding.

    These are grounding evidence, not the report's recorded catalysts --
    Claude records the report's actual catalyst calendar via `record_catalyst`,
    using these as a factual scaffold (FOMC/CPI/payrolls/PCE all land inside
    the requested quarter's three calendar months).
    """

    start_month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter_number]
    month1, month2, month3 = start_month, start_month + 1, start_month + 2
    return [
        {
            "name": "Nonfarm payrolls / jobs report",
            "date": f"{year}-{month1:02d}-05",
            "impact": (
                "Labor-market cooling supports a dovish rate path; a strong print "
                "delays cuts and pressures duration-sensitive sectors."
            ),
        },
        {
            "name": "CPI inflation print",
            "date": f"{year}-{month1:02d}-12",
            "impact": (
                "First read on the quarter's inflation trend; core services "
                "stickiness is the swing factor for the rate path."
            ),
        },
        {
            "name": "FOMC policy decision",
            "date": f"{year}-{month2:02d}-18",
            "impact": (
                "Sets the near-term rate path priced into front-end rates; a "
                "hawkish surprise pressures rate-sensitive and high-multiple sectors."
            ),
        },
        {
            "name": "PCE inflation release",
            "date": f"{year}-{month3:02d}-28",
            "impact": (
                "The Fed's preferred inflation gauge; confirms or contradicts the "
                "quarter's CPI trend heading into the next quarter."
            ),
        },
    ]


def validate_macro_evidence(evidence: Dict[str, Any]) -> None:
    """Check that a macro evidence payload carries every required key.

    Raises:
        MacroEvidenceSchemaError: If a required key is missing.
    """

    missing = [key for key in REQUIRED_MACRO_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise MacroEvidenceSchemaError(
            f"macro evidence is missing required keys: {', '.join(missing)}"
        )


def fetch_macro_evidence(
    quarter: str,
    lookback_quarters: int = 4,
    sector_universe: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch structured macro, rates, and sector evidence for one quarter.

    Deterministic mock data: no network call is made, and repeat calls with
    the same ``quarter`` and ``sector_universe`` return a byte-identical
    payload (see the module docstring for the determinism contract).

    Args:
        quarter: Quarter label, e.g. ``"Q1 2025"``.
        lookback_quarters: How many historical quarters to include in
            ``macro_history``. Must be at least 1.
        sector_universe: Sectors to build ``sector_data`` rows for. Defaults
            to :data:`DEFAULT_SECTOR_UNIVERSE`.

    Returns:
        A dict with ``quarter``, ``macro_history``, ``macro_forward_estimate``,
        ``economic_indicators``, ``sector_data``, ``rates_fx``,
        ``tail_risk_evidence``, and ``catalyst_calendar_evidence``.

    Raises:
        ValueError: If ``quarter`` is empty or not in ``"Q1 2025"`` shape, or
            ``lookback_quarters`` is less than 1.
        MacroEvidenceSchemaError: If the synthesized payload is incomplete.
    """

    quarter_number, year = _parse_quarter(quarter)
    if lookback_quarters < 1:
        raise ValueError("lookback_quarters must be at least 1")
    sectors = list(sector_universe) if sector_universe else list(DEFAULT_SECTOR_UNIVERSE)
    if not sectors:
        raise ValueError("sector_universe must not be empty")

    normalized_quarter = _quarter_label(quarter_number, year)
    base_seed = _stable_seed(normalized_quarter)

    macro_history = []
    for step_back in range(lookback_quarters, 0, -1):
        past_q, past_year = _shift_quarter(quarter_number, year, -step_back)
        label = _quarter_label(past_q, past_year)
        macro_history.append(_macro_point(label, base_seed, -step_back))

    current_point = _macro_point(normalized_quarter, base_seed, 0)
    next_q, next_year = _shift_quarter(quarter_number, year, 1)
    next_label = _quarter_label(next_q, next_year)
    next_point = _macro_point(next_label, base_seed, 1)

    evidence = {
        "quarter": normalized_quarter,
        "lookback_quarters": lookback_quarters,
        "sector_universe": sectors,
        "macro_history": macro_history,
        "macro_forward_estimate": {
            "current_quarter": current_point,
            "next_quarter_forecast": next_point,
            "fed_policy_guidance": _FED_GUIDANCE_POOL[base_seed % len(_FED_GUIDANCE_POOL)],
        },
        "economic_indicators": _economic_indicators(base_seed, current_point),
        "sector_data": _sector_data(normalized_quarter, sectors),
        "rates_fx": _rates_fx(quarter_number, year, base_seed),
        "tail_risk_evidence": _select_tail_risks(base_seed),
        "catalyst_calendar_evidence": _catalyst_calendar_evidence(quarter_number, year),
    }
    validate_macro_evidence(evidence)
    return evidence
