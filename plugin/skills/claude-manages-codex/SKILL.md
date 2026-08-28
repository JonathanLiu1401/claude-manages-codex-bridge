---
name: claude-manages-codex
description: Multi-Agentic Harness - Claude is captain (architect/QA/reviewer); workers do implementation. SUBAGENT LOCALITY (owner rule 2026-08-15, overrides all model routing): a Claude session spawns Claude subagents through the normal Agent tool with a built-in subagent_type (general-purpose, Explore, Plan, claude, ...) and must NOT shell out to cursor-agent, grok, or Codex to delegate. The visible terminal-window workers (start_visible_* MCP tools) are used when the user explicitly asks for the multi-agentic harness by name, for visible windows, or for grok agents / grok workers (including to edit/implement — then start_visible_grok_worker with a write sandbox, do not substitute Claude subagents or leave read-only). start_claude_worker is a secondary headless run-dir path (direct-Anthropic only). The native subagent types "grok", "agy-gemini-3-1-pro", and "agy-gemini-3-7-flash" NO LONGER EXIST - do not try to spawn them. Codex is disabled. Trigger for "delegate to grok", "use the multi-agent harness", "parallelize with subagents", "first mate", or any coding task where Claude decides and a worker codes.
---

# Multi-Agentic Harness (internal id: claude-manages-codex)

> **Rename note (2026-07-15, updated 2026-08-15):** this skill is branded the **Multi-Agentic Harness**. Its internal id / MCP tool prefix / install directory remain `claude-manages-codex` for compatibility. Much of the older prose further down still mentions Codex because it was the original backend - **IGNORE those defaults**. The authoritative spawn policy is **Subagent Locality** plus the **Mandatory Spawn Path** section immediately below. Codex is DISABLED.

Use Claude's active manager model as captain, executive architect, QA tech lead, and reviewer. Delegate low-level work to workers - by default **Claude subagents spawned through the Agent tool**.

## Subagent Locality (owner rule 2026-08-15 - takes precedence over any model-routing guidance)

**Spawn subagents of the harness you are already running in.**

- A **Claude agent** (Claude Code, any Claude model) delegates through the normal Claude subagent path: the `Agent` tool with a built-in `subagent_type` (`general-purpose`, `Explore`, `Plan`, `claude`, ...). It must **NOT** shell out to `cursor-agent`, `grok`, or Codex to do its delegating.
- A session inside the Cursor `cursor-agent` TUI spawns cursor-agent subagents, choosing the worker model per the cursor routing guidance.
- A grok (Grok Build CLI) session spawns grok's own native subagents, default grok model.
- **Only exception:** an explicit user instruction naming a different harness. "Delegate this" on its own means "spawn a subagent of your own kind," not "launch a different CLI."
- **Owner-requested grok agents (2026-08-28):** "use grok", "grok agents", "grok workers", or "have grok edit/implement/fix" **is** that exception. Call `start_visible_grok_worker` (or the Haiku / first-mate grok tools). Do **not** substitute Claude `Agent` subagents. If the owner asked them to edit, pass a write sandbox (`workspace-write`, or `danger-full-access` for SSH/serial/Docker/etc.) — the tool default `read-only` strips Write/Edit and is wrong for that request. Still do not Bash `grok`; use the MCP tool. If grok is actually unavailable, tell the owner; do not silently swap.

This rule overrides every "preferred backend" / "default worker model" statement elsewhere in this file. Those sections remain as mechanics reference for the paths they describe.

## Mandatory Spawn Path (2026-08-15 - hard rule, overrides older sections)

You are reading this inside a **Claude** session, so Subagent Locality puts native Claude `Agent`-tool subagents first. The visible terminal-window workers are the multi-agentic harness proper and are reached only on an explicit request. Do not call Codex tools. Do not try to spawn a native `grok` or `agy-gemini-*` subagent: **those subagent types no longer exist.** They were served by a local multi-provider gateway that has been removed along with its launcher wrappers and per-world config dirs, and their agent definition files are deleted. An `Agent` call naming them will fail.

| Priority | When | How to spawn | How to steer |
| --- | --- | --- | --- |
| **1 (DEFAULT)** | Every ordinary delegation: implementation, scouting, test repair, review, parallel fan-out | `Agent` tool with a built-in `subagent_type` (`general-purpose`, `Explore`, `Plan`, `claude`) | `SendMessage` / follow-up Agent |
| **2 (on explicit request)** | The user asks for the multi-agentic harness by name, for visible terminal windows, or for cursor-agent / Cursor workers | `start_visible_cursor_worker` (or `start_visible_haiku_composed_cursor_worker`; `start_visible_first_mate_cursor_pool` for fan-out) then arm `watch_command`. Default model `cursor-grok-4.6-xhigh-fast` | `steer_visible_cursor_run` |
| **2b (on explicit request)** | The owner asks for grok agents / grok workers (including to edit, implement, or fix), or wants grok CLI extras (Parallel Competition Mode / Work-Checker / `best_of_n`) | `start_visible_grok_worker` (or the Haiku-composed variant; `start_visible_first_mate_grok_pool` for fan-out) then arm `watch_command`. If they asked grok to edit, pass `sandbox="workspace-write"` (or `danger-full-access`); do not leave the `read-only` default | `steer_visible_grok_run` |
| **2c (on explicit request)** | Same, but grok and cursor-agent are capped/exhausted or the owner asks for agy/Gemini | `start_visible_agy_worker` / `start_visible_haiku_composed_agy_worker` | `steer_visible_agy_run` |
| **3 (secondary)** | Long-running run-dir protocol or explicit headless multi-turn with no window | `start_claude_worker(...)` then arm `watch_command` | `steer_claude_run` |
| **NEVER** | Codex path | `start_visible_codex_*`, `codex`, `codex-reply`, interactive Codex TUI | - disabled |
| **NEVER** | Native `grok` / `agy-gemini-3-1-pro` / `agy-gemini-3-7-flash` subagent types | deleted, an `Agent` call naming them fails | - |

The skill activating does **not** by itself count as the user asking for the harness: its trigger list is broad ("any coding task where Claude decides and a worker codes"), so priority 1 governs unless the user names the harness, asks for visible windows, or asks for grok agents / grok workers (including to edit).

**Anti-patterns (agents still do these - stop):**
- Shelling out to `cursor-agent -p`, the `grok` CLI, or Codex from a Bash call to delegate from a Claude session. Subagent Locality forbids that; use the `Agent` tool for everyday work, and `start_visible_cursor_worker` / `start_visible_grok_worker` when the user asked for the harness, for visible windows, or for grok agents. Owner-requested grok-to-edit still goes through the MCP tool, with a write sandbox.
- Substituting Claude `Agent` subagents (or leaving grok on `sandbox=read-only`) after the owner asked for grok agents to edit/implement. That request is permission to spawn writable grok workers.
- Reaching for `start_visible_*` as the everyday default because an older section below still calls it one. It is now an explicit-request path.
- Calling `start_visible_haiku_composed_codex_worker` / `start_visible_first_mate_codex_pool` / `start_visible_codex_worker` because an older section still names them. **Codex is disabled.**
- Spawning `Agent` with `subagent_type: "grok"`, `"agy-gemini-3-1-pro"`, or `"agy-gemini-3-7-flash"` because an older paragraph names them. **Those types are deleted.** Use a built-in `subagent_type` instead, and `start_visible_grok_worker` for explicitly-requested grok work.
- Passing `model="grok-4.6"` (or any other non-Anthropic model id) to `start_claude_worker`. That worked only through the removed gateway; the tool now reaches `api.anthropic.com` only.
- Ending a turn on a visible run without arming its `watch_command` and, for any run that may last more than a few minutes, its `supervise_command`.
- Treating Bash `which cursor-agent` / `command -v cursor-agent` as "not installed" on Windows. Git Bash does not resolve `cursor-agent.cmd`. The CLI lives at `%LOCALAPPDATA%\cursor-agent`. Call `check_worker_backends` and read `cursor_agent`. Do not tell the owner it is missing from a PATH check.
- Conflating cursor-agent with grok. `start_visible_grok_worker` uses `~/.grok/bin/grok.exe` and does not need cursor-agent. A cursor-agent miss (even a real one) is not a reason to skip grok.

Parallel fan-out: launch every independent visible worker first (or use the first-mate pool), before reading any result. Do not serial-spawn.

## Core Model

- Claude owns architecture, task decomposition, acceptance criteria, risk calls, worker assignment, active steering, and final review. In the first-mate flow, Claude is the captain.
- **The worker owns cheap exploration, first-pass implementation, test repair, mechanical refactors, and noisy command/log work.** The default worker is a **Claude `Agent`-tool subagent** (Subagent Locality). The visible cursor-agent / grok / agy workers are the explicit-request harness path (cursor-agent first). **Codex is disabled.**
- **Default orchestration surface is the `Agent` tool** with built-in `subagent_type`s. On an explicit harness request: the visible-window tools (`start_visible_cursor_*` first, then `start_visible_grok_*` / `start_visible_agy_*`, and the first-mate pools). Secondary: `start_claude_worker` for a windowless run-dir session.
- Claude must review worker output and local diffs before claiming completion - antagonistically for grok (see "grok-4.6 rigor and mandatory adversarial review").
- Prefer delegating to a worker over doing implementation in the manager loop.
- The Claude manager model does not write implementation code by default. It writes plans, contracts, constraints, acceptance tests, review findings, steering notes, and the final user response. Route code edits to the worker (default: a Claude `Agent` subagent) unless the edit is tiny, every worker path is unavailable, or the user explicitly asks Claude to code directly.
- Claude sets the worker's reasoning effort per task by judged difficulty. Token savings come from routing work off the manager and matching effort to difficulty. (Effort ladders differ by backend - grok CLI caps at `low`/`medium`/`high`; `start_claude_worker` and agy accept `low` through `max`. Sonnet `Agent` subagents inherit the session effort unless the Agent call sets one.)
- Every new or resumed worker receives session context. For visible and headless runs, pass `session_context`. For a Sonnet subagent, put the compact brief in the Agent prompt. Tell the worker to use `read-past-sessions` when it needs full transcript history.
- Workers need enough tool access to do real work (skills, SSH, CLIs). For visible/headless runners, `sandbox` maps permission intent: `read-only` means no edits (enforced for grok/claude_worker), not a crippled process sandbox. For a Sonnet subagent, encode write vs read-only intent in the brief.
- SSH, serial, live-device, hardware, network, Docker, package-manager, and external-tool debugging need `requires_tool_access: true` / `sandbox: danger-full-access` on the visible/headless runner (or full-tool authorization in a Sonnet brief).
- Do not spend manager-model output tokens on boilerplate, long worker prompts, or raw-log analysis a worker can do. Pass a compact captain brief to the Haiku prompt composer instead of writing the full worker prompt yourself.
- **Spawn path reminder:** `Agent`-tool Claude subagents first (Subagent Locality); `start_visible_cursor_worker` / `start_visible_grok_worker` / visible agy on an explicit harness, visible-window, or grok-agent request (owner-requested grok-to-edit = writable `start_visible_grok_worker`); `start_claude_worker` for windowless run-dir work; **Codex disabled**. The native `grok` / `agy-gemini-*` subagent types are deleted. Interactive TUI tools are deprecated.
- Hidden model reasoning is not displayable. Surface useful progress, summaries, commands, and implementation state instead.

