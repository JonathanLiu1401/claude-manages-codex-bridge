# claude-manages-codex-bridge

A small Python MCP server (`visible_agent_bridge.py`) that powers the **visible-agent harness** for the
`claude-manages-codex` workflow: Claude Code acts as manager/architect/reviewer while OpenAI Codex does
the implementation work. The bridge launches Codex (and Claude advisor) sessions in their own visible
PowerShell windows so you can watch prompts, streamed events, agent messages, commands, token usage, and
diffs live, while also persisting logs under `.claude-codex/runs/<run-id>/`.

## Tools exposed

- `start_visible_codex_worker` — launch `codex exec --json` in a visible window with saved logs.
- `start_visible_first_mate_codex_pool` — launch a visible Codex root coordinator that spawns/manages subagents.
- `start_visible_claude_advisor` — launch a visible Claude Code advisor run.
- `get_visible_run_status` / `list_visible_runs` — read status + recent log lines from a run directory.

## Fixes in this snapshot

This copy includes two fixes over the original bridge, found while testing against Codex CLI **v0.142.2**:

1. **Removed-flag crash.** The launcher passed `codex exec ... --ask-for-approval <policy>`, a flag that
   newer Codex CLIs no longer accept — the visible worker exited immediately with code 2. Replaced with the
   config-override form `-c approval_policy="<policy>"`, which is accepted and equivalent.

2. **UTF-8 BOM read crash.** PowerShell's `Set-Content -Encoding UTF8` writes `status.json` with a BOM
   (Windows PowerShell 5.1 behavior). The Python status readers used `encoding="utf-8"` and threw
   `Unexpected UTF-8 BOM`. The four `status.json` / `metadata.json` reads in `get_visible_run_status` and
   `list_visible_runs` now use `encoding="utf-8-sig"`, which tolerates a BOM or its absence.

## Usage

Wire it into an MCP client (e.g. Claude Code) by pointing at the script:

```json
{
  "mcpServers": {
    "agent-visibility": {
      "command": "python",
      "args": ["path/to/visible_agent_bridge.py"]
    }
  }
}
```

Requires the `codex` CLI on `PATH` (for the Codex tools) and `claude` (for the advisor tool).

> Note: the MCP server loads the script at startup, so after editing it you must reload/restart the MCP
> client for changes to take effect.
