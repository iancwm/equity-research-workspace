"""Dependency-free validation helpers for v2 equity-research workspaces."""

from __future__ import annotations

import csv
import datetime as dt
import heapq
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = SKILL_ROOT / "schemas"

REQUIRED_FILES = (
    "project.json",
    "state/research-context.json",
    "state/ledger.jsonl",
    "state/assumptions.json",
    "state/contradictions.json",
    "state/dependency-graph.json",
    "sources/registry.jsonl",
)

JSON_SCHEMAS = {
    "project.json": "project.schema.json",
    "state/research-context.json": "research-context.schema.json",
    "state/assumptions.json": "assumptions.schema.json",
    "state/contradictions.json": "contradictions.schema.json",
    "state/dependency-graph.json": "dependency-graph.schema.json",
}

CSV_HEADERS = {
    "data/consensus.csv": ("period", "metric", "consensus", "high", "low", "as_of_date", "source_id"),
    "data/forecast.csv": (
        "period", "revenue", "revenue_growth", "ebit_margin", "ebit", "net_income", "eps",
        "cfo", "capex", "fcf", "assumption_set",
    ),
    "data/historical-financials.csv": (
        "period", "revenue", "organic_growth", "reported_growth", "gross_margin", "ebitda",
        "ebitda_margin", "ebit", "ebit_margin", "eps", "cfo", "capex", "fcf", "net_debt",
        "shares", "source_id",
    ),
    "data/peer-comps.csv": (
        "company", "ticker", "revenue_growth", "ebitda_margin", "fcf_margin", "roic",
        "net_leverage", "valuation_metric", "valuation_multiple", "as_of_date", "source_id",
    ),
    "data/valuation-history.csv": (
        "date", "price", "market_cap", "enterprise_value", "pe_fwd", "ev_ebitda_fwd",
        "fcf_yield", "source_id",
    ),
    "data/valuation.csv": (
        "scenario", "method", "assumption_set", "implied_equity_value", "shares",
        "implied_price", "notes",
    ),
}


@dataclass
class ValidationResult:
    workspace: str
    errors: List[str]
    warnings: List[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workspace": self.workspace,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _resolve_local_ref(root: Dict[str, Any], ref: str) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported schema reference: {ref}")
    current: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"schema reference does not resolve to an object: {ref}")
    return current


