from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "skills" / "persistent-equity-research" / "scripts"))

from run_live_evals import _prepare_initialized_workspace, _safe_label, build_parser  # noqa: E402
from workspace_lib import validate_workspace  # noqa: E402


class EvalCorpusTest(unittest.TestCase):
    def test_live_runner_requires_host_and_model_metadata(self) -> None:
        args = build_parser().parse_args([
            "--host", "codex",
            "--model", "synthetic-model",
            "--capability", "filesystem",
            "--command", "agent", "{prompt}",
        ])
        self.assertEqual(args.host, "codex")
        self.assertEqual(args.model, "synthetic-model")
        self.assertEqual(args.capability, ["filesystem"])
        self.assertEqual(_safe_label("openai/gpt:test"), "openai-gpt-test")
        with self.assertRaises(ValueError):
            _safe_label("../../")

    def test_corpus_has_required_vendor_neutral_cases(self) -> None:
        corpus = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        names = {case["name"] for case in corpus["evals"]}
        self.assertEqual(
            names,
            {
                "quick-view-without-persistence",
                "full-initiation-external-workspace",
                "earnings-update-selective-recompute",
                "scenario-preserves-base",
                "publish-from-state",
                "negative-narrow-fact",
            },
        )
        for case in corpus["evals"]:
            self.assertTrue(case["prompt"])
            self.assertTrue(case["assertions"])

    def test_initialized_eval_workspace_validates_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            _prepare_initialized_workspace(workspace)
            result = validate_workspace(workspace, strict=True)
            self.assertTrue(result.valid, result.errors)


if __name__ == "__main__":
    unittest.main()