## Worker Backends & Routing (added 2026-07-14; visible-window path restored 2026-08-15)

**Read "Mandatory Spawn Path" above first.** This section is reference detail only. Do not let older "preferred" wording elsewhere in this file override that table.

Supported backends (in preferred order):

- **Claude native subagent (DEFAULT, Subagent Locality)** - `Agent` tool with a built-in `subagent_type`. No CLI, no auth, no run-dir machinery.
- **cursor-agent in a visible window (explicit harness request)** - `start_visible_cursor_worker`, `start_visible_haiku_composed_cursor_worker`, `start_visible_first_mate_cursor_pool`, `steer_visible_cursor_run`. Default model `cursor-grok-4.6-xhigh-fast` (grok 4.6 xhigh Max Mode fast, Cursor 1M Max Mode). Preferred visible-window path when the user names the harness, cursor-agent, or Cursor workers.
- **Grok CLI in a visible window (explicit harness request)** - `start_visible_grok_worker`, `start_visible_haiku_composed_grok_worker`, `start_visible_first_mate_grok_pool`, `steer_visible_grok_run`. The only path with Parallel Competition Mode and the Mandatory Parallel Work-Checker gate. See "Grok Worker Backend" below and `references/legacy-backends.md`.
- **Antigravity CLI in a visible window (explicit harness request, next on that ladder)** - `start_visible_agy_worker`, `start_visible_haiku_composed_agy_worker`, `steer_visible_agy_run`. Separate agy quota, driven directly against the standalone `agy` CLI. See "Antigravity / Gemini (agy) Worker Backend" below.
- **`start_claude_worker` (SECONDARY windowless path)** - detached headless `claude -p` straight to `api.anthropic.com`; use it when the task wants the run-dir protocol without a terminal window, or explicit `steer_claude_run` multi-turn. Tool default model is `claude-opus-5`; only models `api.anthropic.com` serves are valid. See "Headless claude_worker backend" below.
- **Codex (gpt-5.6-sol)** - **DISABLED** (owner 2026-07-15: ChatGPT login revoked). Do not route to Codex. Tools remain in code for possible revival only.

**Removed backends.** The native Agent-tool subagent types `grok`, `agy-gemini-3-1-pro`, and `agy-gemini-3-7-flash` are gone. They existed only inside a session pointed at a local multi-provider gateway; that gateway, its launcher wrappers, its per-world config dirs, and the three agent definition files have all been deleted. Do not attempt those `subagent_type` values, and do not pass non-Anthropic model ids to `start_claude_worker`.

### Default routing policy (2026-08-15)

Unless the owner says otherwise:

1. **Default SPAWN PATH = the `Agent` tool with a built-in `subagent_type`** (`general-purpose`, `Explore`, `Plan`, `claude`). Subagent Locality: a Claude session spawns Claude subagents and never shells out to `cursor-agent`, `grok`, or Codex to delegate.
2. **Parallel fan-out** → several `Agent` calls in one message, one work item each.
3. **User explicitly asks for the multi-agentic harness / visible windows / cursor-agent** → `start_visible_cursor_worker` (or the Haiku-composed variant, or `start_visible_first_mate_cursor_pool` for fan-out). Default model `cursor-grok-4.6-xhigh-fast`.
4. **Owner asks for grok agents / grok workers (including to edit/implement), or wants grok-CLI extras (Competition Mode / Work-Checker / `best_of_n`)** → `start_visible_grok_worker`. If they asked grok to edit, use a write sandbox; do not substitute Claude subagents.
5. **Same explicit request, but cursor-agent and grok exhausted or the owner asks for agy** → `start_visible_agy_worker`.
6. **Windowless run-dir work** → `start_claude_worker(...)` (secondary).
7. **Codex** → never. Native `grok` / `agy-gemini-*` subagent types → never (deleted).
8. **Call `check_worker_backends` before delegating to a visible-window or headless backend.** If the chosen backend is unavailable, fall back and tell the user why.

### Headless claude_worker backend (added 2026-07-18; SECONDARY as of 2026-08-15)

`start_claude_worker` is the **secondary** windowless backend - use it when the run-dir protocol is wanted without a terminal window, for long-running `steer_claude_run` multi-turn work, or on an explicit headless request. **Do not use it as the everyday default** when an `Agent`-tool Claude subagent works. Implemented by `claude_worker_runner.py`, which builds a `claude -p --verbose --output-format stream-json --permission-mode <mode> --add-dir <cwd> [--model][--effort] ...` invocation and passes the prompt via STDIN - no terminal window opens. It spawns against `api.anthropic.com` on the normal OAuth login.

Full live signature: `start_claude_worker(prompt, cwd, title="Claude worker", model=CLAUDE_WORKER_DEFAULT_MODEL ("claude-opus-5"), sandbox="read-only", effort="", session_context="", resume_session_id="", max_budget_usd="", steer_idle_seconds=20)`.

