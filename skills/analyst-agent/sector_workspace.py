"""In-memory view of a sector-primer workspace, with atomic persistence.

Mirrors ``workspace_adapter.ResearchWorkspace`` in API shape and spirit, but
for a different on-disk schema: the sector-primer workspace created by
``skills/sector-primer/scripts/init_sector_workspace.py``. That schema is
deliberately *not* the v2 company-workspace schema (``state/assumptions.json``
and ``state/contradictions.json`` are plain JSON lists here, not dicts; the
ledger carries no fixed ``record_type`` enum), so this module does not reuse
``ResearchWorkspace`` -- see the analyst-agent task notes for why.

This class owns every read and write of that schema. It does not modify the
``sector-primer`` skill; it loads that skill's validator at runtime (by file
path, the same way ``workspace_adapter._load_workspace_lib`` loads the
persistent-equity-research validator) and writes the same on-disk formats
``init_sector_workspace.py`` produces.
"""

from __future__ import annotations

import csv
import datetime as dt
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SKILLS_ROOT = Path(__file__).resolve().parents[1]
SECTOR_PRIMER_SCRIPTS = SKILLS_ROOT / "sector-primer" / "scripts"
INIT_SECTOR_WORKSPACE_SCRIPT = SECTOR_PRIMER_SCRIPTS / "init_sector_workspace.py"
VALIDATE_SECTOR_WORKSPACE_SCRIPT = SECTOR_PRIMER_SCRIPTS / "validate_sector_workspace.py"

#: Exact header row ``init_sector_workspace.py`` writes for
#: ``data/sector-metrics.csv``. Written in full on every save so the
#: validator's required-subset header check always passes.
SECTOR_METRICS_HEADERS: Sequence[str] = (
    "metric",
    "subsector",
    "value",
    "unit",
    "period",
    "as_of_date",
    "status",
    "definition",
    "numerator",
    "denominator",
    "weighting",
    "source_ids",
    "notes",
)

#: Exact header row ``init_sector_workspace.py`` writes for
#: ``data/company-comps.csv``.
COMPANY_COMPS_HEADERS: Sequence[str] = (
    "issuer",
    "ticker",
    "exchange",
    "peer_tag",
    "subsector",
    "currency",
    "market_data_date",
    "operating_period",
    "basis",
    "market_cap",
    "enterprise_value",
    "revenue",
    "revenue_growth",
    "ebitda_margin",
    "ebit_margin",
    "roic",
    "roe",
    "capex_sales",
    "rd_sales",
    "fcf_margin",
    "cash_conversion",
    "net_debt_ebitda",
    "pe",
    "ev_ebitda",
    "fcf_yield",
    "dividend_yield",
    "total_return",
    "estimate_vintage",
    "source_ids",
    "notes",
)

_LEDGER_CONFIDENCE = ("low", "medium", "high")


class SectorWorkspaceError(RuntimeError):
    """Raised when sector-primer workspace state cannot be loaded or written."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today() -> str:
    return dt.date.today().isoformat()


def _clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _iso_date_or_none(value: Any) -> Optional[str]:
    """Return ``value`` when it is a strict ISO ``YYYY-MM-DD`` date, else None."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.date.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == value.strip() else None


