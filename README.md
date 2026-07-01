# claude-manages-codex-bridge

A small Python MCP server (`visible_agent_bridge.py`) that powers the **visible-agent harness** for the
`claude-manages-codex` workflow: Claude Code's active manager model acts as captain/executive architect/QA tech lead/reviewer while OpenAI Codex
does the implementation work. The bridge launches Codex and Claude advisor sessions in visible PowerShell
windows so you can watch prompts, streamed events, agent messages, commands, token usage, and diffs live,
while also persisting logs under `.claude-codex/runs/<run-id>/`.

## Tools exposed

- `start_visible_codex_worker` - launch `codex exec --json` in a visible window with saved logs.
- `start_visible_haiku_composed_codex_worker` - let Claude pass a compact captain brief, have Claude Haiku expand the full Codex prompt, then launch Codex.
- `start_visible_first_mate_codex_pool` - launch a visible Codex root coordinator that spawns/manages subagents.
- `steer_visible_codex_run` - queue a captain steering note into an active visible Codex run, or launch a visible resume run on the same thread if the window already closed.
- `start_visible_claude_advisor` - launch a visible Claude Code advisor run.
- `get_visible_run_status` / `list_visible_runs` - read status and recent log lines from a run directory.

## Current bridge behavior

- Codex workers are forced to `gpt-5.5`, `xhigh` reasoning, and `service_tier=fast`.
- Claude advisor calls use a central model policy: `fable` / `high` through July 7, 2026, then `opus` / `high`. Override with `CLAUDE_MANAGES_CODEX_ADVISOR_MODEL`.
- The Claude manager model should not write implementation code by default; it writes architecture, constraints, acceptance criteria, steering notes, and review findings.
- Long Codex delegation prompts should be written by the Haiku prompt composer, not by the manager model.
- Visible Codex workers run with full process/tool access so Python-backed skills, `read-past-sessions`, SSH, test runners, and external CLIs work. The requested `sandbox` is treated as permission intent: `read-only` means no edits, not a crippled process sandbox.
- Codex and Claude visible runs record resumable ids (`thread_id` for Codex, `session_id` for Claude).
- Claude can steer visible Codex runs with `steer_visible_codex_run`; active windows consume queued steering on the same Codex thread, then close after a short idle window if no steering arrives.
- Visible Codex workers set `NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` so Playwright MCP and Node-based Playwright tests can run from delegated Codex sessions.

## Firstmate skill

This repo bundles a Codex-facing Firstmate skill at [`codex-skills/firstmate/SKILL.md`](codex-skills/firstmate/SKILL.md).
It adapts the FirstMate pattern so **Claude Code is the captain**, **Codex is the first mate**, and the first mate
coordinates an ensemble of Codex agents for scouting, implementation, verification, and review.

Install/sync it locally to:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills\firstmate" | Out-Null
Copy-Item .\codex-skills\firstmate\SKILL.md "$HOME\.codex\skills\firstmate\SKILL.md" -Force
```

The visible first-mate runner also embeds the same role contract, so the hierarchy still works before Codex
refreshes its skill index.

## Codex agent profiles

Custom Codex agents live under [`codex-agents/`](codex-agents/):

- `claude-explorer` - no-edit codebase scouting with Python/tool access.
- `claude-implementer` - scoped implementation after Claude grants write permission.
- `claude-reviewer` - no-edit diff and regression review.
- `claude-debugger` - full-tool SSH, device, network, serial, and command-heavy debugging when Claude explicitly allows it.

Install/sync them locally to:

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\agents" | Out-Null
Copy-Item .\codex-agents\claude-*.toml "$HOME\.codex\agents\" -Force
```

## Bundled plugin

The Claude Code plugin that drives this bridge lives under [`plugin/`](plugin/):

- `plugin/.claude-plugin/plugin.json` - plugin manifest.
- `plugin/.mcp.json` - registers the `codex-worker` (Codex MCP) and `agent-visibility` (this script) servers.
- `plugin/skills/claude-manages-codex/SKILL.md` - the `claude-manages-codex` skill: Claude as executive captain/architect/reviewer, Codex as first mate and worker harness. Includes the routing mandate that sends parallel-agent fan-out and implementation work through Codex to preserve Claude tokens.

The Codex-side advisor plugin lives under [`codex-plugin/`](codex-plugin/):

- `codex-plugin/.codex-plugin/plugin.json` - Codex plugin manifest.
- `codex-plugin/.mcp.json` - registers the visible Claude advisor bridge for Codex.
- `codex-plugin/skills/codex-consults-claude/SKILL.md` - broader Codex-to-Claude bridge contract.
- `codex-plugin/skills/claude-advisor/SKILL.md` - lightweight advisor flow for plan checks, stuck/confused states, and review.

Install or refresh it locally through your personal Codex plugin marketplace, then start a new Codex session:

