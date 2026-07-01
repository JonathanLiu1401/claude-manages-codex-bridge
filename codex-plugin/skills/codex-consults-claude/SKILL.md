---
name: codex-consults-claude
description: Use when Codex should ask Claude Code for expensive architectural advice, visible advisor output, design review, risk assessment, final code review, plan confirmation, sanity checks, confusion resolution, or decisions that Codex is not fully confident making alone. Trigger for requests like "ask Claude", "consult Claude", "get Claude's opinion", "Claude is the advisor", "Claude should review this", "show Claude working", "visible advisor", "confirm this plan", "sanity check", or when a change is risky, cross-cutting, ambiguous, security-sensitive, data-loss-prone, or outside Codex's confidence.
---

# codex-consults-claude

Use Codex as the worker harness and Claude Code's active manager model as the expensive executive manager/advisor.

## Role Boundary

- Claude owns architecture, scope decisions, permission decisions, and final review.
- Codex owns implementation, exploration, mechanical changes, test repair, and cheap parallel subagent work.
- Codex should not spend Claude tokens on routine implementation details.
- When Codex does call Claude, use the bridge advisor model policy: `fable` / `high` through July 7, 2026, then `opus` / `high`. Do not downgrade the advisor model.
- Every Claude advisor call must include current session context or tell Claude to recover it with `read-past-sessions` before advising.
- Codex workers in this bridge need full process/tool access so Python-backed skills, `read-past-sessions`, SSH, and developer CLIs work. Treat `read-only` as no-edit permission intent, not a literal process sandbox.
- SSH, serial, live-device, hardware, network, Docker, package-manager, and external-tool debugging must use a full-tool Codex worker.
- Do not ask the Claude manager model to write long Codex worker prompts or implementation code. It should return decisions, constraints, acceptance criteria, and review findings; the Claude-side bridge uses Haiku/low to compose detailed Codex prompts.
- When the user wants visibility, use visible advisor tools so the prompt and streamed output appear in a terminal and logs.

Consult Claude when:

- architecture or API boundaries are ambiguous
- the change touches multiple subsystems
- the likely fix involves data loss, auth, security, migrations, money, or destructive operations
- Codex is not fully confident about editing with `workspace-write`
- Codex needs plan confirmation, a sanity check, or confusion resolution before proceeding
- the user explicitly asks for Claude's opinion or review
- Codex produced a non-trivial diff and needs independent review before finalizing

## Dedicated Advisor Skill

Use the bundled `claude-advisor` skill for lightweight advice flows similar to Claude Code's `/advisor` behavior:

- confirming a plan before writes
- sanity-checking an approach
- asking for direction when Codex is confused or stuck
- reviewing a risky or non-trivial diff before finalizing

Use `codex-consults-claude` for the broader bridge contract, first-mate behavior, visible advisor sessions, and persistent Claude/Codex ledger guidance. Use `claude-advisor` when the task is just "ask Claude what Codex should do next."

## Visible Advisor Tool

Use the plugin-provided MCP server `agent-visibility` for Claude consultations. This is the default and preferred Codex-to-Claude path because it is visible, one-shot, budget-capped, and non-persistent.

The server exposes:

- `start_visible_claude_advisor`: launches `claude -p --output-format stream-json --max-budget-usd <budget>` in a visible PowerShell window, saves logs, and records a resumable Claude session id.
- `get_visible_run_status`: reads status and recent display log lines.
- `list_visible_runs`: lists recent visible runs.

Use visible advisor sessions only for expensive/high-level Claude consultations, final review requests, and user-requested observed advisor work.

The visible advisor launcher uses the central advisor model policy even if a caller passes cheaper values: `fable` / `high` through July 7, 2026, then `opus` / `high`. It keeps the process one-shot and exits after the run, but persists the Claude session id so a cut-off run can be resumed.

Use these optional arguments:

- `session_context`: compact current Codex briefing for Claude. Include user goal, prior decisions, files touched, verification, failed attempts, run/thread/session ids, and the exact decision needed.
- `resume_session_id`: Claude session id from `get_visible_run_status.session_id` or `list_visible_runs.session_id`. Use this when continuing an interrupted advisor run.

Hard limits:

- Default `max_budget_usd` is `0.50` because the manager model has higher startup cost.
- Use a lower explicit budget only when the expected answer is tiny and failure from budget cap is acceptable.
- Use more than `0.50` only when the user explicitly asks or the risk is high enough to justify it.
- Do not start extended Claude sessions from Codex.
- Do not use Claude to read broad codebase context; use Codex explorers first and send Claude a distilled brief.
- Ask at most one Claude consultation per decision point. If Claude asks follow-up questions, answer only when the decision is blocked.

