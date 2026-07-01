---
name: claude-manages-codex
description: Use when Claude Code should act as executive architect, QA tech lead, first-mate captain, and reviewer while delegating implementation, exploration, Codex subagent orchestration, codebase reading, mechanical refactors, test repair, or cheap iteration to OpenAI Codex through the bundled codex-worker and visible agent MCP servers. Trigger for requests like "have Claude manage Codex", "delegate this to Codex", "use Codex as the worker", "parallelize with Codex", "ask Codex to implement", "use Codex subagents", "show or steer visible worker logs", "first mate", or any coding task where Claude should make high-level decisions and Codex should do low-level work.
---

# claude-manages-codex

Use Claude's active manager model as captain, executive architect, QA tech lead, and reviewer. Use Codex as the first mate and worker harness, including Codex root sessions and Codex subagents.

## Core Model

- Claude owns architecture, task decomposition, acceptance criteria, risk calls, worker assignment, active steering, and final review. In the first-mate flow, Claude is the captain.
- Codex owns cheap exploration, first-pass implementation, test repair, mechanical refactors, and noisy command/log work. In the first-mate flow, Codex is the first mate that manages the Codex agent ensemble.
- Codex subagents are controlled through the Codex root session. Claude starts or resumes the root session with `codex` / `codex-reply`, then explicitly tells Codex when and how to spawn subagents.
- Claude must review Codex output and local diffs before claiming completion.
- Prefer Codex MCP over manual copy/paste.
- The Claude manager model does not write implementation code by default. It writes plans, contracts, constraints, acceptance tests, review findings, steering notes, and the final user response. Route code edits to Codex unless the edit is tiny, the bridge is unavailable, or the user explicitly asks Claude to code directly.
- Every Codex run uses `gpt-5.5`, `xhigh` reasoning, and `service_tier=fast`. Do not downgrade for cheap scouting; token savings come from routing work to Codex, not weakening Codex.
- Every new or resumed Codex run receives session context. Pass a compact `session_context` argument when using visible tools, and tell Codex to use `read-past-sessions` before acting when it needs the full transcript.
- Codex workers run with full process/tool access by default so Python-backed skills, `read-past-sessions`, SSH, and developer CLIs work. Use the requested `sandbox` as permission intent: `read-only` means no edits, not a crippled process sandbox.
- SSH, serial, live-device, hardware, network, Docker, package-manager, and external-tool debugging must set `requires_tool_access: true` or `sandbox: danger-full-access`.
- Do not spend manager-model output tokens writing long Codex prompts. Claude should pass a compact captain brief to the Haiku prompt composer; Haiku expands the final Codex worker prompt.
- Prefer visible workers when the user wants to observe progress. Visible workers show prompts, streamed events, agent messages, commands, token usage, and diffs in a separate terminal plus logs under `.claude-codex/runs/`.
- Hidden model reasoning is not displayable. Surface useful progress, summaries, commands, and implementation state instead.

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

- use `fable` / `high` through July 7, 2026 while it is available in Claude Code
- use `opus` / `high` after July 7, 2026
- override without editing files by setting `CLAUDE_MANAGES_CODEX_ADVISOR_MODEL`

The manager model should spend reasoning on:

- system architecture, dependency mapping, data-flow decisions, and risk triage
- decomposing work into file-scoped Codex tasks and first-mate pools
- acceptance criteria, verification strategy, and rollback/safety boundaries
- active steering through `steer_visible_codex_run`
- independent diff and test review before completion

The manager model should not spend output tokens on:

- broad codebase reading that Codex can summarize
- boilerplate implementation, mechanical refactors, formatting, or test repair
- long worker prompts; use Haiku prompt composition
- raw log analysis unless Codex cannot summarize the evidence

Default manager loop:

1. Decide the architecture and acceptance criteria.
2. Start or resume a visible Codex worker or first-mate pool with a compact `session_context`.
3. Poll status and steer with short captain instructions when drift appears.
4. Let Codex implement, verify, and summarize.
5. Claude reviews the diff, tests, risks, and worker ledger. Reject or steer repair when the output does not match the architecture.
6. Claude writes the final user response only after the review gate passes or clearly reports incomplete verification.

## Routing Mandate: Parallel Agents and Heavy Work → Codex

**Default rule: while this skill is active, Claude does not spawn its own parallel subagents and does not do implementation directly. That work routes through Codex to preserve Claude tokens and keep the manager model focused on architecture and review.** This overrides the default dispatch behavior of other skills and tools.

