# Persistent Equity Research

A portable set of Agent Skills for evidence-backed institutional equity research. The skills preserve sources, atomic facts, assumptions, contradictions, analytical dependencies, and editable publications so an update can recompute what changed instead of restarting the research.

The repository contains three canonical skill packages:

- **`skills/persistent-equity-research/`** — Interactive company research: build and refine workspaces, run analyses, publish updates, and manage revisions. Use when an analyst guides the research process.
- **`skills/sector-primer/`** — Interactive sector education: structure industry dynamics, peer benchmarking, and sector analytics in a reusable workspace. Use for sector-wide coverage and comparable research.
- **`skills/analyst-agent/`** — Automated report generation: orchestrate initiation of coverage, earnings updates, sector reports, quarterly outlooks, and trading reports from evidence through Claude tool-use analysis into persisted workspace state. Use for programmatic, unattended report runs.

Claude, Codex, hosted Skills APIs, and other [Agent Skills](https://agentskills.io/specification) clients can consume any package.

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

### Interactive research and sector work (persistent-equity-research, sector-primer)

- fast debate maps and screening views;
- full initiation of coverage;
- earnings, guidance, filing, news, and regulatory updates;
- selective recomputation after evidence or assumptions change;
- valuation and bear/base/bull scenarios;
- dashboards, update notes, and initiation reports;
- sector primers covering industry dynamics, sector analytics, and comparable companies;
- structural validation and a separate analytical QA pass.

### Programmatic report generation (analyst-agent)

- automated initiation of coverage with Claude-driven research workflow;
- earnings updates that revise assumptions and recompute valuation after quarterly prints;
- sector reports with peer benchmarking and value-chain analysis;
- quarterly outlooks with macro scenarios and catalyst calendars;
- trading reports with catalyst-driven theses and entry/target/stop analysis;
- deterministic evidence-to-workspace-to-report pipeline with full traceability and gap visibility.

## Getting started with sector-primer

Initialize a dedicated workspace and validate it before publication:

```bash
python3 skills/sector-primer/scripts/init_sector_workspace.py \
  --workspace research/semiconductors \
  --sector-name "Semiconductors" \
  --geography "Global"

python3 skills/sector-primer/scripts/validate_sector_workspace.py research/semiconductors
```

Read [the sector-primer skill](skills/sector-primer/SKILL.md) for its workflow and data contract.

## Getting started with analyst-agent

Initialize a company workspace (using persistent-equity-research), then run an automated analysis:

```python
from skills.analyst_agent.orchestrator import AnalystAgent

agent = AnalystAgent(workspace_root="/path/to/ACME")
result = agent.initiate_coverage(ticker="ACME", company_name="Acme Corporation")
print(result["status"], result["report_path"])
```

Read [the analyst-agent skill](skills/analyst-agent/SKILL.md) for its workflow, report types, and API.

## Documentation

### Skills and workflows

- [Persistent Equity Research SKILL.md](skills/persistent-equity-research/SKILL.md) — Interactive company research workflow.
- [Sector Primer SKILL.md](skills/sector-primer/SKILL.md) — Interactive sector education workflow.
- [Analyst Agent SKILL.md](skills/analyst-agent/SKILL.md) — Automated report generation with five report types.

### System documentation

- [Architecture](docs/architecture.md) explains the package, workspace, and research layers.
- [Workspace v2](docs/workspace-v2.md) defines the persisted data contract and v1 migration.
- [Research state vs. report](docs/state-vs-report.md) explains the distinction between durable research and publications.
- [Installation](docs/installation.md) covers Claude, Codex, hosted APIs, and generic clients.
- [Contributing](CONTRIBUTING.md) covers authoring, tests, evals, and releases.
- [Behavioral evals](evals/README.md) explains optional live comparison runs and result review.
- [Security](SECURITY.md) describes the trust boundary for skills and research sources.
- [Changelog](CHANGELOG.md) tracks the portable contract and release history.

## Building and packaging

Build the portable persistent-equity-research release archive with:

```bash
python3 tools/package_skill.py
```

The runtime skills use only Python 3.9+ standard-library modules. PyYAML is required only by the optional v1 migration utility and its tests. Live Claude runs require the `anthropic` SDK and an API key.
