"""Analyst agent orchestration layer.

The skill directory name contains a hyphen, so it cannot be imported as a Python
package by name. Consumers add this directory to ``sys.path`` and import the flat
modules. Importing this file performs that ``sys.path`` bootstrap so either
style works.

Five report types are implemented, each following the same shape (evidence in,
Claude tool-use analysis, structured state, rendered Markdown out), listed here
grouped by their shared infrastructure:

- Shared: ``agent_common`` (Claude tool-loop runner, client bootstrap, strict
  tool-schema helpers), ``render_helpers`` (Markdown formatting).
- Initiation of Coverage (Phase 1): ``orchestrator.AnalystAgent``,
  ``data_sources``, ``prompts``, ``workspace_adapter``, ``report_generators``.
- Earnings Update (Phase 2a), revises the same company workspace:
  ``earnings_update.EarningsUpdateAgent`` (also reachable as
  ``AnalystAgent.earnings_update``), ``earnings_evidence``,
  ``earnings_prompts``, ``earnings_report``.
- Sector Report (Phase 2b), its own sector-primer workspace:
  ``sector_report.SectorReportAgent``, ``sector_workspace``,
  ``sector_workspace_adapter``, ``sector_evidence``, ``sector_prompts``,
  ``sector_report_render``.
- Quarterly Outlook (Phase 2c), standalone, no workspace:
  ``outlook_report.run_quarterly_outlook``, ``outlook_evidence``,
  ``outlook_prompts``, ``outlook_render``.
- Trading Report (Phase 3), standalone, no workspace:
  ``trading_report.run_trading_report``, ``trading_evidence``,
  ``trading_prompts``, ``trading_report_render``.

See SKILL.md for inputs/outputs and usage of each.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SKILL_DIRECTORY = str(Path(__file__).resolve().parent)
if _SKILL_DIRECTORY not in sys.path:
    sys.path.insert(0, _SKILL_DIRECTORY)

__all__ = [
    # Shared infrastructure
    "agent_common",
    "render_helpers",
    # Initiation of Coverage (Phase 1)
    "data_sources",
    "orchestrator",
    "prompts",
    "report_generators",
    "workspace_adapter",
    # Earnings Update (Phase 2a)
    "earnings_evidence",
    "earnings_prompts",
    "earnings_report",
    "earnings_update",
    # Sector Report (Phase 2b)
    "sector_evidence",
    "sector_prompts",
    "sector_report",
    "sector_report_render",
    "sector_workspace",
    "sector_workspace_adapter",
    # Quarterly Outlook (Phase 2c)
    "outlook_evidence",
    "outlook_prompts",
    "outlook_render",
    "outlook_report",
    # Trading Report (Phase 3)
    "trading_evidence",
    "trading_prompts",
    "trading_report",
    "trading_report_render",
]
