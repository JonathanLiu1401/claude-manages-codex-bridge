---
name: claude-advisor
description: Use when Codex should ask Claude Code for lightweight advice, plan confirmation, sanity checks, confusion resolution, implementation direction, risk review, or a second opinion before editing. Trigger when Codex is unsure, stuck, sees conflicting evidence, needs to confirm a plan, wants an advisor similar to Claude Code's /advisor flow, or needs Claude to review a risky/non-trivial decision without taking over implementation.
---

# Claude Advisor

Use Claude Code as an expensive advisor. Codex remains the worker and final executor.

## When to Ask

Consult Claude when:

- Codex is confused, stuck, or has conflicting evidence.
- A plan needs confirmation before `workspace-write` edits.
- The choice affects architecture, API shape, data model, migrations, auth, security, money, or destructive behavior.
- A simpler or safer approach may exist but Codex is not confident.
- Verification failures are unclear after one focused repair attempt.
- A non-trivial diff needs a sanity check before finalizing.
- The user explicitly asks for Claude, advisor mode, plan confirmation, or a second opinion.

Do not consult Claude for routine syntax, small local edits, formatting, straightforward test fixes, or information Codex can cheaply verify directly.

## Advisor Tools

Use the plugin-provided `agent-visibility` MCP server for all Claude consultations. It launches Claude as a one-shot, budget-capped advisor run and records a resumable session id.

Available tools:

- `start_visible_claude_advisor`
- `get_visible_run_status`
- `list_visible_runs`

Default advisor limits:

- Claude model: `opus`
- Claude effort: `high`
- `max_budget_usd`: `0.50`
- use a smaller explicit budget only when the answer is tiny and budget-cap failure is acceptable
- session persistence is enabled so cut-off advisor runs can be resumed by session id
- the visible terminal auto-closes a few seconds after completion

Do not start extended Claude sessions from Codex. Do not use Claude for broad codebase reading; summarize with Codex first, then send Claude the distilled decision point.

Visible advisor output shows prompts, streamed messages, tool/progress events, cost metadata, and logs. It cannot show hidden chain-of-thought.

When calling `start_visible_claude_advisor`, pass:

- `session_context`: compact current-session summary, including user goal, prior decisions, files touched, verification, failed attempts, and known mistakes to avoid.
- `resume_session_id`: only when continuing an interrupted Claude advisor run. Get it from `get_visible_run_status.session_id` or `list_visible_runs.session_id`.

If the context started in an earlier chat or was compacted, use `read-past-sessions` first or instruct Claude in the prompt to use it before advising.

## Quick Advisor Prompt

Use this shape for a quick plan check:

```text
You are Claude Code acting as advisor. Codex is the implementation worker.

Task: <user goal>
Session context: <compact current/previous-session briefing; include run ids and prior failures>
Current plan: <short numbered plan>
Facts observed: <brief evidence with file paths, no large excerpts>
Uncertainty: <what Codex is unsure about>
Constraints: <tests, safety, style, permissions, non-goals>
Proposed next action: <what Codex will do if you agree>

Please respond concisely with:
1. approve / revise / stop
2. recommended plan
3. risks or missing checks
4. exact instructions Codex should follow next

Do not edit files.
```

## Confusion Prompt

Use this when Codex is stuck:

```text
You are Claude Code acting as advisor. Codex is confused and needs direction.

Goal: <user goal>
Session context: <what has already happened and what not to repeat>
What happened: <commands/checks tried and outcomes>
Conflicting evidence: <facts that do not line up>
Current hypothesis: <best guess, or "none">
Files involved: <paths only with one-line notes>

Explain the likely issue and give the next 1-3 concrete steps Codex should take.
Do not edit files.
```

## Review Prompt

Use this before finalizing a risky or non-trivial diff:

```text
You are Claude Code acting as advisor and reviewer. Codex implemented the change.

Goal: <user goal>
Session context: <compact current/previous-session briefing>
Approach: <brief summary>
Changed files: <paths and one-line purpose>
Verification: <commands run and results>
Known risks: <remaining uncertainty>

Review for architecture, correctness, security, regression risk, and missing tests.
Return findings first. If there are no blocking issues, say so.
Do not edit files.
```

## Handling Advice

- Treat Claude's answer as advice, not user approval.
- Ask the user before destructive, irreversible, broad-permission, credential, or external-state actions.
- If Claude says `stop`, do not edit. Report the blocker or ask the user for direction.
- If Claude says `revise`, update the plan before writing.
- If Claude approves, proceed only within the user's request and current sandbox.
- Record meaningful Claude decisions in `.claude-codex/BRIDGE.md` when that ledger exists or the work spans multiple turns.
- Record Claude `session_id` when a continuation may be useful.

Keep advisor prompts compact. Send facts, paths, constraints, and options; avoid raw logs, large code dumps, secrets, or hidden reasoning.
Ask Claude for architectural decisions, not fully written Codex prompts. If Claude needs to delegate more work to Codex, it should use the Haiku-composed Codex worker path so Opus emits only a compact captain brief.
