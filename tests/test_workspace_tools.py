from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "persistent-equity-research"
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workspace_lib import downstream_nodes, validate_workspace  # noqa: E402


INIT = SCRIPTS / "init_workspace.py"
MIGRATE = SCRIPTS / "migrate_v1_workspace.py"
VALIDATE = SCRIPTS / "validate_workspace.py"


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


class WorkspaceToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "ACME"
        result = run_script(
            INIT,
            "--workspace", str(self.workspace),
            "--ticker", "acme",
            "--company-name", "Acme Components plc",
            "--exchange", "TEST",
            "--benchmark", "Synthetic 100",
            "--format", "json",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initializer_creates_external_valid_workspace(self) -> None:
        project = json.loads((self.workspace / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["schema_version"], 2)
        self.assertEqual(project["ticker"], "ACME")
        self.assertTrue((self.workspace / "analysis").is_dir())
        self.assertTrue((self.workspace / "sources" / "extracts").is_dir())
        validation = validate_workspace(self.workspace)
        self.assertTrue(validation.valid, validation.errors)
        self.assertIn("source registry is empty", validation.warnings)

    def test_initializer_refuses_existing_destination(self) -> None:
        result = run_script(
            INIT,
            "--workspace", str(self.workspace),
            "--ticker", "ACME",
            "--company-name", "Acme Components plc",
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.workspace.is_dir())

    def test_initializer_failure_leaves_no_partial_workspace(self) -> None:
        destination = self.root / "invalid"
        result = run_script(
            INIT,
            "--workspace", str(destination),
            "--ticker", "not valid!",
            "--company-name", "Invalid Company",
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())

    def test_initializer_without_optional_benchmark_is_valid(self) -> None:
        workspace = self.root / "NO-BENCHMARK"
        result = run_script(
            INIT,
            "--workspace", str(workspace),
            "--ticker", "NBM",
            "--company-name", "No Benchmark plc",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        validation = validate_workspace(workspace)
        self.assertTrue(validation.valid, validation.errors)

    def test_cli_usage_errors_exit_two(self) -> None:
        result = run_script(VALIDATE)
        self.assertEqual(result.returncode, 2)

    def test_corrupt_json_is_reported(self) -> None:
        (self.workspace / "project.json").write_text("{not-json", encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("invalid JSON" in error for error in result.errors))

    def test_corrupt_jsonl_is_reported_with_line_number(self) -> None:
        (self.workspace / "state" / "ledger.jsonl").write_text("{}\nnot-json\n", encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("line 2: invalid JSON" in error for error in result.errors))

    def test_unsupported_schema_version_is_rejected(self) -> None:
        path = self.workspace / "project.json"
        project = json.loads(path.read_text(encoding="utf-8"))
        project["schema_version"] = 99
        path.write_text(json.dumps(project), encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("expected constant 2" in error for error in result.errors))

    def test_duplicate_ledger_id_and_missing_source_are_reported(self) -> None:
        record = {
            "id": "OBS-1",
            "record_type": "observed_fact",
            "statement": "Synthetic fact.",
            "confidence": "high",
            "status": "active",
            "source_ids": ["MISSING"],
            "nodes": [],
            "depends_on": [],
            "supersedes": None,
            "metric": None,
            "value": None,
            "unit": None,
            "period": None,
            "as_of_date": None,
            "notes": None,
        }
        text = json.dumps(record) + "\n" + json.dumps(record) + "\n"
        (self.workspace / "state" / "ledger.jsonl").write_text(text, encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("duplicate id OBS-1" in error for error in result.errors))
        self.assertTrue(any("unknown source id MISSING" in error for error in result.errors))

    def test_dependency_cycle_is_reported(self) -> None:
        path = self.workspace / "state" / "dependency-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["source_ingestion"]["depends_on"] = ["qa"]
        path.write_text(json.dumps(graph), encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("dependency cycle" in error for error in result.errors))

    def test_downstream_dependency_traversal_is_selective_and_ordered(self) -> None:
        graph = json.loads(
            (self.workspace / "state" / "dependency-graph.json").read_text(encoding="utf-8")
        )
        affected = downstream_nodes(graph, ["valuation"])
        self.assertEqual(set(affected), {"valuation", "strategist_dashboard", "synthesis", "qa"})
        self.assertLess(affected.index("valuation"), affected.index("strategist_dashboard"))
        self.assertLess(affected.index("strategist_dashboard"), affected.index("synthesis"))
        self.assertLess(affected.index("synthesis"), affected.index("qa"))

    def test_fresh_node_requires_fresh_dependencies(self) -> None:
        path = self.workspace / "state" / "dependency-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["economic_engine"]["status"] = "fresh"
        output = self.workspace / graph["nodes"]["economic_engine"]["outputs"][0]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("# Synthetic output\n", encoding="utf-8")
        path.write_text(json.dumps(graph), encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("dependency source_ingestion is not fresh" in error for error in result.errors))

    def test_csv_and_ledger_node_references_are_validated(self) -> None:
        forecast = self.workspace / "data" / "historical-financials.csv"
        forecast.write_text(
            forecast.read_text(encoding="utf-8") +
            "FY2024,100,5,5,40,30,30,20,20,1,25,5,20,0,10,MISSING\n",
            encoding="utf-8",
        )
        record = {
            "id": "OBS-1",
            "record_type": "research_gap",
            "statement": "Synthetic gap.",
            "metric": None,
            "value": None,
            "unit": None,
            "period": None,
            "as_of_date": None,
            "source_ids": [],
            "confidence": "medium",
            "nodes": ["missing_node"],
            "depends_on": [],
            "supersedes": None,
            "status": "unresolved",
            "notes": None,
        }
        (self.workspace / "state" / "ledger.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("unknown source id MISSING" in error for error in result.errors))
        self.assertTrue(any("unknown dependency node missing_node" in error for error in result.errors))

    def test_path_escape_is_reported(self) -> None:
        path = self.workspace / "state" / "dependency-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["source_ingestion"]["outputs"] = ["../outside.json"]
        path.write_text(json.dumps(graph), encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("unsafe output path" in error for error in result.errors))

    def test_windows_drive_output_is_reported_on_every_host(self) -> None:
        path = self.workspace / "state" / "dependency-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["source_ingestion"]["outputs"] = ["C:/outside.json"]
        path.write_text(json.dumps(graph), encoding="utf-8")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("unsafe output path" in error for error in result.errors))

    def test_workspace_symlink_is_rejected(self) -> None:
        target = self.root / "outside.json"
        target.write_text("{}", encoding="utf-8")
        link = self.workspace / "state" / "linked.json"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("symlinks are unavailable on this platform")
        result = validate_workspace(self.workspace)
        self.assertFalse(result.valid)
        self.assertTrue(any("symlinks are not allowed" in error for error in result.errors))

    def test_stale_warning_becomes_strict_failure(self) -> None:
        path = self.workspace / "state" / "dependency-graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["source_ingestion"]["status"] = "stale"
        path.write_text(json.dumps(graph), encoding="utf-8")
        ordinary = validate_workspace(self.workspace)
        strict = validate_workspace(self.workspace, strict=True)
        self.assertTrue(ordinary.valid, ordinary.errors)
        self.assertFalse(strict.valid)
        self.assertTrue(any("strict mode" in error for error in strict.errors))

    def test_json_cli_output(self) -> None:
        result = run_script(VALIDATE, str(self.workspace), "--format", "json")
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["workspace"], str(self.workspace.resolve()))


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "legacy"
        shutil.copytree(ROOT / "tests" / "fixtures" / "v1-workspace", self.source)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_dry_run_does_not_create_destination(self) -> None:
        destination = self.root / "dry-run-destination"
        result = run_script(MIGRATE, str(self.source), str(destination), "--dry-run", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertFalse(destination.exists())
        self.assertTrue(self.source.exists())
        self.assertFalse(json.loads(result.stdout)["migrated"])

    def test_migration_preserves_user_artifacts_and_validates(self) -> None:
        destination = self.root / "v2"
        result = run_script(MIGRATE, str(self.source), str(destination), "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue((destination / "analysis" / "custom-analysis.md").is_file())
        self.assertTrue((destination / "outputs" / "custom-output.md").is_file())
        self.assertTrue((self.source / "project.yaml").is_file())
        project = json.loads((destination / "project.json").read_text(encoding="utf-8"))
        assumptions = json.loads((destination / "state" / "assumptions.json").read_text(encoding="utf-8"))
        self.assertEqual(project["ticker"], "ACME")
        self.assertEqual(assumptions["assumptions"][0]["id"], "ASM-0001")
        registry_lines = (destination / "sources" / "registry.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(registry_lines), 1)
        validation = validate_workspace(destination)
        self.assertTrue(validation.valid, validation.errors)

    def test_migration_refuses_existing_destination(self) -> None:
        destination = self.root / "existing"
        destination.mkdir()
        result = run_script(MIGRATE, str(self.source), str(destination))
        self.assertEqual(result.returncode, 1)

    def test_migration_refuses_destination_inside_source(self) -> None:
        destination = self.source / "nested-v2"
        result = run_script(MIGRATE, str(self.source), str(destination))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())

    def test_failed_migration_leaves_no_partial_destination(self) -> None:
        (self.source / "project.yaml").write_text("ticker: invalid ticker!\n", encoding="utf-8")
        destination = self.root / "failed-v2"
        result = run_script(MIGRATE, str(self.source), str(destination))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
