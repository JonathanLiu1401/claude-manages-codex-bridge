---
name: claude-manages-codex
description: Multi-Agentic Harness - Claude is captain (architect/QA/reviewer); workers do implementation. ALWAYS spawn via native Agent-tool subagents first (subagent_type "grok" default in proxy/clx sessions; agy-gemini-3-1-pro / agy-gemini-3-5-flash on grok exhaustion; model sonnet as always-available fallback). Do NOT default to start_claude_worker, start_visible_*, or any Codex tool. start_claude_worker is secondary (headless run-dir / non-proxy only). start_visible_* is legacy on-request only (Competition Mode / Work-Checker). Codex is disabled. Trigger for "delegate to grok", "use the multi-agent harness", "parallelize with subagents", "first mate", or any coding task where Claude decides and a worker codes.
---

# Multi-Agentic Harness (internal id: claude-manages-codex)

> **Rename note (2026-07-15, updated 2026-07-20):** this skill is branded the **Multi-Agentic Harness**. Its internal id / MCP tool prefix / install directory remain `claude-manages-codex` for compatibility. Much of the older prose further down still mentions Codex / `start_visible_*` because those were the original backends - **IGNORE those defaults**. The authoritative spawn policy is the **Mandatory Spawn Path** section immediately below. Codex is DISABLED. Visible-window tools are legacy/on-request only.

Use Claude's active manager model as captain, executive architect, QA tech lead, and reviewer. Delegate low-level work to workers - by default **grok-4.5 as a native Agent-tool subagent**.

## Mandatory Spawn Path (2026-07-20 - hard rule, overrides older sections)

**ALWAYS use native subagents first.** Do not open PowerShell windows. Do not call Codex tools. Do not reach for `start_claude_worker` or `start_visible_*` unless a condition below explicitly allows it.

| Priority | When | How to spawn | How to steer |
| --- | --- | --- | --- |
| **1 (DEFAULT)** | Proxy-backed session (`clx`, or plain merged with CLIProxyAPI) and default worker | `Agent` tool, `subagent_type: "grok"` | `SendMessage` |
| **1b** | Grok capped/exhausted, or owner asks for agy/Gemini | `Agent` tool, `subagent_type: "agy-gemini-3-1-pro"` (harder) or `"agy-gemini-3-5-flash"` (fast) | `SendMessage` |
| **1c** | Proxy/grok unavailable, or task needs Claude-only capability | `Agent` tool, `model: sonnet` (or Explore / general-purpose) | `SendMessage` / follow-up Agent |
| **2 (secondary)** | Native cannot apply: non-proxy session that still needs grok; long-running run-dir protocol; explicit headless multi-turn with `steer_claude_run` | `start_claude_worker(model="grok-4.5", ...)` then arm `watch_command` | `steer_claude_run` |
| **3 (legacy, on request only)** | Owner asks to watch a terminal, OR task needs grok-CLI-only Parallel Competition Mode / Work-Checker | `start_visible_grok_worker` / pool / haiku-composed | `steer_visible_grok_run` |
| **NEVER** | Codex path | `start_visible_codex_*`, `codex`, `codex-reply`, interactive Codex TUI | - disabled |

**Anti-patterns (agents still do these - stop):**
- Calling `start_visible_haiku_composed_codex_worker` / `start_visible_first_mate_codex_pool` / `start_visible_codex_worker` because an older section still names them. **Codex is disabled.**
- Calling `start_visible_grok_worker` as the default "delegate to grok" path. Default is `Agent` + `subagent_type: "grok"`.
- Calling `start_claude_worker` for every delegation when a native `Agent` spawn would work. Prefer native.
- Treating "Windowless worker backends" and "Visible Agent Harness" sections below as the default loop. Those are secondary/legacy docs.

Parallel fan-out: issue multiple `Agent` calls in one message (or a Workflow). Do not serial-spawn.

## Core Model

- Claude owns architecture, task decomposition, acceptance criteria, risk calls, worker assignment, active steering, and final review. In the first-mate flow, Claude is the captain.
- **The worker owns cheap exploration, first-pass implementation, test repair, mechanical refactors, and noisy command/log work.** The default worker is **grok-4.5 via native `Agent` (`subagent_type: "grok"`)**. Fallbacks: agy Gemini native subagents, then Claude Sonnet subagents. **Codex is disabled.**
- **Default orchestration surface is the `Agent` tool and Workflows** (native subagents: `grok`, `agy-*`, Sonnet). Secondary: `start_claude_worker`. Legacy: `start_visible_*` only for CLI-only extras or on request.
- Claude must review worker output and local diffs before claiming completion - antagonistically for grok (see "grok-4.5 rigor and mandatory adversarial review").
- Prefer delegating to a worker over doing implementation in the manager loop.
- The Claude manager model does not write implementation code by default. It writes plans, contracts, constraints, acceptance tests, review findings, steering notes, and the final user response. Route code edits to the worker (default grok-4.5 native) unless the edit is tiny, every worker path is unavailable, or the user explicitly asks Claude to code directly.
- Claude sets the worker's reasoning effort per task by judged difficulty. Token savings come from routing work off the manager and matching effort to difficulty. (Effort ladders differ by backend - grok CLI caps at `low`/`medium`/`high`; `start_claude_worker` and agy accept `low`…`max`. Native Agent subagents inherit the session effort unless the Agent call sets one.)
- Every new or resumed worker receives session context. For native subagents, put the compact brief in the Agent prompt. For headless/visible runs, pass `session_context`. Tell the worker to use `read-past-sessions` when it needs full transcript history.
- Workers need enough tool access to do real work (skills, SSH, CLIs). For native subagents, encode write vs read-only intent in the brief. For headless/visible runners, `sandbox` maps permission intent: `read-only` means no edits (enforced for grok/claude_worker), not a crippled process sandbox.
- SSH, serial, live-device, hardware, network, Docker, package-manager, and external-tool debugging need full tool access in the brief (or `requires_tool_access: true` / `sandbox: danger-full-access` on headless/visible runners).
- Do not spend manager-model output tokens on boilerplate, long worker prompts, or raw-log analysis a worker can do. Keep Agent prompts compact. For legacy visible-CLI backends only, pass a compact captain brief to the Haiku prompt composer.
- **Spawn path reminder:** native `Agent` first; `start_claude_worker` second; `start_visible_*` only on request / Competition Mode; **Codex disabled**. Interactive TUI tools are deprecated.
- Hidden model reasoning is not displayable. Surface useful progress, summaries, commands, and implementation state instead.

## Worker Backends & Routing (added 2026-07-14; native-first locked 2026-07-20)

**Read "Mandatory Spawn Path" above first.** This section is reference detail only. Do not let older "preferred" wording elsewhere in this file override the native-first table.