- `model`: any model `api.anthropic.com` serves - `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, etc. Non-Anthropic ids such as `grok-4.6` are **no longer valid**: they only resolved through the removed gateway. For grok work use `start_visible_grok_worker`.
- `sandbox` maps to Claude Code CLI permission modes: `read-only` -> `plan` (+ `Write`/`Edit` stripped, enforced not just requested), `workspace-write` -> `acceptEdits`, `danger-full-access` -> `bypassPermissions`.
- `effort`: `low` / `medium` / `high` / `xhigh` / `max`.
- `steer_claude_run(run_dir, instruction, ..., interrupt_current_turn=False)` steers or resumes a run mid-flight. Unlike the visible steers (which interrupt the in-flight turn by DEFAULT), its `interrupt_current_turn` defaults to **False** (queue/resume-oriented) - pass `True` to interrupt. There is no `requires_tool_access` param.
- Full run-dir protocol preserved: `events.jsonl`, `display.log`, `status.json`, `captain_reports/`, `captain_help/`, `steer_queue/` - the same backend-agnostic `get_visible_run_status` / `list_visible_runs` / `submit_captain_report` / `list_captain_reports` / `request_captain_help` / `list_captain_help_requests` / `respond_to_captain_help_request` tools every other backend uses.
- `check_worker_backends` reports a `claude_worker` entry alongside `claude_sonnet` / `cursor_agent` / `grok` / `codex` / `agy`.
- Every claude-worker prompt auto-carries the Worker Rigor Contract - see "grok-4.6 rigor and mandatory adversarial review" below - but NOT the grok-CLI-only Parallel Competition Mode / Mandatory Parallel Work-Checker extras (`competition_agents`, `best_of_n`, `self_check` are grok-CLI params, not `start_claude_worker` params). Escalate a hard problem to the visible grok backend when those extras are wanted.

### Memory (claude-mem) integration (added 2026-07-18)

Headless `claude -p` workers spawned by `start_claude_worker` are Claude Code processes with the `claude-mem` plugin enabled, so claude-mem's SessionStart/PostToolUse/Stop hooks fire for those workers automatically, and their prompts/session-init get passively captured into the shared claude-mem store (the global daemon on `127.0.0.1:37777` backing a SQLite DB + vector store) - no bridge code change needed. Keep this conservative:

- Observation *richness* depends on run length - a short worker turn may produce few or no distilled observations.
- The non-Claude CLI backends (grok CLI, agy CLI) are not Claude Code processes, so they fire no claude-mem hooks and their work is not captured. When one of those explicit-request paths is used, its activity is covered only by the parent session's own capture (plugin `claude-mem@thedotmack`).
- `Agent`-tool subagents (the default path) run inside the parent Claude Code session, so the same parent-session capture covers their top-level activity.

### Leveraging SuperGrok Heavy (grok "heavy mode")

There is no separate `heavy` CLI flag or model id - SuperGrok Heavy (owner is tier 5) is a subscription tier that raises grok's compute/rate limits, and grok exposes that power through its agent system, which the bridge already uses:

- **Native subagents are ENABLED by default** on every grok worker (the bridge never passes `--no-subagents`), so a single `start_visible_grok_worker` can already spawn parallel child agents ("uses agents efficiently") when the task warrants it.
- **`start_visible_first_mate_grok_pool`** is the explicit fan-out path - a grok root that coordinates native subagents, the grok analog of the first-mate pool.
- **`best_of_n` param** (wired 2026-07-15) on `start_visible_grok_worker` / `start_visible_haiku_composed_grok_worker`: pass `best_of_n=N` (capped 1-6) to run the initial task N ways in parallel and keep the best (`--best-of-n`, initial turn only). The concrete Heavy-tier quality lever - but it costs ~N× tokens, so reserve it for hard, high-value tasks.
- **`self_check` param** (wired 2026-07-15): pass `self_check=True` to append grok's own self-verification loop (`--check`) to the initial turn - a cheap quality boost on top of Claude's review.
- **`[subagents]` config** in `~/.grok/config.toml` (per-agent model pins, roles, personas) is a further lever tuned outside the bridge.

### Strict read-only enforcement (grok)

For a grok worker launched with `sandbox="read-only"`, the bridge now **enforces** no-edit by passing `--disallowed-tools Write,Edit` so Grok's file-mutation tools are removed - it truly cannot edit, not merely asked not to (borrowed from faeton/claude-grok-plugin). Bash is intentionally kept so read-only inspection (Python-backed skills, read-past-sessions, safe read commands) still works - the bridge's read-only means "no edits", not "no commands". Use `read-only` for scouting / second-opinion / review workers; use `workspace-write` or full access when the worker must edit.

*(These three - read-only enforcement, `best_of_n`, `self_check` - were adopted 2026-07-15 after surveying existing grok↔Claude Code plugins; the multimodal / xAI-API-key / older-model-tier features from those plugins were intentionally not adopted, since this harness runs the newer grok-4.6 via the SuperGrok Heavy OAuth CLI.)*

### grok-4.6 rigor and mandatory adversarial review (owner assessment 2026-07-15)

**grok-4.6 is a fast coder but a weak engineer** - roughly gpt-5.3-codex-spark class. Its observed failure modes: it fixates on a single hypothesis, does not consider multiple scenarios, skips edge cases and error paths, and declares work "done" without ever executing it end to end. Treat every grok result as **unverified and probably buggy until you prove otherwise.** Two mechanisms enforce this:

1. **Worker Rigor Contract (automatic).** Every grok worker prompt is prepended with a mandatory contract (`_grok_rigor_contract`) that forces the worker to: enumerate 2-3 hypotheses/approaches and the edge/error/boundary cases before coding; adversarially pressure-test its own change; **actually run it end to end and paste the observed output as proof** (a confident "done" without executed evidence is defined as a failure); and report what it did NOT test plus the top 2 ways it could still be wrong. You do not need to add this to your brief - it is always injected - but your `prompt_brief` should still name the concrete acceptance test and the specific scenarios/edge cases you want covered.

2. **Mandatory Opus-captain adversarial review (you).** Do NOT trust grok's "done." Review its diff and claims **antagonistically, assuming they are wrong**, and specifically:
  - Independently VERIFY end to end yourself - run the tests / CLI / endpoint / repro, read the real output. Grok's own "I tested it" is not sufficient evidence; grok's self-check (`--check`) is weak self-marking, not proof.
  - Hunt the cases grok most likely skipped: the edge/empty/null/boundary inputs, the error branch, concurrency, the opposite of the happy path, and the scenario it fixated away from.
  - Check for tunnel vision: did it fix the reported symptom while missing the root cause or breaking an adjacent case?
  - If it drifted, fixated, or reported success without executed proof, reject and re-steer with the specific missing case - or escalate: raise `reasoning_effort`, set `self_check=True`, or use `best_of_n=2-3` so grok generates and self-selects among multiple attempts on hard tasks.
  - Only report a grok result to the user as done after YOU have executed the acceptance test and seen it pass. This is not optional for grok - it is the primary defense against its weaknesses.

For non-trivial or correctness-sensitive grok work, prefer `best_of_n` (multiple scenarios) and `self_check=True` (its own verify pass) on top of your adversarial review - but they supplement, never replace, the captain's independent e2e verification.

### Parallel Competition Mode (grok-4.6, up to 16 in-turn competitors)

grok usage is abundant and resets often, so lean on parallelism to compensate for grok-4.6's weak single-shot reasoning. Every grok worker prompt carries a **Parallel Competition Mode** contract (`_grok_competition_contract`, controlled by the `competition_agents` param, default 16, cap 16): for a HARD or open-ended problem the root worker spawns up to N diverse subagents **inside its single turn** (native grok subagents - one terminal, no extra windows, so the owner is not spammed), each independently attempting the full task with a different strategy; the root then acts as judge, discards competitors that lack executed evidence, and **compiles the best result** (picks the strongest or synthesizes a superior combination), then verifies the compiled result end to end. This is the grok-4.6 analog of the grok-4.20 multi-agent harness.

- It is judgment-gated: the contract tells grok to compete only when the task is hard enough to benefit and to solve simple/mechanical tasks directly, so it does not fan out 16 agents to reply with a token.
- Set `competition_agents=1` to disable competition for a run (e.g. trivial or strictly-sequential tasks); set 2-16 to cap the competitor count.
- It composes with the rest: competitors still obey the Rigor Contract (run + prove), and the Opus captain STILL independently e2e-verifies the compiled result - a grok-run competition that picks a winner is not a substitute for the captain's own verification.
- `competition_agents` is a prompt capability, not a CLI flag; it stacks with `best_of_n` (a CLI-level N-way retry) but the two overlap, so prefer one lever at a time unless a task is genuinely huge.

### Mandatory parallel work-checker (grok, every run)

Every grok worker prompt also carries a **Mandatory Parallel Work-Checker** contract (`_grok_work_checker_contract`, always injected) that fires right before the worker may report done: it must spawn a fleet of parallel checker subagents inside the same turn (one terminal), each adversarially auditing its OWN finished work from a different lens (correctness/logic, edge cases & error paths, did-it-actually-run/re-execute the acceptance test, requirements coverage, regressions/blast-radius, and security/concurrency/perf where relevant), then consolidate the proven findings (no cry-wolf), **fix every real issue, and re-run the checkers until they come back clean.** A grok worker may not declare done until a clean parallel work-checker pass, and its report must include what the checkers found, what it fixed, and the final clean verification output. This is the automatic, worker-side counterpart to the captain's own adversarial review - it directly attacks grok-4.6's "declares done without testing" habit. (It is judgment-scaled: a purely trivial informational reply self-verifies instead of spawning a full fleet.) The captain STILL independently e2e-verifies after - the worker's self-run checker is not a substitute for the captain's verification.

### `check_worker_backends`

`check_worker_backends(cwd=None, deep=False) -> {"claude_sonnet": {...}, "claude_worker": {...}, "grok": {...}, "codex": {...}, "agy": {...}, "cursor_agent": {...}}`, one `{available, reason, detail}` record per backend.

**This MCP tool is the availability source of truth.** Do not Bash `which` / `command -v` / `where` to decide. On Windows, Git Bash `command -v cursor-agent` is a known false negative: the installer ships `cursor-agent.cmd` (and a versioned `node.exe` + `index.js` under `%LOCALAPPDATA%\cursor-agent\versions\`), which MSYS does not treat as the name `cursor-agent`. The bridge resolver looks at that versions directory first; `cursor_agent.available` is true on this machine when that tree is present. Grok is a separate binary (`~/.grok/bin/grok.exe`); `cursor_agent` false does not mean `grok` is false.

- Default (`deep=False`) is cheap: CLI path existence, auth-file presence/parseability, and (for Codex) local JWT-expiry decoding. No network calls.
- The `claude_worker` entry checks that the `claude` CLI is present and usable - call this before delegating to `start_claude_worker`, exactly like the other backends.
- `deep=True` additionally runs one short live `codex exec` round trip (roughly 5-15s, a trivial no-tool prompt) that catches server-side token revocation a locally-valid JWT hides. Grok and agy do not get a live ping in `deep` mode - their file-based expiry/refresh-token check is already reliable, and a live ping would spend a real prompt turn for no better signal.
- Observed live on this machine (2026-07-14): `claude_sonnet`, `grok`, and `agy` available; `codex` available=False under `deep=True` with reason `"codex not logged in (ChatGPT login lost / token revoked server-side)"` - the ChatGPT session was revoked while the local access-token JWT and `codex login status` both still looked fine, which is exactly the case `deep=True` exists to catch.

### Callback model (Grok and Antigravity/agy workers)

(`start_claude_worker`'s own report/callback behavior is covered by the general run-dir protocol in "Headless claude_worker backend" above - the run-dir carries `captain_reports/` for every backend. This subsection covers the two legacy visible-window backends specifically.)

Every non-Codex backend's worker gets a result back to Claude through two layers:

1. **Layer 1 - runner auto-report (robust, always on).** The Grok and agy PowerShell runners each write `captain_reports/final.json` + `final.md` themselves from the worker's own answer text after every turn, independent of whether the worker ever calls an MCP tool. `get_visible_run_status` and `list_captain_reports` read it the same way they read a Codex `submit_captain_report` call. For agy this is the ONLY callback path (see below); for Grok it is the always-on fallback under Layer 2.
2. **Layer 2 - live MCP callback.** Where wired (Grok: `~/.grok/config.toml` `[mcp_servers.agent-visibility]`, pointed at the deployed bridge), the worker prompt also instructs the model to call `submit_captain_report` / `request_captain_help` mid-run, matching the Codex `codex-consults-claude` pattern. The shared allowlist in `submit_captain_report` and `request_captain_help` accepts `metadata.agent in (None, "codex", "grok", "agy", "claude", "cursor")`. Cursor workers are Layer-2 wired via `~/.cursor/mcp.json` (`agent-visibility`) plus `--approve-mcps` on the CLI. Grok is wired via `~/.grok/config.toml`. **agy has NO Layer 2 wired**.

> **Reading everything below (Reasoning Effort Policy to Claude Review Standard):** these sections still use **Codex as the historical example** for effort tiers, supervision, watchers, captain-help, and review language. **Codex is DISABLED. The Mandatory Spawn Path at the top of this file always wins.** Map "Codex" to "the worker"; map `start_visible_codex_*` to `start_visible_cursor_worker` / `start_visible_first_mate_cursor_pool` (preferred visible), `start_visible_grok_worker` / `start_visible_first_mate_grok_pool` (grok-CLI extras), `start_visible_agy_worker`, or secondary `start_claude_worker`; map `steer_visible_codex_run` to `steer_visible_cursor_run` / `steer_visible_grok_run` / `steer_visible_agy_run` / `steer_claude_run`. Do not call Codex tools because an older paragraph still names them.

## Reasoning Effort Policy

Codex runs on `gpt-5.6-sol`. Claude - the manager - chooses the Codex reasoning effort per task by judging its difficulty. Effort is no longer pinned to `xhigh`; Claude scales it up or down along this ladder:

- `high`: routine, low-ambiguity work - mechanical refactors, formatting, narrow test repair, small well-scoped edits, cheap scouting where the answer is easy to find.
- `xhigh`: normal multi-file implementation, non-trivial exploration, moderate debugging, and reviews with some ambiguity. This is the default floor when Claude does not specify.
- `max`: hard problems - subtle concurrency/correctness bugs, cross-cutting refactors, tricky architecture-sensitive changes, or work where a wrong answer is expensive.
- `ultra`: the hardest, highest-stakes tasks - deep multi-subsystem reasoning, gnarly root-cause hunts, or large coordinated changes. `ultra` is `gpt-5.6-sol`'s top effort tier: instead of only spending more chain-of-thought in a single turn, it natively decomposes the problem into cooperative internal subagents (see below). It costs significantly more tokens per turn and is preview-gated, so reserve it for genuinely hard, parallelizable work. Ultra runs are intentionally unbudgeted - do not cap them with a token or dollar budget (owner decision 2026-07-14).

(`minimal`, `low`, and `medium` are also valid `model_reasoning_effort` values the bridge accepts, but Codex worker tasks in this bridge should stay on the `high` → `ultra` range above unless Claude has a specific reason to go lower.)

How Claude selects:

- Assess difficulty yourself before dispatching: scope (files/subsystems touched), ambiguity, blast radius of a mistake, and how much independent reasoning the worker must do. Pick the lowest tier that comfortably covers the task; escalate when the signals are high.
- Pass the chosen tier as `reasoning_effort` (or `config.model_reasoning_effort`) on the Codex/visible/TUI start tools. The bridge validates it against `gpt-5.6-sol`'s accepted values (`minimal` / `low` / `medium` / `high` / `xhigh` / `max` / `ultra`) and falls back to the `xhigh` floor if it is missing or unrecognized.
- Re-judge on steering. If a task turns out harder than expected (repeated failed attempts, confused workers, growing scope), raise the effort on the next run or resume; if it turns out trivial, drop it. Do not leave everything at one fixed tier.
- Match effort to the worker's job, not just the overall goal: a cheap `claude-explorer` scout can run at `high` while the `claude-implementer` doing the hard change on the same goal runs at `max` or `ultra`.

### Ultra effort and native subagent fan-out

At `ultra` effort, `gpt-5.6-sol` decomposes the work into its own cooperative internal subagents and reassembles the result - the model-native equivalent of the first-mate pool. Use it when Claude has judged the task hard and genuinely parallelizable (independent subsystems, a wide search, or a large coordinated change). For a Codex root/first-mate coordinator, `ultra` also backs its explicit `claude-explorer` / `claude-implementer` / `claude-reviewer` fan-out (file-disjoint for writes).

Keep it bounded and captain-governed:

- Claude authorizes `ultra` and the fan-out in the brief; a worker does not unilaterally escalate its own effort tier or spawn a deep subagent tree.
- Respect the existing fan-out cap (at most the worker count Claude requested, otherwise 6) and the no-recursive-trees rule - ultra widens a single layer, it does not nest layers.
- Prefer one `ultra` run over spraying many separate high-effort workers for genuinely parallelizable work. Do not attach a rollout token budget or any other spend cap to an `ultra` run - the owner removed the ultra budget limit (2026-07-14); the bounds on `ultra` are scope and the fan-out cap, not tokens.
- Lower tiers (`high` / `xhigh` / `max`) run as single workers unless Claude explicitly asks for a small parallel split.

## Official OpenAI Codex Plugin

This bridge is designed to work with OpenAI's official Claude Code plugin at `https://github.com/openai/codex-plugin-cc`.

