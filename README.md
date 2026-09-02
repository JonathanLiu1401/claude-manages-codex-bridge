# Multi-Agentic Harness

> Internal id / repo / MCP-tool prefix / install dir remain **`claude-manages-codex`** for tool-name,
> permission-allowlist, and install compatibility. The skill/project is **branded "Multi-Agentic Harness"**
> (renamed 2026-07-15) to reflect that it now drives several worker backends, not just Codex. A full
> id-level rename (MCP tool names, install directory, GitHub repo) is a separate breaking change.

## Subagent Locality (owner rule 2026-08-15 - takes precedence over any model-routing guidance)

**Spawn subagents of the harness you are already running in.**

- A **Claude agent** (Claude Code, any Claude model) delegates through the normal Claude subagent path: the `Agent` tool with a built-in `subagent_type` (`general-purpose`, `Explore`, `Plan`, `claude`, ...). It must **NOT** shell out to `cursor-agent`, `grok`, or Codex to do its delegating.
- A session inside the Cursor `cursor-agent` TUI spawns cursor-agent subagents, choosing the worker model per the cursor routing guidance.
- A grok (Grok Build CLI) session spawns grok's own native subagents, default grok model.
- **Only exception:** an explicit user instruction naming a different harness. "Delegate this" on its own means "spawn a subagent of your own kind," not "launch a different CLI."

For a Claude captain this means: `Agent`-tool Claude subagents are the default, and the visible terminal-window workers (`start_visible_*`) documented throughout this README are the **explicit-request** path, used when the user asks for the multi-agentic harness by name or for visible windows. Delegation stays ONE level deep, and every worker result is treated as unverified until the captain re-runs the acceptance test.

## Provider models in the Claude Code TUI: clx / clg (2026-09-02)

`clx` and `clg` run Grok and Google Antigravity models inside the Claude Code TUI
through a stock local CLIProxyAPI gateway on `127.0.0.1:8317`, with isolated
config dirs (`~/.claude-clx`, `~/.claude-clg`). Plain `claude` and `~/.claude`
are untouched. Two commands because the context window is process-wide: clx is
500k for grok, clg is 1M for gemini.

clx and clg are not cross-compatible. clx uses native Agent `grok` and the
Antigravity CLI for agy work. clg uses native Agent `agy-gemini-3-8-flash` and
the Grok Build CLI for grok work. A plain Claude captain never uses those
native types: grok/agy work from `~/.claude` is `start_visible_grok_worker` /
`start_visible_agy_worker`. Cursor was attempted and rejected (no working tool
bridge); use `cursor-agent`'s own TUI for Cursor work.

**Full documentation, including every measured gotcha:
[`docs/setup/clx-clg-gateway.md`](docs/setup/clx-clg-gateway.md).**

## What this is

A small Python MCP server (`visible_agent_bridge.py`) that powers a **multi-agent worker harness**: Claude
Code's active manager model acts as captain / executive architect / QA tech lead / reviewer while a
**worker backend** does the implementation work in a visible PowerShell window (the `start_visible_*`
tools), with logs persisted under `.claude-codex/runs/<run-id>/` and structured captain steering,
completion watchers, and captain-help mailboxes.

**Live running code vs. this repo:** the authoritative running bridge is `C:/Users/jonny/.agent-bridge/visible_agent_bridge.py` + `claude_worker_runner.py` (NOT a git-tracked directory). This git repo is the source/reference; changes here must be synced into `~/.agent-bridge/` to take effect. The installed skill lives at the double-nested `~/.claude/skills/claude-manages-codex/skills/claude-manages-codex/SKILL.md`.

