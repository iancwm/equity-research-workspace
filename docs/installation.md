# Installation and Distribution

Every surface uses the same directory: `skills/persistent-equity-research/`. Do not copy individual files out of it.

## Claude Code

For one project, copy or link the canonical directory to:

```text
.claude/skills/persistent-equity-research/
```

For marketplace installation, add this repository and install its plugin:

```text
/plugin marketplace add iancwm/equity-research-workspace
/plugin install equity-research@equity-research-skills
```

Plugin installations use the namespaced command `/equity-research:persistent-equity-research`; normal task matching can also invoke it automatically.

## Codex

Copy or link the canonical directory into the Codex skills directory:

```text
$CODEX_HOME/skills/persistent-equity-research/
```

When `CODEX_HOME` is unset, use `~/.codex/skills/persistent-equity-research/`. The included `agents/openai.yaml` adds optional Codex UI metadata without adding tool dependencies or changing automatic invocation.

## Hosted Skills APIs

Run `python3 tools/package_skill.py` and upload `dist/persistent-equity-research-2.0.0.zip` as a custom skill. The archive contains one enclosing directory whose name matches the `SKILL.md` name.

- [Claude Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- [OpenAI skill creation API](https://developers.openai.com/api/reference/python/resources/skills/methods/create)

Hosted containers need writable storage to persist a workspace beyond one response. If the host does not retain files, export the workspace as an artifact and restore it in the next session.

## Other Agent Skills clients

Install the canonical directory in the location that the client scans for Agent Skills. A compatible client must expose the `name` and `description`, load `SKILL.md` when relevant, resolve bundled relative paths from the skill root, and provide Python 3.9+ when it expects to run the workspace scripts.

Web access is optional for using supplied evidence and required for genuinely fresh research. No connector, market-data vendor, MCP server, or model family is assumed.
