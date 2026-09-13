"""Evidence sourcing for the sector-report agent.

Phase 2b is deliberately offline, exactly like ``data_sources.py`` for the
company-level agent: :func:`fetch_sector_evidence` returns deterministic mock
evidence so the orchestrator, adapter, and report renderer can be exercised
end to end without network access or vendor credentials. Real providers
(industry data vendors, consensus estimate feeds, market data) replace
:func:`_synthesize_evidence` later while the returned schema stays the same.

Determinism mirrors ``data_sources._synthesize_evidence``: every figure is a
function of a stable hash of the inputs, never of wall-clock randomness, so
two calls with the same arguments (on the same day) return byte-identical
evidence.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

#: Keys every evidence payload must carry, whatever the backing provider.
REQUIRED_EVIDENCE_KEYS = (
    "sector_overview",
    "value_chain",
    "peers",
    "structural_drivers",
    "cyclicality",
    "macro_lens",
    "geopolitical_risk",
    "sources",
)

_NAME_POOL = (
    "Northgate", "Meridian", "Vantage", "Summit", "Atlas", "Beacon",
    "Crestwood", "Lodestar", "Ridgeline", "Cobalt", "Ironwood", "Fernbridge",
)

_GROWTH_DRIVER_POOL = (
    "structural demand growth from underlying end-market electrification and digitization",
    "share gains by scaled players as smaller competitors exit on rising compliance costs",
    "a multi-year replacement cycle for an aging installed base",
    "pricing power from capacity constraints relative to demand",
    "expansion into adjacent geographies with lower current penetration",
    "mix shift toward higher-value, higher-margin product tiers",
)

_TAILWIND_POOL = (
    "consolidation among mid-tier competitors is reducing price competition",
    "regulatory standards are raising the specification bar in ways scaled incumbents clear more easily",
    "a wave of technology disruption is expanding the addressable market rather than merely reallocating it",
    "customer concentration is easing as new buyer segments enter the category",
)

_HEADWIND_POOL = (
    "new low-cost entrants are compressing pricing in the commodity tier",
    "input cost volatility is compressing margins faster than pricing can adjust",
    "a substitute technology threatens to disintermediate the core value proposition over the cycle",
)

_LEADING_INDICATOR_POOL = (
    "distributor channel inventory-to-sales ratio",
    "new order bookings and book-to-bill ratio",
    "capacity utilization across the largest producers",
    "credit spreads for sector issuers as a funding-cost proxy",
    "purchasing-manager survey new-orders subindex for the relevant end markets",
)


class EvidenceSchemaError(ValueError):
    """Raised when an evidence payload is missing required keys."""


def _stable_seed(*parts: str) -> int:
    """Return a deterministic, platform-independent seed for the given text.

    ``hash()`` is salted per process in Python 3, so it cannot be used where
    repeat runs must agree; this mirrors ``data_sources._stable_seed``.
    """

    text = "|".join(parts).upper()
    total = 0
    for position, character in enumerate(text):
        total += (position + 1) * ord(character)
    return total % 97


def _sector_prefix(sector_name: str) -> str:
    letters = [character for character in sector_name.upper() if character.isalpha()]
    if not letters:
        return "SECT"
    prefix = "".join(letters[:4])
    return prefix.ljust(4, "X")


def _quality_tier(roic_pct: float, pe_ratio: float) -> str:
    if roic_pct >= 16 and pe_ratio <= 20:
        return "Tier 1 - premium compounder"
    if roic_pct >= 10:
        return "Tier 2 - core holding"
    return "Tier 3 - value / turnaround"


def _synthesize_peer(seed: int, index: int, ticker: str, company: str) -> Dict[str, Any]:
    revenue_usd_m = round(600.0 + ((seed + index * 37) % 40) * 85.0, 1)
    eps_growth_pct = round(2.0 + ((seed + index * 13) % 20), 1)
    pe_ratio = round(11.0 + ((seed + index * 7) % 18) + index * 0.4, 1)
    ev_ebitda = round(pe_ratio * 0.58 + 1.6, 1)
    pb_ratio = round(pe_ratio * 0.19, 2)
    roic_pct = round(7.0 + ((seed + index * 5) % 15), 1)
    fcf_yield_pct = round(3.0 + ((seed + index * 9) % 7), 1)
    trend = ("up", "flat", "down")[(seed + index) % 3]
    return {
        "ticker": ticker,
        "company": company,
        "revenue_usd_m": revenue_usd_m,
        "eps_growth_pct": eps_growth_pct,
        "pe_ratio": pe_ratio,
        "ev_ebitda": ev_ebitda,
        "pb_ratio": pb_ratio,
        "roic_pct": roic_pct,
        "fcf_yield_pct": fcf_yield_pct,
        "eps_revision_trend": trend,
        "quality_tier": _quality_tier(roic_pct, pe_ratio),
    }


def _build_peers(sector_name: str, seed: int, peer_universe: Optional[List[str]]) -> List[Dict[str, Any]]:
    sector_word = (sector_name.split() or ["Sector"])[0]
    if peer_universe:
        peers = []
        for index, ticker in enumerate(peer_universe):
            ticker = str(ticker).strip().upper() or f"PEER{index + 1}"
            name = _NAME_POOL[(seed + index) % len(_NAME_POOL)]
            company = f"{name} {sector_word}"
            peers.append(_synthesize_peer(seed, index, ticker, company))
        return peers

    prefix = _sector_prefix(sector_name)
    peers = []
    for index in range(5):
        ticker = f"{prefix}{index + 1}"
        name = _NAME_POOL[(seed + index) % len(_NAME_POOL)]
        company = f"{name} {sector_word}"
        peers.append(_synthesize_peer(seed, index, ticker, company))
    return peers


def _pick(pool: Any, seed: int, count: int, offset: int = 0) -> List[str]:
    """Deterministically pick ``count`` distinct items from ``pool``."""

    picked: List[str] = []
    index = seed + offset
    while len(picked) < min(count, len(pool)):
        candidate = pool[index % len(pool)]
        if candidate not in picked:
            picked.append(candidate)
        index += 1
    return picked


def _synthesize_evidence(
    sector_name: str,
    geography: str,
    peer_universe: Optional[List[str]],
    look_forward_years: int,
) -> Dict[str, Any]:
    seed = _stable_seed(sector_name, geography)
    today = dt.date.today()

    tam_usd_bn = round(45.0 + seed * 3.3, 1)
    forward_cagr_pct = round(3.5 + (seed % 9) * 0.7, 1)
    growth_drivers = _pick(_GROWTH_DRIVER_POOL, seed, 3)
    capacity_cycle_note = (
        f"Capacity additions announced across the sector would raise industry-wide output by an "
        f"estimated {6 + seed % 10}% over the next {look_forward_years} years; absorbing that "
        "capacity depends on demand growth tracking the forward CAGR rather than the cycle trough."
    )

    value_chain = [
        {
            "name": "Upstream inputs and raw materials",
            "position": "upstream",
            "gross_margin_pct": round(18.0 + (seed % 7) * 1.1, 1),
            "operating_margin_pct": round(9.0 + (seed % 5) * 0.9, 1),
            "roic_pct": round(7.0 + (seed % 6) * 0.8, 1),
            "moat": "Scale economics and long-term supply contracts create switching costs for downstream buyers.",
            "key_risk": "Commodity input price volatility can outrun the ability to pass costs through on contract.",
        },
        {
            "name": "Core manufacturing and assembly",
            "position": "core",
            "gross_margin_pct": round(30.0 + (seed % 9) * 1.0, 1),
            "operating_margin_pct": round(15.0 + (seed % 7) * 0.9, 1),
            "roic_pct": round(13.0 + (seed % 8) * 0.9, 1),
            "moat": (
                f"Specification lock-in and qualification costs give incumbents in {sector_name} "
                "multi-year revenue visibility once designed into a customer's product."
            ),
            "key_risk": "New entrants with a disruptive technology can bypass qualification cycles entirely.",
        },
        {
            "name": "Downstream distribution and aftermarket",
            "position": "downstream",
            "gross_margin_pct": round(38.0 + (seed % 6) * 1.2, 1),
            "operating_margin_pct": round(19.0 + (seed % 6) * 1.0, 1),
            "roic_pct": round(20.0 + (seed % 9) * 1.0, 1),
            "moat": "Installed-base service relationships and parts availability are difficult for a new entrant to replicate quickly.",
            "key_risk": "Distributor destocking cycles can swing reported growth well away from underlying end demand.",
        },
    ]

    peers = _build_peers(sector_name, seed, peer_universe)

    structural_drivers = [
        {"kind": "tailwind", "statement": statement}
        for statement in _pick(_TAILWIND_POOL, seed, 2, offset=1)
    ] + [
        {"kind": "headwind", "statement": statement}
        for statement in _pick(_HEADWIND_POOL, seed, 1, offset=2)
    ]

    recession_sensitivity = ("high", "medium", "low")[seed % 3]
    operating_leverage = ("high", "medium", "low")[(seed + 1) % 3]
    leading_indicators = _pick(_LEADING_INDICATOR_POOL, seed, 3, offset=3)

    cyclicality = {
        "recession_sensitivity": recession_sensitivity,
        "operating_leverage": operating_leverage,
        "leading_indicators": leading_indicators,
        "note": (
            f"Demand in {sector_name} has historically shown {recession_sensitivity} sensitivity to a "
            f"broad industrial recession, amplified by {operating_leverage} fixed-cost operating "
            "leverage through the manufacturing base."
        ),
    }

    macro_factors = ("policy rates", "GDP growth", "commodity input costs", "FX translation")
    dominant_factor = macro_factors[seed % len(macro_factors)]
    macro_lens = {
        "dominant_factor": dominant_factor,
        "statement": (
            f"Sector earnings are most sensitive to {dominant_factor}: a 100bp adverse move in the "
            f"dominant driver has historically moved sector EBIT by an estimated "
            f"{2 + seed % 6}-{5 + seed % 6}% over a {look_forward_years}-year window, before any "
            "second-order demand effect."
        ),
    }

    geopolitical_risk = {
        "statement": (
            f"Supply chains serving {geography} customers in {sector_name} run through a small number "
            "of concentrated manufacturing regions; trade-policy shifts or export controls affecting "
            "those regions are a tail risk that is not diversifiable within the peer set."
        ),
    }

    sources = [
        {
            "title": f"{sector_name} Market Size and Forecast, {geography}",
            "url": f"https://industrydata.example.com/{sector_name.lower().replace(' ', '-')}/market-size",
            "date": (today - dt.timedelta(days=21)).isoformat(),
            "publisher": "Industry Data Service",
            "extract": f"TAM estimated at ${tam_usd_bn:,.1f}bn with a {forward_cagr_pct:.1f}% forward CAGR.",
        },
        {
            "title": f"{sector_name} Peer Multiples Snapshot",
            "url": f"https://marketdata.example.com/peers/{sector_name.lower().replace(' ', '-')}",
            "date": (today - dt.timedelta(days=2)).isoformat(),
            "publisher": "Market Data Service",
            "extract": (
                f"Peer forward P/E range of {min(p['pe_ratio'] for p in peers):.1f}x to "
                f"{max(p['pe_ratio'] for p in peers):.1f}x."
            ),
        },
        {
            "title": "Macro Indicator Snapshot",
            "url": "https://macro.example.com/global/snapshot",
            "date": today.isoformat(),
            "publisher": "Macro Data Service",
            "extract": macro_lens["statement"],
        },
        {
            "title": f"{sector_name} Capacity and Supply Chain Review",
            "url": f"https://industrydata.example.com/{sector_name.lower().replace(' ', '-')}/capacity",
            "date": (today - dt.timedelta(days=45)).isoformat(),
            "publisher": "Industry Data Service",
            "extract": capacity_cycle_note,
        },
        {
            "title": f"{sector_name} Trade and Regulatory Watch, {geography}",
            "url": f"https://policy.example.com/{sector_name.lower().replace(' ', '-')}/trade-watch",
            "date": (today - dt.timedelta(days=9)).isoformat(),
            "publisher": "Policy Monitor",
            "extract": geopolitical_risk["statement"],
        },
    ]

    return {
        "sector_overview": {
            "sector_name": sector_name,
            "geography": geography,
            "tam_usd_bn": tam_usd_bn,
            "forward_cagr_pct": forward_cagr_pct,
            "growth_drivers": growth_drivers,
            "capacity_cycle_note": capacity_cycle_note,
        },
        "value_chain": value_chain,
        "peers": peers,
        "structural_drivers": structural_drivers,
        "cyclicality": cyclicality,
        "macro_lens": macro_lens,
        "geopolitical_risk": geopolitical_risk,
        "sources": sources,
    }


def validate_evidence(evidence: Dict[str, Any]) -> None:
    """Check that an evidence payload carries every required key.

    Raises:
        EvidenceSchemaError: If a required key is missing.
    """

    missing = [key for key in REQUIRED_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise EvidenceSchemaError(f"evidence is missing required keys: {', '.join(missing)}")


def fetch_sector_evidence(
    sector_name: str,
    geography: str = "Global",
    peer_universe: Optional[List[str]] = None,
    look_forward_years: int = 3,
) -> Dict[str, Any]:
    """Fetch structured sector evidence.

    Phase 2b returns deterministic mock data; no network call is made.

    Args:
        sector_name: e.g. ``"Semiconductors"``.
        geography: e.g. ``"Global"``.
        peer_universe: Explicit tickers to synthesize peer financials for. When
            ``None``, at least five peers are auto-synthesized deterministically
            from ``sector_name`` and ``geography``.
        look_forward_years: Forward window referenced in the capacity-cycle and
            macro-sensitivity notes.

    Returns:
        A dict with ``sector_overview``, ``value_chain``, ``peers``,
        ``structural_drivers``, ``cyclicality``, ``macro_lens``,
        ``geopolitical_risk``, and ``sources``.

    Raises:
        ValueError: If ``sector_name`` is empty.
        EvidenceSchemaError: If the synthesized payload is incomplete.
    """

    sector_name = (sector_name or "").strip()
    geography = (geography or "Global").strip() or "Global"
    if not sector_name:
        raise ValueError("sector_name must not be empty")
    if look_forward_years < 1:
        look_forward_years = 1

    cleaned_universe = None
    if peer_universe:
        cleaned_universe = [str(ticker).strip() for ticker in peer_universe if str(ticker).strip()]
        cleaned_universe = cleaned_universe or None

    evidence = _synthesize_evidence(sector_name, geography, cleaned_universe, look_forward_years)
    validate_evidence(evidence)
    return evidence


def limit_sources(evidence: Dict[str, Any], max_sources: int) -> List[Dict[str, Any]]:
    """Return at most ``max_sources`` source records, preserving their order."""

    sources = evidence.get("sources") or []
    if max_sources < 1:
        return []
    return list(sources[:max_sources])
