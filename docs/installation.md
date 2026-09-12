# Installation and Distribution

The repository contains two standalone skill directories, `skills/persistent-equity-research/` and `skills/sector-primer/`. Install the skill that matches the task, and do not copy individual files out of it.

## Claude Code

For one project, copy or link the canonical directory to:

```text
.claude/skills/persistent-equity-research/
.claude/skills/sector-primer/
```

For marketplace installation, add this repository and install its plugin:

```text
/plugin marketplace add iancwm/equity-research-workspace
/plugin install equity-research@equity-research-skills
```

Plugin installations use the namespaced commands `/equity-research:persistent-equity-research` and `/equity-research:sector-primer`; normal task matching can also invoke them automatically.

## Codex

Copy or link the canonical directory into the Codex skills directory:

```text
$CODEX_HOME/skills/persistent-equity-research/
$CODEX_HOME/skills/sector-primer/
```

When `CODEX_HOME` is unset, use `~/.codex/skills/<skill-name>/`. Each skill's included `agents/openai.yaml` adds optional Codex UI metadata without adding tool dependencies or changing automatic invocation.

## Hosted Skills APIs

Run `python3 tools/package_skill.py` and upload the resulting persistent-equity-research archive as a custom skill. The archive contains one enclosing directory whose name matches the `SKILL.md` name. For the sector primer, upload the standalone `skills/sector-primer/` directory using the hosted platform's custom-skill packaging format.

- [Claude Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- [OpenAI skill creation API](https://developers.openai.com/api/reference/python/resources/skills/methods/create)

Hosted containers need writable storage to persist a workspace beyond one response. If the host does not retain files, export the workspace as an artifact and restore it in the next session.

## Other Agent Skills clients

Install the canonical directory in the location that the client scans for Agent Skills. A compatible client must expose the `name` and `description`, load `SKILL.md` when relevant, resolve bundled relative paths from the skill root, and provide Python 3.9+ when it expects to run the workspace scripts.

Web access is optional for using supplied evidence and required for genuinely fresh research. No connector, market-data vendor, MCP server, or model family is assumed.