**Worker backends (2026-07-15, visible-window path restored 2026-08-15, cursor-agent wired 2026-08-26):** for a Claude captain the default spawn path is a **Claude `Agent`-tool subagent** with a
built-in `subagent_type`. When the harness is explicitly requested, the preferred visible worker is
**cursor-agent** at `cursor-grok-4.6-xhigh-fast` (`start_visible_cursor_worker`,
`start_visible_haiku_composed_cursor_worker`, `start_visible_first_mate_cursor_pool`,
`steer_visible_cursor_run`). The **grok CLI** remains the path for Parallel Competition Mode and the
Mandatory Parallel Work-Checker. Native Agent-tool subagent types are **profile-dependent** as of 2026-09-02: in a
plain Claude session they do not resolve, but in a session started by the `clx` (grok, 500k) or `clg`
(gemini/agy, 1M) launcher the native `grok` / `agy-gemini-3-8-flash` subagents work and are the
preferred delegation path there - they run inside Claude Code's own agentic runtime with no detached
console. The local CLIProxyAPI gateway those depend on was decommissioned on 2026-08-15 and
deliberately reinstated as a stock install; see `docs/setup/clx-clg-gateway.md`. The older types
`agy-gemini-3-1-pro` / `agy-gemini-3-7-flash` are still gone - `agy-gemini-3-8-flash` replaces them.
**Google Antigravity (agy)** is reached through the legacy visible-terminal `start_visible_agy_worker`,
which drives the `agy` CLI under its own login and **separate quota** (not the real Claude/Anthropic
subscription); **Codex is disabled until further notice** (its ChatGPT login is revoked, the code is left
intact but not used). Always `check_worker_backends` before delegating. Much of the older prose below is
Codex-centric because Codex was the original backend: read "Codex" as "the worker backend."

## Tools exposed

> ⚠️ **Codex is DISABLED (owner 2026-07-15, ChatGPT login revoked).** The Codex worker tools below remain documented for a possible future revival only - do not route to Codex. Preferred visible worker today is cursor-agent through `start_visible_cursor_worker` (model `cursor-grok-4.6-xhigh-fast`). Use `start_visible_grok_worker` when you need grok-CLI Competition/Work-Checker extras.

- `start_visible_codex_worker` - launch the default single-worker `codex exec --json` path from a final prompt in a visible window with saved structured logs.
- `start_visible_haiku_composed_codex_worker` - let Claude pass a compact captain brief, have Claude Haiku expand the full Codex prompt, then launch the default non-interactive visible CLI worker.
- `start_visible_first_mate_codex_pool` - launch the default non-interactive visible CLI root coordinator for fan-out with structured logs.
- `start_interactive_codex_tui` (**deprecated**) - launch the real interactive Codex TUI only for an explicit user request for a hands-on terminal, while the bridge records sidecar metadata.
- `start_interactive_first_mate_codex_tui` (**deprecated**) - launch the first-mate Codex coordinator in the real interactive Codex TUI only for an explicit hands-on user request.
- `steer_visible_codex_run` - directly interrupt and steer an active visible Codex run on the same thread by default, or launch a visible resume run if the window already closed.
- `request_captain_help` - let a stuck visible Codex worker ask the same Claude captain for feedback through the run mailbox.
- `list_captain_help_requests` / `respond_to_captain_help_request` - let Claude inspect and answer worker help requests, or escalate to the user before steering the same run.
- `submit_captain_report` / `list_captain_reports` - let interactive TUI workers hand a final report back to Claude through a sidecar artifact instead of terminal-only text.
- `start_visible_claude_advisor` - launch a visible Claude Code advisor run.
- `get_visible_run_status` / `list_visible_runs` - read status and recent log lines from a run directory.

## Current bridge behavior

- Codex workers run `gpt-5.6-sol` with `service_tier=fast`. Reasoning effort is selected by Claude per task across `high` / `xhigh` / `max` / `ultra` (defaulting to the `xhigh` floor), rather than pinned to a single tier. At `ultra` effort, `gpt-5.6-sol` natively decomposes work into cooperative subagents within the captain's scope (token-heavy and preview-gated; intentionally unbudgeted - no token or spend cap).
- Claude advisor calls use a central model policy: `fable` / `high` through July 7, 2026, then `opus` / `high`. Override with `CLAUDE_MANAGES_CODEX_ADVISOR_MODEL`.
- The Claude manager model should not write implementation code by default; it writes architecture, constraints, acceptance criteria, steering notes, and review findings.
- Long Codex delegation prompts should be written by the Haiku prompt composer, not by the manager model.
- Claude-managed visible Codex work defaults to `start_visible_first_mate_codex_pool` for fan-out, `start_visible_haiku_composed_codex_worker` for compact single-worker briefs, and `start_visible_codex_worker` when the final prompt already exists.
- The default non-interactive visible CLI path supports structured JSONL logs, direct interrupt steering with `steer_visible_codex_run`, completion watchers, and captain-help mailboxes.
- Visible Codex workers run with full process/tool access so Python-backed skills, `read-past-sessions`, SSH, test runners, and external CLIs work. The requested `sandbox` is treated as permission intent: `read-only` means no edits, not a crippled process sandbox.
- Codex and Claude visible runs record resumable ids (`thread_id` for Codex, `session_id` for Claude).
- Claude steers non-interactive visible Codex runs directly with `steer_visible_codex_run` by default: an in-flight turn is interrupted and the same thread resumes immediately, while an idle JSON-worker window consumes the queue without interruption and closes after a short idle window if no steering arrives.
- If Claude interrupts an active JSON worker, the bridge sends Ctrl+C first and resumes the same Codex thread when its session file is readable; if Codex left an empty interrupted thread, the bridge launches a fresh follow-up with the saved run context and steering instruction.
- Stuck visible Codex workers can call back to the same Claude captain with `request_captain_help`; Claude answers with `respond_to_captain_help_request` or asks the user first when owner judgment is required.
- Visible Codex workers set `NODE_PATH` and `PLAYWRIGHT_BROWSERS_PATH` so Playwright MCP and Node-based Playwright tests can run from delegated Codex sessions.
- Deprecated interactive TUI runs use top-level `codex` rather than `codex exec --json`; when explicitly requested they are user-steered, default to `on-request` approvals, submit final handoff through `captain_reports/final.*`, and auto-close a few seconds after the report by sending Ctrl+C to the run's console with a scoped process-tree fallback.

