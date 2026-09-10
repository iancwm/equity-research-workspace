# Persistent Equity Research

A portable Agent Skill for building and maintaining evidence-backed institutional equity research. It preserves sources, atomic facts, assumptions, contradictions, analytical dependencies, and editable publications so an update can recompute what changed instead of restarting the research.

The repository contains one canonical skill package at `skills/persistent-equity-research/`. Claude, Codex, hosted Skills APIs, and other [Agent Skills](https://agentskills.io/specification) clients consume that same package.

## Five-minute start

From a repository checkout:

```bash
python3 skills/persistent-equity-research/scripts/init_workspace.py \
  --workspace research/ACME \
  --ticker ACME \
  --company-name "Acme Corporation"

python3 skills/persistent-equity-research/scripts/validate_workspace.py research/ACME
```

Install or upload the skill using [the platform instructions](docs/installation.md), then ask the agent to use `persistent-equity-research` with the workspace path. Generated research belongs in that external workspace, never inside the installed skill.

## What it supports

- fast debate maps and screening views;
- full initiation of coverage;
- earnings, guidance, filing, news, and regulatory updates;
- selective recomputation after evidence or assumptions change;
- valuation and bear/base/bull scenarios;
- dashboards, update notes, and initiation reports;
- structural validation and a separate analytical QA pass.

## Project map

- [Architecture](docs/architecture.md) explains the package, workspace, and research layers.
- [Workspace v2](docs/workspace-v2.md) defines the persisted data contract and v1 migration.
- [Installation](docs/installation.md) covers Claude, Codex, hosted APIs, and generic clients.
- [Contributing](CONTRIBUTING.md) covers authoring, tests, evals, and releases.
- [Behavioral evals](evals/README.md) explains optional live comparison runs and result review.
- [Security](SECURITY.md) describes the trust boundary for skills and research sources.
- [Changelog](CHANGELOG.md) tracks the portable contract, and the [2.0.0 release verification](docs/releases/2.0.0.md) records external smoke-test status.

Build the portable release archive with:

```bash
python3 tools/package_skill.py
```

The runtime skill uses only Python 3.9+ standard-library modules. PyYAML is required only by the optional v1 migration utility and its tests.