Use the official `codex` plugin when it is installed and the task matches one of its standard workflows:

- `/codex:setup`: check local Codex CLI readiness and authentication; use this before first use or when Codex errors suggest missing setup.
- `/codex:review`: read-only review of current work or branch diff.
- `/codex:adversarial-review`: read-only challenge review that pressure-tests implementation direction, assumptions, tradeoffs, and risk areas.
- `/codex:rescue`: delegate a substantial investigation, bug fix, or follow-up task to Codex through the official companion runtime.
- `/codex:transfer`: transfer the current Claude Code session into a resumable Codex thread.
- `/codex:status`, `/codex:result`, `/codex:cancel`: manage official plugin background jobs.

Installation path for the official plugin:

```bash
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

Do not copy the official plugin command scripts into this plugin just to expose `/codex:*`; that namespace belongs to the official plugin. If the official plugin is not installed, use this bridge's bundled MCP tools and visible-agent harness as the fallback and tell the user the official plugin can be installed with the commands above.

Use this bridge's visible first-mate pool instead of `/codex:rescue` when the user wants observable multi-agent fan-out, a Claude-as-captain / Codex-as-first-mate hierarchy, or a coordinated ensemble of Codex agents. The official `/codex:rescue` path is best for single delegated rescue tasks and background job management.

## Manager Model Policy

Treat the active Claude manager model as the executive orchestrator, not the implementing engineer.

Default advisor model policy:

- use the active highest-available manager model: **Fable 5 / `high`** when present in Claude Code, otherwise **Opus / `high`**
- override without editing files by setting `CLAUDE_MANAGES_CODEX_ADVISOR_MODEL`

The manager model should spend reasoning on:

- system architecture, dependency mapping, data-flow decisions, and risk triage
- decomposing work into file-scoped worker tasks
- acceptance criteria, verification strategy, and rollback/safety boundaries
- active steering (`steer_visible_grok_run` / `steer_visible_agy_run` for visible runs; `steer_claude_run` for headless; `SendMessage` for Sonnet subagents)
- independent diff and test review before completion

The manager model should not spend output tokens on:

- broad codebase reading that a worker can summarize
- boilerplate implementation, mechanical refactors, formatting, or test repair
- long worker prompts (pass a compact `prompt_brief` to the Haiku composer instead)
- raw log analysis unless the worker cannot summarize the evidence

Default manager loop (**Claude-subagent-first**):

1. Decide the architecture and acceptance criteria.
2. Spawn a **Claude `Agent` subagent** with a compact brief and a built-in `subagent_type`. For independent parallel work, issue several `Agent` calls in one message. Only on an explicit harness request, spawn a visible cursor-agent worker instead (`start_visible_cursor_worker` or the Haiku-composed variant, `start_visible_first_mate_cursor_pool` for fan-out; grok CLI if Competition/Work-Checker is wanted) and arm its `watch_command`, per the Mandatory Spawn Path.
3. Every 10 minutes while a **visible or headless** fleet is active, run the mandatory direct supervision pass (see "Mandatory 10-Minute Direct Supervision"). `Agent` subagents are instead supervised by waiting on their result and reviewing the returned report/diff - not by run-dir polling.
4. Let the worker implement, verify, and summarize.
5. Claude reviews the diff, tests, risks, and (if used) the worker ledger. Reject or re-steer when the output does not match the architecture. For grok, review antagonistically and re-run acceptance yourself.
6. Claude writes the final user response only after the review gate passes or clearly reports incomplete verification.

## Routing Mandate: Parallel Agents and Heavy Work → Claude subagents first

**Default rule: while this skill is active, Claude keeps the manager model focused on architecture, decomposition, steering, and review, and pushes low-level execution to subagents of its own harness.** This overrides older skill prose that still names Codex, the visible-window tools, or native `grok` / `agy-gemini-*` subagents as defaults.

Primary delegation surface (use this):

1. **Claude `Agent`-tool subagents (DEFAULT).** A built-in `subagent_type` (`general-purpose`, `Explore`, `Plan`, `claude`) per work item; several `Agent` calls in one message for parallel fan-out. Steer with `SendMessage`. Never shell out to `cursor-agent`, `grok`, or Codex to delegate.

Explicit-request / secondary (only when conditions in Mandatory Spawn Path match):

2. **Visible-window workers** - `start_visible_cursor_worker` / `start_visible_haiku_composed_cursor_worker` for a single worker, `start_visible_first_mate_cursor_pool` for structured parallel fan-out; `start_visible_grok_worker` when grok-CLI extras are wanted; `start_visible_agy_worker` next on that ladder. Steer with the matching `steer_visible_*_run`. **Never Codex.**
3. **`start_claude_worker`** - secondary windowless path for run-dir multi-turn work.

**Route heavy/parallel work off the manager** - through `Agent` subagents first:

- **Any parallel agent fan-out another skill or tool would trigger** - e.g. `dispatching-parallel-agents`, `subagent-driven-development`, `feature-dev`, the `Explore` / `Plan` agents, or a direct `Agent` / Task-tool dispatch - run it as a **fleet of `Agent`-tool subagents**. Do not implement the fan-out inline in the manager loop, and do not convert it into a different CLI's workers.
- **Heavy coding work** - multi-file implementation, mechanical or large refactors, test repair, broad codebase reading, and noisy command/log iteration - route to a subagent (default: an `Agent`-tool Claude subagent).

**Honor the other skill's discipline, delegate its execution.** When a process skill applies (TDD, systematic-debugging, executing-plans), Claude still follows that skill's method and checklist - but the actual fan-out and edits are carried out by the workers, with the brief encoding the required discipline (e.g. "write the failing test first, then implement"). Claude decomposes, writes the briefs, and reviews; the workers execute.

**Claude keeps (never delegate):** architecture, task decomposition, acceptance criteria, risk and security calls, steering decisions, final review of every diff, and the user-facing response.

**Delegation is ONE level deep.** A spawned subagent/worker (grok, agy, Sonnet, claude_worker) must not delegate further, spawn its own subagents, or re-invoke this skill - only the top-level manager delegates. This is what prevents infinite agent loops.

**Do the work in the manager loop only when:**

- The edit is tiny (single file, a few lines) where delegation overhead exceeds the token savings and the user has not asked for strict delegation.
- The work needs tools or context only Claude can reach (MCP servers the worker lacks, this session's live state).
- Every worker path is unavailable/capped - fall back to doing it directly and tell the user.
- The user explicitly asks Claude to do the work directly.

## Parallel Fan-Out Contract

Every start tool returns quickly, so simultaneous workers run in parallel: one visible window per worker. Serial spawning is a manager error, not a platform limit.

- When tasks are independent, spawn every worker first (back-to-back start-tool calls), before reading any result from any of them.
- Never await one worker's completion before launching an independent sibling. Waiting between spawns silently serializes the fleet and wastes wall-clock time.
- After the full fleet is launched: arm every `watch_command` and supervise per the "Mandatory 10-Minute Direct Supervision" contract. For Sonnet `Agent` subagents, collect results and review instead.
- Prefer `start_visible_first_mate_grok_pool` when one coordinator should own the fan-out, and separate visible grok workers when the work items are cleanly file-disjoint. Do **not** use `start_visible_first_mate_codex_pool` (Codex disabled).

## Worker Exhaustion Fallback (down the backend ladder)

When the active worker backend runs out (grok capped, agy buckets cooling, etc.), keep delegating - just move down the ladder (grok-4.6 → agy → Claude Sonnet subagents). Do not silently start doing all the implementation as the manager model; the point is still to route heavy/parallel work off the manager. The no-nesting / no-parking / flat-fallback rules below are backend-agnostic and apply to every fallback fleet ("Codex" in the detection triggers = the capped backend).

**Only the top-level Claude manager owns this switch.** The Codex→Sonnet decision is made once, at the captain level. A spawned worker (a Codex first mate, a Codex subagent, or a Sonnet fallback agent) that discovers Codex is capped MUST NOT decide to build its own fallback fleet - it stops and reports the cap upward, and the top-level manager reroutes. This is what prevents the nesting spiral: workers hitting the cap and each spinning up their own Sonnet sub-fleets.

**Detect Codex-out.** Treat Codex as unavailable when any of these hold:

- `codex` / `codex-reply` or a visible/interactive start tool returns a usage, quota, rate-limit, plan-cap, `429`, "usage limit reached", "insufficient quota", or "out of credits" error.
- Codex repeatedly fails to start or immediately exits with a usage/billing message.
- The user says Codex usage is out or asks to stop using Codex for cost/quota reasons.

Verify it is genuinely a usage problem, not a transient network blip or a one-off tool error, before switching. A single retryable error is not exhaustion; a clear quota/limit message or repeated usage failures is.

**Latch the cap once; do not let every worker rediscover it.** As soon as the manager confirms Codex is out, record it in `.claude-codex/BRIDGE.md` (e.g. `Codex: CAPPED until <reset date/time>`) and stop issuing Codex delegation for the rest of the session. Do not keep firing `codex` / visible-start calls per work item and letting each one fail into the cap - that is what produced the flood of failed delegations. If the cap has a known reset (e.g. usage returns July 10), note it and treat Codex as unavailable until then rather than retrying on every task.

**Fall back to Sonnet subagents.** Once Codex is confirmed out:

- Spawn Claude subagents with the `Agent` tool using `model: sonnet` for the worker roles Codex would have filled - exploration, first-pass implementation, mechanical refactors, test repair, and broad codebase reading.
- Map the Codex roles to Sonnet agent types: use the `Explore` agent (or `general-purpose` with a read-only brief) in place of `claude-explorer`, `general-purpose` in place of `claude-implementer`, and a review-focused `general-purpose`/`code-reviewer` brief in place of `claude-reviewer`.
- Keep the same manager discipline: Claude still owns architecture, decomposition, acceptance criteria, scope, and final review; Sonnet agents only execute the briefs. For file-disjoint parallel work, dispatch multiple Sonnet agents in one message so they run concurrently, one work item each.
- Reuse the same briefs, permission intent, and acceptance criteria you would have handed Codex. The routing target changes; the captain/worker split does not.
- Tell the user Codex usage is exhausted and that work is now running on Sonnet agents. Note that visible-terminal steering, `captain_report`, and the Codex-specific visible/first-mate harness do not apply to Sonnet agents; steer them through follow-up `Agent`/`SendMessage` briefs and review their returned results directly.

**Flat fallback - no nesting, no parking, no rogue-writer games.** The Sonnet fallback fleet is one flat layer of workers under the top-level manager. Enforce all of the following, and encode them into every fallback brief:

- **No re-delegation.** A Sonnet fallback agent executes its brief and returns a result. It must not itself try to "delegate to Codex," must not spawn further sub-agents, and must not invoke the claude-manages-codex routing. Only the top-level manager delegates. (Codex being capped means the whole "route to Codex" instruction is off for the session - say so in the brief so the worker does not try and fail.)
- **No parking.** Fallback agents run to completion and terminate with a result or a concrete blocker. They do not idle, wait for Codex to come back, or wait for a captain hand-off. The captain-help mailbox, `request_captain_help`, `submit_captain_report`, and "blocked_waiting_for_captain" are Codex visible-harness concepts and DO NOT apply to Agent-tool Sonnet workers - a blocked Sonnet agent returns its blocker text and stops.
- **No stand-down protocol between workers.** Fallback agents do not message each other, do not police the working tree for other writers, and do not invent "stand-down" or "rogue writer" handshakes. Coordination is the manager's job: give each parallel agent a file-disjoint scope up front so they never need to negotiate.
- **The user and the manager are not rogue writers.** Concurrent edits from the human owner or the Claude manager are expected and legitimate. An agent that sees files change under it must NOT label that a "rogue writer," stand down, or abort - it reports the unexpected change as an observation and continues within its own scope, and the manager reconciles. Only the top-level manager arbitrates real file-scope conflicts.

**Recover.** When Codex usage is restored (new billing window, user tops up, or the user asks to resume Codex), return to routing heavy/parallel work through Codex per the Routing Mandate. Sonnet-agent fallback is a stopgap, not the default fleet.

## Codex MCP Harness (DISABLED)

**Do not use.** Codex is disabled (ChatGPT login revoked). The `codex-worker` MCP tools remain only for a possible future revival.

Historical surface (do not call):

- `codex`: start a new Codex root worker session.
- `codex-reply`: continue a Codex root worker session with a `threadId`.

Important `codex` arguments:

- `prompt`: the worker brief.
- `cwd`: project directory.
- `sandbox`: `read-only`, `workspace-write`, or `danger-full-access`.
- `approval-policy`: use `never` unless the user explicitly wants interactive approvals.
- `developer-instructions`: use this to enforce Claude manager / Codex worker roles.
- `model`: set `gpt-5.6-sol`.
- `config`: include `model_reasoning_effort="<tier>"` where `<tier>` is the effort Claude selected for this task (`high`, `xhigh`, `max`, or `ultra`), and `service_tier="fast"`.

When a Codex response includes `structuredContent.threadId`, record it and use `codex-reply` for follow-up to that same root worker.

## Visible Agent Harness (the explicit-request path)

> **This is the explicit-request spawn path** (see Subagent Locality and Mandatory Spawn Path): a worker runs in its own visible window with a run directory. Reach for it when the user asks for the multi-agentic harness by name, for visible windows, for cursor-agent, or for the grok-only extras. Within it, use the **cursor-agent** tools first, then **grok CLI** for Competition/Work-Checker extras, then **agy**. **The Codex visible tools named in this section are DISABLED - never call them.**

Use the plugin-provided MCP server `agent-visibility` for visible runs, shared status/report tools, and captain-help mailboxes on visible and headless runs.

Backend-agnostic tools you use with every run:

- `get_visible_run_status`, `list_visible_runs`, `submit_captain_report`, `list_captain_reports`, `request_captain_help`, `list_captain_help_requests`, `respond_to_captain_help_request`
- `start_visible_cursor_worker` / `start_visible_haiku_composed_cursor_worker` / `start_visible_first_mate_cursor_pool` / `steer_visible_cursor_run` (first within this path - documented under "Cursor Agent Worker Backend")
- `start_visible_grok_worker` / `start_visible_haiku_composed_grok_worker` / `start_visible_first_mate_grok_pool` / `steer_visible_grok_run` (grok-CLI extras - documented under "Grok Worker Backend")
- `start_visible_agy_worker` / `start_visible_haiku_composed_agy_worker` / `steer_visible_agy_run` (next on the ladder - documented under "Antigravity / Gemini (agy) Worker Backend")
- `start_claude_worker` / `steer_claude_run` (secondary windowless - documented under "Headless claude_worker backend")

**DISABLED Codex tools (do not call):**

- `start_visible_codex_worker`, `start_visible_haiku_composed_codex_worker`, `start_visible_first_mate_codex_pool`
- `start_interactive_codex_tui`, `start_interactive_first_mate_codex_tui` (also deprecated even if Codex returns)
- `steer_visible_codex_run`, `codex`, `codex-reply`

Historical documentation of those Codex tools is retained only for a possible future revival. Skip the rest of this section's Codex defaults.

The server historically exposed (disabled):

- `start_visible_codex_worker`: (DISABLED) launched `codex exec --json` in a visible PowerShell window.
- `start_visible_haiku_composed_codex_worker`: (DISABLED)
- `start_visible_first_mate_codex_pool`: (DISABLED)
- `start_interactive_codex_tui` / `start_interactive_first_mate_codex_tui`: (DISABLED + deprecated)
- `steer_visible_codex_run`: (DISABLED)
- `request_captain_help`: worker-side callback for a stuck visible Codex run to ask the same Claude captain for feedback.
- `list_captain_help_requests`: captain-side view of pending stuck-worker requests.
- `respond_to_captain_help_request`: captain-side response that records the answer and queues steering back to the same Codex run/thread.
- `submit_captain_report`: worker-side final report handoff for interactive TUI runs. It writes `captain_reports/final.json` and `final.md` so Claude receives the result even when the TUI closes.
- `list_captain_reports`: captain-side view of final reports from interactive TUI runs.
- `get_visible_run_status`: reads status and recent log lines from a visible run directory.
- `list_visible_runs`: lists recent visible runs.

Visible start tools force Codex to `gpt-5.6-sol` / `service_tier=fast` and honor the `reasoning_effort` Claude passes for the run, validated against `gpt-5.6-sol`'s accepted values (`minimal` / `low` / `medium` / `high` / `xhigh` / `max` / `ultra`; an unknown or missing value falls back to the `xhigh` default floor). Pass `reasoning_effort` on the start/pool/TUI tools to set the task's effort. The Haiku composer uses Claude `haiku` / `low` and a small default budget before Codex starts.

Use these optional arguments:

- `session_context`: compact current-session briefing for the spawned worker. Include the user goal, decisions already made, files touched, verification results, blockers, and any known mistakes to avoid.
- `resume_session_id`: Codex thread/session id from `get_visible_run_status.thread_id`, `list_visible_runs.thread_id`, or a prior Codex result. Use this when a visible Codex run was cut off or needs continuation.
- `requires_tool_access`: set `true` for SSH, live-device, serial, hardware, network, Docker, package-manager, or external-tool debugging.
- `compose_with_haiku`: optional on `start_visible_codex_worker`; set `true` when `prompt` is a compact brief rather than a final Codex prompt.
- `prompt_brief`: use this with `start_visible_haiku_composed_codex_worker`. Keep it short: objective, decisions, constraints, scope, verification, and non-goals.
- `steer_idle_seconds`: visible Codex runs wait briefly after each turn for queued steering, then close and reap child processes.
- `captain_help`: returned by visible start tools; points to the per-run same-captain help mailbox.
- `no_alt_screen`: interactive TUI tools can preserve scrollback when set to `true`.
- `close_on_exit`: interactive TUI tools close when the underlying TUI exits by default.
- `auto_close_after_report`: interactive TUI tools watch for `captain_reports/final.*` and close the terminal a few seconds after the report by default.

**Default to `Agent`-tool Claude subagents.** Everyday codebase reading, fan-out, implementation, test repair, and tool-heavy debugging all go to an `Agent` call with a built-in `subagent_type`.

Reach for the visible tools in this section only for:

- an explicit user request for the multi-agentic harness, a visible terminal window, or cursor-agent / Cursor workers (then `start_visible_cursor_worker` / `start_visible_first_mate_cursor_pool`)
- an explicit user request for grok agents / grok workers, including to edit, implement, or fix (then `start_visible_grok_worker` / `start_visible_first_mate_grok_pool` with a write sandbox — do not substitute Claude subagents or leave `read-only`)
- Parallel Competition Mode or the Mandatory Parallel Work-Checker gate (then `start_visible_grok_worker` / `start_visible_first_mate_grok_pool`, with `start_visible_agy_worker` next when grok is capped)
- run-dir multi-turn work that must not open a window (then `start_claude_worker`)
- a tiny edit where delegation overhead exceeds the savings (then do it in the manager loop)

Never call `start_visible_first_mate_codex_pool`, `start_visible_haiku_composed_codex_worker`, or `start_visible_codex_worker` - those are Codex-disabled.

## Deprecated: Interactive TUI mode

`start_interactive_codex_tui` and `start_interactive_first_mate_codex_tui` remain available only when the user explicitly asks for a hands-on interactive Codex terminal; tell the user when choosing this deprecated path. TUI mode can flash-close, cannot accept programmatic bridge steering in an already-open terminal, and relies on the worker remembering `submit_captain_report` for captain handoff. It is not the fallback when routing is uncertain.

## Cursor Agent Worker Backend (added 2026-08-26; explicit-request path)

**Explicit-request path.** cursor-agent in a visible console is the preferred visible-window worker when the user asks for the multi-agentic harness, for cursor-agent, or for Cursor workers. Default model is `cursor-grok-4.6-xhigh-fast` (grok 4.6 xhigh Max Mode fast; Cursor Max Mode in `~/.cursor/cli-config.json` unlocks the 1M window). Everyday Claude delegation still uses the `Agent` tool (Subagent Locality): do **not** Bash `cursor-agent -p` from a Claude session; call these MCP tools instead.

The server exposes:

- `start_visible_cursor_worker`: launches `cursor-agent -p --output-format stream-json --trust --approve-mcps --sandbox disabled --workspace <cwd> --model cursor-grok-4.6-xhigh-fast` (`--mode plan` when sandbox is read-only, `--force` when writes are allowed) in a new console window via `cursor_worker_runner.py`. Print mode has no `--prompt-file` and rejects stdin, so long briefs are executed by a short bootstrap that Reads `prompt.md` under the run directory. Every turn's answer is auto-written to `captain_reports/final.json` / `final.md`. On Windows the runner injects Git Bash (`MSYSTEM`/`EXEPATH`/`SHELL` + `Git\\bin` on PATH) so cursor-agent's Shell tool does not fall through to the WSL `bash.exe` stub.
- `start_visible_haiku_composed_cursor_worker`: compact `prompt_brief` expanded by Claude Haiku, then cursor-agent executes the composed prompt.
- `start_visible_first_mate_cursor_pool`: one cursor-agent process with native Task/subagent capability left enabled, using the same `_first_mate_prompt` brief as the other first-mate pools.
- `steer_visible_cursor_run`: queued steering while the window is idle; otherwise interrupt + `--resume <session_id>` (session id is stable across turns; probed live).

Default is always **Cursor Grok 4.6 Extra High Fast · MAX** (`--model cursor-grok-4.6-xhigh-fast`, `~/.cursor/cli-config.json` `"maxMode": true`). The start tool turns Max Mode on if it was off. `reasoning_effort` selects among `cursor-grok-4.6-{low,medium,high,xhigh}-fast`. Pass `model` only when the owner names another Cursor model. Do not silently pick Composer, Kimi, Opus, or a non-fast / lower-effort grok slug.

Layer 2 callback: `~/.cursor/mcp.json` `mcpServers.agent-visibility` points at the deployed bridge. The start tool merges that entry additively. Workers also get `--approve-mcps`.

## Grok Worker Backend (added 2026-07-14; explicit-request path as of 2026-08-15)

**Explicit-request path.** grok-4.6 in a visible PowerShell window is the grok-CLI backend of the multi-agentic harness, used when the user asks for grok specifically or for Parallel Competition Mode / Work-Checker (Subagent Locality keeps the everyday default on `Agent`-tool Claude subagents; the preferred visible worker is cursor-agent). The native `subagent_type: "grok"` alternative is gone: it needed the removed local gateway. See Mandatory Spawn Path and `references/legacy-backends.md`. Codex remains disabled.

The server exposes:

- `start_visible_grok_worker`: launches `grok --prompt-file <prompt.md> --output-format streaming-json --cwd <cwd> --permission-mode bypassPermissions -m grok-4.6 --reasoning-effort xhigh [-r <sessionId>]` in a separate visible PowerShell window, saves prompt/event logs, and returns a run directory. (`-p`/`--single` and `--prompt-file` are alternative ways to supply the prompt - confirmed live that combining them errors with `a value is required for '--single <PROMPT>'` - so the runner uses `--prompt-file` alone.) Every turn's answer is auto-written to `captain_reports/final.json` / `final.md` (Layer 1 callback, see "Worker Backends & Routing").
- `start_visible_haiku_composed_grok_worker`: Claude passes a compact `prompt_brief`; the Haiku/low composer expands it (the same composer flow the Codex path uses, including its non-fatal fallback to the raw brief on composer failure), then Grok executes the composed prompt.
- `start_visible_first_mate_grok_pool`: launches a single grok-4.6 process with its native subagent capability left enabled (no `--no-subagents`), using the same `_first_mate_prompt` brief as the Codex first-mate pool.
- `steer_visible_grok_run`: sends a captain steering instruction to an existing visible Grok run, mirroring `steer_visible_codex_run`. An idle worker consumes the queued instruction within a second; an active worker is interrupted best-effort (Ctrl+C/taskkill) when a launcher pid is known, then resumed with `grok -r <sessionId>`. Grok has no on-disk session-readiness probe like Codex's thread-file check, so after an interrupt this always launches the resume run directly on the last recorded session id - queued-at-idle delivery is the more reliable v1 path.
- Grok workers share the backend-agnostic read/report/help tools unchanged: `get_visible_run_status`, `list_visible_runs`, `submit_captain_report`, `list_captain_reports`, `request_captain_help`, `list_captain_help_requests`, `respond_to_captain_help_request` (see the callback-model limitation in "Worker Backends & Routing" for the live-MCP-callback caveat on `submit_captain_report` / `request_captain_help`).

### Grok effort (grok-4.6 xhigh)

Grok 4.6 xhigh fully supersedes grok 4.5. xhigh is available in both grok Build CLI and cursor-agent CLI. For grok Build CLI, pass `-m grok-4.6 --reasoning-effort xhigh`, or omit the flag so `~/.grok/config.toml` `default_reasoning_effort = "xhigh"` applies. For Cursor workers from this harness, use `start_visible_cursor_worker` (default `--model cursor-grok-4.6-xhigh-fast`) with Cursor Max Mode on (`~/.cursor/cli-config.json` `"maxMode": true`). Do not Bash `cursor-agent -p` from a Claude session. Pass a lower `reasoning_effort` only when a lower tier is deliberately wanted.

### Machine setup: `~/.grok/config.toml` MCP entry

To let a Grok worker reach the shared MCP tools (Layer 2 callback), the bridge added this to `~/.grok/config.toml` (backed up first to `config.toml.bak`, merged additively - the existing `[mcp_servers.kicad]` / `[mcp_servers.altium]` entries were preserved):

```toml
[mcp_servers.agent-visibility]
command = "C:/Users/jonny/AppData/Local/Python/pythoncore-3.14-64/python.exe"
args = ["C:/Users/jonny/.agent-bridge/visible_agent_bridge.py"]
enabled = true

