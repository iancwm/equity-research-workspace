# Contributing

## Authoring principles

- Keep one canonical skill under `skills/persistent-equity-research/`; do not create vendor copies.
- Keep triggering language in the `SKILL.md` description and conditional detail in directly linked references.
- Prefer capability language over product, model, or reasoning-level assumptions.
- Add instructions only when they change decisions or protect a real invariant.
- Treat schemas and command-line behavior as public interfaces. Breaking changes require a major version.
- Keep runtime scripts compatible with Python 3.9+ and the standard library.

## Development checks

Install the migration-only development dependency and run:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 tools/package_skill.py
```

Tests must cover observable behavior rather than generated wording. Any schema change needs valid and invalid fixtures. Any workflow change needs a matching eval assertion or a short explanation of why behavior is unaffected.

## Behavioral evals

`evals/evals.json` is the vendor-neutral corpus. Live runs are optional because they consume model capacity and may require credentials. Run both with-skill and baseline cases in temporary workspaces; record the agent, model, date, and available capabilities. Never commit credentials, proprietary source documents, or sensitive generated research.

## Releases

1. Update `VERSION`, `SKILL.md` metadata, `.claude-plugin/plugin.json`, marketplace metadata, and `CHANGELOG.md`.
2. Run all offline tests and build the archive twice to confirm reproducibility.
3. Smoke-test the archive in Claude Code and Codex.
4. Upload it once to each supported hosted Skills API, or document why that smoke test was skipped.
5. Tag the commit as `v<version>` only after the preceding checks pass.