## Worker backends (added 2026-07-14, visible-window path restored 2026-08-15)

Codex is the historically most-documented backend in this README, but the bridge supports these worker
backends behind the same run-dir mechanics: **Grok CLI** (`grok-4.6`, visible window, the default path and
the only one with Parallel Competition Mode + the Mandatory Parallel Work-Checker gate), **Claude Sonnet**
(in-process `Agent` tool, always available), **Antigravity/agy** (`start_visible_agy_worker`, the `agy` CLI
in a visible window on its own separate quota), **claude_worker** (`start_claude_worker` /
`steer_claude_run`, detached headless `claude -p` implemented by `claude_worker_runner.py`, now
direct-Anthropic only), and **Codex** (`gpt-5.6-sol`, disabled).
Per Subagent Locality, a Claude captain's default is a **Claude `Agent`-tool subagent**; **grok-4.6 in a
visible grok window is the preferred worker/spawn path once the harness is explicitly requested** (owner
upgraded to SuperGrok Heavy on 2026-07-15), with agy next on that ladder when grok is unavailable or
capped.

The native Agent-tool subagent types `grok`, `agy-gemini-3-1-pro`, and `agy-gemini-3-7-flash` are **gone**.
They only ever worked inside a session pointed at a local multi-provider gateway, and that gateway, its
launcher wrappers, and its per-world config dirs have been removed. `start_claude_worker` no longer reads a
gateway `proxy.json`, so its `model` argument is limited to what `api.anthropic.com` serves.

**Memory capture (claude-mem):** headless `claude_worker` runs are Claude Code processes, so claude-mem's hooks fire for them natively. The grok-CLI and agy visible-window backends are not Claude Code processes and fire no hooks (no claude-mem); their work is covered only by the parent session's own capture.

Codex is currently **DISABLED** (ChatGPT login revoked) - do not route to it. Use **Antigravity (agy)** as a fallback when grok-4.6 is exhausted/capped, or when explicitly requested - it is a documented fallback path, not last-resort-only. Always call `check_worker_backends` first to confirm a backend is usable.

### Grok backend

New tools, mirroring their Codex counterparts: `start_visible_grok_worker`,
`start_visible_haiku_composed_grok_worker`, `start_visible_first_mate_grok_pool`,
`steer_visible_grok_run`. Grok workers share the same backend-agnostic
`get_visible_run_status` / `list_visible_runs` / `submit_captain_report` / `list_captain_reports` /
`request_captain_help` / `list_captain_help_requests` / `respond_to_captain_help_request` tools Codex
uses.

- Invocation: `grok --prompt-file <prompt.md> --output-format streaming-json --cwd <cwd>
  --permission-mode bypassPermissions -m grok-4.6 [--reasoning-effort low|medium|high] [-r <sessionId>]`.
  (`-p`/`--single` and `--prompt-file` are alternative ways to supply the prompt; combining them errors
  live with `a value is required for '--single <PROMPT>'`, so the runner uses `--prompt-file` alone.)
- Effort caveat: the CLI only accepts `low`/`medium`/`high` on `--reasoning-effort`; `xhigh`/`max` are
  rejected. Grok's own config defaults to `xhigh`, which only applies when the flag is **omitted** - so
  the bridge omits it by default to reach the owner's preferred xhigh tier.
