"""Evidence sourcing for the analyst-agent earnings-update report type.

Phase 2a is deliberately offline, mirroring ``data_sources.py``'s own
docstring about mock-vs-real evidence: :func:`fetch_earnings_evidence` returns
deterministic mock evidence so the earnings-update agent can be exercised end
to end without network access or vendor credentials. Phase 2 replaces
:func:`_synthesize_earnings_evidence` with real providers (earnings-release
feeds, transcript vendors, consensus-revision services, sell-side note
aggregators) while keeping the returned schema unchanged. Every consumer in
this package depends only on the schema, not on the mock values.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

#: Keys every earnings-evidence payload must carry, whatever the backing provider.
REQUIRED_EARNINGS_EVIDENCE_KEYS = (
    "earnings_release",
    "call_transcript",
    "consensus_revisions",
    "street_commentary",
    "stock_reaction",
    "sources",
)

#: Guidance-direction values accepted by :func:`fetch_earnings_evidence`.
GUIDANCE_CHANGES = ("raised", "lowered", "in-line")


class EarningsEvidenceSchemaError(ValueError):
    """Raised when an earnings-evidence payload is missing required keys."""


def compute_surprise_pct(actual: Any, consensus: Any) -> Optional[float]:
    """Return the percent surprise of ``actual`` vs. ``consensus``.

    Args:
        actual: Reported figure.
        consensus: Prior consensus estimate for the same figure.

    Returns:
        ``(actual - consensus) / abs(consensus) * 100``, or ``None`` when
        either value is not numeric or ``consensus`` is zero (a percent
        surprise against a zero base is undefined).
    """

    try:
        actual_f = float(actual)
        consensus_f = float(consensus)
    except (TypeError, ValueError):
        return None
    if consensus_f == 0:
        return None
    return (actual_f - consensus_f) / abs(consensus_f) * 100.0


def _surprise_word(surprise_pct: Optional[float]) -> str:
    if surprise_pct is None:
        return "in-line"
    if surprise_pct > 0.05:
        return "beat"
    if surprise_pct < -0.05:
        return "miss"
    return "in-line"


def _stable_seed(ticker: str, earnings_date: str) -> int:
    """Deterministic, platform-independent seed for a ticker + earnings date.

    ``hash()`` is salted per process in Python 3, so it cannot be used where
    repeat runs must agree; mirrors ``data_sources._stable_seed``.
    """

    total = 0
    for position, character in enumerate(f"{ticker.upper()}|{earnings_date}"):
        total += (position + 1) * ord(character)
    return total % 97


def _guidance_commentary(company_name: str, guidance_change: Optional[str], year: int) -> str:
    if guidance_change == "raised":
        return (
            f"Management raised full-year FY{year} guidance, citing stronger backlog "
            "conversion and pricing carryover into the back half."
        )
    if guidance_change == "lowered":
        return (
            f"Management lowered full-year FY{year} guidance, citing softer order intake "
            "and channel inventory adjustments weighing on the near-term outlook."
        )
    if guidance_change == "in-line":
        return f"Management reiterated prior FY{year} guidance, with no change to the outlook range."
    return f"Management did not update forward FY{year} guidance on the call."


def _consensus_revisions(
    eps_actual: float,
    eps_consensus: float,
    revenue_actual: float,
    revenue_consensus: float,
    guidance_change: Optional[str],
) -> Dict[str, Any]:
    """Synthesize post-print consensus estimate revisions for the next period.

    ``*_before`` is the consensus supplied for the just-reported quarter;
    ``*_after`` is a deterministic estimate of where sell-side models move
    following the print, consistent with the guidance direction.
    """

    revision_factor = {"raised": 1.03, "lowered": 0.95, "in-line": 1.0}.get(guidance_change, 1.0)
    return {
        "eps_next_period_before": round(float(eps_consensus), 2),
        "eps_next_period_after": round(float(eps_actual) * revision_factor, 2),
        "revenue_next_period_before": round(float(revenue_consensus), 1),
        "revenue_next_period_after": round(float(revenue_actual) * revision_factor, 1),
        "revision_direction": (
            "up" if revision_factor > 1.0 else "down" if revision_factor < 1.0 else "unchanged"
        ),
    }


def _street_commentary(
    company_name: str,
    eps_direction: str,
    revenue_direction: str,
    guidance_change: Optional[str],
    seed: int,
) -> List[Dict[str, str]]:
    firms = ("Northbridge Securities", "Adler Capital Markets")
    stance = "constructive" if guidance_change == "raised" else (
        "cautious" if guidance_change == "lowered" else "neutral"
    )
    notes = []
    for index, firm in enumerate(firms):
        notes.append(
            {
                "firm": firm,
                "headline": (
                    f"{company_name}: {eps_direction} on EPS, {revenue_direction} on revenue, "
                    f"guidance {guidance_change or 'unchanged'}"
                ),
                "view": (
                    f"{firm} stays {stance} following the print, flagging "
                    f"{'margin durability' if index == seed % 2 else 'demand visibility'} "
                    "as the key swing factor into next quarter."
                ),
            }
        )
    return notes


def _stock_reaction(
    eps_surprise_pct: Optional[float],
    revenue_surprise_pct: Optional[float],
    guidance_change: Optional[str],
) -> Dict[str, Any]:
    guidance_adjustment = {"raised": 3.0, "lowered": -4.0, "in-line": 0.0}.get(guidance_change, 0.0)
    move = (
        0.6 * (eps_surprise_pct or 0.0) / 10.0
        + 0.4 * (revenue_surprise_pct or 0.0) / 10.0
        + guidance_adjustment
    )
    move = max(-20.0, min(20.0, round(move, 1)))
    direction = "higher" if move > 0 else "lower" if move < 0 else "flat"
    return {
        "pct_move": move,
        "session": "next-day close",
        "description": f"Shares traded {direction} by {abs(move):.1f}% following the release.",
    }


def _synthesize_earnings_evidence(
    ticker: str,
    company_name: str,
    earnings_date: str,
    eps_actual: float,
    eps_consensus: float,
    revenue_actual: float,
    revenue_consensus: float,
    guidance_change: Optional[str],
    earnings_call_transcript_url: Optional[str],
) -> Dict[str, Any]:
    """Build deterministic mock earnings evidence for one quarter.

    Internally consistent given the same inputs: the surprise percentages,
    guidance commentary, consensus revisions, street commentary, and stock
    reaction all derive from the same actual/consensus figures and guidance
    direction, so repeat calls with the same arguments return identical data.
    """

    seed = _stable_seed(ticker, earnings_date)
    year = dt.date.fromisoformat(earnings_date).year
    quarter = ((dt.date.fromisoformat(earnings_date).month - 1) // 3) + 1

    eps_surprise_pct = compute_surprise_pct(eps_actual, eps_consensus)
    revenue_surprise_pct = compute_surprise_pct(revenue_actual, revenue_consensus)
    eps_direction = _surprise_word(eps_surprise_pct)
    revenue_direction = _surprise_word(revenue_surprise_pct)

    headline = (
        f"{company_name} reports Q{quarter} FY{year} results: EPS {eps_direction}, "
        f"revenue {revenue_direction}."
    )
    management_commentary = (
        f"Management characterized the quarter as driven by "
        f"{'demand strength' if eps_direction == 'beat' else 'mixed execution' if eps_direction == 'in-line' else 'demand and cost pressure'}, "
        f"with EPS of {eps_actual:.2f} against a consensus of {eps_consensus:.2f} and revenue of "
        f"{revenue_actual:,.1f}m against a consensus of {revenue_consensus:,.1f}m."
    )
    guidance_commentary = _guidance_commentary(company_name, guidance_change, year)

    sources: List[Dict[str, Any]] = [
        {
            "title": f"{company_name} Q{quarter} FY{year} Earnings Release",
            "url": f"https://investor.example.com/{ticker.lower()}/q{quarter}-fy{year}-release",
            "date": earnings_date,
            "publisher": company_name,
            "extract": f"{headline} {guidance_commentary}",
        },
    ]

    call_transcript: Dict[str, Any] = {
        "available": bool(earnings_call_transcript_url),
        "url": earnings_call_transcript_url,
    }
    if earnings_call_transcript_url:
        tone = "confident" if guidance_change == "raised" else (
            "defensive" if guidance_change == "lowered" else "measured"
        )
        qa_highlights = [
            (
                f"Analysts pressed management on {'margin sustainability' if seed % 2 == 0 else 'demand visibility'} "
                "into next quarter; management pointed to backlog coverage as the offsetting factor."
            ),
            (
                f"Management confirmed capital allocation priorities are unchanged despite the "
                f"{'guidance raise' if guidance_change == 'raised' else 'guidance cut' if guidance_change == 'lowered' else 'reiterated outlook'}."
            ),
        ]
        call_transcript.update({"management_tone": tone, "qa_highlights": qa_highlights})
        sources.append(
            {
                "title": f"{company_name} Q{quarter} FY{year} Earnings Call Transcript",
                "url": earnings_call_transcript_url,
                "date": earnings_date,
                "publisher": "Investor Relations",
                "extract": f"Management tone: {tone}. " + " ".join(qa_highlights),
            }
        )
    else:
        call_transcript["note"] = "No transcript URL was supplied; call detail is unavailable."

    consensus_revisions = _consensus_revisions(
        eps_actual, eps_consensus, revenue_actual, revenue_consensus, guidance_change
    )
    sources.append(
        {
            "title": f"{ticker} Consensus Estimate Revisions",
            "url": f"https://marketdata.example.com/{ticker.lower()}/consensus-revisions",
            "date": earnings_date,
            "publisher": "Market Data Service",
            "extract": (
                f"Next-period EPS consensus moves {consensus_revisions['revision_direction']} from "
                f"{consensus_revisions['eps_next_period_before']:.2f} to "
                f"{consensus_revisions['eps_next_period_after']:.2f}."
            ),
        }
    )

    street_commentary = _street_commentary(
        company_name, eps_direction, revenue_direction, guidance_change, seed
    )
    for note in street_commentary:
        sources.append(
            {
                "title": f"{note['firm']} note on {company_name}",
                "url": f"https://sellside.example.com/{ticker.lower()}/{note['firm'].split()[0].lower()}",
                "date": earnings_date,
                "publisher": note["firm"],
                "extract": note["view"],
            }
        )

    stock_reaction = _stock_reaction(eps_surprise_pct, revenue_surprise_pct, guidance_change)
    sources.append(
        {
            "title": f"{ticker} Post-Earnings Stock Reaction",
            "url": f"https://marketdata.example.com/{ticker.lower()}/price-reaction",
            "date": earnings_date,
            "publisher": "Market Data Service",
            "extract": stock_reaction["description"],
        }
    )

    return {
        "earnings_release": {
            "headline": headline,
            "management_commentary": management_commentary,
            "guidance_commentary": guidance_commentary,
            "eps_actual": eps_actual,
            "eps_consensus": eps_consensus,
            "eps_surprise_pct": eps_surprise_pct,
            "revenue_actual": revenue_actual,
            "revenue_consensus": revenue_consensus,
            "revenue_surprise_pct": revenue_surprise_pct,
            "guidance_change": guidance_change,
        },
        "call_transcript": call_transcript,
        "consensus_revisions": consensus_revisions,
        "street_commentary": street_commentary,
        "stock_reaction": stock_reaction,
        "sources": sources,
    }


def validate_earnings_evidence(evidence: Dict[str, Any]) -> None:
    """Check that an earnings-evidence payload carries every required key.

    Raises:
        EarningsEvidenceSchemaError: If a required key is missing.
    """

    missing = [key for key in REQUIRED_EARNINGS_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise EarningsEvidenceSchemaError(f"evidence is missing required keys: {', '.join(missing)}")


def fetch_earnings_evidence(
    ticker: str,
    company_name: str,
    earnings_date: str,
    eps_actual: float,
    eps_consensus: float,
    revenue_actual: float,
    revenue_consensus: float,
    guidance_change: Optional[str],
    earnings_call_transcript_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch structured earnings evidence for one quarter.

    Phase 2a returns deterministic mock data; no network call is made.

    Args:
        ticker: Exchange ticker, e.g. ``ACME``.
        company_name: Display name, e.g. ``Acme Corp``.
        earnings_date: Release date as ``YYYY-MM-DD``.
        eps_actual: Reported EPS.
        eps_consensus: Prior consensus EPS estimate.
        revenue_actual: Reported revenue, in the company's reporting units.
        revenue_consensus: Prior consensus revenue estimate, same units.
        guidance_change: One of ``"raised"``, ``"lowered"``, ``"in-line"``, or
            ``None`` when guidance was not addressed.
        earnings_call_transcript_url: Transcript URL, if one is available.

    Returns:
        A dict with ``earnings_release``, ``call_transcript``,
        ``consensus_revisions``, ``street_commentary``, ``stock_reaction``,
        and ``sources``.

    Raises:
        ValueError: If ``ticker``/``company_name`` is empty, ``earnings_date``
            is not ``YYYY-MM-DD``, or ``guidance_change`` is not a recognized
            value.
        EarningsEvidenceSchemaError: If the synthesized payload is incomplete.
    """

    ticker = (ticker or "").strip().upper()
    company_name = (company_name or "").strip()
    if not ticker:
        raise ValueError("ticker must not be empty")
    if not company_name:
        raise ValueError("company_name must not be empty")

    earnings_date = (earnings_date or "").strip()
    try:
        parsed_date = dt.date.fromisoformat(earnings_date)
    except ValueError as exc:
        raise ValueError(f"earnings_date must be YYYY-MM-DD, got {earnings_date!r}") from exc
    if parsed_date.isoformat() != earnings_date:
        raise ValueError(f"earnings_date must be YYYY-MM-DD, got {earnings_date!r}")

    if guidance_change is not None and guidance_change not in GUIDANCE_CHANGES:
        raise ValueError(
            f"guidance_change must be one of {GUIDANCE_CHANGES} or None, got {guidance_change!r}"
        )

    for name, value in (
        ("eps_actual", eps_actual),
        ("eps_consensus", eps_consensus),
        ("revenue_actual", revenue_actual),
        ("revenue_consensus", revenue_consensus),
    ):
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric, got {value!r}") from exc

    evidence = _synthesize_earnings_evidence(
        ticker,
        company_name,
        earnings_date,
        float(eps_actual),
        float(eps_consensus),
        float(revenue_actual),
        float(revenue_consensus),
        guidance_change,
        earnings_call_transcript_url,
    )
    validate_earnings_evidence(evidence)
    return evidence


def limit_sources(evidence: Dict[str, Any], max_sources: int) -> List[Dict[str, Any]]:
    """Return at most ``max_sources`` source records, preserving their order.

    Args:
        evidence: A payload from :func:`fetch_earnings_evidence`.
        max_sources: Upper bound on returned sources; values below 1 return none.
    """

    sources = evidence.get("sources") or []
    if max_sources < 1:
        return []
    return list(sources[:max_sources])