The visible window shows prompts, streamed messages, tool/progress events, cost metadata, and logs. It closes automatically a few seconds after completion. It cannot show hidden chain-of-thought. Phrase this as visible progress and implementation state, not private thoughts.

## Consultation Template

```text
You are Claude Code, the executive architectural advisor. Codex is the implementation worker.

Goal: <what the user wants>
Session context: <compact summary of current conversation and previous run ids>
Current decision: <specific choice or risk>
Relevant files: <paths only, plus short notes>
Constraints: <tests, style, safety, user requirements>
Codex confidence: <high/medium/low and why>

Give a concise recommendation with:
1. decision
2. reasoning
3. risks
4. acceptance criteria and specific instructions Codex should follow

Do not edit files or write implementation code.
```

## Session Context and Resume

Do not call Claude as a blank advisor.

Before `start_visible_claude_advisor`:

1. Summarize the current Codex session: user goal, decisions already made, evidence, changed files, commands run, verification, known failures, and the exact advice needed.
2. If this work began in an earlier chat or a prior visible run, use `read-past-sessions` first or instruct Claude to use it before answering.
3. Pass that summary as `session_context`.
4. If continuing a cut-off Claude run, pass `resume_session_id` from the earlier run's `session_id`.
5. Store useful Claude decisions and session ids in `.claude-codex/BRIDGE.md` when the task spans turns.

Start a fresh Claude session only for unrelated decisions or polluted prior context.

## Codex Subagent Harness

Codex can spawn subagents only when explicitly asked by the user or Claude. Do not fan out on your own for routine tasks.

Preferred custom agents for Claude-managed work:

- `claude-explorer`: no-edit scouting, Python-backed skill use, file discovery, dependency tracing, context summaries.
- `claude-implementer`: bounded implementation after Claude gives scope and write permission.
- `claude-reviewer`: no-edit review of diffs and risk.
- `claude-debugger`: full-tool SSH, live-device, network, serial, and command-heavy debugging after Claude gives full tool access.

Use built-in Codex agents only when custom agents are unavailable:

- `explorer` for read-heavy discovery.
- `worker` for implementation.
- `default` as fallback.

Subagents inherit the parent process access unless their agent config overrides it. No-edit intent means do not attempt write work even though Python/tools are available.
For SSH/live-device/tool-heavy debugging, use `claude-debugger` and report commands plus results. Ask Claude before destructive, persistent, credential, service, firmware, or data-loss actions.

## First Mate Behavior

When Claude asks Codex to act as first mate, treat token savings as the main objective.

Do:

- spawn `claude-explorer` subagents to read and summarize codebase areas
- keep Claude out of raw file-reading unless a decision requires it
- run low-level implementation and verification through Codex workers
- return compact manager briefs: architecture, key files, tests, risks, edit plan, changed files, verification
- update `.claude-codex/BRIDGE.md`

Do not:

- send Claude raw logs or large code dumps
- ask Claude to make low-level implementation choices
- spawn recursive subagent trees
- run write-capable parallel agents on overlapping files

Default first-mate worker settings when Claude asks:

- use `gpt-5.5` with `xhigh` reasoning and `service_tier=fast`
- use `claude-explorer` for no-edit context discovery
- use `claude-implementer` only after Claude gives a scoped plan and write permission
- use `claude-reviewer` for independent review before finalizing substantial changes
- use `claude-debugger` only when Claude explicitly authorizes full tool access

## Workspace-Write Policy

Use `workspace-write` only when Codex is fully confident the task is well-scoped and safe and Claude or the user has given permission to implement.

If not fully confident:

1. do no-edit analysis,
2. consult Claude,
3. wait for a concrete implementation decision before writing.

Never use Claude's advice as a substitute for required user approval for destructive, broad-permission, or external actions.

## Persistent Bridge Memory

For non-trivial multi-agent work, use `.claude-codex/BRIDGE.md` in the repository root.

If it exists, read it before consulting Claude. If it does not exist and the task will span multiple turns, create:

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

Update it after major Claude decisions, Codex implementation passes, subagent summaries, and verification results. Keep it concise; do not paste full transcripts.

## Finalization

Before reporting completion:

- review the diff directly
- run feasible verification
- ask Claude for review if the change is risky or non-trivial
- summarize Claude's advice separately from Codex's implementation
