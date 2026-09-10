# Behavioral Evals

The corpus in `evals.json` is vendor-neutral. Live runs are opt-in because they may consume paid model capacity and depend on local authentication.

The runner invokes each case twice in separate temporary directories: once with an explicit path to the skill and once as a baseline. It captures output, exit status, duration, and generated file paths; assertions remain human-reviewed because research quality is not reducible to wording checks.

Examples:

```bash
python3 tools/run_live_evals.py --host codex --model MODEL \
  --capability filesystem --capability web --command \
  codex exec --skip-git-repo-check --sandbox workspace-write -C '{workspace}' '{prompt}'

python3 tools/run_live_evals.py --host claude-code --model MODEL \
  --capability filesystem --capability web --command \
  claude -p --plugin-dir '{repository}' '{prompt}'
```

Adapt the command to the installed CLI version. Available placeholders are `{prompt}`, `{workspace}`, `{skill}`, and `{repository}`. Results are written beneath the ignored `evals/results/` directory. Review the assertions manually and record the agent, model, date, and capabilities in release notes.