[mcp_servers.agent-visibility.env]
```

This points at the **deployed** bridge copy (matching how Codex's own `agent-visibility` MCP wiring points at the deployed copy, not the dev repo), so it keeps working once the manager syncs this addition from `claude-manages-codex-bridge/` into `~/.agent-bridge/`.

## Antigravity / Gemini (agy) Worker Backend (added 2026-07-14; visible-window path)

The next rung below grok on the explicit-request visible-window ladder (see "Worker Backends & Routing" above and `references/legacy-backends.md` for a condensed summary). Use it when the harness was explicitly requested and grok is capped or exhausted, or when the owner explicitly asks for Antigravity/Gemini (see "Default routing policy" above). It drives the standalone `agy` CLI directly under its own Google login (`~/.gemini/oauth_creds.json`) and separate quota, so it is unaffected by the removal of the local gateway; the native `agy-gemini-*` subagent types are the part that is gone with that gateway.

The server exposes:

- `start_visible_agy_worker`: launches `agy -p "<prompt>" --model "<model>" --dangerously-skip-permissions --add-dir <cwd>` (running with `cwd` set to the target directory) in a separate visible PowerShell window, saves prompt/output/display logs, and returns a run directory. Every turn's raw stdout is auto-written to `captain_reports/final.json` / `final.md` (Layer 1 callback - the ONLY callback path for agy, see "Callback model" above).
- `start_visible_haiku_composed_agy_worker`: Claude passes a compact `prompt_brief`; the Haiku/low composer expands it (the same composer flow the Codex/Grok paths use, including non-fatal fallback to the raw brief on composer failure), then agy executes the composed prompt.
- `steer_visible_agy_run`: sends a captain steering instruction to an existing visible agy run. An idle worker (in its steering window) consumes the queued instruction within a second, running `agy --continue` inside the SAME still-open window. A closed or interrupted run instead launches a brand-new `start_visible_agy_worker` run whose first turn is itself `agy --continue` (internal `resume_continue=True` knob) - this reaches the same underlying conversation only because `--continue` is cwd-scoped (see "No session id" below), not because any thread id is tracked. No first-mate pool tool is offered for agy (single worker only; the spec did not call for one).
- agy workers share the backend-agnostic read/report/help tools unchanged: `get_visible_run_status`, `list_visible_runs`, `submit_captain_report`, `list_captain_reports`, `request_captain_help`, `list_captain_help_requests`, `respond_to_captain_help_request` - the allowlist accepts `metadata.agent == "agy"`, but nothing in the agy worker's own prompt tells it to call them (see "Callback model" above), so these only matter if Claude calls them directly against an agy run directory.

### agy is plain text, not streaming JSON

Unlike Codex (`--json`) and Grok (`--output-format streaming-json`), `agy` has no structured event stream: `agy --help` exposes no `--output-format`/`--json`-style flag. The runner cannot parse `type: "text"/"end"/"error"` events the way the Codex/Grok runners do - it runs `agy` as one blocking call per turn, redirects stdout/stderr to separate temp files (`1> ... 2> ...`, not merged), appends the full stdout to `output.txt` + `display.log`, and writes `captain_reports/final.md`/`final.json` from that turn's **complete, unfiltered** stdout. stderr is logged to `display.log` only and never enters `output.txt` or the captain report. Because there is no incremental streaming, the visible window shows nothing new between "Starting Antigravity new/resume turn" and the turn's exit - this is expected, not a hang, for the turn durations observed live (single-digit seconds for a short prompt).

### agy effort is baked into the model name

`agy` has no `--reasoning-effort` flag at all. Effort is selected by picking a different `--model` value:

```
AGY_MODELS_BY_EFFORT = {"high": "Gemini 3.7 Flash (High)", "medium": "Gemini 3.7 Flash (Medium)", "low": "Gemini 3.7 Flash (Low)"}
AGY_DEFAULT_MODEL = "Gemini 3.7 Flash (High)"
```

`start_visible_agy_worker`'s `reasoning_effort` parameter (default `"high"`) is looked up in this table via `_agy_model_for_effort`; anything outside `low`/`medium`/`high` (case-insensitive) falls back to the `"high"` model. `agy models` also lists non-Gemini options (`Gemini 3.1 Pro (Low|High)`, `Claude Sonnet 4.6 (Thinking)`, `Claude Opus 4.6 (Thinking)`, `GPT-OSS 120B (Medium)`) that this bridge does not route to - the effort table only covers the three Gemini 3.7 Flash tiers the owner asked for.

### agy has no session id - `--continue` is cwd-scoped, not thread-scoped

`agy` never prints a session/conversation id on a plain-text turn. `agy --help` does expose `--conversation <id>` (resume a specific conversation) alongside `--continue`/`-c` (resume the **most recent** conversation for the current working directory), but with no id ever surfaced in stdout to capture, `--conversation <id>` is unusable from this bridge. Every resume in this backend therefore uses `--continue`, which is a **best-effort, cwd-scoped** resume: it reaches whatever agy conversation was most recently active in that directory, not a specific tracked thread. This is weaker than Grok's `-r <sessionId>` or Codex's thread-file resume - if another agy conversation is started in the same cwd between a run closing and a steer/resume call, `--continue` would pick up that other conversation instead. Verified live (2026-07-14): a `steer_visible_agy_run` call on a fully closed run correctly recalled the exact marker text from the original run's first turn after a `launched_resume` follow-up, confirming `--continue` does carry real context across process launches within a cwd, subject to the caveat above.

### Long-prompt inline handling

`agy` has no `--prompt-file` flag; the full prompt (including the permission contract and session-context bootstrap, when not using the Haiku composer) is passed inline as a single `-p` argument via PowerShell array splatting (`& $Agy @argsList`), the same mechanism Codex/Grok use for their own long arguments. This avoids `cmd.exe`'s 8191-character line limit (agy.exe is a real executable, not a `.cmd` shim), but very large prompts are still subject to the OS process-argument limit (Windows `CreateProcess` command-line cap, roughly 32K characters combined). Prefer `start_visible_haiku_composed_agy_worker` for large captain briefs, matching the existing Codex/Grok guidance.

## Active Steering Loop

**Default path (`Agent` subagents):** wait for the result (or steer mid-flight with `SendMessage`), review the returned report/diff, and re-spawn with a repair brief if needed. **Explicit-request visible path:** start a visible worker, arm its `watch_command`, poll `get_visible_run_status`, steer with `steer_visible_grok_run` / `steer_visible_agy_run`, and review the run's diff and `captain_report` before reporting anything.

Claude actively manages visible and headless (`start_claude_worker`) runs instead of letting them drift. An explicitly requested deprecated TUI run is user-steered in the terminal and must be reviewed through its sidecar metadata/session artifacts plus `captain_report` afterward.

1. **Start the worker:** spawn one `Agent` subagent (or a parallel fleet of them) with the goal, constraints, and acceptance criteria. Use a visible worker on an explicit harness request, or `start_claude_worker` for windowless run-dir work, per the Mandatory Spawn Path.
2. Poll with `get_visible_run_status`; read the tail, pending steer count, pending help requests, thread/session id, status, and `captain_report`.
3. At least every 10 minutes for long-running fleets, run the captain checkup script (see "Mandatory 10-Minute Direct Supervision"), then verdict and steer. A status poll or "still running" check is not a pass.
4. Periodically check up with active agents before they spiral: ask for a compact health/status checkpoint, current assumption, blocker, next action, and expected verification. Use short steering notes; do not wait for obvious failure if output quality is drifting, confused, or bug-prone.
5. If `pending_help_requests` is nonzero, read `help_requests` or call `list_captain_help_requests`, then answer with `respond_to_captain_help_request`.
6. When a worker needs correction, narrowing, extra context, changed priorities, or a review checkpoint: for visible runs use the matching `steer_visible_grok_run` / `steer_visible_agy_run`; for headless use `steer_claude_run`; for Sonnet subagents use `SendMessage` (or a follow-up Agent with a repair brief). **Never** `steer_visible_codex_run` / `codex-reply` (disabled).
7. When multiple agents converge on the same root cause or design decision from different directions, consolidate it into one canonical world model and steer every active run to that model. Do not let stale assumptions keep running in parallel.
8. If a headless/visible worker is right to escalate, ask the user the specific decision question yourself, then call `respond_to_captain_help_request` with the user's answer. Sonnet subagents return a blocker and stop (no captain-help mailbox).
9. Prefer steering an existing worker over starting a new one. For visible runs the matching `steer_visible_*` tool interrupts by default. For headless, `steer_claude_run` defaults to queue/resume (`interrupt_current_turn=False`); pass `True` to interrupt.
10. If Claude changes permission intent mid-session on a visible/headless run, pass the updated `sandbox` in the steer call.
11. If a visible window closed, resume via the matching visible steer / `steer_claude_run` / `respond_to_captain_help_request`. Start fresh only for unrelated work or polluted context.
12. Non-interactive visible/headless workers report through structured run artifacts / `captain_report`. Sonnet subagents report in their returned message.

Keep steering notes short. State the decision, changed scope, files or tests to focus on, and required next response shape. Do not restate the whole task unless the thread lost context.

## Mandatory 10-Minute Direct Supervision

While any visible or headless worker / fleet is active (cursor-agent, grok, agy, `start_claude_worker`; not everyday `Agent` subagents), the captain runs a direct supervision pass at least every 10 minutes. This is supervision and review of the work itself, not a liveness probe: confirming the process is still running, or reading only the `status` field, does not count as a pass. A liveness or status-only poll never counts. **Alive is not on-track** — a worker can be busy implementing the wrong thing.

### The checkup script (required)

Do not improvise a `ps` / `Get-Process` / `status.json` peek. Run the bundled script, read its briefing, then verdict and steer.

Immediate (first pass after spawn, and any time you need evidence now):

```bash
python "$HOME/.agent-bridge/captain_checkup.py" --run-dir "<run_dir>" --cwd "<repo>" --since-minutes 10
```

Fleet (every active run under the repo):

```bash
python "$HOME/.agent-bridge/captain_checkup.py" --cwd "<repo>" --active --since-minutes 10
```

The same file also lives next to this skill at `scripts/captain_checkup.py`. The start tools return `supervise_command`: a Bash one-liner that `sleep 600`s, runs the script on that `run_dir`, and prints `CAPTAIN-SUPERVISION-DUE`. Arm it as a background Bash task (`run_in_background: true`) right after spawn, in addition to `watch_command`.

- `watch_command` wakes you when the run **finishes**.
- `supervise_command` wakes you every **10 minutes** with a direction briefing while it is still working.
- On `CAPTAIN-SUPERVISION-DUE`: read the script output (or re-run the script), issue the verdict, steer if off-track, then **re-arm** `supervise_command` if the run is still non-terminal.

The script prints recent `display.log` work, parsed tools/commands, git snapshot, captain-report, and unanswered help. It cannot fill the verdict. Flags such as `ALIVE_ONLY_NOT_A_VERDICT`, `STALE_OUTPUT_*`, `PENDING_HELP`, and `PID_DEAD_STATUS_STILL_RUNNING` are hints, not a pass.

### Every pass must do all of the following

1. Run `captain_checkup.py` (or read the `supervise_command` output that just woke you). Then read the worker's actual recent work — commands run, files touched, stated reasoning, and output produced since the last pass. `get_visible_run_status` is extra, not a substitute for the script.
2. Check the captain-help mailbox and the pending steer queue (the script lists both).
3. Render an explicit on-track / off-track verdict against Claude's stated architecture, acceptance criteria, and permission contract. Record the verdict in the bridge ledger for long-running fleets.
4. Act on the verdict immediately. If off-track, drifting, or approaching an expensive or irreversible step: send a short captain correction through the matching steer tool (`steer_visible_cursor_run` / `steer_visible_grok_run` / `steer_visible_agy_run` / `steer_claude_run`) that quotes or names the specific reviewed output it is correcting. If on-track: say so in the ledger, and request a compact checkpoint (current assumption, blocker, next action, expected verification) whenever the next milestone is unclear.
5. Note when the next pass is due (10 minutes or less) and re-arm `supervise_command` before returning to other work.

A steer issued without first reading the recent work is not supervision, and a read without a verdict is not review. If two consecutive passes are missed, treat it as a supervision failure: stop launching new delegation, re-read the full ledger and each active run's recent output, and re-establish verdicts before continuing.

## Completion Watcher Contract

The bridge never wakes Claude when a Codex run finishes: start tools are fire-and-forget, and an idle Claude turn is never re-invoked by the MCP server. Without a watcher, a finished worker sits unnoticed while Claude "waits" forever.

- Immediately after every default non-interactive spawn or resume - single worker, pool, or steer follow-up - arm **both** `watch_command` and `supervise_command` as background Bash tasks (`run_in_background: true`). `watch_command` exits when the run reaches a terminal state. `supervise_command` sleeps 10 minutes, runs `captain_checkup.py`, and prints `CAPTAIN-SUPERVISION-DUE`. An explicitly requested deprecated TUI also returns a watcher that terminates on closure or a captain report.
- Never end a turn waiting for a visible/headless worker without a watcher armed on every active run, and without a supervision alarm armed if the run may last more than a few minutes.
- Watchers detect completion; they do not replace the 10-minute direct supervision passes, which review direction while the run is still working. A liveness or status-only poll never counts.
- On wake, read the run's `captain_report` / status and continue: review the result, steer, or report to the user. Do not re-arm a watcher on a run that already reached a terminal state.

## Codex Run Ownership and Subagent Handoff

Every Codex run has exactly one owner: the main Claude manager loop. Ephemeral Claude subagents die with their task, and any watcher or supervision duty they held dies with them - a Codex run started inside a subagent and left running when the subagent returns is an orphan nobody will ever check on.

- Do not spawn Codex runs from ephemeral Claude subagents. The Routing Mandate already routes fan-out through Codex itself: when Codex work is needed, the manager spawns it directly and arms the watcher in its own loop.
- A subagent that must start a Codex run anyway has exactly two valid exits: (1) stay alive until the run reaches a terminal state and fold the outcome into its final report, or (2) hand the run off - its final message must list every run it started under a "Codex runs handed off" heading with `run_dir`, `thread_id`, current status, and `watch_command` so the main loop can adopt them.
- The manager adopts handed-off runs immediately, before any other work: arm each `watch_command` as a background task, record the run in the bridge ledger, and fold it into the 10-minute supervision rotation.
- Safety sweep: after any Claude subagent returns - and at the start of any session that may have inherited work - call `list_visible_runs` on the working repo and adopt every run still in a non-terminal status. An active run with no owner is a supervision failure to fix on the spot.

## Same-Captain Help Callback

Visible Codex prompts include a run-specific captain-help callback. When a spawned worker is blocked, confused, sees conflicting evidence, lacks confidence for `workspace-write`, or needs user-level approval, it should call `request_captain_help` with the visible `run_dir`, then stop its current turn with `Outcome: blocked_waiting_for_captain`.

Claude owns the response:

- use `get_visible_run_status` or `list_captain_help_requests` to inspect the request
- answer with `respond_to_captain_help_request` when Claude can decide
- ask the user a focused question when the request needs owner judgment, credentials, destructive permission, product direction, or risk acceptance
- after the user answers, send the decision back with `respond_to_captain_help_request`
- for a deprecated interactive TUI run, expect the answer to be a recorded mailbox artifact; direct terminal steering or a resumed TUI may still be needed because queued steering cannot type into an already-open TUI

Do not route same-captain help through `start_visible_claude_advisor` unless Claude explicitly wants a separate one-shot advisor. The point of the callback is to keep the spawned worker connected to the captain that launched it.

## Codex Subagents

Codex only spawns subagents when explicitly asked. Claude must be explicit.

Available built-in Codex agents:

- `explorer`: read-heavy codebase exploration.
- `worker`: implementation and fixes.
- `default`: general fallback.

Personal custom Codex agents installed for this bridge:

- `claude-explorer`: no-edit, low-cost scouting, Python-backed skill use, and context distillation.
- `claude-implementer`: bounded implementation under Claude's scope.
- `claude-reviewer`: no-edit correctness/security/regression review.
- `claude-debugger`: full-tool SSH, live-device, network, serial, and command-heavy debugging after Claude explicitly allows full tool access.

Use subagents for independent, noisy, read-heavy, or parallelizable work. Avoid subagents for tiny edits or where the coordination overhead exceeds the benefit.

## First Mate Pattern

When a task requires codebase understanding, do not spend Claude tokens reading everything. **Claude is the captain.** Fan out **`Agent`-tool scouts** with read-only briefs (one `Explore` / read-only `general-purpose` subagent per area, issued in a single message), collect their summaries, then decide. On an explicit harness request, use visible grok scouts instead (`start_visible_grok_worker` per area, or one `start_visible_first_mate_grok_pool` coordinator).

Do **not** start `start_visible_first_mate_codex_pool` or any Codex first-mate path (disabled).

Default first-mate settings:

- default scout: one `Agent`-tool subagent per area (explicit-request alternative: `start_visible_first_mate_grok_pool`, or one visible grok worker per area)
- permission intent: read-only for mapping; write only after Claude chooses a scoped path
- max fan-out: 6 unless the task is clearly smaller
- one level deep: scouts return results; they do not spawn further agents

First-mate responsibilities (executed by Claude as captain + the scout fleet):

- spawn parallel read-only scouts for independent codebase areas
- summarize architecture, key files, tests, data flow, risks, and likely edit points
- optionally update `.claude-codex/BRIDGE.md` for long multi-agent work
- return a compact manager brief for Claude
- avoid dumping raw logs or large code excerpts into Claude's context

For broad codebase understanding, batch scouts with:

```text
Read-only codebase map. Do not edit files. Cover your assigned subsystem. Return architecture, key files, tests, risk areas, and recommended implementation plan as a compact manager brief.
```

## Session Context and Resume

Do not treat spawned Codex as a blank chat.

Before starting or resuming Codex:

1. Build a compact `session_context` from the live Claude conversation: user goal, decisions, constraints, prior errors, run ids, thread ids, changed files, verification, and open questions.
2. If context predates the current Claude window or was compacted, invoke `read-past-sessions` or tell Codex to use it immediately.
3. When the worker needs broad project/codebase context, tell Codex to use read-past-sessions' Graphify memory flow before brute-force file reading: try `memory-query`; if no graph exists, build/refresh the curated corpus with `memory-corpus` plus `memory-codex --build-graph` when Codex CLI is authenticated, or `memory-graph` as deterministic fallback.
4. Pass `session_context` into the non-interactive visible CLI start or pool tool by default. Pass it into a TUI start tool only for an explicitly requested deprecated interactive run.
5. If continuing previous work, pass `resume_session_id` instead of starting a new root run. For Codex this is the `thread_id` shown by `get_visible_run_status` or `list_visible_runs`.
6. For an already-running visible worker, call the matching `steer_visible_grok_run` / `steer_visible_agy_run` instead of starting another root session.
7. Record resumable ids in `.claude-codex/BRIDGE.md`.

Use a fresh Codex session only for unrelated work or when the old session is polluted.

## Permission Policy

Default the permission intent to `read-only`/no-edit unless Claude is fully confident the work is well-scoped and safe. The actual visible Codex process still has full tool access so Python skills and developer tooling work.

Use `workspace-write` only when all are true:

- Claude has chosen the implementation direction.
- Target files or ownership boundaries are clear.
- The task is not destructive, broad, security-sensitive, or data-loss-prone.
- Parallel writers will not touch the same files.

If not fully confident, use no-edit intent and ask Codex to return findings, risks, and questions. Claude decides next.

Use `danger-full-access` intent only when the user or Claude explicitly authorizes broad/full tool work. This bridge has user authorization to support full-tool Codex debugging; do not cripple Codex with a literal read-only process sandbox, because that breaks Python and skills.

Subagents inherit the parent Codex process access unless a custom agent overrides it. Start the root Codex session with the intended permission intent. Use `claude-debugger` for full-tool subagent tasks.

## Delegation Patterns

The brief templates below are backend-agnostic: by default hand them to an `Agent`-tool Claude subagent, and use the named visible-worker tool on an explicit harness, visible-window, or grok-agent request (Subagent Locality; owner-requested grok-to-edit is writable `start_visible_grok_worker`). The permission wording maps to the `sandbox` argument on the visible/headless runners and to plain read-only vs write intent in an `Agent` brief.

### No-Edit Scout

Use when Claude needs context before deciding.

Launch one or more visible grok workers with `sandbox="read-only"` (enforced, not merely requested). For independent areas, launch one per area back to back:

```text
Read-only scout. Do not edit files.