def _atomic_write(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically, keeping partial writes invisible."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=str(path.parent))
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
        raise SectorWorkspaceError(f"cannot read {path}: {exc}") from exc


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SectorWorkspaceError(f"cannot read {path}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SectorWorkspaceError(f"{path} line {number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise SectorWorkspaceError(f"{path} line {number}: record must be an object")
        records.append(value)
    return records


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_sector_validator():
    """Import ``validate_sector_workspace`` from the installed sector-primer skill.

    Loaded by file path -- not by ``sys.path`` mutation -- so importing this
    module never shadows a same-named module elsewhere in the host process.
    Mirrors ``workspace_adapter._load_workspace_lib``'s loading pattern exactly.
    """

    if not VALIDATE_SECTOR_WORKSPACE_SCRIPT.is_file():
        raise SectorWorkspaceError(
            f"sector-primer validate_sector_workspace.py not found at "
            f"{VALIDATE_SECTOR_WORKSPACE_SCRIPT}"
        )
    spec = importlib.util.spec_from_file_location(
        "analyst_agent_vendored_validate_sector_workspace", VALIDATE_SECTOR_WORKSPACE_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise SectorWorkspaceError(f"cannot load validator from {VALIDATE_SECTOR_WORKSPACE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


_sector_validator = None


def _sector_validator_module():
    global _sector_validator
    if _sector_validator is None:
        _sector_validator = _load_sector_validator()
    return _sector_validator


class SectorWorkspace:
    """In-memory view of a sector-primer workspace, with atomic persistence.

    Attributes:
        root: Absolute path to the workspace directory.
        project: ``project.json`` contents.
        context: ``state/research-context.json`` contents.
        sources: Rows from ``sources/registry.jsonl``.
        ledger: Rows from ``state/ledger.jsonl``. Schema-free beyond a common
            base shape (see :meth:`add_ledger_record`); report-type-specific
            fields ride along as extra keys on each record.
        assumptions: Plain list from ``state/assumptions.json``.
        contradictions: Plain list from ``state/contradictions.json``.
        sector_metrics: Rows from ``data/sector-metrics.csv``.
        company_comps: Rows from ``data/company-comps.csv``.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.project: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {}
        self.sources: List[Dict[str, Any]] = []
        self.ledger: List[Dict[str, Any]] = []
        self.assumptions: List[Dict[str, Any]] = []
        self.contradictions: List[Dict[str, Any]] = []
        self.sector_metrics: List[Dict[str, str]] = []
        self.company_comps: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Loading, creating, and saving
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, workspace_root: Any) -> "SectorWorkspace":
        """Load an initialized sector-primer workspace from disk.

        Args:
            workspace_root: Path to a workspace created by
                ``init_sector_workspace.py`` (or :meth:`create`).

        Returns:
            A populated :class:`SectorWorkspace`.

        Raises:
            SectorWorkspaceError: If the directory is missing or not a
                sector-primer workspace.
        """

        root = Path(workspace_root).expanduser().resolve()
        if not root.is_dir():
            raise SectorWorkspaceError(f"workspace directory does not exist: {root}")
        if not (root / "project.json").is_file():
            raise SectorWorkspaceError(f"not a sector-primer workspace, missing project.json: {root}")

        workspace = cls(root)
        workspace.project = _read_json(root / "project.json")
        if workspace.project.get("workspace_type") != "sector-primer":
            raise SectorWorkspaceError(
                f"{root} is not a sector-primer workspace "
                f"(workspace_type={workspace.project.get('workspace_type')!r})"
            )
        context_path = root / "state" / "research-context.json"
        workspace.context = _read_json(context_path) if context_path.is_file() else {}
        workspace.sources = _read_jsonl(root / "sources" / "registry.jsonl")
        workspace.ledger = _read_jsonl(root / "state" / "ledger.jsonl")

        assumptions_path = root / "state" / "assumptions.json"
        workspace.assumptions = _read_json(assumptions_path) if assumptions_path.is_file() else []
        if not isinstance(workspace.assumptions, list):
            raise SectorWorkspaceError(f"{assumptions_path} must contain a JSON array")

        contradictions_path = root / "state" / "contradictions.json"
        workspace.contradictions = _read_json(contradictions_path) if contradictions_path.is_file() else []
        if not isinstance(workspace.contradictions, list):
            raise SectorWorkspaceError(f"{contradictions_path} must contain a JSON array")

        workspace.sector_metrics = _read_csv_rows(root / "data" / "sector-metrics.csv")
        workspace.company_comps = _read_csv_rows(root / "data" / "company-comps.csv")
        return workspace

    @classmethod
    def create(
        cls,
        workspace_root: Any,
        sector_name: str,
        geography: str = "Global",
        benchmark: Optional[str] = None,
    ) -> "SectorWorkspace":
        """Initialize a new sector-primer workspace and load it.

        Shells out to ``skills/sector-primer/scripts/init_sector_workspace.py``
        rather than replicating its output structure in Python. That script is
        the canonical initializer this repository ships (and this package is
        forbidden from editing); invoking it directly guarantees byte-for-byte
        agreement with what a human running the sector-primer skill would
        produce, and stays correct automatically if that script's output ever
        changes shape.

        Args:
            workspace_root: Path to create the workspace at. Must not exist
                yet, or must exist and be empty.
            sector_name: e.g. ``"Semiconductors"``.
            geography: e.g. ``"Global"``.
            benchmark: Optional benchmark index name.

        Returns:
            A populated :class:`SectorWorkspace` loaded from the new files.

        Raises:
            SectorWorkspaceError: If the initializer script fails.
        """

        root = Path(workspace_root).expanduser().resolve()
        if not INIT_SECTOR_WORKSPACE_SCRIPT.is_file():
            raise SectorWorkspaceError(
                f"sector-primer init_sector_workspace.py not found at {INIT_SECTOR_WORKSPACE_SCRIPT}"
            )
        command = [
            sys.executable,
            str(INIT_SECTOR_WORKSPACE_SCRIPT),
            "--workspace",
            str(root),
            "--sector-name",
            sector_name,
            "--geography",
            geography,
        ]
        if benchmark:
            command.extend(["--benchmark", benchmark])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise SectorWorkspaceError(
                f"failed to initialize sector workspace at {root}: {result.stderr or result.stdout}"
            )
        return cls.load(root)

    def save(self) -> None:
        """Persist all mutated state atomically, file by file.

        ``outputs/sector-primer.md`` is not written here: it is a rendered
        publication view, written by the report renderer, not workspace state.
        """

        self.project["updated_at"] = _now_iso()
        _atomic_write(self.root / "project.json", json.dumps(self.project, indent=2, ensure_ascii=False) + "\n")
        _atomic_write(
            self.root / "state" / "research-context.json",
            json.dumps(self.context, indent=2, ensure_ascii=False) + "\n",
        )
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
        self._write_csv(self.root / "data" / "sector-metrics.csv", SECTOR_METRICS_HEADERS, self.sector_metrics)
        self._write_csv(self.root / "data" / "company-comps.csv", COMPANY_COMPS_HEADERS, self.company_comps)

    @staticmethod
    def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[Dict[str, str]]) -> None:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(headers), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
        _atomic_write(path, buffer.getvalue())

    def validate(self) -> List[str]:
        """Validate on-disk state with the sector-primer validator.

        Returns:
            A list of error strings; empty means valid.
        """

        return _sector_validator_module().validate(self.root)

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    @property
    def sector_name(self) -> str:
        return str(self.project.get("sector_name", ""))

    @property
    def geography(self) -> str:
        return str(self.project.get("geography", ""))

    def _next_id(self, prefix: str, existing: Sequence[str]) -> str:
        highest = 0
        for identifier in existing:
            if isinstance(identifier, str) and identifier.startswith(f"{prefix}-"):
                suffix = identifier[len(prefix) + 1 :]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"{prefix}-{highest + 1:04d}"

    @property
    def known_source_ids(self) -> List[str]:
        return [str(record.get("source_id")) for record in self.sources]

    def ledger_by_type(self, record_type: str) -> List[Dict[str, Any]]:
        """Return active ledger records of one ``record_type``, in insertion order."""

        return [
            record
            for record in self.ledger
            if record.get("record_type") == record_type and record.get("status") in ("active", "unresolved")
        ]

    def state_ledger_keys(self) -> List[str]:
        """Return the state collections that currently hold records."""

        keys: List[str] = []
        if self.sources:
            keys.append("sources")
        if self.ledger:
            keys.append("ledger")
        if self.assumptions:
            keys.append("assumptions")
        if self.contradictions:
            keys.append("contradictions")
        if self.sector_metrics:
            keys.append("sector_metrics")
        if self.company_comps:
            keys.append("company_comps")
        return keys

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

        Registration is idempotent on title and URL, exactly like
        ``ResearchWorkspace.add_source``: re-recording a source already
        ingested returns the existing id instead of duplicating it.
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
        source_ids: Optional[Sequence[str]] = None,
        status: str = "active",
        confidence: str = "medium",
        notes: Optional[str] = None,
        **fields: Any,
    ) -> str:
        """Append a ledger record and return its generated id.

        The sector-primer ledger enforces no fixed record shape beyond "valid
        JSON object per line", so report-type-specific fields (e.g. a peer
        benchmark's ``pe_ratio``, a value-chain segment's ``moat``) ride along
        as extra keyword arguments rather than being forced into a generic
        ``metric``/``value`` pair. Every record still carries an id, a
        statement, source ids, and a status, in the spirit of the company
        workspace's ledger.
        """

        record_id = self._next_id("LED", [str(item.get("id")) for item in self.ledger])
        record: Dict[str, Any] = {
            "id": record_id,
            "record_type": record_type,
            "statement": _clean_text(statement, "Unspecified statement."),
            "source_ids": list(source_ids or []),
            "confidence": confidence if confidence in _LEDGER_CONFIDENCE else "medium",
            "as_of_date": _today(),
            "status": status,
            "notes": notes,
        }
        record.update(fields)
        self.ledger.append(record)
        return record_id

    def add_assumption(
        self,
        name: str,
        value: Any,
        units: str = "",
        rationale: Optional[str] = None,
        source_ids: Optional[Sequence[str]] = None,
    ) -> str:
        """Append an assumption to the plain ``state/assumptions.json`` list."""

        assumption_id = self._next_id("ASM", [str(item.get("id")) for item in self.assumptions])
        self.assumptions.append(
            {
                "id": assumption_id,
                "name": _clean_text(name, "Unnamed assumption"),
                "value": value,
                "units": _clean_text(units),
                "rationale": _clean_text(rationale) or None,
                "source_ids": list(source_ids or []),
                "last_updated": _today(),
                "status": "active",
            }
        )
        return assumption_id

    def add_contradiction(
        self,
        summary: str,
        source_ids: Optional[Sequence[str]] = None,
        ledger_ids: Optional[Sequence[str]] = None,
    ) -> str:
        """Append an open contradiction to the plain ``state/contradictions.json`` list."""

        contradiction_id = self._next_id("CON", [str(item.get("id")) for item in self.contradictions])
        self.contradictions.append(
            {
                "id": contradiction_id,
                "summary": _clean_text(summary, "Unspecified contradiction."),
                "source_ids": list(source_ids or []),
                "ledger_ids": list(ledger_ids or []),
                "status": "open",
                "resolution": None,
                "last_updated": _today(),
            }
        )
        return contradiction_id

    def add_sector_metric_row(
        self,
        metric: str,
        subsector: str = "",
        value: Any = "",
        unit: str = "",
        period: str = "",
        as_of_date: Optional[str] = None,
        status: str = "estimated",
        definition: str = "",
        numerator: str = "",
        denominator: str = "",
        weighting: str = "",
        source_ids: Optional[Sequence[str]] = None,
        notes: str = "",
    ) -> None:
        """Append one row to ``data/sector-metrics.csv``, all headers populated."""

        self.sector_metrics.append(
            {
                "metric": _clean_text(metric),
                "subsector": _clean_text(subsector),
                "value": "" if value in (None, "") else str(value),
                "unit": _clean_text(unit),
                "period": _clean_text(period),
                "as_of_date": _clean_text(as_of_date) or _today(),
                "status": _clean_text(status, "estimated"),
                "definition": _clean_text(definition),
                "numerator": _clean_text(numerator),
                "denominator": _clean_text(denominator),
                "weighting": _clean_text(weighting),
                "source_ids": ";".join(str(item) for item in (source_ids or [])),
                "notes": _clean_text(notes),
            }
        )

    def add_company_comp_row(
        self,
        issuer: str,
        ticker: str,
        exchange: str = "",
        peer_tag: str = "",
        subsector: str = "",
        currency: str = "USD",
        market_data_date: Optional[str] = None,
        operating_period: str = "",
        basis: str = "",
        market_cap: Any = "",
        enterprise_value: Any = "",
        revenue: Any = "",
        revenue_growth: Any = "",
        ebitda_margin: Any = "",
        ebit_margin: Any = "",
        roic: Any = "",
        roe: Any = "",
        capex_sales: Any = "",
        rd_sales: Any = "",
        fcf_margin: Any = "",
        cash_conversion: Any = "",
        net_debt_ebitda: Any = "",
        pe: Any = "",
        ev_ebitda: Any = "",
        fcf_yield: Any = "",
        dividend_yield: Any = "",
        total_return: Any = "",
        estimate_vintage: str = "",
        source_ids: Optional[Sequence[str]] = None,
        notes: str = "",
    ) -> None:
        """Append one row to ``data/company-comps.csv``, all headers populated."""

        def text(value: Any) -> str:
            return "" if value in (None, "") else str(value)

        self.company_comps.append(
            {
                "issuer": _clean_text(issuer),
                "ticker": _clean_text(ticker),
                "exchange": _clean_text(exchange),
                "peer_tag": _clean_text(peer_tag),
                "subsector": _clean_text(subsector),
                "currency": _clean_text(currency, "USD"),
                "market_data_date": _clean_text(market_data_date) or _today(),
                "operating_period": _clean_text(operating_period),
                "basis": _clean_text(basis),
                "market_cap": text(market_cap),
                "enterprise_value": text(enterprise_value),
                "revenue": text(revenue),
                "revenue_growth": text(revenue_growth),
                "ebitda_margin": text(ebitda_margin),
                "ebit_margin": text(ebit_margin),
                "roic": text(roic),
                "roe": text(roe),
                "capex_sales": text(capex_sales),
                "rd_sales": text(rd_sales),
                "fcf_margin": text(fcf_margin),
                "cash_conversion": text(cash_conversion),
                "net_debt_ebitda": text(net_debt_ebitda),
                "pe": text(pe),
                "ev_ebitda": text(ev_ebitda),
                "fcf_yield": text(fcf_yield),
                "dividend_yield": text(dividend_yield),
                "total_return": text(total_return),
                "estimate_vintage": _clean_text(estimate_vintage),
                "source_ids": ";".join(str(item) for item in (source_ids or [])),
                "notes": _clean_text(notes),
            }
        )

    def record_context_gap(self, description: str) -> None:
        """Append a gap description to ``state/research-context.json``'s research_gaps.

        Idempotent on exact text so re-running the agent against an existing
        workspace does not pile up duplicate gap entries.
        """

        gaps = self.context.setdefault("research_gaps", [])
        text = _clean_text(description)
        if text and text not in gaps:
            gaps.append(text)

    def touch_research_update(self) -> None:
        """Stamp today's date on the research context's ``as_of_date``."""

        self.context["as_of_date"] = _today()
