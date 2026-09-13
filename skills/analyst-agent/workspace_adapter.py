"""Bridge between Claude tool calls and a v2 persistent-equity-research workspace.

This module owns every write into the research workspace. It deliberately does
not modify the ``persistent-equity-research`` skill: it loads that skill's
validator (``workspace_lib``) at runtime and writes the same on-disk formats.

The workspace is the source of truth. Publications are rendered from it by
``report_generators``; nothing in this module renders prose.
"""

from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import io
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SKILLS_ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_SKILL_SCRIPTS = SKILLS_ROOT / "persistent-equity-research" / "scripts"

#: Dependency-graph node that owns assumptions produced by the analyst agent.
ASSUMPTION_OWNER_NODE = "company_overlay"

#: Dependency-graph node marked fresh once evidence has been ingested.
SOURCE_INGESTION_NODE = "source_ingestion"

#: Marks ``data/valuation.csv`` rows that carry a scenario price target rather
#: than the output of a valuation method.
SCENARIO_METHOD_PREFIX = "Scenario: "

_LEDGER_CONFIDENCE = ("low", "medium", "high")


class WorkspaceAdapterError(RuntimeError):
    """Raised when workspace state cannot be loaded or written."""


def _load_workspace_lib():
    """Import ``workspace_lib`` from the installed persistent-equity-research skill.

    Loaded by path rather than by ``sys.path`` mutation so that importing this
    module never shadows a same-named module elsewhere in the host process.
    """

    module_path = PERSISTENT_SKILL_SCRIPTS / "workspace_lib.py"
    if not module_path.is_file():
        raise WorkspaceAdapterError(
            f"persistent-equity-research workspace_lib.py not found at {module_path}"
        )
    spec = importlib.util.spec_from_file_location(
        "analyst_agent_vendored_workspace_lib", module_path
    )
    if spec is None or spec.loader is None:
        raise WorkspaceAdapterError(f"cannot load workspace_lib from {module_path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because dataclasses in the loaded module
    # resolve their own module from sys.modules at class-creation time.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


workspace_lib = _load_workspace_lib()


@dataclass
class ToolResult:
    """One ``tool_use`` block emitted by Claude.

    Attributes:
        name: Tool name, e.g. ``record_assumption``.
        input: Decoded tool input object.
        tool_use_id: The block id, used to correlate ``tool_result`` replies.
    """

    name: str
    input: Dict[str, Any]
    tool_use_id: str = ""


@dataclass
class AdapterReport:
    """What a batch of tool calls actually changed in the workspace."""

    applied: Dict[str, int] = field(default_factory=dict)
    source_ids: List[str] = field(default_factory=list)
    assumption_ids: List[str] = field(default_factory=list)
    ledger_ids: List[str] = field(default_factory=list)
    dropped_source_links: List[str] = field(default_factory=list)
    unknown_tools: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when every tool call mapped into state without normalization."""

        return not self.dropped_source_links and not self.unknown_tools


def _today() -> str:
    return dt.date.today().isoformat()


def _iso_date_or_none(value: Any) -> Optional[str]:
    """Return ``value`` when it is a strict ISO ``YYYY-MM-DD`` date, else None."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.date.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == value.strip() else None


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _atomic_write(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically, keeping partial writes invisible."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceAdapterError(f"cannot read {path}: {exc}") from exc


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise WorkspaceAdapterError(f"cannot read {path}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkspaceAdapterError(f"{path} line {number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise WorkspaceAdapterError(f"{path} line {number}: record must be an object")
        records.append(value)
    return records


class ResearchWorkspace:
    """In-memory view of a v2 equity-research workspace, with atomic persistence.

    ``persistent-equity-research`` ships validators and an initializer but no
    workspace object, so this class supplies the read/modify/write surface the
    orchestrator needs without modifying that skill. Mutations stay in memory
    until :meth:`save` is called.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.project: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {}
        self.sources: List[Dict[str, Any]] = []
        self.ledger: List[Dict[str, Any]] = []
        self.assumptions: Dict[str, Any] = {"assumptions": [], "scenario_overrides": {}}
        self.contradictions: Dict[str, Any] = {"contradictions": []}
        self.valuation_rows: List[Dict[str, str]] = []
        self.dependency_graph: Dict[str, Any] = {"nodes": {}}

    # ------------------------------------------------------------------
    # Loading and saving
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, workspace_root: Any) -> "ResearchWorkspace":
        """Load an initialized workspace from disk.

        Args:
            workspace_root: Path to a workspace created by ``init_workspace.py``.

        Returns:
            A populated :class:`ResearchWorkspace`.

        Raises:
            WorkspaceAdapterError: If the directory is missing or not a v2 workspace.
        """

        root = Path(workspace_root).expanduser().resolve()
        if not root.is_dir():
            raise WorkspaceAdapterError(f"workspace directory does not exist: {root}")
        workspace = cls(root)
        for relative in ("project.json", "state/research-context.json"):
            if not (root / relative).is_file():
                raise WorkspaceAdapterError(f"not a v2 workspace, missing {relative}: {root}")

        workspace.project = _read_json(root / "project.json")
        workspace.context = _read_json(root / "state" / "research-context.json")
        workspace.dependency_graph = _read_json(root / "state" / "dependency-graph.json")
        workspace.assumptions = _read_json(root / "state" / "assumptions.json")
        workspace.contradictions = _read_json(root / "state" / "contradictions.json")
        workspace.sources = _read_jsonl(root / "sources" / "registry.jsonl")
        workspace.ledger = _read_jsonl(root / "state" / "ledger.jsonl")
        workspace.valuation_rows = workspace._read_valuation_rows()
        return workspace

    def _read_valuation_rows(self) -> List[Dict[str, str]]:
        path = self.root / "data" / "valuation.csv"
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def save(self) -> None:
        """Persist all mutated state atomically, file by file."""

        _atomic_write(
            self.root / "sources" / "registry.jsonl",
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in self.sources),
        )
        _atomic_write(
            self.root / "state" / "ledger.jsonl",
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in self.ledger),
        )
        _atomic_write(
            self.root / "state" / "assumptions.json",
            json.dumps(self.assumptions, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_write(
            self.root / "state" / "contradictions.json",
            json.dumps(self.contradictions, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_write(
            self.root / "state" / "dependency-graph.json",
            json.dumps(self.dependency_graph, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_write(
            self.root / "project.json",
            json.dumps(self.project, indent=2, ensure_ascii=False) + "\n",
        )
        self._write_valuation_csv()

    def _write_valuation_csv(self) -> None:
        headers = workspace_lib.CSV_HEADERS["data/valuation.csv"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(headers), lineterminator="\n")
        writer.writeheader()
        for row in self.valuation_rows:
            writer.writerow({header: row.get(header, "") for header in headers})
        _atomic_write(self.root / "data" / "valuation.csv", buffer.getvalue())

    def validate(self, strict: bool = False):
        """Validate on-disk state with the persistent-equity-research validator."""

        return workspace_lib.validate_workspace(self.root, strict=strict)

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def ticker(self) -> str:
        return str(self.project.get("ticker", ""))

    @property
    def company_name(self) -> str:
        return str(self.project.get("company_name", ""))

    @property
    def base_currency(self) -> str:
        return str(self.project.get("base_currency", "USD"))

    @property
    def rating_convention(self) -> str:
        return str(self.project.get("rating_convention", ""))

    def _next_id(self, prefix: str, existing: Sequence[str]) -> str:
        highest = 0
        for identifier in existing:
            if isinstance(identifier, str) and identifier.startswith(f"{prefix}-"):
                suffix = identifier[len(prefix) + 1:]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"{prefix}-{highest + 1:04d}"

    @property
    def known_source_ids(self) -> List[str]:
        return [str(record.get("source_id")) for record in self.sources]

    @property
    def known_node_ids(self) -> List[str]:
        nodes = self.dependency_graph.get("nodes")
        return list(nodes) if isinstance(nodes, dict) else []

    def state_ledger_keys(self) -> List[str]:
        """Return the state collections that currently hold records."""

        keys: List[str] = []
        if self.sources:
            keys.append("sources")
        if self.ledger:
            keys.append("ledger")
        if self.assumptions.get("assumptions"):
            keys.append("assumptions")
        if self.assumptions.get("scenario_overrides"):
            keys.append("scenario_overrides")
        if self.contradictions.get("contradictions"):
            keys.append("contradictions")
        if self.valuation_rows:
            keys.append("valuation")
        return keys

    def ledger_by_type(self, record_type: str) -> List[Dict[str, Any]]:
        """Return active ledger records of one ``record_type``, in insertion order."""

        return [
            record
            for record in self.ledger
            if record.get("record_type") == record_type
            and record.get("status") in ("active", "unresolved")
        ]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_source(
        self,
        title: str,
        url: str,
        date: Optional[str] = None,
        extract: Optional[str] = None,
        publisher: Optional[str] = None,
        source_type: str = "web",
        quality_tier: int = 3,
        primary_source: bool = False,
    ) -> str:
        """Append a source record and return its ``source_id``.

        Registration is idempotent on title and URL: re-recording a source that
        the orchestrator already ingested returns the existing id instead of
        creating a duplicate registry entry.
        """

        title_key = _clean_text(title).casefold()
        url_key = _clean_text(url).casefold()
        for existing in self.sources:
            if (
                _clean_text(existing.get("title")).casefold() == title_key
                and _clean_text(existing.get("url_or_ref")).casefold() == url_key
            ):
                return str(existing.get("source_id"))

        source_id = self._next_id("SRC", self.known_source_ids)
        self.sources.append(
            {
                "source_id": source_id,
                "title": _clean_text(title, "Untitled source"),
                "source_type": _clean_text(source_type, "web"),
                "publisher": _clean_text(publisher) or _clean_text(url, "unknown"),
                "url_or_ref": _clean_text(url, "unspecified"),
                "publication_date": _iso_date_or_none(date),
                "observation_period": None,
                "accessed_at": _today(),
                "primary_source": bool(primary_source),
                "quality_tier": max(1, min(4, int(quality_tier))),
                "notes": _clean_text(extract) or None,
            }
        )
        return source_id

    def add_ledger_record(
        self,
        record_type: str,
        statement: str,
        confidence: str = "medium",
        status: str = "active",
        source_ids: Optional[Sequence[str]] = None,
        nodes: Optional[Sequence[str]] = None,
        metric: Optional[str] = None,
        value: Any = None,
        unit: Optional[str] = None,
        period: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Append a ledger record and return its generated id."""

        record_id = self._next_id("LED", [str(item.get("id")) for item in self.ledger])
        self.ledger.append(
            {
                "id": record_id,
                "record_type": record_type,
                "statement": _clean_text(statement, "Unspecified statement."),
                "metric": metric,
                "value": value,
                "unit": unit,
                "period": period,
                "as_of_date": _today(),
                "source_ids": list(source_ids or []),
                "confidence": confidence if confidence in _LEDGER_CONFIDENCE else "medium",
                "nodes": list(nodes or []),
                "depends_on": [],
                "supersedes": None,
                "status": status,
                "notes": notes,
            }
        )
        return record_id

    def add_assumption(
        self,
        name: str,
        base: Any,
        units: str = "",
        rationale: Optional[str] = None,
        source_ids: Optional[Sequence[str]] = None,
        bull: Any = None,
        bear: Any = None,
        owner_node: str = ASSUMPTION_OWNER_NODE,
    ) -> str:
        """Append an assumption and return its generated id."""

        records = self.assumptions.setdefault("assumptions", [])
        assumption_id = self._next_id("ASM", [str(item.get("id")) for item in records])
        record: Dict[str, Any] = {
            "id": assumption_id,
            "name": _clean_text(name, "Unnamed assumption"),
            "base": base,
            "units": _clean_text(units),
            "owner_node": owner_node,
            "rationale": _clean_text(rationale) or None,
            "source_ids": list(source_ids or []),
            "last_updated": _today(),
            "status": "active",
        }
        if bull is not None:
            record["bull"] = bull
        if bear is not None:
            record["bear"] = bear
        records.append(record)
        return assumption_id

    def find_active_assumption(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the most recent active assumption record with this name, if any.

        Used by report types that revise a prior workspace (e.g. an earnings
        update) to detect whether a named driver actually changed before
        deciding whether to supersede it.
        """

        target = _clean_text(name).casefold()
        for record in reversed(self.assumptions.get("assumptions", [])):
            if (
                record.get("status") == "active"
                and _clean_text(record.get("name")).casefold() == target
            ):
                return record
        return None

    def mark_assumption_stale(self, assumption_id: str) -> bool:
        """Mark one assumption record ``stale`` by id. Returns whether it was found."""

        for record in self.assumptions.get("assumptions", []):
            if record.get("id") == assumption_id:
                record["status"] = "stale"
                return True
        return False

    def add_contradiction(
        self,
        summary: str,
        source_ids: Optional[Sequence[str]] = None,
        ledger_ids: Optional[Sequence[str]] = None,
    ) -> str:
        """Append an open contradiction and return its generated id."""

        records = self.contradictions.setdefault("contradictions", [])
        contradiction_id = self._next_id("CON", [str(item.get("id")) for item in records])
        records.append(
            {
                "id": contradiction_id,
                "summary": _clean_text(summary, "Unspecified contradiction."),
                "ledger_ids": list(ledger_ids or []),
                "source_ids": list(source_ids or []),
                "status": "open",
                "resolution": None,
                "last_updated": _today(),
            }
        )
        return contradiction_id

    def add_valuation_row(
        self,
        scenario: str,
        method: str,
        implied_price: Any = "",
        implied_equity_value: Any = "",
        shares: Any = "",
        assumption_set: str = "base",
        notes: str = "",
    ) -> None:
        """Append one row to ``data/valuation.csv``."""

        self.valuation_rows.append(
            {
                "scenario": _clean_text(scenario),
                "method": _clean_text(method),
                "assumption_set": _clean_text(assumption_set, "base"),
                "implied_equity_value": "" if implied_equity_value in (None, "") else str(implied_equity_value),
                "shares": "" if shares in (None, "") else str(shares),
                "implied_price": "" if implied_price in (None, "") else str(implied_price),
                "notes": _clean_text(notes),
            }
        )

    def set_scenario_override(self, name: str, payload: Dict[str, Any]) -> None:
        """Record a named scenario under ``assumptions.scenario_overrides``."""

        overrides = self.assumptions.setdefault("scenario_overrides", {})
        overrides[_clean_text(name, "unnamed")] = payload

    def mark_node_fresh(self, node: str) -> None:
        """Mark a dependency-graph node fresh when its outputs exist on disk."""

        nodes = self.dependency_graph.get("nodes")
        if not isinstance(nodes, dict) or node not in nodes:
            return
        outputs = nodes[node].get("outputs", [])
        if all((self.root / output).is_file() for output in outputs):
            nodes[node]["status"] = "fresh"

    def touch_research_update(self) -> None:
        """Stamp today's date on the project's ``last_research_update``."""

        self.project["last_research_update"] = _today()
        if self.project.get("status") == "new":
            self.project["status"] = "active"


# ----------------------------------------------------------------------
# Claude tool results -> workspace state
# ----------------------------------------------------------------------


def _resolve_source_ids(
    workspace: ResearchWorkspace,
    requested: Any,
    report: AdapterReport,
    context: str,
) -> List[str]:
    """Keep only source ids that exist in the registry, recording any dropped."""

    if not isinstance(requested, (list, tuple)):
        return []
    known = set(workspace.known_source_ids)
    resolved: List[str] = []
    for identifier in requested:
        text = _clean_text(identifier)
        if text in known:
            resolved.append(text)
        elif text:
            report.dropped_source_links.append(f"{context}: {text}")
    return resolved


def _as_mapping(payload: Any) -> Dict[str, Any]:
    """Normalize a name/value collection into a plain mapping.

    Tool schemas express free-form maps as arrays of ``{"name", "value"}`` pairs
    so they can run under strict schema validation; plain objects are accepted
    too, for callers that build tool results by hand.
    """

    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, (list, tuple)):
        mapping: Dict[str, Any] = {}
        for item in payload:
            if isinstance(item, dict) and "name" in item:
                mapping[_clean_text(item.get("name"))] = item.get("value")
        return mapping
    return {}


def _format_range(payload: Any) -> str:
    """Render a valuation output range as compact ``key=value`` text."""

    if isinstance(payload, dict):
        return ", ".join(f"{key}={value}" for key, value in payload.items())
    return _clean_text(payload)


def _apply_record_source(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    source_id = workspace.add_source(
        title=payload.get("title", ""),
        url=payload.get("url", ""),
        date=payload.get("date"),
        extract=payload.get("extract"),
        publisher=payload.get("publisher"),
    )
    report.source_ids.append(source_id)


def _apply_record_assumption(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    name = _clean_text(payload.get("name"), "Unnamed assumption")
    source_ids = _resolve_source_ids(workspace, payload.get("source_ids"), report, f"assumption {name}")
    assumption_id = workspace.add_assumption(
        name=name,
        base=payload.get("value"),
        units=_clean_text(payload.get("units")),
        rationale=payload.get("rationale"),
        source_ids=source_ids,
    )
    report.assumption_ids.append(assumption_id)
    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="assumption",
            statement=f"{name}: {_clean_text(payload.get('value'))}",
            confidence="medium",
            source_ids=source_ids,
            nodes=[ASSUMPTION_OWNER_NODE],
            metric=name,
            value=payload.get("value"),
            notes=_clean_text(payload.get("rationale")) or None,
        )
    )


def _apply_record_valuation(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    method = _clean_text(payload.get("method"), "unspecified")
    inputs = _as_mapping(payload.get("inputs"))
    output = payload.get("output")
    notes = "; ".join(f"{key}={value}" for key, value in inputs.items())

    if isinstance(output, dict):
        for band in ("low", "base", "high"):
            if band in output:
                workspace.add_valuation_row(
                    scenario=band,
                    method=method,
                    implied_price=output[band],
                    assumption_set=band,
                    notes=notes,
                )
    else:
        workspace.add_valuation_row(scenario="base", method=method, implied_price=output, notes=notes)

    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="derived_metric",
            statement=f"{method} valuation implies {_format_range(output)}.",
            confidence="medium",
            nodes=["valuation"],
            metric=method,
            value=output if not isinstance(output, dict) else None,
            unit=workspace.base_currency,
            notes=notes or None,
        )
    )


def _apply_record_scenario(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    name = _clean_text(payload.get("name"), "Base")
    assumptions = _as_mapping(payload.get("assumptions"))
    valuation = payload.get("valuation")
    price_target = payload.get("price_target")
    weight = payload.get("weight")

    workspace.set_scenario_override(
        name,
        {
            "assumptions": assumptions,
            "valuation": valuation,
            "price_target": price_target,
            "weight": weight,
        },
    )
    # Prefixed so publication views can tell a scenario target apart from a
    # valuation method; both legitimately live in data/valuation.csv.
    workspace.add_valuation_row(
        scenario=name,
        method=f"{SCENARIO_METHOD_PREFIX}{_clean_text(_format_range(valuation), 'unspecified')}",
        implied_price=price_target,
        assumption_set=name.lower(),
        notes=f"weight={weight}" if weight is not None else "",
    )
    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="analytical_conclusion",
            statement=(
                f"{name} case: 12-month price target {price_target} "
                f"{workspace.base_currency} at {weight} probability weight."
            ),
            confidence="medium",
            nodes=["valuation", "strategist_dashboard"],
            metric=f"price_target_{name.lower()}",
            value=price_target,
            unit=workspace.base_currency,
            notes="; ".join(f"{key}={value}" for key, value in assumptions.items()) or None,
        )
    )


def _apply_record_catalyst(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    name = _clean_text(payload.get("name"), "Unnamed catalyst")
    timeframe = _clean_text(payload.get("timeframe"), "unspecified")
    direction = _clean_text(payload.get("direction"), "unspecified")
    magnitude = payload.get("magnitude_estimate_pct", payload.get("magnitude"))
    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="catalyst",
            statement=f"{name} ({direction}, {timeframe}).",
            confidence="medium",
            nodes=["strategist_dashboard"],
            metric=name,
            value=magnitude,
            unit="percent",
            period=timeframe,
            notes=f"direction={direction}",
        )
    )


def _apply_flag_analysis_gap(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    category = _clean_text(payload.get("category"), "general")
    description = _clean_text(payload.get("description"), "Unspecified gap.")
    report.ledger_ids.append(
        workspace.add_ledger_record(
            record_type="research_gap",
            statement=f"[{category}] {description}",
            confidence="medium",
            status="unresolved",
            nodes=[SOURCE_INGESTION_NODE],
            metric=category,
        )
    )


def _apply_flag_contradiction(workspace: ResearchWorkspace, payload: Dict[str, Any], report: AdapterReport) -> None:
    field1 = _clean_text(payload.get("field1"), "signal A")
    field2 = _clean_text(payload.get("field2"), "signal B")
    description = _clean_text(payload.get("description"), "Conflicting evidence.")
    workspace.add_contradiction(summary=f"{field1} vs {field2}: {description}")


#: Tool name -> handler. Ordering of application is fixed by ``_APPLY_ORDER``.
_HANDLERS = {
    "record_source": _apply_record_source,
    "record_assumption": _apply_record_assumption,
    "record_valuation": _apply_record_valuation,
    "record_scenario": _apply_record_scenario,
    "record_catalyst": _apply_record_catalyst,
    "flag_analysis_gap": _apply_flag_analysis_gap,
    "flag_contradiction": _apply_flag_contradiction,
}

#: Sources are written first so later records can reference their ids regardless
#: of the order in which Claude emitted the tool calls.
_APPLY_ORDER = (
    "record_source",
    "record_assumption",
    "record_valuation",
    "record_scenario",
    "record_catalyst",
    "flag_analysis_gap",
    "flag_contradiction",
)


def update_workspace_from_claude(
    workspace: ResearchWorkspace,
    claude_tool_results: Sequence[ToolResult],
) -> AdapterReport:
    """Translate Claude ``tool_use`` blocks into workspace ledger writes.

    Tool calls are applied grouped by type in :data:`_APPLY_ORDER` (sources
    first), so a reference to a source recorded later in the same response still
    resolves. Within a group, Claude's original ordering is preserved.

    Exceptions from malformed payloads are not caught; the caller decides how to
    recover. References to unknown source ids are dropped rather than raised, and
    reported in :attr:`AdapterReport.dropped_source_links`, so that one bad link
    cannot invalidate an otherwise complete workspace.

    Args:
        workspace: The workspace to mutate in memory. Call ``save()`` afterwards.
        claude_tool_results: Tool-use blocks in the order Claude emitted them.

    Returns:
        An :class:`AdapterReport` describing what was written and normalized.
    """

    report = AdapterReport()
    grouped: Dict[str, List[ToolResult]] = {name: [] for name in _APPLY_ORDER}
    for result in claude_tool_results:
        if result.name in grouped:
            grouped[result.name].append(result)
        else:
            report.unknown_tools.append(result.name)

    for name in _APPLY_ORDER:
        handler = _HANDLERS[name]
        for result in grouped[name]:
            payload = result.input if isinstance(result.input, dict) else {}
            handler(workspace, payload, report)
            report.applied[name] = report.applied.get(name, 0) + 1

    return report