Areas:
1. <area A>
2. <area B>

For each: relevant files, current behavior, risks, unanswered questions. Return a consolidated summary only.
```

### Bounded Implementation

Use when Claude is confident enough to permit writes.

Launch a visible grok worker with `sandbox="workspace-write"`. For file-disjoint fan-out, one worker per work item, launched back to back. Secondary only: `start_claude_worker(..., sandbox="workspace-write")` when the run must be windowless.

```text
Claude has chosen the implementation path. Implement only the listed scope.

Scope:
- Goal: <goal>
- Files/areas: <paths>
- Non-goals: <what not to touch>
- Acceptance criteria: <criteria>
- Verification: <commands>

Do not change architecture. If the scope is ambiguous, stop and report the blocker (do not re-delegate). Run the verification and paste proof.
```

### Live Debugging, SSH, and Tool Access

Use when the worker must run real developer tools, SSH, serial, package managers, or hardware/runtime debugging.

Prefer a visible grok worker with `requires_tool_access: true` / `sandbox: danger-full-access`. Secondary: `start_claude_worker` with `sandbox: danger-full-access`.

```text
Claude explicitly authorizes full tool access for this debugging scope.
Start with read-only inspection, report commands and results, and stop before destructive actions, service restarts, credential changes, data deletion, firmware flashing, or persistent system changes unless the brief already allows them.