**Always route to Codex** — start or resume a Codex root session, then have it spawn `claude-explorer` / `claude-implementer` / `claude-reviewer` subagents:

- **Any parallel agent fan-out another skill or tool would trigger** — e.g. `dispatching-parallel-agents`, `subagent-driven-development`, `feature-dev`, the `Explore` / `Plan` agents, or any direct `Agent` / Task-tool subagent dispatch. Do not spawn Claude subagents for the fan-out; have Codex spawn its subagents instead.
- **Heavy coding work** — multi-file implementation, mechanical or large refactors, test repair, broad codebase reading, and noisy command/log iteration.

**Honor the other skill's discipline, delegate its execution.** When a process skill applies (TDD, systematic-debugging, executing-plans), Claude still follows that skill's method and checklist — but the actual fan-out and edits are carried out by Codex subagents, with the brief encoding the required discipline (e.g. "write the failing test first, then implement"). Claude decomposes, writes the briefs, and reviews; Codex executes.

**Claude keeps (never route):** architecture, task decomposition, acceptance criteria, risk and security calls, steering decisions, final review of every Codex diff, and the user-facing response.

**Do NOT route to Codex when:**

- The edit is tiny (single file, a few lines) where Codex coordination overhead exceeds the token savings and the user has not asked for strict delegation.
- The work needs tools or context only Claude can reach (MCP servers Codex lacks, this session's live state).
- The Codex bridge is unavailable or erroring — fall back to Claude and tell the user.
- The user explicitly asks Claude to do the work directly.

When routing, prefer a **visible** Codex run (`start_visible_first_mate_codex_pool` for fan-out, `start_visible_codex_worker` for a single worker) so the user can watch the token-saving work happen; use invisible `codex` / `codex-reply` only for quick, low-noise exchanges.

## Codex MCP Harness

Use the plugin-provided MCP server `codex-worker`.

The server exposes:

- `codex`: start a new Codex root worker session.
- `codex-reply`: continue a Codex root worker session with a `threadId`.

Important `codex` arguments:

- `prompt`: the worker brief.
- `cwd`: project directory.
- `sandbox`: `read-only`, `workspace-write`, or `danger-full-access`.
- `approval-policy`: use `never` unless the user explicitly wants interactive approvals.
- `developer-instructions`: use this to enforce Claude manager / Codex worker roles.
- `model`: set `gpt-5.5`.
- `config`: include `model_reasoning_effort="xhigh"` and `service_tier="fast"`.

When a Codex response includes `structuredContent.threadId`, record it and use `codex-reply` for follow-up to that same root worker.

## Visible Agent Harness

Use the plugin-provided MCP server `agent-visibility` when the user wants to see what is happening or when work will take more than a quick turn.

The server exposes:

- `start_visible_codex_worker`: launches `codex exec --json` in a separate visible PowerShell window, saves the prompt and event logs, and returns a run directory.
- `start_visible_haiku_composed_codex_worker`: launches a visible run where Claude passes a compact `prompt_brief`, Haiku/low composes the full Codex prompt, then Codex executes it.
- `start_visible_first_mate_codex_pool`: launches a visible Codex root coordinator instructed to spawn and manage Codex subagents.
- `steer_visible_codex_run`: sends a captain steering instruction to an existing visible Codex run. If the visible window is active, the instruction is queued and consumed on the same Codex thread. If the window already closed and a `thread_id` exists, it launches a visible resume run on that thread.
- `get_visible_run_status`: reads status and recent log lines from a visible run directory.
- `list_visible_runs`: lists recent visible runs.

Visible start tools force Codex to `gpt-5.5` / `xhigh` / `service_tier=fast` even if a caller passes weaker values. The Haiku composer uses Claude `haiku` / `low` and a small default budget before Codex starts.

Use these optional arguments:

- `session_context`: compact current-session briefing for the spawned worker. Include the user goal, decisions already made, files touched, verification results, blockers, and any known mistakes to avoid.
- `resume_session_id`: Codex thread/session id from `get_visible_run_status.thread_id`, `list_visible_runs.thread_id`, or a prior Codex result. Use this when a visible Codex run was cut off or needs continuation.
- `requires_tool_access`: set `true` for SSH, live-device, serial, hardware, network, Docker, package-manager, or external-tool debugging.
- `compose_with_haiku`: optional on `start_visible_codex_worker`; set `true` when `prompt` is a compact brief rather than a final Codex prompt.
- `prompt_brief`: use this with `start_visible_haiku_composed_codex_worker`. Keep it short: objective, decisions, constraints, scope, verification, and non-goals.
- `steer_idle_seconds`: visible Codex runs wait briefly after each turn for queued steering, then close and reap child processes.

Use visible tools for:

- codebase-reading passes that should be observable
- first-mate worker pools
- long implementation or test-repair runs
- SSH, live-device, serial, hardware, network, Docker, package-manager, or external-tool debugging where Codex must run the same tools a developer would run
- any user request to see live work

Default to `start_visible_haiku_composed_codex_worker` for non-trivial single-worker delegation so the manager model emits a compact brief instead of the full Codex prompt. Use direct `start_visible_codex_worker` only for tiny prompts or when a final prompt already exists outside Claude output.

## Active Steering Loop

Claude should actively manage a visible Codex run instead of letting it drift:

1. Start one visible Codex root or first-mate run with the goal, constraints, and acceptance criteria.
2. Poll with `get_visible_run_status`; read the tail, pending steer count, thread id, and status.
3. When Codex needs correction, narrowing, extra context, changed priorities, or a review checkpoint, call `steer_visible_codex_run` with a short captain instruction and the same run directory.
4. Prefer queued steering over a new run. Use `interrupt_current_turn: true` only when Codex is actively doing harmful or clearly wasted work and a `thread_id` has already been recorded.
5. If Claude changes permission intent mid-session, pass `sandbox: workspace-write` or `sandbox: danger-full-access` in the steering call so Codex receives an updated permission contract.
6. If the visible window closed, let `steer_visible_codex_run` launch a visible resume run on the same thread. Start fresh only for unrelated work or polluted context.

Keep steering notes short. State the decision, changed scope, files or tests to focus on, and required next response shape. Do not restate the whole task unless the thread lost context.

Use invisible `codex` / `codex-reply` for quick, low-noise, manager-controlled exchanges where live observation is not needed.

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

When a task requires codebase understanding, do not spend Claude tokens reading everything. Start a visible first-mate pool or a no-edit Codex root session and tell Codex to map the repo for Claude.

The bridge bundles a Codex-facing Firstmate skill at `codex-skills/firstmate/SKILL.md`. Install or sync it to `~/.codex/skills/firstmate/SKILL.md` when using this repo locally. The visible first-mate runner also embeds the same role contract so the hierarchy works even before Codex refreshes its skill index.

Default first-mate settings:

- model: `gpt-5.5`
- reasoning effort: `xhigh`
- service tier: `fast`
- process sandbox: full tool access by default so Python skills and external tooling work
- permission intent: `read-only`/no-edit for codebase mapping, `workspace-write` only after Claude chooses a scoped implementation path, `danger-full-access` or `requires_tool_access: true` for SSH/live-device/tool debugging
- max worker fan-out: 6 unless the task is clearly smaller

First-mate responsibilities:

- spawn `claude-explorer` subagents for independent codebase areas
- summarize architecture, key files, tests, data flow, risks, and likely edit points
- update `.claude-codex/BRIDGE.md`
- return a compact manager brief for Claude
- avoid dumping raw logs or large code excerpts into Claude's context

For broad codebase understanding, ask:

```text
Use the firstmate skill. Claude is the captain; Codex is the first mate. Spawn claude-explorer subagents to map the codebase by subsystem. Do not edit files. Return a compact manager brief with architecture, key files, tests, risk areas, and recommended implementation plan.
```

## Session Context and Resume

Do not treat spawned Codex as a blank chat.

Before starting or resuming Codex:

1. Build a compact `session_context` from the live Claude conversation: user goal, decisions, constraints, prior errors, run ids, thread ids, changed files, verification, and open questions.
2. If context predates the current Claude window or was compacted, invoke `read-past-sessions` or tell Codex to use it immediately.
3. Pass `session_context` into `start_visible_codex_worker` / `start_visible_first_mate_codex_pool`.
4. If continuing previous work, pass `resume_session_id` instead of starting a new root run. For Codex this is the `thread_id` shown by `get_visible_run_status` or `list_visible_runs`.
5. For an already-running visible worker, call `steer_visible_codex_run` instead of starting another root session.
6. Record resumable ids in `.claude-codex/BRIDGE.md`.

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

### No-Edit Scout

Use when Claude needs context before deciding.

Start Codex with no-edit permission intent, or use `start_visible_first_mate_codex_pool`, and tell it:

```text
Spawn claude-explorer subagents for the independent areas below. Wait for all agents, then return a consolidated summary only.

Areas:
1. <area A>
2. <area B>

For each result include: relevant files, current behavior, risks, and unanswered questions. Do not edit files.
```

### Bounded Implementation

Use when Claude is confident enough to permit writes.

Start or resume Codex with `sandbox: workspace-write`, or use `start_visible_codex_worker`, and tell it:

```text
Claude has chosen the implementation path. Use one claude-implementer subagent unless the listed work items are file-disjoint.

Scope:
- Goal: <goal>
- Files/areas: <paths>
- Non-goals: <what not to touch>
- Acceptance criteria: <criteria>
- Verification: <commands>

Do not change architecture. If the scope is ambiguous, stop and ask Claude.
```

### Live Debugging, SSH, and Tool Access

Use when Codex must run real developer tools, SSH to a device, inspect network state, use serial tooling, run package managers, or debug hardware/runtime behavior.

Start or resume Codex with `requires_tool_access: true` and include the previous `resume_session_id` when continuing the same run. Tell it:

```text
Claude explicitly authorizes full tool access for this debugging scope.
Use claude-debugger for SSH/live-device/tool-heavy work. Start with read-only inspection commands, report commands and results, and ask Claude before destructive actions, service restarts, credential changes, data deletion, firmware flashing, or persistent system changes.

Scope:
- Target: <host/device/repo>
- Goal: <observable issue>
- Allowed commands/tools: <ssh/tests/logs/etc.>
- Forbidden actions: <destructive or persistent actions>
- Verification: <what proves the issue is fixed>
```

If an older Codex thread was created before the full-tool default and still cannot access Python/tools after resume, start a fresh full-tool worker and pass the old thread id in `session_context`.

### Parallel Implementation

Use only for file-disjoint work.

Tell Codex exactly how to split work:

```text
Spawn exactly N claude-implementer subagents, one per work item. These work items are file-disjoint. Each subagent may edit only its assigned files. Wait for all agents, resolve non-overlapping results, and return changed files plus verification.
```

If file ownership is not clear, do not parallelize writes.

### Review Pass

After a non-trivial diff, use a no-edit Codex review or Claude's own review.

```text
Spawn one claude-reviewer subagent. Review the current diff against Claude's stated architecture and acceptance criteria. Do not edit files. Findings first, ordered by severity, with file references. If no issues, say so and list residual risk.
```

## Token Efficiency

- For non-trivial Codex delegation, Claude writes a compact captain brief and calls `start_visible_haiku_composed_codex_worker`. Haiku/low writes the long worker prompt.
- Keep the Claude-authored `prompt_brief` to decisions and constraints: goal, scope, permission intent, files/areas, non-goals, verification, and open questions.
- Do not have Claude restate standard bridge rules, full task templates, or long worker checklists; the bridge and Haiku composer add those.
- Send Codex distilled briefs, not the whole Claude transcript.
- Include enough session context that Codex does not repeat already-fixed mistakes. For very long history, instruct Codex to use `read-past-sessions` and return a compact briefing before implementation.
- Ask Codex to read and summarize the codebase before Claude reads files directly.
- Use visible first-mate pools for broad understanding instead of loading file after file into Claude.
- Put noisy exploration, logs, and test repair inside Codex subagents.
- Ask Codex to return summaries, changed files, verification results, blockers, and questions.
- Avoid making Claude read raw logs unless Codex cannot summarize them reliably.
- Reuse a root Codex `threadId` when follow-up context matters.
- Start fresh root sessions for unrelated work to avoid context pollution.
- Prefer `claude-explorer` for cheap parallel scans before spending Claude tokens on design decisions.
- Do not ask Codex to consult Claude unless the decision is high-value or uncertain.
- Keep subagent fan-out bounded. Codex defaults are designed for shallow delegation; do not request recursive subagent spawning.

## Visibility Standard

When launching visible work:

1. Tell the user a visible terminal window is opening.
2. Include the run directory in the bridge ledger.
3. Use `get_visible_run_status` for concise progress checks instead of reading raw JSONL.
4. Use `steer_visible_codex_run` when Claude needs to redirect the active worker; the terminal will show queued steering and follow-up turns.
5. Expect the visible terminal to show prompts, messages, commands, token usage, and diff summaries.
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

If the result is wrong, use `steer_visible_codex_run` for visible runs or `codex-reply` for invisible runs with a specific repair instruction. Do not ask Codex to review itself as the only validation step.