```powershell
codex plugin add codex-consults-claude@personal
```

## Official OpenAI Codex plugin companion

This bridge is designed to cooperate with OpenAI's official Claude Code plugin:
[`openai/codex-plugin-cc`](https://github.com/openai/codex-plugin-cc).

Use the official plugin for stable `/codex:*` workflows:

- `/codex:setup`
- `/codex:review`
- `/codex:adversarial-review`
- `/codex:rescue`
- `/codex:transfer`
- `/codex:status`
- `/codex:result`
- `/codex:cancel`

Install it in Claude Code with:

```bash
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

Use this bridge's `start_visible_first_mate_codex_pool` when you want the observable Claude-as-captain /
Codex-as-first-mate hierarchy over multiple Codex agents. Use the official `/codex:rescue` command for single
delegated rescue tasks and `/codex:review` or `/codex:adversarial-review` for standard read-only review.

## Fixes in this snapshot

This copy includes fixes over the original bridge, found while testing against Codex CLI **v0.142.2**:

1. **Removed-flag crash.** The launcher passed `codex exec ... --ask-for-approval <policy>`, a flag that
   newer Codex CLIs no longer accept. Replaced it with the config-override form
   `-c approval_policy="<policy>"`, which is accepted and equivalent.

2. **UTF-8 BOM read crash.** PowerShell's `Set-Content -Encoding UTF8` writes `status.json` with a BOM
   in Windows PowerShell 5.1. The status readers now use `encoding="utf-8-sig"` for `status.json` and
   `metadata.json`, which tolerates a BOM or its absence.

3. **UTF-8 mojibake / UTF-16 log corruption.** The detached PowerShell inherited the system OEM code page,
   and `Tee-Object` wrote `display.log` as UTF-16LE. Both runners now force UTF-8 console encoding before
   launching the child and tee through a `Write-Raw` helper (`Add-Content -Encoding UTF8`).

4. **Leaked agent runtimes.** Codex left orphaned `codex.exe`, `node.exe`, and `codex-windows-sandbox-setup.exe`
   processes alive after each run. Each run script now reaps its own descendant process tree on completion via
   `Stop-RunDescendants`, scoped strictly to descendants of that run's own PowerShell `$PID`. The Python server
   also registers an `atexit` hook that `taskkill /T /F`s every visible-run window it launched at session end.

5. **Read-only sandbox broke Python, skills, and SSH.** Visible Codex workers now get full process/tool access
   while the prompt carries a separate permission contract. A `read-only` request becomes no-edit intent, so
   Codex can still run Python, `read-past-sessions`, SSH, and repo tooling without permission to mutate files.

6. **Expensive manager-model prompt writing.** Non-trivial Codex delegation can now go through
   `start_visible_haiku_composed_codex_worker`: Claude emits a compact captain brief, Haiku/low expands the full
   worker prompt in safe mode, and Codex executes the composed prompt.

7. **Session context and resume.** Visible workers inject a session-context bootstrap and can resume prior Codex
   threads or Claude advisor sessions by id.

8. **Claude could not steer visible Codex mid-session.** Visible Codex runs now create `steer_queue/` and
   `steer_done/` directories. Claude can call `steer_visible_codex_run` to queue captain instructions into an
   active run; the same visible window consumes them on the recorded Codex thread after the current turn. If the
   window already closed, the tool starts a visible `codex resume` run against the same `thread_id`. Steering can
   also carry an updated `sandbox` permission intent when Claude moves a run from scouting to scoped writes.

9. **Visible launcher stayed stuck at `created`.** The launcher used PowerShell `-NoExit`, which could leave a
   visible shell alive while the run directory stayed locked or never advanced cleanly from the caller's view. It
   now launches with `-NoProfile` and lets the script's own short close delay control visibility and cleanup.

## E2E verification

Run the full bridge E2E from the repo root:

```powershell
python .\tests\e2e_visible_bridge.py
```

The suite launches real visible runs for queued steering, closed-run resume steering, interrupt steering,
Haiku-composed Codex, first-mate Codex, and the budget-capped Claude advisor path.

## Usage

Wire it into an MCP client, such as Claude Code, by pointing at the script:

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

Requires the `codex` CLI on `PATH` for Codex tools and `claude` for the advisor tool.

> Note: the MCP server loads the script at startup, so after editing it you must reload/restart the MCP
> client for changes to take effect.

If you use Claude Code's permission allowlist, include the Haiku-composed worker tool alongside the older
visible-agent tools:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_codex_worker",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_haiku_composed_codex_worker",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_first_mate_codex_pool",
      "mcp__plugin_claude-manages-codex_agent-visibility__steer_visible_codex_run",
      "mcp__plugin_claude-manages-codex_agent-visibility__get_visible_run_status",
      "mcp__plugin_claude-manages-codex_agent-visibility__list_visible_runs"
    ]
  }
}
```