def validate_against_schema(
    value: Any,
    schema: Dict[str, Any],
    path: str = "$",
    root: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Validate the JSON Schema subset used by this skill."""

    root = root or schema
    if "$ref" in schema:
        return validate_against_schema(value, _resolve_local_ref(root, schema["$ref"]), path, root)

    errors: List[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not one of {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else expected
        if not any(_json_type_matches(value, item) for item in expected_types):
            errors.append(f"{path}: expected type {expected!r}, got {type(value).__name__}")
            return errors

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        for key, child in value.items():
            if key in properties:
                errors.extend(validate_against_schema(child, properties[key], f"{path}.{key}", root))
                continue
            additional = schema.get("additionalProperties", True)
            if additional is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                errors.extend(validate_against_schema(child, additional, f"{path}.{key}", root))

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            errors.extend(validate_against_schema(child, schema["items"], f"{path}[{index}]", root))

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if minimum_length is not None and len(value) < minimum_length:
            errors.append(f"{path}: string is shorter than {minimum_length}")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{path}: value does not match pattern {pattern!r}")
        if schema.get("format") == "date" and value:
            try:
                parsed = dt.date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: expected an ISO 8601 date (YYYY-MM-DD)")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value is above maximum {schema['maximum']}")
    return errors


def _load_json(path: Path, errors: List[str]) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: invalid JSON: {exc}")
        return None


def _load_jsonl(path: Path, label: str, errors: List[str]) -> List[Tuple[int, Dict[str, Any]]]:
    records: List[Tuple[int, Dict[str, Any]]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"{label}: cannot read file: {exc}")
        return records
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{label} line {line_number}: record must be an object")
            continue
        records.append((line_number, value))
    return records


def _load_schema(name: str) -> Dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _safe_workspace_path(workspace: Path, relative: str) -> bool:
    if "\\" in relative:
        return False
    if re.match(r"^[A-Za-z]:", relative):
        return False
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        return False
    try:
        (workspace / Path(*pure.parts)).resolve().relative_to(workspace.resolve())
    except ValueError:
        return False
    return True


def downstream_nodes(graph: Dict[str, Any], changed_nodes: Sequence[str]) -> List[str]:
    """Return changed nodes and all dependents in deterministic dependency order."""

    nodes = graph.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("dependency graph must contain a nodes object")
    changed = set(changed_nodes)
    unknown = sorted(changed - set(nodes))
    if unknown:
        raise ValueError(f"unknown changed dependency nodes: {', '.join(unknown)}")

    dependents: Dict[str, List[str]] = {name: [] for name in nodes}
    for name, node in nodes.items():
        if not isinstance(node, dict):
            raise ValueError(f"dependency node {name} must be an object")
        for dependency in node.get("depends_on", []):
            if dependency not in nodes:
                raise ValueError(f"dependency node {name} has unknown dependency {dependency}")
            dependents[dependency].append(name)

    affected = set(changed)
    pending = list(changed)
    while pending:
        current = pending.pop()
        for dependent in dependents[current]:
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)

    indegree = {
        name: sum(1 for dependency in nodes[name].get("depends_on", []) if dependency in affected)
        for name in affected
    }
    ready = [name for name, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: List[str] = []
    while ready:
        current = heapq.heappop(ready)
        ordered.append(current)
        for dependent in sorted(dependents[current]):
            if dependent not in indegree:
                continue
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(affected):
        raise ValueError("affected dependency nodes contain a cycle")
    return ordered


def _check_dependency_graph(workspace: Path, graph: Any, errors: List[str], warnings: List[str]) -> set:
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), dict):
        return set()
    nodes = graph["nodes"]
    for name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for dependency in node.get("depends_on", []):
            if dependency not in nodes:
                errors.append(f"dependency node {name}: unknown dependency {dependency}")
            elif (
                node.get("status") == "fresh"
                and (
                    not isinstance(nodes[dependency], dict)
                    or nodes[dependency].get("status") != "fresh"
                )
            ):
                errors.append(f"fresh dependency node {name}: dependency {dependency} is not fresh")
        for output in node.get("outputs", []):
            if not isinstance(output, str) or not _safe_workspace_path(workspace, output):
                errors.append(f"dependency node {name}: unsafe output path {output!r}")
            elif node.get("status") == "fresh" and not (workspace / output).is_file():
                errors.append(f"fresh dependency node {name}: missing output {output}")
        if node.get("status") == "stale":
            warnings.append(f"dependency node {name} is stale")

    visiting: set = set()
    visited: set = set()

    def visit(name: str, trail: Sequence[str]) -> None:
        if name in visiting:
            start = list(trail).index(name) if name in trail else 0
            cycle = list(trail)[start:] + [name]
            errors.append(f"dependency cycle: {' -> '.join(cycle)}")
            return
        if name in visited:
            return
        visiting.add(name)
        node = nodes.get(name, {})
        if isinstance(node, dict):
            for dependency in node.get("depends_on", []):
                if dependency in nodes:
                    visit(dependency, tuple(trail) + (name,))
        visiting.remove(name)
        visited.add(name)

    for node_name in nodes:
        visit(node_name, ())
    return set(nodes)


def _check_csv_files(workspace: Path, source_ids: set, errors: List[str]) -> None:
    for relative, required_headers in CSV_HEADERS.items():
        path = workspace / relative
        if not path.exists() or path.is_symlink():
            errors.append(f"missing required file: {relative}")
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                headers = tuple(reader.fieldnames or ())
                rows = list(reader)
        except OSError as exc:
            errors.append(f"{relative}: cannot read CSV: {exc}")
            continue
        missing = [header for header in required_headers if header not in headers]
        if missing:
            errors.append(f"{relative}: missing CSV columns {', '.join(missing)}")
        if "source_id" in headers:
            for line_number, row in enumerate(rows, 2):
                source_id = (row.get("source_id") or "").strip()
                if source_id and source_id not in source_ids:
                    errors.append(f"{relative} line {line_number}: unknown source id {source_id}")


def validate_workspace(workspace: Path, strict: bool = False) -> ValidationResult:
    workspace = workspace.resolve()
    errors: List[str] = []
    warnings: List[str] = []
    if not workspace.is_dir():
        return ValidationResult(str(workspace), [f"workspace directory does not exist: {workspace}"], [])

    for path in workspace.rglob("*"):
        if path.is_symlink():
            errors.append(f"symlinks are not allowed in a workspace: {path.relative_to(workspace).as_posix()}")

    for relative in REQUIRED_FILES:
        if not (workspace / relative).is_file() or (workspace / relative).is_symlink():
            errors.append(f"missing required file: {relative}")

    documents: Dict[str, Any] = {}
    for relative, schema_name in JSON_SCHEMAS.items():
        path = workspace / relative
        if not path.is_file() or path.is_symlink():
            continue
        value = _load_json(path, errors)
        if value is None:
            continue
        documents[relative] = value
        schema = _load_schema(schema_name)
        for problem in validate_against_schema(value, schema):
            errors.append(f"{relative}: {problem}")

    project = documents.get("project.json")
    context = documents.get("state/research-context.json")
    if isinstance(project, dict) and isinstance(context, dict):
        for field in ("company_name", "ticker", "exchange", "base_currency", "rating_convention"):
            if project.get(field) != context.get(field):
                errors.append(f"project/context mismatch for {field}")

    source_records = _load_jsonl(workspace / "sources/registry.jsonl", "sources/registry.jsonl", errors) \
        if (workspace / "sources/registry.jsonl").is_file() and not (workspace / "sources/registry.jsonl").is_symlink() else []
    source_schema = _load_schema("source-record.schema.json")
    source_ids: set = set()
    for line_number, record in source_records:
        for problem in validate_against_schema(record, source_schema):
            errors.append(f"sources/registry.jsonl line {line_number}: {problem}")
        source_id = record.get("source_id")
        if isinstance(source_id, str):
            if source_id in source_ids:
                errors.append(f"sources/registry.jsonl line {line_number}: duplicate source_id {source_id}")
            source_ids.add(source_id)
    if not source_records:
        warnings.append("source registry is empty")

    ledger_records = _load_jsonl(workspace / "state/ledger.jsonl", "state/ledger.jsonl", errors) \
        if (workspace / "state/ledger.jsonl").is_file() and not (workspace / "state/ledger.jsonl").is_symlink() else []
    ledger_schema = _load_schema("ledger-record.schema.json")
    ledger_ids: set = set()
    ledger_links: List[Tuple[int, str, str]] = []
    for line_number, record in ledger_records:
        for problem in validate_against_schema(record, ledger_schema):
            errors.append(f"state/ledger.jsonl line {line_number}: {problem}")
        record_id = record.get("id")
        if isinstance(record_id, str):
            if record_id in ledger_ids:
                errors.append(f"state/ledger.jsonl line {line_number}: duplicate id {record_id}")
            ledger_ids.add(record_id)
        for source_id in record.get("source_ids", []):
            ledger_links.append((line_number, "source", source_id))
        for dependency in record.get("depends_on", []):
            ledger_links.append((line_number, "ledger", dependency))
        supersedes = record.get("supersedes")
        if supersedes:
            ledger_links.append((line_number, "ledger", supersedes))
        if record.get("record_type") == "observed_fact" and not record.get("source_ids"):
            warnings.append(f"state/ledger.jsonl line {line_number}: observed fact has no source_ids")
    if not ledger_records:
        warnings.append("research ledger is empty")
    for line_number, link_type, identifier in ledger_links:
        known = source_ids if link_type == "source" else ledger_ids
        if identifier not in known:
            errors.append(f"state/ledger.jsonl line {line_number}: unknown {link_type} id {identifier}")

    graph = documents.get("state/dependency-graph.json")
    node_ids = _check_dependency_graph(workspace, graph, errors, warnings)
    for line_number, record in ledger_records:
        for node_id in record.get("nodes", []):
            if node_id not in node_ids:
                errors.append(f"state/ledger.jsonl line {line_number}: unknown dependency node {node_id}")

    assumptions = documents.get("state/assumptions.json")
    assumption_ids: set = set()
    if isinstance(assumptions, dict):
        for index, record in enumerate(assumptions.get("assumptions", [])):
            if not isinstance(record, dict):
                continue
            assumption_id = record.get("id")
            if assumption_id in assumption_ids:
                errors.append(f"state/assumptions.json assumption {index}: duplicate id {assumption_id}")
            assumption_ids.add(assumption_id)
            for source_id in record.get("source_ids", []):
                if source_id not in source_ids:
                    errors.append(f"state/assumptions.json assumption {index}: unknown source id {source_id}")
            owner = record.get("owner_node")
            if owner and owner not in node_ids:
                errors.append(f"state/assumptions.json assumption {index}: unknown owner_node {owner}")

    contradictions = documents.get("state/contradictions.json")
    contradiction_ids: set = set()
    if isinstance(contradictions, dict):
        for index, record in enumerate(contradictions.get("contradictions", [])):
            if not isinstance(record, dict):
                continue
            contradiction_id = record.get("id")
            if contradiction_id in contradiction_ids:
                errors.append(f"state/contradictions.json contradiction {index}: duplicate id {contradiction_id}")
            contradiction_ids.add(contradiction_id)
            for source_id in record.get("source_ids", []):
                if source_id not in source_ids:
                    errors.append(f"state/contradictions.json contradiction {index}: unknown source id {source_id}")
            for ledger_id in record.get("ledger_ids", []):
                if ledger_id not in ledger_ids:
                    errors.append(f"state/contradictions.json contradiction {index}: unknown ledger id {ledger_id}")

    _check_csv_files(workspace, source_ids, errors)
    if strict and warnings:
        errors.extend(f"strict mode: {warning}" for warning in warnings)
    return ValidationResult(str(workspace), errors, warnings)
