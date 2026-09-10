#!/usr/bin/env python3
"""Run the behavioral corpus through any command-line agent."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "persistent-equity-research" / "SKILL.md"
CORPUS = ROOT / "evals" / "evals.json"
TEMPLATE = ROOT / "skills" / "persistent-equity-research" / "assets" / "company-workspace"


def _snapshot(workspace: Path) -> List[str]:
    return sorted(
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not label:
        raise ValueError("eval label must contain a letter or number")
    return label[:100]


def _prepare_initialized_workspace(workspace: Path) -> None:
    shutil.copytree(TEMPLATE, workspace)
    (workspace / "analysis").mkdir()
    (workspace / "sources" / "extracts").mkdir()

    project_path = workspace / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project.update({
        "company_name": "Acme Components plc",
        "ticker": "ACME",
        "exchange": "TEST",
        "benchmark": "Synthetic 100",
        "status": "active",
        "created_at": "2025-01-02",
        "last_research_update": "2025-01-03",
    })
    _write_json(project_path, project)

    context_path = workspace / "state" / "research-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context.update({
        "company_name": "Acme Components plc",
        "ticker": "ACME",
        "exchange": "TEST",
        "benchmark": "Synthetic 100",
        "research_date": "2025-01-03",
        "existing_state": True,
    })
    _write_json(context_path, context)

    source = {
        "source_id": "SRC-0001",
        "title": "Synthetic annual report",
        "source_type": "company_filing",
        "publisher": "Acme Components",
        "url_or_ref": "fixture:annual-report",
        "publication_date": "2025-01-02",
        "observation_period": "FY2024",
        "accessed_at": "2025-01-03",
        "primary_source": True,
        "quality_tier": 1,
        "notes": "Synthetic live-eval input.",
    }
    (workspace / "sources" / "registry.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
    ledger = {
        "id": "OBS-0001",
        "record_type": "observed_fact",
        "statement": "Acme reported FY2024 revenue of 100 units.",
        "metric": "revenue",
        "value": 100,
        "unit": "units",
        "period": "FY2024",
        "as_of_date": "2024-12-31",
        "source_ids": ["SRC-0001"],
        "confidence": "high",
        "nodes": ["source_ingestion", "company_overlay"],
        "depends_on": [],
        "supersedes": None,
        "status": "active",
        "notes": "Synthetic live-eval input.",
    }
    (workspace / "state" / "ledger.jsonl").write_text(json.dumps(ledger) + "\n", encoding="utf-8")
    _write_json(workspace / "state" / "assumptions.json", {
        "assumptions": [{
            "id": "ASM-0001",
            "name": "Revenue growth",
            "base": 5.0,
            "bear": 1.0,
            "bull": 8.0,
            "units": "percent",
            "owner_node": "company_overlay",
            "rationale": "Synthetic live-eval input.",
            "source_ids": ["SRC-0001"],
            "last_updated": "2025-01-03",
            "status": "active",
        }],
        "scenario_overrides": {},
    })

    graph_path = workspace / "state" / "dependency-graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    for node_name, node in graph["nodes"].items():
        node["status"] = "fresh"
        for output in node["outputs"]:
            path = workspace / output
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# Synthetic {node_name} output\n", encoding="utf-8")
    _write_json(graph_path, graph)


def _run(command_template: List[str], prompt: str, workspace: Path) -> Dict[str, object]:
    replacements = {
        "prompt": prompt,
        "workspace": str(workspace),
        "skill": str(SKILL),
        "repository": str(ROOT),
    }
    command = [argument.format(**replacements) for argument in command_template]
    if not any("{prompt}" in argument for argument in command_template):
        command.append(prompt)
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": ["<prompt>" if argument == prompt else argument for argument in command],
        "duration_seconds": round(time.monotonic() - started, 3),
        "exit_code": completed.returncode,
        "files": _snapshot(workspace),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run opt-in with-skill and baseline behavioral evals.")
    parser.add_argument("--host", required=True, help="Agent host or client, such as codex or claude-code")
    parser.add_argument("--model", required=True, help="Model identifier used for the run")
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Available capability to record; repeat for multiple values",
    )
    parser.add_argument("--label", help="Optional filename label; defaults to <host>-<model>")
    parser.add_argument("--output", help="Result JSON path; defaults beneath evals/results")
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True, help="Agent command and arguments")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.command:
        print("ERROR: --command requires an executable and arguments", file=sys.stderr)
        return 2
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    try:
        label = _safe_label(args.label or f"{args.host}-{args.model}")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    result = {
        "label": label,
        "host": args.host,
        "model": args.model,
        "capabilities": args.capability,
        "run_at": timestamp,
        "skill": str(SKILL),
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="persistent-equity-research-evals-") as temporary:
        temporary_root = Path(temporary)
        for case in corpus["evals"]:
            case_result: Dict[str, object] = {
                "id": case["id"],
                "name": case["name"],
                "assertions": case.get("assertions", []),
            }
            for mode in ("with_skill", "baseline"):
                run_directory = temporary_root / f"case-{case['id']}-{mode}"
                run_directory.mkdir()
                workspace = run_directory / "workspace"
                if case.get("setup") == "initialized_workspace":
                    _prepare_initialized_workspace(workspace)
                user_prompt = case["prompt"].replace("{workspace}", str(workspace))
                if mode == "with_skill":
                    prompt = (
                        f"Read and use the Agent Skill at {SKILL} for this request. "
                        f"Keep generated files inside {run_directory}.\n\nUser request: {user_prompt}"
                    )
                else:
                    prompt = (
                        "Complete this request without reading or using the persistent-equity-research skill. "
                        f"Keep generated files inside {run_directory}.\n\nUser request: {user_prompt}"
                    )
                case_result[mode] = _run(args.command, prompt, run_directory)
            result["cases"].append(case_result)

    if args.output:
        output = Path(args.output).expanduser().resolve()
    else:
        safe_timestamp = timestamp.replace(":", "-")
        output = ROOT / "evals" / "results" / f"{safe_timestamp}-{label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote eval results: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