Supported backends (in preferred order):

- **Native grok subagent (DEFAULT)** - `Agent` tool, `subagent_type: "grok"`, defined by `agents/grok.md`. Proxy-backed sessions only. See "Native grok subagent backend" below.
- **Native agy Gemini subagents (next on ladder)** - `Agent` tool, `subagent_type: "agy-gemini-3-1-pro"` / `"agy-gemini-3-5-flash"`. Separate agy quota. See "Native agy subagent backend" below.
- **Claude Sonnet native subagent (always-available fallback)** - `Agent` tool, `model: sonnet`. No CLI, no auth, no run-dir machinery.
- **`start_claude_worker` (SECONDARY headless path)** - detached headless `claude -p` via CLIProxyAPI; use only when native Agent spawn does not apply (non-proxy needing grok, explicit run-dir / `steer_claude_run` multi-turn). Tool default model is `claude-opus-5` - pass `model="grok-4.5"` explicitly for default grok work. See "Headless claude_worker backend" below.
- **Grok CLI (legacy visible-window)** - only for Parallel Competition Mode / Work-Checker gate, or when the owner asks for a visible terminal. `start_visible_grok_worker`, `start_visible_haiku_composed_grok_worker`, `start_visible_first_mate_grok_pool`, `steer_visible_grok_run`. See `references/legacy-backends.md`.
- **Antigravity CLI (legacy visible-window)** - `start_visible_agy_worker` etc. **On request only.** Prefer native agy subagents.
- **Codex (gpt-5.6-sol)** - **DISABLED** (owner 2026-07-15: ChatGPT login revoked). Do not route to Codex. Tools remain in code for possible revival only.

### Default routing policy (2026-07-20)

Unless the owner says otherwise:

1. **Default worker MODEL = grok-4.5. Default SPAWN PATH = native `Agent` subagent** (`subagent_type: "grok"`) in any proxy-backed session.
2. **Grok exhausted / owner asks for agy** → native `agy-gemini-3-1-pro` or `agy-gemini-3-5-flash` (grok-4.5 still routes first when available).
3. **Proxy/grok unavailable or Claude-only task** → Claude Sonnet `Agent` subagent.
4. **Native cannot apply** → `start_claude_worker(model="grok-4.5", ...)` (secondary). Never treat this as the everyday default when native works.
5. **Competition Mode / Work-Checker / "open a terminal"** → legacy `start_visible_grok_*` only.
6. **Codex** → never.
7. **Always call `check_worker_backends` before delegating to headless/visible CLI backends.** For native `Agent` spawns in an already-working proxy session, a live proxy is implied; if the native spawn fails (model not served / 350-tool cap / auth), fall down the ladder and tell the user why.

### Native grok subagent backend (added 2026-07-18)

Spawn with the `Agent` tool, `subagent_type: "grok"`. Defined by `agents/grok.md`: frontmatter pins `model: grok-4.5` and a deliberately small toolset (Read, Write, Edit, Bash, Grep, Glob, TodoWrite, NotebookEdit, WebFetch, WebSearch) - grok-4.5 rejects any request carrying more than 350 tools, and a full plain session can expose far more than that across loaded MCP servers, so the toolset is kept narrow on purpose.