Scope:
- Target: <host/device/repo>
- Goal: <observable issue>
- Allowed commands/tools: <ssh/tests/logs/etc.>
- Forbidden actions: <destructive or persistent actions>
- Verification: <what proves the issue is fixed>
```

### Parallel Implementation

Use only for file-disjoint work. Launch N visible workers back to back (one work item each), or use the first-mate pool. Do not ask a single worker to spawn its own subagents (one-level-deep rule).

```text
You own only work item K of N. Edit only your assigned files. Verify and return changed files plus verification proof.
```

If file ownership is not clear, do not parallelize writes.

### Review Pass

After a non-trivial diff, launch a no-edit visible worker (or review yourself as captain):

```text
Read-only review of the current diff against Claude's stated architecture and acceptance criteria. Do not edit files. Findings first, ordered by severity, with file references. If no issues, say so and list residual risk.
```

## Token Efficiency

- **Default:** a compact captain brief in an `Agent` call with a built-in `subagent_type`. On an explicit harness request: `start_visible_haiku_composed_grok_worker` (Haiku expands the brief) or a final prompt through `start_visible_grok_worker`. No Codex.
- For independent fan-out, issue several `Agent` calls in one message; on an explicit harness request, launch several visible workers back to back or one `start_visible_first_mate_grok_pool`. Do not call `start_visible_first_mate_codex_pool`.
- Keep briefs to decisions and constraints: goal, scope, permission intent, files/areas, non-goals, verification, open questions.
- Do not restate this entire skill into every worker prompt; workers get their own injected rigor contract.
- Send distilled briefs, not the whole Claude transcript. For long history, tell the worker to use `read-past-sessions`.
- For broad project context, have the worker query read-past-sessions Graphify memory before brute-force reading many sources.
- Ask the worker to summarize the codebase before Claude reads files directly.
- Put noisy exploration, logs, and test repair inside workers, not the manager loop.
- Ask workers to return summaries, changed files, verification results (with pasted proof for grok), blockers, and questions.
- Avoid making Claude read raw logs unless the worker cannot summarize them.
- For visible and headless runs, reuse `resume_session_id` / steer when follow-up context matters; start fresh for unrelated work.
- Keep fan-out one level deep - no recursive subagent trees from workers.

## Visibility Standard

Tell the user which backend you spawned (`Agent` subagent / visible grok / visible agy / headless claude_worker). On the explicit-request harness paths, workers run in their own terminal window so the owner can watch them.

When launching visible work:

1. Tell the user a visible CLI worker is opening and what it is doing.
2. Include the run directory in the bridge ledger.
3. Use `get_visible_run_status` for concise progress checks instead of reading raw JSONL.
4. Steer with the matching `steer_visible_*_run` / `steer_claude_run` for that backend - never `steer_visible_codex_run` (disabled).
5. Read structured run status / `captain_report` for handoff.
6. Do not promise hidden thoughts. Say "progress, reasoning summaries, commands, and implementation state" instead.

## Bridge Ledger

For non-trivial multi-agent work, use `.claude-codex/BRIDGE.md` in the repository root.

If the file does not exist, create:

```markdown
# Claude-Codex Bridge

## Goal

## Architecture Decisions

## Worker Ledger

| Worker | Thread ID | Sandbox | Scope | Status | Next Action |
| --- | --- | --- | --- | --- | --- |

## Visible Runs

| Run | Directory | Purpose | Status |
| --- | --- | --- | --- |

## Changed Files

## Open Questions

## Verification
```

Keep it concise. Record:

- Claude decisions
- Codex root `threadId`s
- subagent plan and ownership
- file scopes
- verification status
- blockers and next actions

Do not paste full transcripts.

## Claude Review Standard

Before final response, Claude independently checks:

- diff scope matches the user request
- implementation follows Claude's architecture
- parallel workers did not conflict
- verification was run where feasible
- no unrelated files or metadata changed
- no destructive or broad-permission action was taken without user approval

If the result is wrong, re-steer with the matching `steer_visible_grok_run` / `steer_visible_agy_run` (visible), `steer_claude_run` (headless), or `SendMessage` (Sonnet subagent) with a specific repair instruction. Never `steer_visible_codex_run` / `codex-reply`. Do not ask the worker to review itself as the only validation step.
