from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "skills" / "sector-primer" / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

import init_sector_workspace  # noqa: E402
import validate_sector_workspace  # noqa: E402


class SectorPrimerWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "semiconductors"
        init_sector_workspace.build_workspace(self.workspace, "Semiconductors", "Global", "TEST")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initializer_creates_valid_workspace_and_expected_headers(self) -> None:
        self.assertEqual(validate_sector_workspace.validate(self.workspace), [])
        project = json.loads((self.workspace / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["workspace_type"], "sector-primer")
        self.assertEqual(project["benchmark"], "TEST")
        metric_header = (self.workspace / "data" / "sector-metrics.csv").read_text(encoding="utf-8").splitlines()[0]
        comp_header = (self.workspace / "data" / "company-comps.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("definition", metric_header)
        self.assertIn("ev_ebitda", comp_header)
        self.assertIn("cash_conversion", comp_header)

    def test_initializer_refuses_non_empty_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace is not empty"):
            init_sector_workspace.build_workspace(self.workspace, "Other Sector", "US", None)

    def test_validator_reports_missing_file(self) -> None:
        (self.workspace / "state" / "ledger.jsonl").unlink()
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertIn("missing file: state/ledger.jsonl", errors)

    def test_validator_reports_bad_jsonl_and_invalid_json_documents(self) -> None:
        (self.workspace / "state" / "ledger.jsonl").write_text("{}\nnot-json\n", encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertTrue(any("invalid JSON on line 2" in error for error in errors))

        (self.workspace / "project.json").write_text("{not-json", encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertTrue(any("project.json: invalid JSON" in error for error in errors))

    def test_validator_reports_non_object_jsonl_and_empty_csv(self) -> None:
        (self.workspace / "state" / "ledger.jsonl").write_text("[]\n", encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertTrue(any("must be a JSON object" in error for error in errors))

        (self.workspace / "state" / "ledger.jsonl").write_text("", encoding="utf-8")
        (self.workspace / "data" / "sector-metrics.csv").write_text("", encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertTrue(any("sector-metrics.csv: missing CSV header" in error for error in errors))

    def test_validator_reports_shape_and_header_errors(self) -> None:
        (self.workspace / "project.json").write_text("[]\n", encoding="utf-8")
        (self.workspace / "state/research-context.json").write_text("[]\n", encoding="utf-8")
        (self.workspace / "state/assumptions.json").write_text("{}\n", encoding="utf-8")
        (self.workspace / "data/sector-metrics.csv").write_text("metric,value\n", encoding="utf-8")
        (self.workspace / "data/company-comps.csv").write_text("issuer,ticker\n", encoding="utf-8")
        project = {
            "schema_version": "1.0",
            "workspace_type": "wrong-type",
            "sector_name": "",
            "geography": "",
        }
        (self.workspace / "project.json").write_text(json.dumps(project), encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertIn("project.json missing non-empty field: sector_name", errors)
        self.assertIn("project.json missing non-empty field: geography", errors)
        self.assertIn("project.json workspace_type must be 'sector-primer'", errors)

        (self.workspace / "project.json").write_text("[]\n", encoding="utf-8")
        errors = validate_sector_workspace.validate(self.workspace)
        self.assertIn("project.json must contain an object", errors)
        self.assertIn("research-context.json must contain an object", errors)
        self.assertIn("state/assumptions.json must contain a JSON array", errors)
        self.assertTrue(any("sector-metrics.csv is missing required headers" in error for error in errors))
        self.assertTrue(any("company-comps.csv is missing required headers" in error for error in errors))

    def test_cli_entry_points_cover_success_and_error_paths(self) -> None:
        cli_workspace = self.root / "cli"
        with patch.object(
            init_sector_workspace.sys,
            "argv",
            [
                "init_sector_workspace.py",
                "--workspace",
                str(cli_workspace),
                "--sector-name",
                "Energy",
            ],
        ):
            self.assertEqual(init_sector_workspace.main(), 0)

        with patch.object(
            init_sector_workspace.sys,
            "argv",
            [
                "init_sector_workspace.py",
                "--workspace",
                str(cli_workspace),
                "--sector-name",
                "Energy",
            ],
        ):
            self.assertEqual(init_sector_workspace.main(), 1)

        with patch.object(validate_sector_workspace.sys, "argv", ["validate_sector_workspace.py", str(cli_workspace)]):
            self.assertEqual(validate_sector_workspace.main(), 0)

        with patch.object(
            validate_sector_workspace.sys,
            "argv",
            ["validate_sector_workspace.py", str(self.root / "missing")],
        ):
            self.assertEqual(validate_sector_workspace.main(), 1)

    def test_cli_reports_missing_workspace(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_ROOT / "validate_sector_workspace.py"), str(self.root / "missing")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("workspace directory not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
