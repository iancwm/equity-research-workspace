"""Evidence sourcing for the analyst agent.

Phase 1 is deliberately offline: :func:`fetch_company_evidence` returns
deterministic mock evidence so the orchestrator, adapter, and report generator
can be exercised end to end without network access or vendor credentials.

Phase 2 replaces :func:`_synthesize_evidence` with real providers (filings,
market data, macro series) while keeping the returned schema unchanged. Every
consumer in this package depends only on the schema, not on the mock values.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

#: Keys every evidence payload must carry, whatever the backing provider.
REQUIRED_EVIDENCE_KEYS = (
    "company_overview",
    "latest_news",
    "financial_metrics",
    "peer_universe",
    "macro_context",
    "sources",
)


class EvidenceSchemaError(ValueError):
    """Raised when an evidence payload is missing required keys."""


def _stable_seed(ticker: str) -> int:
    """Return a deterministic, platform-independent seed for a ticker.

    ``hash()`` is salted per process in Python 3, so it cannot be used where
    repeat runs must agree.
    """

    total = 0
    for position, character in enumerate(ticker.upper()):
        total += (position + 1) * ord(character)
    return total % 97


def _synthesize_evidence(ticker: str, company_name: str) -> Dict[str, Any]:
    """Build realistic, deterministic mock evidence for one company.

    The figures are internally consistent (EPS reconciles to revenue, net
    margin, and share count) and deliberately contain one guidance-versus-history
    tension, so the analyst prompt has something genuine to reconcile or flag.
    """

    seed = _stable_seed(ticker)
    today = dt.date.today()
    year = today.year

    revenue = 2_400.0 + seed * 45.0
    net_margin = 0.098 + (seed % 11) * 0.004
    shares = 118.0 + (seed % 17) * 2.5
    eps = round(revenue * net_margin / shares, 2)
    price = round(eps * (15.0 + (seed % 9)), 2)
    historical_cagr = round(0.055 + (seed % 7) * 0.006, 3)
    guided_growth = round(historical_cagr + 0.035, 3)

    return {
        "company_overview": {
            "name": company_name,
            "ticker": ticker,
            "sector": "Industrials",
            "industry": "Electrical Components and Equipment",
            "geography": "North America, Europe",
            "market_cap": round(price * shares, 1),
            "currency": "USD",
            "employees": 8_400 + seed * 55,
            "business_model": (
                f"{company_name} designs and manufactures electrical components sold through "
                "distributors and directly to OEMs. Revenue splits between a cyclical original-equipment "
                "channel and a higher-margin aftermarket and service channel."
            ),
            "segments": [
                {"name": "Original Equipment", "revenue_share": 0.62, "ebit_margin": 0.101},
                {"name": "Aftermarket and Service", "revenue_share": 0.38, "ebit_margin": 0.214},
            ],
            "competitive_position": (
                "Third-largest supplier in its niche by installed base. Competes on lead time and "
                "specification lock-in rather than headline price."
            ),
        },
        "latest_news": [
            {
                "title": f"{company_name} reports Q4 results, guides {guided_growth:.1%} revenue growth",
                "url": f"https://investor.example.com/{ticker.lower()}/q4-results",
                "date": (today - dt.timedelta(days=34)).isoformat(),
                "summary": (
                    f"Management guided to {guided_growth:.1%} revenue growth for FY{year}, above the "
                    f"{historical_cagr:.1%} five-year historical CAGR, citing backlog conversion and "
                    "aftermarket attach rates."
                ),
            },
            {
                "title": f"{company_name} announces capacity expansion",
                "url": f"https://investor.example.com/{ticker.lower()}/capacity-expansion",
                "date": (today - dt.timedelta(days=71)).isoformat(),
                "summary": (
                    "A new plant adds roughly 12% to unit capacity from FY"
                    f"{year + 1}, with capex weighted to the first half."
                ),
            },
            {
                "title": "Distributor destocking pressures near-term orders",
                "url": f"https://news.example.com/{ticker.lower()}/destocking",
                "date": (today - dt.timedelta(days=12)).isoformat(),
                "summary": (
                    "Channel checks point to distributor inventory reduction into the next two quarters, "
                    "a headwind to reported growth that is not reflected in current guidance."
                ),
            },
        ],
        "financial_metrics": {
            "period": f"FY{year - 1}",
            "currency": "USD",
            "revenue": round(revenue, 1),
            "revenue_growth": historical_cagr,
            "revenue_cagr_5y": historical_cagr,
            "gross_margin": round(0.312 + (seed % 5) * 0.008, 3),
            "ebit_margin": round(0.132 + (seed % 6) * 0.005, 3),
            "net_margin": round(net_margin, 3),
            "eps": eps,
            "fcf": round(revenue * (0.072 + (seed % 5) * 0.003), 1),
            "roic": round(0.118 + (seed % 8) * 0.004, 3),
            "net_debt_to_ebitda": round(1.4 + (seed % 6) * 0.15, 2),
            "shares_outstanding": round(shares, 1),
            "price": price,
            "pe_ratio": round(price / eps, 1),
            "ev_ebitda": round(9.2 + (seed % 7) * 0.4, 1),
            "dividend_yield": round(0.014 + (seed % 4) * 0.003, 3),
        },
        "peer_universe": [
            {
                "ticker": "PEER-A",
                "company": "Northfield Electric",
                "pe_ratio": round(17.4 + (seed % 5) * 0.3, 1),
                "ev_ebitda": round(10.1 + (seed % 4) * 0.3, 1),
                "eps_growth": 0.081,
                "ebitda_margin": 0.186,
                "roic": 0.134,
            },
            {
                "ticker": "PEER-B",
                "company": "Cobalt Industrial",
                "pe_ratio": round(15.1 + (seed % 6) * 0.3, 1),
                "ev_ebitda": round(8.6 + (seed % 5) * 0.3, 1),
                "eps_growth": 0.052,
                "ebitda_margin": 0.151,
                "roic": 0.101,
            },
            {
                "ticker": "PEER-C",
                "company": "Meridian Components",
                "pe_ratio": round(19.8 + (seed % 4) * 0.4, 1),
                "ev_ebitda": round(11.3 + (seed % 6) * 0.3, 1),
                "eps_growth": 0.114,
                "ebitda_margin": 0.221,
                "roic": 0.168,
            },
        ],
        "macro_context": {
            "as_of": today.isoformat(),
            "region": "United States",
            "gdp_growth": 0.019,
            "unemployment": 0.042,
            "cpi_inflation": 0.027,
            "policy_rate": 0.0375,
            "ten_year_yield": 0.0418,
            "industrial_production_growth": 0.008,
            "sector_note": (
                "Electrification and grid-replacement spending are structural tailwinds; short-cycle "
                "industrial demand remains soft and rate-sensitive."
            ),
        },
        "sources": [
            {
                "title": f"{company_name} Annual Report FY{year - 1}",
                "url": f"https://investor.example.com/{ticker.lower()}/annual-report",
                "date": (today - dt.timedelta(days=96)).isoformat(),
                "publisher": company_name,
                "extract": (
                    f"FY{year - 1} revenue of ${revenue:,.1f}m, EPS of ${eps:.2f}, "
                    f"five-year revenue CAGR of {historical_cagr:.1%}."
                ),
            },
            {
                "title": f"{company_name} Q4 Earnings Call Transcript",
                "url": f"https://investor.example.com/{ticker.lower()}/q4-transcript",
                "date": (today - dt.timedelta(days=34)).isoformat(),
                "publisher": "Investor Relations",
                "extract": f"Management guided FY{year} revenue growth of {guided_growth:.1%}.",
            },
            {
                "title": "Electrical Components Peer Multiples",
                "url": "https://marketdata.example.com/peers/electrical-components",
                "date": (today - dt.timedelta(days=3)).isoformat(),
                "publisher": "Market Data Service",
                "extract": "Peer forward P/E range of 15.1x to 19.8x; median EV/EBITDA of 10.1x.",
            },
            {
                "title": "Macro Indicator Snapshot",
                "url": "https://macro.example.com/us/snapshot",
                "date": today.isoformat(),
                "publisher": "Macro Data Service",
                "extract": "US GDP growth 1.9%, CPI 2.7%, policy rate 3.75%, 10-year yield 4.18%.",
            },
            {
                "title": "Distributor Channel Inventory Survey",
                "url": f"https://news.example.com/{ticker.lower()}/destocking",
                "date": (today - dt.timedelta(days=12)).isoformat(),
                "publisher": "Industry News",
                "extract": "Distributors expect two more quarters of inventory reduction.",
            },
        ],
    }


def validate_evidence(evidence: Dict[str, Any]) -> None:
    """Check that an evidence payload carries every required key.

    Basic schema checking only; deep validation is the workspace validator's job.

    Raises:
        EvidenceSchemaError: If a required key is missing.
    """

    missing = [key for key in REQUIRED_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise EvidenceSchemaError(f"evidence is missing required keys: {', '.join(missing)}")


def fetch_company_evidence(ticker: str, company_name: str) -> Dict[str, Any]:
    """Fetch structured evidence for one company.

    Phase 1 returns deterministic mock data; no network call is made.

    Args:
        ticker: Exchange ticker, e.g. ``ACME``.
        company_name: Display name, e.g. ``Acme Corp``.

    Returns:
        A dict with ``company_overview``, ``latest_news``, ``financial_metrics``,
        ``peer_universe``, ``macro_context``, and ``sources``.

    Raises:
        ValueError: If ``ticker`` or ``company_name`` is empty.
        EvidenceSchemaError: If the synthesized payload is incomplete.
    """

    ticker = (ticker or "").strip().upper()
    company_name = (company_name or "").strip()
    if not ticker:
        raise ValueError("ticker must not be empty")
    if not company_name:
        raise ValueError("company_name must not be empty")

    evidence = _synthesize_evidence(ticker, company_name)
    validate_evidence(evidence)
    return evidence


def limit_sources(evidence: Dict[str, Any], max_sources: int) -> List[Dict[str, Any]]:
    """Return at most ``max_sources`` source records, preserving their order.

    Args:
        evidence: A payload from :func:`fetch_company_evidence`.
        max_sources: Upper bound on returned sources; values below 1 return none.
    """

    sources = evidence.get("sources") or []
    if max_sources < 1:
        return []
    return list(sources[:max_sources])
