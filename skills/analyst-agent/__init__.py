"""Analyst agent orchestration layer.

The skill directory name contains a hyphen, so it cannot be imported as a Python
package by name. Consumers add this directory to ``sys.path`` and import the flat
modules (``orchestrator``, ``data_sources``, ``report_generators``,
``workspace_adapter``, ``prompts``). Importing this file performs that
``sys.path`` bootstrap so either style works.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SKILL_DIRECTORY = str(Path(__file__).resolve().parent)
if _SKILL_DIRECTORY not in sys.path:
    sys.path.insert(0, _SKILL_DIRECTORY)

__all__ = [
    "data_sources",
    "orchestrator",
    "prompts",
    "report_generators",
    "workspace_adapter",
]