- Appears in Claude Code's own agent list; steer it natively with `SendMessage` (no external process, no window, no `steer_visible_*` tool needed).
- **Precondition:** only works in a proxy-backed session (the `clx` launcher, or a plain session merged with the proxy) whose endpoint actually serves grok. In a plain direct-Anthropic session grok is not a valid native-subagent model - use `start_claude_worker(model="grok-4.5")` there instead.
- `agents/grok.md` bakes the Worker Rigor Contract and a no-further-delegation rule directly into the agent's own system prompt (it is itself a spawned worker and must not delegate further, spawn its own subagents, or re-invoke this skill).
- **Context window (verified 2026-07-19, claude 2.1.21x):** grok subagents and workflow agents get grok-4.5's accurate **~500k window** via `CLAUDE_CODE_MAX_CONTEXT_TOKENS=500000` in the settings.json `env` block (set in the plain and clx worlds). That undocumented env var applies only to model IDs not starting with `claude-` (checked after the `[1m]`/native-1M paths), so grok resolves to 500k with default percentage-based autocompaction against it while Claude models in the same process keep their own catalog windows. Without it, Claude Code budgets unknown model IDs at 200k, and no other mechanism exists (gateway model discovery reads only `id`/`display_name` and discards non-`claude`/`anthropic` ids; capability env vars are inert behind `ANTHROPIC_BASE_URL`; `/v1/models` has no context-length field - Ollama's `ollama launch claude` hit the same wall and ships a hardcoded table exported as `CLAUDE_CODE_AUTO_COMPACT_WINDOW`). Do NOT put `grok-4.5[1m]` in agent frontmatter: subagent resolution can strip the suffix (anthropics/claude-code#45169), and a 1M assumption would overshoot the real 500k ceiling with no compaction safety. Re-verify the env var after Claude Code version bumps (undocumented internal). Main-model grok sessions: use the **`clg`** launcher (`~\.local\bin\clg.cmd`: bare `grok-4.5`, window from the same env var).

### Native agy subagent backend (added 2026-07-19)

Two Google Antigravity **Gemini** models are wired as **native Claude Code subagents** (Agent tool, `subagent_type`), served through CLIProxyAPI's **antigravity** OAuth channel - the non-terminal alternative to `start_visible_agy_worker`. Each draws the agy account's **SEPARATE** quota, never the owner's real Claude/Anthropic subscription. Defined by `~/.claude/agents/agy-*.md` (deployed from repo `plugin/agents/`, junction-shared into `~/.claude-clx`).

- Subagents (capability order): `agy-gemini-3-1-pro` > `agy-gemini-3-5-flash` (Gemini 3.1 Pro / 3.5 Flash High). The agy Claude 4.6 models (opus/sonnet) are deliberately NOT wired - their Antigravity quota bucket's limits are too low to be usable (see Quota below). Owner rule of thumb: `agy-gemini-3-5-flash` = speedy ops, `agy-gemini-3-1-pro` = harder/slower.
- **Routing:** grok-4.5 FIRST (grok-4.5 > agy Gemini); use agy on grok-exhaustion or explicit request. Like any native subagent, only in a proxy-backed session (plain merged / clx).
- **Quota:** the two wired Gemini subagents draw the {gemini flash, pro} bucket (ample - ~96%+ free in practice). The other bucket {Claude opus, sonnet, gpt-oss} has very low limits - its 5-hour window exhausts fast (observed at 0% while Gemini had ~96%) - so the Claude 4.6 models AND GPT-OSS 120B are served but deliberately UNWIRED. Gemini rides free quota.
- **Context windows:** each Gemini subagent pins `<id>[1m]` → ~1M client window (Gemini is natively ~1M). If `[1m]` is stripped in subagent resolution (anthropics/claude-code#45169) the fallback is safe (agy-*→500k global) - under-budget, never overflow.
- **Setup** (`-antigravity-login` + `oauth-model-alias.antigravity` config + the config-needs-a-proxy-RESTART caveat, since Windows fsnotify misses the atomic-save config edit): `docs/setup/agy-antigravity.md`. New agent files need `/reload-plugins` (or restart) to appear in a running interactive session; fresh `claude -p` / workers pick them up automatically. Verified e2e 2026-07-19.
- **Operational caveats:** large-context agy calls occasionally return a **malformed HTTP 200** through the proxy - treat an empty/malformed body as a retry/fallback signal, not success. (The agy Claude 4.6 models were dropped because their bucket's 5-hour limit exhausts too fast to be usable - see Quota above.)
- **`/model` picker (proxy world):** holds exactly ONE non-Claude model - the single `ANTHROPIC_CUSTOM_MODEL_OPTION` slot (tier slots are Claude-only; gateway discovery is dead: OAuth has no static auth token + a claude-prefix filter). So grok OR gemini in the menu, not both; reach the rest via typed `/model <id>` or `clg`. A non-Claude MAIN model needs the `[1m]` suffix for 1M (bare = 500k global); grok stays bare. Detail: `docs/setup/env-vars.md` → "Model selector / picker configuration".

### Headless claude_worker backend (added 2026-07-18; SECONDARY as of 2026-07-20)

`start_claude_worker` is the **secondary** windowless backend - use it only when native `Agent` subagents do not apply (non-proxy session that still needs grok via proxy, long-running run-dir / `steer_claude_run` multi-turn, or an explicit headless request). **Do not use it as the everyday default** when `subagent_type: "grok"` (or agy/Sonnet native) works. Implemented by `claude_worker_runner.py`, which builds a `claude -p --verbose --output-format stream-json --permission-mode <mode> --add-dir <cwd> [--model][--effort] ...` invocation, passes the prompt via STDIN, and sets `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` (from `proxy.json`) and `CLAUDE_CONFIG_DIR` in the child environment - no terminal window opens.

Full live signature: `start_claude_worker(prompt, cwd, title="Claude worker", model=CLAUDE_WORKER_DEFAULT_MODEL ("claude-opus-5"), sandbox="read-only", effort="", session_context="", resume_session_id="", max_budget_usd="", steer_idle_seconds=20, use_proxy=True)`.

- `model`: any model the local CLIProxyAPI gateway (`127.0.0.1:8317`, ~38 models as of 2026-07-19) serves - `grok-4.5`, `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, etc. - honored exactly as passed. The tool's own default is `claude-opus-5`, so pass `model="grok-4.5"` explicitly for default grok work.
- `sandbox` maps to Claude Code CLI permission modes: `read-only` -> `plan` (+ `Write`/`Edit` stripped, enforced not just requested), `workspace-write` -> `acceptEdits`, `danger-full-access` -> `bypassPermissions`.
- `effort`: `low` / `medium` / `high` / `xhigh` / `max`.
- `steer_claude_run(run_dir, instruction, ..., interrupt_current_turn=False)` steers or resumes a run mid-flight. Unlike the visible steers (which interrupt the in-flight turn by DEFAULT), its `interrupt_current_turn` defaults to **False** (queue/resume-oriented) - pass `True` to interrupt. There is no `requires_tool_access` param.
- `use_proxy=False` bypasses the proxy for a direct-Anthropic spawn.
- Full run-dir protocol preserved: `events.jsonl`, `display.log`, `status.json`, `captain_reports/`, `captain_help/`, `steer_queue/` - the same backend-agnostic `get_visible_run_status` / `list_visible_runs` / `submit_captain_report` / `list_captain_reports` / `request_captain_help` / `list_captain_help_requests` / `respond_to_captain_help_request` tools every other backend uses.
- `check_worker_backends` reports a `claude_worker` entry (proxy reachable + model count) alongside `claude_sonnet` / `grok` / `codex` / `agy`.
- Every claude-worker prompt (any model, including grok-4.5 via this tool) auto-carries the Worker Rigor Contract - see "grok-4.5 rigor and mandatory adversarial review" below - but NOT the grok-CLI-only Parallel Competition Mode / Mandatory Parallel Work-Checker extras (`competition_agents`, `best_of_n`, `self_check` are grok-CLI params, not `start_claude_worker` params). Escalate a hard problem to the legacy grok-CLI backend when those extras are wanted.

### Memory (claude-mem) integration (added 2026-07-18)

Headless `claude -p` workers spawned by `start_claude_worker` run under an isolated Claude config dir (e.g. `~/.claude-clx`) with the `claude-mem` plugin enabled. Because of that, claude-mem's SessionStart/PostToolUse/Stop hooks fire for those workers automatically, and their prompts/session-init get passively captured into the shared claude-mem store (the global daemon on `127.0.0.1:37777` backing a SQLite DB + vector store) - no bridge code change needed. Keep this conservative:

- Observation *richness* depends on run length - a short worker turn may produce few or no distilled observations.
- The non-Claude CLI backends (grok CLI, agy CLI) are not Claude Code processes, so they fire no claude-mem hooks and their work is not captured.
- Native `subagent_type: "grok"` **and `agy-*`** subagents run inside the parent Claude Code session, so only that parent session's own claude-mem capture (plugin `claude-mem@thedotmack`) covers their top-level activity.

### Leveraging SuperGrok Heavy (grok "heavy mode")

There is no separate `heavy` CLI flag or model id - SuperGrok Heavy (owner is tier 5) is a subscription tier that raises grok's compute/rate limits, and grok exposes that power through its agent system, which the bridge already uses:

- **Native subagents are ENABLED by default** on every grok worker (the bridge never passes `--no-subagents`), so a single `start_visible_grok_worker` can already spawn parallel child agents ("uses agents efficiently") when the task warrants it.
- **`start_visible_first_mate_grok_pool`** is the explicit fan-out path - a grok root that coordinates native subagents, the grok analog of the first-mate pool.
- **`best_of_n` param** (wired 2026-07-15) on `start_visible_grok_worker` / `start_visible_haiku_composed_grok_worker`: pass `best_of_n=N` (capped 1-6) to run the initial task N ways in parallel and keep the best (`--best-of-n`, initial turn only). The concrete Heavy-tier quality lever - but it costs ~N× tokens, so reserve it for hard, high-value tasks.
- **`self_check` param** (wired 2026-07-15): pass `self_check=True` to append grok's own self-verification loop (`--check`) to the initial turn - a cheap quality boost on top of Claude's review.
- **`[subagents]` config** in `~/.grok/config.toml` (per-agent model pins, roles, personas) is a further lever tuned outside the bridge.

### Strict read-only enforcement (grok)

For a grok worker launched with `sandbox="read-only"`, the bridge now **enforces** no-edit by passing `--disallowed-tools Write,Edit` so Grok's file-mutation tools are removed - it truly cannot edit, not merely asked not to (borrowed from faeton/claude-grok-plugin). Bash is intentionally kept so read-only inspection (Python-backed skills, read-past-sessions, safe read commands) still works - the bridge's read-only means "no edits", not "no commands". Use `read-only` for scouting / second-opinion / review workers; use `workspace-write` or full access when the worker must edit.

*(These three - read-only enforcement, `best_of_n`, `self_check` - were adopted 2026-07-15 after surveying existing grok↔Claude Code plugins; the multimodal / xAI-API-key / older-model-tier features from those plugins were intentionally not adopted, since this harness runs the newer grok-4.5 via the SuperGrok Heavy OAuth CLI.)*

### grok-4.5 rigor and mandatory adversarial review (owner assessment 2026-07-15)

**grok-4.5 is a fast coder but a weak engineer** - roughly gpt-5.3-codex-spark class. Its observed failure modes: it fixates on a single hypothesis, does not consider multiple scenarios, skips edge cases and error paths, and declares work "done" without ever executing it end to end. Treat every grok result as **unverified and probably buggy until you prove otherwise.** Two mechanisms enforce this:

1. **Worker Rigor Contract (automatic).** Every grok worker prompt is prepended with a mandatory contract (`_grok_rigor_contract`) that forces the worker to: enumerate 2-3 hypotheses/approaches and the edge/error/boundary cases before coding; adversarially pressure-test its own change; **actually run it end to end and paste the observed output as proof** (a confident "done" without executed evidence is defined as a failure); and report what it did NOT test plus the top 2 ways it could still be wrong. You do not need to add this to your brief - it is always injected - but your `prompt_brief` should still name the concrete acceptance test and the specific scenarios/edge cases you want covered.

2. **Mandatory Opus-captain adversarial review (you).** Do NOT trust grok's "done." Review its diff and claims **antagonistically, assuming they are wrong**, and specifically:
  - Independently VERIFY end to end yourself - run the tests / CLI / endpoint / repro, read the real output. Grok's own "I tested it" is not sufficient evidence; grok's self-check (`--check`) is weak self-marking, not proof.
  - Hunt the cases grok most likely skipped: the edge/empty/null/boundary inputs, the error branch, concurrency, the opposite of the happy path, and the scenario it fixated away from.
  - Check for tunnel vision: did it fix the reported symptom while missing the root cause or breaking an adjacent case?
  - If it drifted, fixated, or reported success without executed proof, reject and re-steer with the specific missing case - or escalate: raise `reasoning_effort`, set `self_check=True`, or use `best_of_n=2-3` so grok generates and self-selects among multiple attempts on hard tasks.
  - Only report a grok result to the user as done after YOU have executed the acceptance test and seen it pass. This is not optional for grok - it is the primary defense against its weaknesses.

For non-trivial or correctness-sensitive grok work, prefer `best_of_n` (multiple scenarios) and `self_check=True` (its own verify pass) on top of your adversarial review - but they supplement, never replace, the captain's independent e2e verification.

### Parallel Competition Mode (grok-4.5, up to 16 in-turn competitors)

grok usage is abundant and resets often, so lean on parallelism to compensate for grok-4.5's weak single-shot reasoning. Every grok worker prompt carries a **Parallel Competition Mode** contract (`_grok_competition_contract`, controlled by the `competition_agents` param, default 16, cap 16): for a HARD or open-ended problem the root worker spawns up to N diverse subagents **inside its single turn** (native grok subagents - one terminal, no extra windows, so the owner is not spammed), each independently attempting the full task with a different strategy; the root then acts as judge, discards competitors that lack executed evidence, and **compiles the best result** (picks the strongest or synthesizes a superior combination), then verifies the compiled result end to end. This is the grok-4.5 analog of the grok-4.20 multi-agent harness.

- It is judgment-gated: the contract tells grok to compete only when the task is hard enough to benefit and to solve simple/mechanical tasks directly, so it does not fan out 16 agents to reply with a token.
- Set `competition_agents=1` to disable competition for a run (e.g. trivial or strictly-sequential tasks); set 2-16 to cap the competitor count.
- It composes with the rest: competitors still obey the Rigor Contract (run + prove), and the Opus captain STILL independently e2e-verifies the compiled result - a grok-run competition that picks a winner is not a substitute for the captain's own verification.
- `competition_agents` is a prompt capability, not a CLI flag; it stacks with `best_of_n` (a CLI-level N-way retry) but the two overlap, so prefer one lever at a time unless a task is genuinely huge.

### Mandatory parallel work-checker (grok, every run)

Every grok worker prompt also carries a **Mandatory Parallel Work-Checker** contract (`_grok_work_checker_contract`, always injected) that fires right before the worker may report done: it must spawn a fleet of parallel checker subagents inside the same turn (one terminal), each adversarially auditing its OWN finished work from a different lens (correctness/logic, edge cases & error paths, did-it-actually-run/re-execute the acceptance test, requirements coverage, regressions/blast-radius, and security/concurrency/perf where relevant), then consolidate the proven findings (no cry-wolf), **fix every real issue, and re-run the checkers until they come back clean.** A grok worker may not declare done until a clean parallel work-checker pass, and its report must include what the checkers found, what it fixed, and the final clean verification output. This is the automatic, worker-side counterpart to the captain's own adversarial review - it directly attacks grok-4.5's "declares done without testing" habit. (It is judgment-scaled: a purely trivial informational reply self-verifies instead of spawning a full fleet.) The captain STILL independently e2e-verifies after - the worker's self-run checker is not a substitute for the captain's verification.

### `check_worker_backends`

`check_worker_backends(cwd=None, deep=False) -> {"claude_sonnet": {...}, "claude_worker": {...}, "grok": {...}, "codex": {...}, "agy": {...}}`, one `{available, reason, detail}` record per backend.

- Default (`deep=False`) is cheap: CLI path existence, auth-file presence/parseability, and (for Codex) local JWT-expiry decoding. No network calls.
- The `claude_worker` entry checks that the local CLIProxyAPI gateway is reachable and reports the number of models it serves - call this before delegating to `start_claude_worker` or a native grok subagent, exactly like the other backends.
- `deep=True` additionally runs one short live `codex exec` round trip (roughly 5-15s, a trivial no-tool prompt) that catches server-side token revocation a locally-valid JWT hides. Grok and agy do not get a live ping in `deep` mode - their file-based expiry/refresh-token check is already reliable, and a live ping would spend a real prompt turn for no better signal.
- Observed live on this machine (2026-07-14): `claude_sonnet`, `grok`, and `agy` available; `codex` available=False under `deep=True` with reason `"codex not logged in (ChatGPT login lost / token revoked server-side)"` - the ChatGPT session was revoked while the local access-token JWT and `codex login status` both still looked fine, which is exactly the case `deep=True` exists to catch.

### Callback model (Grok and Antigravity/agy workers)

(`start_claude_worker`'s own report/callback behavior is covered by the general run-dir protocol in "Headless claude_worker backend" above - the run-dir carries `captain_reports/` for every backend. This subsection covers the two legacy visible-window backends specifically.)

Every non-Codex backend's worker gets a result back to Claude through two layers:

1. **Layer 1 - runner auto-report (robust, always on).** The Grok and agy PowerShell runners each write `captain_reports/final.json` + `final.md` themselves from the worker's own answer text after every turn, independent of whether the worker ever calls an MCP tool. `get_visible_run_status` and `list_captain_reports` read it the same way they read a Codex `submit_captain_report` call. For agy this is the ONLY callback path (see below); for Grok it is the always-on fallback under Layer 2.
2. **Layer 2 - live MCP callback.** Where wired (Grok: `~/.grok/config.toml` `[mcp_servers.agent-visibility]`, pointed at the deployed bridge), the worker prompt also instructs the model to call `submit_captain_report` / `request_captain_help` mid-run, matching the Codex `codex-consults-claude` pattern. The shared allowlist in `submit_captain_report` and `request_captain_help` was widened from `metadata.agent in (None, "codex")` to `(None, "codex", "grok", "agy")`, so a Grok (or agy, once/if wired) worker's live call is accepted and surfaces through `list_captain_reports` / `list_captain_help_requests` exactly like a Codex call. Codex behavior is unchanged; the codex-only `steer_visible_codex_run` gate stays codex-specific (Grok/agy steer through their own `steer_visible_*_run` tools). **agy has NO Layer 2 wired**: `agy --help` exposes no `mcp` subcommand, and the only MCP-shaped file found on this machine, `~/.gemini/config/mcp_config.json`, is 0 bytes with no schema documented anywhere reachable - editing it blindly to guess a schema would risk the owner's real authenticated agy config for an unverified guess, so this was deliberately left unwired (checked live 2026-07-14; revisit if `agy` ever ships an `mcp` subcommand or documents the config file). The agy worker prompt does NOT tell the model to call `submit_captain_report`/`request_captain_help` (unlike Codex/Grok prompts), since it has no way to reach them.

> **Reading everything below (Reasoning Effort Policy to Claude Review Standard):** these sections still use **Codex as the historical example** for effort tiers, supervision, watchers, captain-help, and review language. **Codex is DISABLED. The Mandatory Spawn Path at the top of this file always wins.** Map "Codex" to "the worker"; map `start_visible_codex_*` to native `Agent` (`subagent_type: "grok"`) first (or secondary `start_claude_worker` / Workflow); map `steer_visible_codex_run` to `SendMessage` (native) or `steer_claude_run` / `steer_visible_grok_run` / `steer_visible_agy_run`. Do not call Codex tools because an older paragraph still names them.

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
- decomposing work into file-scoped native-subagent tasks (or secondary headless runs)
- acceptance criteria, verification strategy, and rollback/safety boundaries
- active steering (`SendMessage` for native subagents; `steer_claude_run` for headless; `steer_visible_*` only for legacy visible runs)
- independent diff and test review before completion

The manager model should not spend output tokens on:

- broad codebase reading that a worker can summarize
- boilerplate implementation, mechanical refactors, formatting, or test repair
- long worker prompts (keep Agent briefs compact; Haiku composition is only for legacy visible paths)
- raw log analysis unless the worker cannot summarize the evidence

Default manager loop (**native-first**):

1. Decide the architecture and acceptance criteria.
2. Spawn a **native `Agent` subagent** with a compact brief (default `subagent_type: "grok"` in proxy sessions; else Sonnet / agy per the Mandatory Spawn Path). For independent parallel work, issue multiple `Agent` calls in one message or run a Workflow. Only if native cannot apply, use `start_claude_worker` and arm its `watch_command`.
3. For long-running headless/visible fleets only: every 10 minutes run the mandatory direct supervision pass (see "Mandatory 10-Minute Direct Supervision"). Native Agent subagents are supervised by waiting on their result and reviewing the returned report/diff - not by run-dir polling.
4. Let the worker implement, verify, and summarize.
5. Claude reviews the diff, tests, risks, and (if used) the worker ledger. Reject or re-steer when the output does not match the architecture. For grok, review antagonistically and re-run acceptance yourself.
6. Claude writes the final user response only after the review gate passes or clearly reports incomplete verification.

## Routing Mandate: Parallel Agents and Heavy Work → native subagents first

**Default rule: while this skill is active, Claude keeps the manager model focused on architecture, decomposition, steering, and review, and pushes low-level execution to native subagents.** This overrides the default dispatch behavior of other skills and tools, and overrides older skill prose that still names Codex / `start_visible_*` as defaults.

Primary delegation surface (use this):

1. **Native subagents and Workflows (DEFAULT).** Spawn with the `Agent` tool: `subagent_type: "grok"` (default worker), `agy-gemini-*` (ladder), or `model: sonnet` (fallback). Use **Workflows** for structured parallel fan-out. Steer with `SendMessage`. *(This inverts the older rule that forbade Claude from spawning its own parallel agents - that rule existed when Codex was the only backend; it no longer applies.)*

Secondary / legacy (only when conditions in Mandatory Spawn Path match):

2. **`start_claude_worker`** - secondary headless path for run-dir multi-turn or non-proxy grok.
3. **`start_visible_*`** - legacy terminal path for Competition Mode / Work-Checker or owner-requested visible windows. **Never Codex.**

**Route heavy/parallel work off the manager** - via native subagents/Workflows first:

- **Any parallel agent fan-out another skill or tool would trigger** - e.g. `dispatching-parallel-agents`, `subagent-driven-development`, `feature-dev`, the `Explore` / `Plan` agents, or a direct `Agent` / Task-tool dispatch - run it as **native subagents or a Workflow**. Do not implement the fan-out inline in the manager loop, and do not re-route it through visible Codex/grok windows by default.
- **Heavy coding work** - multi-file implementation, mechanical or large refactors, test repair, broad codebase reading, and noisy command/log iteration - route to the worker (default: native grok-4.5).

**Honor the other skill's discipline, delegate its execution.** When a process skill applies (TDD, systematic-debugging, executing-plans), Claude still follows that skill's method and checklist - but the actual fan-out and edits are carried out by native subagents/workers, with the brief encoding the required discipline (e.g. "write the failing test first, then implement"). Claude decomposes, writes the briefs, and reviews; the workers execute.

**Claude keeps (never delegate):** architecture, task decomposition, acceptance criteria, risk and security calls, steering decisions, final review of every diff, and the user-facing response.

**Delegation is ONE level deep.** A spawned subagent/worker (grok, agy, Sonnet, claude_worker) must not delegate further, spawn its own subagents, or re-invoke this skill - only the top-level manager delegates. This is what prevents infinite agent loops.

**Do the work in the manager loop only when:**

- The edit is tiny (single file, a few lines) where delegation overhead exceeds the token savings and the user has not asked for strict delegation.
- The work needs tools or context only Claude can reach (MCP servers the worker lacks, this session's live state).
- Every worker path is unavailable/capped - fall back to doing it directly and tell the user.
- The user explicitly asks Claude to do the work directly.

## Parallel Fan-Out Contract

Native subagents and Workflows fan out concurrently: send multiple `Agent` calls in one message; a Workflow's `parallel`/`pipeline` runs its stages concurrently. Secondary headless start tools also return quickly so simultaneous workers run in parallel. Serial spawning is a manager error, not a platform limit.

- When tasks are independent, spawn every worker first (batch `Agent` calls / start tools), before reading any result from any of them.
- Never await one worker's completion before launching an independent sibling. Waiting between spawns silently serializes the fleet and wastes wall-clock time.
- After the full fleet is launched: for native Agents, collect results and review; for headless/visible fleets, supervise per the "Mandatory 10-Minute Direct Supervision" contract and arm every `watch_command`.
- Prefer multiple native `Agent` spawns (or one Workflow) for fan-out. Do **not** default to `start_visible_first_mate_codex_pool` (Codex disabled) or other visible first-mate pools unless the owner asked for a terminal or Competition Mode.

## Worker Exhaustion Fallback (down the backend ladder)

When the active worker backend runs out (grok capped, agy buckets cooling, etc.), keep delegating - just move down the ladder (grok-4.5 → agy → Claude Sonnet subagents). Do not silently start doing all the implementation as the manager model; the point is still to route heavy/parallel work off the manager. The no-nesting / no-parking / flat-fallback rules below are backend-agnostic and apply to every fallback fleet ("Codex" in the detection triggers = the capped backend).

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

## Visible Agent Harness (LEGACY - not the default)

> **STOP.** The default spawn path is **native `Agent` subagents** (see Mandatory Spawn Path). Use this section only when (a) the owner asks for a visible terminal, (b) you need grok-CLI Competition Mode / Work-Checker, or (c) you are reading status of an already-running visible run. **Codex visible tools in this section are DISABLED - never call them.**

Use the plugin-provided MCP server `agent-visibility` for legacy visible runs, shared status/report tools, and captain-help mailboxes on headless/visible runs.

Backend-agnostic tools you still use with secondary/legacy runs:

- `get_visible_run_status`, `list_visible_runs`, `submit_captain_report`, `list_captain_reports`, `request_captain_help`, `list_captain_help_requests`, `respond_to_captain_help_request`
- `start_claude_worker` / `steer_claude_run` (secondary headless - documented under "Headless claude_worker backend")

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

**Do not default to any visible tool.** For everyday codebase reading, first-mate-style fan-out, implementation, test repair, and tool-heavy debugging, use **native `Agent` subagents** (or secondary `start_claude_worker` when native cannot apply).

Use legacy visible tools only for:

- an explicit user request to open / watch a terminal window
- grok-CLI Parallel Competition Mode / Mandatory Parallel Work-Checker (visible grok path only)
- inspecting or steering a visible run that is already running

Never "default to" `start_visible_first_mate_codex_pool`, `start_visible_haiku_composed_codex_worker`, or `start_visible_codex_worker` - those are Codex-disabled.

## Deprecated: Interactive TUI mode

`start_interactive_codex_tui` and `start_interactive_first_mate_codex_tui` remain available only when the user explicitly asks for a hands-on interactive Codex terminal; tell the user when choosing this deprecated path. TUI mode can flash-close, cannot accept programmatic bridge steering in an already-open terminal, and relies on the worker remembering `submit_captain_report` for captain handoff. It is not the fallback when routing is uncertain.

## Grok Worker Backend (added 2026-07-14; legacy visible-window path as of 2026-07-18)

**LEGACY path.** The preferred default for grok-4.5 is native `Agent` (`subagent_type: "grok"`). Use this visible grok-CLI path only when a task needs its CLI-only extras (Parallel Competition Mode, Mandatory Parallel Work-Checker) or the owner asks for a terminal. See Mandatory Spawn Path and `references/legacy-backends.md`. Codex remains disabled.

The server exposes:

- `start_visible_grok_worker`: launches `grok --prompt-file <prompt.md> --output-format streaming-json --cwd <cwd> --permission-mode bypassPermissions -m grok-4.5 [--reasoning-effort low|medium|high] [-r <sessionId>]` in a separate visible PowerShell window, saves prompt/event logs, and returns a run directory. (`-p`/`--single` and `--prompt-file` are alternative ways to supply the prompt - confirmed live that combining them errors with `a value is required for '--single <PROMPT>'` - so the runner uses `--prompt-file` alone.) Every turn's answer is auto-written to `captain_reports/final.json` / `final.md` (Layer 1 callback, see "Worker Backends & Routing").
- `start_visible_haiku_composed_grok_worker`: Claude passes a compact `prompt_brief`; the Haiku/low composer expands it (the same composer flow the Codex path uses, including its non-fatal fallback to the raw brief on composer failure), then Grok executes the composed prompt.
- `start_visible_first_mate_grok_pool`: launches a single grok-4.5 process with its native subagent capability left enabled (no `--no-subagents`), using the same `_first_mate_prompt` brief as the Codex first-mate pool.
- `steer_visible_grok_run`: sends a captain steering instruction to an existing visible Grok run, mirroring `steer_visible_codex_run`. An idle worker consumes the queued instruction within a second; an active worker is interrupted best-effort (Ctrl+C/taskkill) when a launcher pid is known, then resumed with `grok -r <sessionId>`. Grok has no on-disk session-readiness probe like Codex's thread-file check, so after an interrupt this always launches the resume run directly on the last recorded session id - queued-at-idle delivery is the more reliable v1 path.
- Grok workers share the backend-agnostic read/report/help tools unchanged: `get_visible_run_status`, `list_visible_runs`, `submit_captain_report`, `list_captain_reports`, `request_captain_help`, `list_captain_help_requests`, `respond_to_captain_help_request` (see the callback-model limitation in "Worker Backends & Routing" for the live-MCP-callback caveat on `submit_captain_report` / `request_captain_help`).

### Grok effort caveat

`grok-4.5`'s `--reasoning-effort` CLI flag only accepts `low` / `medium` / `high` - `xhigh` and `max` are rejected outright ("unknown effort level"). Grok's own `~/.grok/config.toml` sets `default_reasoning_effort = "xhigh"`, which applies only when the flag is **omitted**. So the owner's desired default (grok-4.5 at xhigh) is reached by passing `reasoning_effort=""` (or anything outside low/medium/high) so the bridge's `_grok_effort_flag` omits the CLI flag entirely. Pass `reasoning_effort="high"` (etc.) only when a lower tier than the config default is deliberately wanted.

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

## Antigravity / Gemini (agy) Worker Backend (added 2026-07-14; on-request, legacy visible-window path)

A peer backend alongside Codex and Grok - not a replacement for either, and not one of the two windowless default paths (see "Worker Backends & Routing" above and `references/legacy-backends.md` for a condensed summary). Use it only when the owner explicitly asks for Antigravity/Gemini (see "Default routing policy" above).

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
AGY_MODELS_BY_EFFORT = {"high": "Gemini 3.5 Flash (High)", "medium": "Gemini 3.5 Flash (Medium)", "low": "Gemini 3.5 Flash (Low)"}
AGY_DEFAULT_MODEL = "Gemini 3.5 Flash (High)"
```

`start_visible_agy_worker`'s `reasoning_effort` parameter (default `"high"`) is looked up in this table via `_agy_model_for_effort`; anything outside `low`/`medium`/`high` (case-insensitive) falls back to the `"high"` model. `agy models` also lists non-Gemini options (`Gemini 3.1 Pro (Low|High)`, `Claude Sonnet 4.6 (Thinking)`, `Claude Opus 4.6 (Thinking)`, `GPT-OSS 120B (Medium)`) that this bridge does not route to - the effort table only covers the three Gemini 3.5 Flash tiers the owner asked for.

### agy has no session id - `--continue` is cwd-scoped, not thread-scoped

`agy` never prints a session/conversation id on a plain-text turn. `agy --help` does expose `--conversation <id>` (resume a specific conversation) alongside `--continue`/`-c` (resume the **most recent** conversation for the current working directory), but with no id ever surfaced in stdout to capture, `--conversation <id>` is unusable from this bridge. Every resume in this backend therefore uses `--continue`, which is a **best-effort, cwd-scoped** resume: it reaches whatever agy conversation was most recently active in that directory, not a specific tracked thread. This is weaker than Grok's `-r <sessionId>` or Codex's thread-file resume - if another agy conversation is started in the same cwd between a run closing and a steer/resume call, `--continue` would pick up that other conversation instead. Verified live (2026-07-14): a `steer_visible_agy_run` call on a fully closed run correctly recalled the exact marker text from the original run's first turn after a `launched_resume` follow-up, confirming `--continue` does carry real context across process launches within a cwd, subject to the caveat above.

### Long-prompt inline handling

`agy` has no `--prompt-file` flag; the full prompt (including the permission contract and session-context bootstrap, when not using the Haiku composer) is passed inline as a single `-p` argument via PowerShell array splatting (`& $Agy @argsList`), the same mechanism Codex/Grok use for their own long arguments. This avoids `cmd.exe`'s 8191-character line limit (agy.exe is a real executable, not a `.cmd` shim), but very large prompts are still subject to the OS process-argument limit (Windows `CreateProcess` command-line cap, roughly 32K characters combined). Prefer `start_visible_haiku_composed_agy_worker` for large captain briefs, matching the existing Codex/Grok guidance.

## Active Steering Loop

**Native path (default):** spawn with `Agent`, wait for the result (or steer mid-flight with `SendMessage`), review the returned report/diff, and re-spawn or SendMessage with a repair brief if needed. Most of this section's run-dir / visible-window steps apply only to secondary headless and legacy visible runs.

Claude actively manages secondary headless (`start_claude_worker`) and legacy visible runs instead of letting them drift. An explicitly requested deprecated TUI run is user-steered in the terminal and must be reviewed through its sidecar metadata/session artifacts plus `captain_report` afterward.

1. **Prefer native:** start one `Agent` subagent (or a parallel batch) with the goal, constraints, and acceptance criteria. Only if native cannot apply, start `start_claude_worker` (secondary) or a legacy visible worker (on request).
2. Poll with `get_visible_run_status`; read the tail, pending steer count, pending help requests, thread/session id, status, and `captain_report`.
3. At least every 10 minutes for long-running fleets, run an active supervision pass per the "Mandatory 10-Minute Direct Supervision" contract, not just a status poll: inspect recent actions/log tails/reports, check the captain-help mailbox, compare direction against Claude's architecture and acceptance criteria, decide whether the worker is on track, and steer drift immediately.
4. Periodically check up with active agents before they spiral: ask for a compact health/status checkpoint, current assumption, blocker, next action, and expected verification. Use short steering notes; do not wait for obvious failure if output quality is drifting, confused, or bug-prone.
5. If `pending_help_requests` is nonzero, read `help_requests` or call `list_captain_help_requests`, then answer with `respond_to_captain_help_request`.
6. When a worker needs correction, narrowing, extra context, changed priorities, or a review checkpoint: for native Agents use `SendMessage` (or a follow-up Agent with a repair brief); for secondary headless use `steer_claude_run`; for legacy visible use the matching `steer_visible_grok_run` / `steer_visible_agy_run`. **Never** `steer_visible_codex_run` / `codex-reply` (disabled).
7. When multiple agents converge on the same root cause or design decision from different directions, consolidate it into one canonical world model and steer every active run to that model. Do not let stale assumptions keep running in parallel.
8. If a headless/visible worker is right to escalate, ask the user the specific decision question yourself, then call `respond_to_captain_help_request` with the user's answer. Native Agents return a blocker and stop (no captain-help mailbox).
9. Prefer steering an existing worker over starting a new one. For headless, `steer_claude_run` defaults to queue/resume (`interrupt_current_turn=False`); pass `True` to interrupt. For legacy visible, the matching `steer_visible_*` tool interrupts by default.
10. If Claude changes permission intent mid-session on a headless/visible run, pass the updated `sandbox` in the steer call.
11. If a secondary/legacy window closed, resume via `steer_claude_run` / the matching visible steer / `respond_to_captain_help_request`. Start fresh only for unrelated work or polluted context.
12. Non-interactive headless/visible workers report through structured run artifacts / `captain_report`. Native Agents report in their returned message.

Keep steering notes short. State the decision, changed scope, files or tests to focus on, and required next response shape. Do not restate the whole task unless the thread lost context.

## Mandatory 10-Minute Direct Supervision

While any default non-interactive Codex worker or fleet is active, Claude runs a direct supervision pass at least every 10 minutes. The same cadence applies to an explicitly requested deprecated TUI session. This is supervision and review of the work itself, not a liveness probe: confirming the process is still running, or reading only the `status` field, does not count as a pass.

Every pass must do all of the following:

1. Read the worker's actual recent work from the `get_visible_run_status` tail and structured run artifacts - commands run, files touched, stated reasoning, and output produced since the last pass. For a deprecated TUI run, read `captain_report` / `list_captain_reports` and its sidecar artifacts.
2. Check the captain-help mailbox and the pending steer queue.
3. Render an explicit on-track / off-track verdict against Claude's stated architecture, acceptance criteria, and permission contract. Record the verdict in the bridge ledger for long-running fleets.
4. Act on the verdict immediately. If off-track, drifting, or approaching an expensive or irreversible step: send a short captain correction through `steer_visible_codex_run` that quotes or names the specific reviewed output it is correcting. For a deprecated TUI run, use terminal steering or session resume. If on-track: say so in the ledger, and request a compact checkpoint (current assumption, blocker, next action, expected verification) whenever the next milestone is unclear.
5. Note when the next pass is due (10 minutes or less) before returning to other work.

A steer issued without first reading the recent work is not supervision, and a read without a verdict is not review. If two consecutive passes are missed, treat it as a supervision failure: stop launching new delegation, re-read the full ledger and each active run's recent output, and re-establish verdicts before continuing.

## Completion Watcher Contract

The bridge never wakes Claude when a Codex run finishes: start tools are fire-and-forget, and an idle Claude turn is never re-invoked by the MCP server. Without a watcher, a finished worker sits unnoticed while Claude "waits" forever.

- Immediately after every default non-interactive spawn or resume - single worker, pool, or steer follow-up - arm the `watch_command` returned by the start tool as a background Bash task (`run_in_background: true`). The command exits the moment the run reaches a terminal state, which wakes Claude with a completion notification. An explicitly requested deprecated TUI also returns a watcher that terminates on closure or a captain report.
- Never end a turn waiting for Codex without a watcher armed on every active run.
- Watchers detect completion; they do not replace the 10-minute direct supervision passes, which review direction while the run is still working.
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

## First Mate Pattern (native-first rewrite)

When a task requires codebase understanding, do not spend Claude tokens reading everything. **Claude is the captain.** Fan out **native `Agent` scouts** (default `subagent_type: "grok"` in proxy sessions; Sonnet/Explore otherwise) with read-only briefs, collect their summaries, then decide.

Do **not** start `start_visible_first_mate_codex_pool` or any Codex first-mate path (disabled). A legacy visible grok first-mate pool is only for Competition Mode / owner-requested terminals.

Default first-mate settings (native):

- default worker model: grok-4.5 via `subagent_type: "grok"`
- permission intent: read-only for mapping; write only after Claude chooses a scoped path
- max fan-out: 6 unless the task is clearly smaller
- one level deep: scouts return results; they do not spawn further agents

First-mate responsibilities (executed by Claude as captain + native scouts):

- spawn parallel read-only scouts for independent codebase areas
- summarize architecture, key files, tests, data flow, risks, and likely edit points
- optionally update `.claude-codex/BRIDGE.md` for long multi-agent work
- return a compact manager brief for Claude
- avoid dumping raw logs or large code excerpts into Claude's context

For broad codebase understanding, batch Agents with:

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
6. For an already-running visible worker, call `steer_visible_codex_run` instead of starting another root session.
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

## Delegation Patterns (native-first)

### No-Edit Scout

Use when Claude needs context before deciding.

Spawn one or more native `Agent` subagents with read-only intent in the brief (default `subagent_type: "grok"` in proxy sessions; Explore / Sonnet otherwise). For independent areas, issue multiple `Agent` calls in one message:

```text
Read-only scout. Do not edit files.

Areas:
1. <area A>
2. <area B>

For each: relevant files, current behavior, risks, unanswered questions. Return a consolidated summary only.
```

### Bounded Implementation

Use when Claude is confident enough to permit writes.

Spawn a native `Agent` (default `subagent_type: "grok"`) with write intent in the brief. For file-disjoint fan-out, one Agent per work item in a single message batch. Secondary only: `start_claude_worker(..., sandbox="workspace-write", model="grok-4.5")` when native cannot apply.

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

Prefer a native `Agent` with full-tool authorization in the brief. Secondary: `start_claude_worker` with `sandbox: danger-full-access` (or legacy visible only if the owner wants a terminal).

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

Use only for file-disjoint work. Issue N native `Agent` calls in one message (one work item each). Do not ask a single worker to spawn its own subagents (one-level-deep rule).

```text
You own only work item K of N. Edit only your assigned files. Verify and return changed files plus verification proof.
```

If file ownership is not clear, do not parallelize writes.

### Review Pass

After a non-trivial diff, spawn a no-edit native `Agent` (or review yourself as captain):

```text
Read-only review of the current diff against Claude's stated architecture and acceptance criteria. Do not edit files. Findings first, ordered by severity, with file references. If no issues, say so and list residual risk.
```

## Token Efficiency

- **Default:** compact `Agent` brief + native subagent (`grok` / agy / Sonnet). No Haiku composer, no visible window, no Codex.
- For independent fan-out, batch multiple `Agent` calls (or a Workflow). Do not call `start_visible_first_mate_codex_pool`.
- Keep briefs to decisions and constraints: goal, scope, permission intent, files/areas, non-goals, verification, open questions.
- Do not restate this entire skill into every worker prompt; workers get their own agent file / rigor contract.
- Send distilled briefs, not the whole Claude transcript. For long history, tell the worker to use `read-past-sessions`.
- For broad project context, have the worker query read-past-sessions Graphify memory before brute-force reading many sources.
- Ask the worker to summarize the codebase before Claude reads files directly.
- Put noisy exploration, logs, and test repair inside workers, not the manager loop.
- Ask workers to return summaries, changed files, verification results (with pasted proof for grok), blockers, and questions.
- Avoid making Claude read raw logs unless the worker cannot summarize them.
- For secondary headless runs, reuse `resume_session_id` / steer when follow-up context matters; start fresh for unrelated work.
- Keep fan-out one level deep - no recursive subagent trees from workers.

## Visibility Standard

Native `Agent` work is already visible in Claude Code's agent list (no PowerShell window). Tell the user which subagent type you spawned (`grok` / agy / sonnet).

When launching **legacy visible** work only:

1. Tell the user a visible CLI worker is opening (and why native was not used).
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

If the result is wrong, re-steer with `SendMessage` (native), `steer_claude_run` (headless), or the matching `steer_visible_grok_run` / `steer_visible_agy_run` (legacy visible) with a specific repair instruction. Never `steer_visible_codex_run` / `codex-reply`. Do not ask the worker to review itself as the only validation step.