- Callback model: every Grok runner turn auto-writes `captain_reports/final.json` + `final.md` from the
  worker's answer text (Layer 1, robust, always on) regardless of whether a live MCP callback succeeds.
  A `~/.grok/config.toml` `[mcp_servers.agent-visibility]` entry (backed up, merged additively) lets a
  Grok worker also call `submit_captain_report` / `request_captain_help` live (Layer 2). The shared
  allowlist in those two tools was widened from `metadata.agent in (None, "codex")` to
  `(None, "codex", "grok", "agy")`, so Grok workers now report back live; Codex behavior
  is unchanged, and the codex-only steer gate stays codex-specific. See
  `plugin/skills/claude-manages-codex/SKILL.md`, "Worker Backends & Routing" and "Grok Worker Backend",
  for the full doctrine and the config snippet.

### Cursor agent backend (preferred visible worker, 2026-08-26)

Cursor workers run `cursor-agent` (Node CLI) in a visible console via `cursor_worker_runner.py`.
Claude must not Bash `cursor-agent -p` itself: that is the Subagent Locality exception for this
harness. Call the MCP tools instead.

New tools, mirroring grok: `start_visible_cursor_worker`,
`start_visible_haiku_composed_cursor_worker`, `start_visible_first_mate_cursor_pool`,
`steer_visible_cursor_run`. Shared status / report / help tools are backend-agnostic.

- Invocation: `node.exe <index.js> -p --output-format stream-json --trust --approve-mcps --sandbox disabled --model <id> [--mode plan] [--force] [--resume <session_id>] --workspace <cwd> -- <prompt>`.
  Stdin is not a prompt. There is no `--prompt-file`. Prompts longer than ~16k chars are written to
  `prompt.md` and the CLI is given a bootstrap that tells the worker to Read that file.
- Default model is `cursor-grok-4.6-xhigh-fast`. Effort maps to `cursor-grok-4.6-{low|medium|high|xhigh}-fast`.
  Cursor Max Mode (`~/.cursor/cli-config.json` `"maxMode": true`) is the 1M-context unlock, not a CLI flag.
  Do **not** pass `--force` together with `--mode plan` (the CLI then reports `permissionMode: default`).
- On Windows the runner sets `MSYSTEM`/`EXEPATH`/`SHELL` and prepends `Git\bin` so the Shell tool
  uses Git Bash. cursor-agent's `Mt()` returns early without `MSYSTEM`, and `bash` on PATH is the
  WSL/WindowsApps stub. Already-open worker windows keep the old env; spawn a new one after deploy.
- Session ids are UUIDs on every stream-json event. `--resume <session_id>` keeps the same id.
- Layer 1 auto-writes `captain_reports/final.json` + `final.md`. Layer 2 uses `~/.cursor/mcp.json`
  `mcpServers.agent-visibility` (created additively on first start). Allowlist includes `"cursor"`.
- Do not inject grok Parallel Competition Mode or Work-Checker into cursor prompts; those are grok-CLI flags.

### Antigravity (agy) backend

The agy backend is the `agy` CLI in a visible window, under its own Antigravity login and **separate
quota** (not the real Claude/Anthropic subscription). The native `agy-gemini-*` subagent path that used to
be preferred here is gone with the local gateway it depended on, but the visible-window agy tools are
unaffected: they invoke `agy.exe` directly and authenticate off `~/.gemini/oauth_creds.json`, never the
gateway.

Visible-terminal tools, mirroring their Codex/Grok counterparts: `start_visible_agy_worker`,
`start_visible_haiku_composed_agy_worker`, `steer_visible_agy_run` (no first-mate pool tool for this
backend). agy workers share the same backend-agnostic `get_visible_run_status` / `list_visible_runs` /
`submit_captain_report` / `list_captain_reports` / `request_captain_help` / `list_captain_help_requests` /
`respond_to_captain_help_request` tools Codex/Grok use, though nothing in the agy worker's own prompt
tells it to call them (see callback model below).

- Invocation: `agy -p "<prompt>" --model "<model>" --dangerously-skip-permissions --add-dir <cwd>`, run
  with the process `cwd` set to the target directory. agy has no `--prompt-file`, so the full prompt is
  passed inline as a single `-p` argument via PowerShell array splatting (not a `cmd.exe` command line, so
  no 8191-char shim limit - prefer the Haiku composer for very large briefs anyway).
