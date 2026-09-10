from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "persistent-equity-research"
sys.path.insert(0, str(ROOT / "tools"))

from package_skill import build_archive  # noqa: E402

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover - development requirements define this dependency
    Draft202012Validator = None
    FormatChecker = None


class SkillContractTest(unittest.TestCase):
    def test_frontmatter_and_name_follow_agent_skills_contract(self) -> None:
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(content.splitlines()), 200)
        self.assertTrue(content.startswith("---\n"))
        frontmatter = content.split("---\n", 2)[1]
        parsed = yaml.safe_load(frontmatter)
        self.assertEqual(
            set(parsed),
            {"name", "description", "license", "compatibility", "metadata"},
        )
        name = re.search(r"(?m)^name:\s*(\S+)\s*$", frontmatter).group(1)
        description = re.search(r"(?m)^description:\s*(.+)$", frontmatter).group(1)
        self.assertEqual(name, SKILL.name)
        self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(name), 64)
        self.assertLessEqual(len(description), 1024)
        self.assertIn("Use for", description)
        self.assertLessEqual(len(parsed["compatibility"]), 500)
        self.assertEqual(parsed["license"], "GPL-3.0-only")
        self.assertTrue(all(isinstance(value, str) for value in parsed["metadata"].values()))

    def test_all_local_markdown_links_resolve(self) -> None:
        missing = []
        markdown_files = [
            ROOT / "README.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "SECURITY.md",
            *sorted((ROOT / "docs").glob("*.md")),
            SKILL / "SKILL.md",
            *sorted((SKILL / "references").glob("*.md")),
        ]
        for markdown in markdown_files:
            content = markdown.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", content):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (markdown.parent / target.split("#", 1)[0]).resolve()
                if not resolved.exists():
                    missing.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_canonical_instructions_have_no_legacy_paths_or_vendor_routing(self) -> None:
        checked = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]
        content = "\n".join(path.read_text(encoding="utf-8") for path in checked)
        for forbidden in (
            "project.yaml",
            "research-context.yaml",
            "assumptions.yaml",
            "dependency-graph.yaml",
            "registry.csv",
            "agentic Work",
            "highest-cost reasoning",
        ):
            self.assertNotIn(forbidden, content)

    def test_version_metadata_is_synchronized(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertIn(f'version: "{version}"', skill)
        self.assertEqual(plugin["version"], version)
        self.assertEqual(marketplace["plugins"][0]["version"], version)
        self.assertIn(f"## [{version}]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_packaged_license_matches_repository_license(self) -> None:
        self.assertEqual((SKILL / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_platform_adapters_point_to_the_canonical_skill_without_dependencies(self) -> None:
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        openai = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8"))
        self.assertEqual(plugin["skills"], "./skills/")
        self.assertEqual(plugin["license"], "GPL-3.0-only")
        self.assertEqual(marketplace["plugins"][0]["source"], "./")
        self.assertFalse({"mcpServers", "hooks", "commands"} & set(plugin))
        self.assertEqual(set(openai), {"interface"})
        self.assertEqual(
            set(openai["interface"]),
            {"display_name", "short_description", "default_prompt"},
        )
        self.assertIn("$persistent-equity-research", openai["interface"]["default_prompt"])

    def test_schemas_are_valid_draft_2020_12_documents(self) -> None:
        if Draft202012Validator is None:
            self.fail("jsonschema is required to run the development test suite")
        schemas = {}
        for path in sorted((SKILL / "schemas").glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            schemas[path.name] = schema
        template = SKILL / "assets" / "company-workspace"
        documents = {
            "project.schema.json": template / "project.json",
            "research-context.schema.json": template / "state" / "research-context.json",
            "assumptions.schema.json": template / "state" / "assumptions.json",
            "contradictions.schema.json": template / "state" / "contradictions.json",
            "dependency-graph.schema.json": template / "state" / "dependency-graph.json",
        }
        for schema_name, document_path in documents.items():
            document = json.loads(document_path.read_text(encoding="utf-8"))
            errors = list(Draft202012Validator(
                schemas[schema_name],
                format_checker=FormatChecker(),
            ).iter_errors(document))
            if schema_name in ("project.schema.json", "research-context.schema.json"):
                self.assertTrue(errors, "uninitialized templates should require identity and dates")
            else:
                self.assertEqual(errors, [])


class PackageTest(unittest.TestCase):
    def test_archive_output_must_be_outside_skill(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the canonical skill"):
            build_archive(SKILL / "nested-release.zip")

    def test_archive_is_reproducible_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            report = build_archive(first)
            build_archive(second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            self.assertLess(report["uncompressed_bytes"], 30 * 1024 * 1024)
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertTrue(names)
                self.assertTrue(all(name.startswith("persistent-equity-research/") for name in names))
                self.assertEqual(len({name.split("/", 1)[0] for name in names}), 1)
                self.assertIn("persistent-equity-research/SKILL.md", names)
                self.assertFalse(any(".." in Path(name).parts for name in names))
                self.assertFalse(any({"companies", "research", "research-workspaces"} & set(Path(name).parts) for name in names))
                for info in archive.infolist():
                    mode = (info.external_attr >> 16) & 0o170000
                    self.assertNotEqual(mode, 0o120000)


if __name__ == "__main__":
    unittest.main()
