"""Shared Markdown rendering primitives for every analyst-agent report type.

Kept dependency-free and workspace-agnostic: these functions format values and
tables; they never decide what belongs in a report. Report-type-specific
generators (``report_generators.py`` and its siblings) own that decision and
call into here only for formatting.
"""

from __future__ import annotations

from typing import Any, Sequence


def format_number(value: Any, digits: int = 2) -> str:
    """Render a number for display, passing non-numeric values through as text."""

    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and abs(number) < 1e15:
        return f"{int(number):,}"
    return f"{number:,.{digits}f}"


def format_price(value: Any) -> str:
    """Render a per-share value at fixed precision, so a column reads evenly."""

    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def format_pct(value: Any, digits: int = 1) -> str:
    """Render a ratio (0.08) or already-percent number as a percentage string."""

    if value is None or value == "":
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    # Heuristic consistent with the rest of the package: values already
    # expressed as whole percentages (e.g. 8 for "8%") are far more common in
    # hand-authored evidence than true ratios above 1.5, so only values in
    # [-1.5, 1.5] are treated as ratios to be scaled up.
    if -1.5 <= number <= 1.5:
        number *= 100
    return f"{number:,.{digits}f}%"


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a GitHub-flavoured Markdown table."""

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def source_label(known_source_ids: Sequence[str], source_ids: Sequence[str]) -> str:
    """Render a comma-joined citation list, dropping any id not in the registry."""

    known = set(known_source_ids)
    resolved = [identifier for identifier in source_ids if identifier in known]
    return ", ".join(resolved) if resolved else "unsourced"