- **Plain text, not streaming JSON**: `agy` has no `--output-format`/`--json` flag at all. The runner runs
  one blocking `agy` call per turn, redirects stdout and stderr to separate files (never merged), appends
  the turn's full unfiltered stdout to `output.txt` + `display.log`, and writes
  `captain_reports/final.md`/`final.json` from that raw stdout. stderr goes to `display.log` only, never
  into `output.txt` or the captain report.
- **Effort is baked into `--model`**, not a flag: `AGY_MODELS_BY_EFFORT = {"high": "Gemini 3.7 Flash
  (High)", "medium": "Gemini 3.7 Flash (Medium)", "low": "Gemini 3.7 Flash (Low)"}`,
  `AGY_DEFAULT_MODEL = "Gemini 3.7 Flash (High)"`. `start_visible_agy_worker`'s `reasoning_effort`
  parameter (default `"high"`) selects the model via `_agy_model_for_effort`; anything unrecognized falls
  back to the default "high" model.
- **No session id, `--continue` is cwd-scoped, not thread-scoped**: agy never prints a session id on a
  plain-text turn. `--conversation <id>` exists in `agy --help` but is unusable without a way to learn
  `<id>`, so all resume/steer in this backend uses `--continue` (resumes the MOST RECENT conversation for
  the working directory, best-effort, not a specific tracked thread). Verified live: a `steer_visible_agy_run`
  call on a fully closed run correctly recalled context from the original run's first turn after launching a
  `--continue` follow-up, confirming real continuity subject to the cwd-scoped caveat.
- Callback model: every agy runner turn auto-writes `captain_reports/final.json` + `final.md` from the
  worker's raw stdout (Layer 1, robust, always on). **No Layer 2 live MCP callback is wired for agy**: `agy
  --help` has no `mcp` subcommand, and the only MCP-shaped file found, `~/.gemini/config/mcp_config.json`,
  is 0 bytes with no documented schema - editing it blindly was judged too risky to the owner's real
  authenticated agy config, so it was left unwired and Layer 1 is the only result path for this backend.
  The shared `submit_captain_report`/`request_captain_help` allowlist does accept `metadata.agent == "agy"`
  (forward-compatible), but the agy worker prompt does not instruct the model to call them. See
  `plugin/skills/claude-manages-codex/SKILL.md`, "Worker Backends & Routing" and "Antigravity / Gemini
  (agy) Worker Backend", for the full doctrine.

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
- `plugin/skills/claude-manages-codex/SKILL.md` - the `claude-manages-codex` skill: Claude as executive captain/architect/reviewer, delegating to a worker backend (visible-window grok-4.6 by default, Codex historically). Includes the routing mandate that sends parallel-agent fan-out and implementation work off the manager model to preserve Claude tokens.
- `plugin/skills/claude-manages-codex/references/legacy-backends.md` - per-backend mechanics for the legacy/on-request worker backends (grok CLI, Antigravity/agy, disabled Codex).

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

Use this bridge's `start_visible_first_mate_codex_pool` for the observable, captain-steered
Claude-as-captain / Codex-as-first-mate hierarchy over multiple Codex agents. Use a deprecated interactive first-mate TUI only when the user explicitly requests hands-on terminal control. Use the official `/codex:rescue` command for single
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
   `steer_done/` directories. Claude can call `steer_visible_codex_run`; by default it interrupts an in-flight
   turn and resumes the same recorded Codex thread immediately with the captain instruction. Pass
   `interrupt_current_turn=false` to wait for the turn boundary instead. If the window already closed, the tool
   starts a visible `codex resume` run against the same `thread_id`. Steering can
    also carry an updated `sandbox` permission intent when Claude moves a run from scouting to scoped writes.

9. **Visible launcher stayed stuck at `created`.** The launcher used PowerShell `-NoExit`, which could leave a
    visible shell alive while the run directory stayed locked or never advanced cleanly from the caller's view. It
    now launches with `-NoProfile` and lets the script's own short close delay control visibility and cleanup.

10. **Stuck workers had no same-captain callback.** Visible Codex prompts now include a per-run captain-help
    mailbox. A stuck worker calls `request_captain_help` and stops; Claude polls the request, can ask the user if
    the decision requires owner judgment, then `respond_to_captain_help_request` queues steering back to the same
    run/thread for non-interactive workers. Open TUI workers need direct terminal steering or a resumed TUI session
    because queued steering cannot type into an already-open TUI.

11. **Interactive TUI reports were terminal-only.** Real Codex TUI sessions do not emit `codex exec --json`
    events or `--output-last-message`, so a final answer typed into the TUI is not a reliable captain handoff.
    Interactive prompts now require `submit_captain_report`; the bridge writes `captain_reports/final.json` and
    `final.md`, exposes them through `get_visible_run_status`, and closes the TUI after the report unless the
    worker sets `close_tui=false`.

12. **Interactive TUI windows could outlive the finished agent turn.** Closing only the launcher PowerShell
    process could leave the `cmd.exe`/Codex TUI process that owned the visible terminal window. The report
    watcher now sends Ctrl+C to the run's console, waits briefly, then falls back to `taskkill /T /F` for that
    launcher tree only.

13. **Interrupt steering could race Codex's local thread store.** A forced kill could return a thread id whose
    rollout JSONL was still empty, making `codex resume` fail. Interrupt steering now tries Ctrl+C first,
    waits for a readable thread before resuming, and falls back to a fresh context-rich follow-up when the
    interrupted thread is not recoverable.

## Deprecated: Interactive TUI Mode

This mode remains functional for regression compatibility, but it is not the default. Use it only when the user explicitly asks for a hands-on interactive Codex terminal, and say when this deprecated path is being used.

Use `start_interactive_codex_tui` for an explicitly requested hands-on single-worker terminal. Use `start_interactive_first_mate_codex_tui` only when that explicit request also needs a first mate coordinating Codex subagents.

This mode opens the real Codex TUI in a visible terminal. The user can approve, reject, and steer inside that terminal. The bridge still creates `.claude-codex/runs/<run-id>/` with `prompt.md`, `session_context.md`, `metadata.json`, `status.json`, `notes.md`, and best-effort `session_id.txt`.

Interactive TUI prompts include a captain handoff contract. Codex must call `submit_captain_report` before stopping, which writes `captain_reports/final.json` and `final.md`; Claude reads those through `get_visible_run_status` or `list_captain_reports`. By default the launcher watches for that report, waits about five seconds, sends Ctrl+C to the TUI console, and uses a scoped process-tree fallback if the window does not exit. Pass `auto_close_after_report=false` or `close_tui=false` when the terminal should stay open.

This mode is intentionally lower-fidelity than `codex exec --json`: it can flash-close, `display.log` contains launcher/status lines rather than a full transcript, queued steering is not injected into an already-open TUI, and captain handoff depends on the worker remembering `submit_captain_report`. Use `start_visible_haiku_composed_codex_worker` or `start_visible_codex_worker` for the default single-worker path and `start_visible_first_mate_codex_pool` for fan-out.

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

Requires the `grok` CLI on `PATH` for the default visible grok worker, `agy` for the Antigravity worker,
`claude` for the advisor tool and `start_claude_worker`, and the `codex` CLI for the legacy (disabled)
Codex tools.

> Note: the MCP server loads the script at startup, so after editing it you must reload/restart the MCP
> client for changes to take effect.

If you use Claude Code's permission allowlist, include the windowless worker tools
(`start_claude_worker`, `steer_claude_run`, `check_worker_backends`) alongside the Haiku-composed worker
tool and the older visible-agent tools:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_codex_worker",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_haiku_composed_codex_worker",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_visible_first_mate_codex_pool",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_interactive_codex_tui",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_interactive_first_mate_codex_tui",
      "mcp__plugin_claude-manages-codex_agent-visibility__steer_visible_codex_run",
      "mcp__plugin_claude-manages-codex_agent-visibility__request_captain_help",
      "mcp__plugin_claude-manages-codex_agent-visibility__list_captain_help_requests",
      "mcp__plugin_claude-manages-codex_agent-visibility__respond_to_captain_help_request",
      "mcp__plugin_claude-manages-codex_agent-visibility__submit_captain_report",
      "mcp__plugin_claude-manages-codex_agent-visibility__list_captain_reports",
      "mcp__plugin_claude-manages-codex_agent-visibility__get_visible_run_status",
      "mcp__plugin_claude-manages-codex_agent-visibility__list_visible_runs",
      "mcp__plugin_claude-manages-codex_agent-visibility__start_claude_worker",
      "mcp__plugin_claude-manages-codex_agent-visibility__steer_claude_run",
      "mcp__plugin_claude-manages-codex_agent-visibility__check_worker_backends"
    ]
  }
}
```
