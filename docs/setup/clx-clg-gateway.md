# clx / clg: provider models in the Claude Code TUI

Set up 2026-09-02. Runs Grok and Google Antigravity (Gemini) models inside the
Claude Code TUI, via a stock local CLIProxyAPI gateway, with fully isolated
config. The plain `claude` entry point and `~/.claude` are untouched.

Owner brief: "I think claude code is the best agent harness for long horizon
reasoning tasks... this should not impact my current claude code configs."
Follow-up: "let's just stick to the default setup that the developers intended"
after judging the 2026-08 attempt as "trying to do too much".

## What runs

| Command | Provider | Config dir | Context | Autostart task |
| --- | --- | --- | --- | --- |
| `clx` | Grok 4.5 / 4.6 | `~/.claude-clx` | 500k | `CLIProxyAPI` |
| `clg` | Gemini 3.6/3.7/3.8 Flash, 3.1 Pro | `~/.claude-clg` | 1M | `CLIProxyAPI` |

One gateway serves both: CLIProxyAPI v7.2.147 at `~/cliproxyapi/`, bound to
`127.0.0.1:8317`, started at logon by a per-user scheduled task.

Launchers live in `~/bin/{clx,clg}` (Git Bash) and `~/bin/{clx,clg}.ps1`, with
`~/.local/bin/{clx,clg}.cmd` shims for PowerShell/cmd. Full operator detail is in
`~/.cc-bridge/SETUP.md`; this file documents the harness-relevant parts.

## Native subagents (the harness change)

`plugin/agents/grok.md` and `plugin/agents/agy-gemini-3-8-flash.md` are restored.
They were deleted in `2df4291` when the gateway was decommissioned; the gateway
is back, so they work again.

**Routing is now profile-dependent**, which is the one behavioural change to the
`claude-manages-codex` skill:

- **Plain Claude session** - unchanged. Native proxy-backed subagent types do
  not resolve (the gateway env vars are not set), so everyday delegation uses
  built-in `subagent_type`s and the visible terminal-window workers
  (`start_visible_*`) remain the harness proper on explicit request.
- **clx / clg session** - spawn the native `grok` / `agy-gemini-3-8-flash`
  subagents through the ordinary `Agent` tool. They run inside Claude Code's own
  agentic runtime, so tools, permissions, diffs and steering work with no
  detached console. Prefer them over a terminal-window worker there.

This satisfies Subagent Locality rather than bending it: a clx session **is**
Claude Code, so an `Agent`-tool spawn is same-harness delegation. The forbidden
thing was ever Bashing another CLI, not using a provider model in this runtime.

Verified 2026-09-02: a subagent spawned in a `clx` session confirmed it launched
as a Claude Code TUI subagent and reported its model as `grok-4.6 (high)`.

## Non-obvious facts, all measured

Every item here cost real debugging time. Re-verify after a Claude Code bump.

### Model picker

- **`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` does nothing.** The binary
  guards the fetch and filters ids to `/^(claude|anthropic)/i`, so it only fills
  the picker with Claude aliases that 400 against this gateway. The launchers
  unset it.
- **Tier slots cannot be remapped.** `ANTHROPIC_DEFAULT_OPUS_MODEL` and friends
  accept only ids Claude Code already knows; pointing one at a gateway-served
  Claude id is ignored and `--model opus` still resolves to `claude-opus-5` and
  400s. Build the picker from `availableModels` + `enforceAvailableModels` +
  `modelPicker` in the profile's `settings.json` instead.
- **`modelPicker` must be an OBJECT**, not an array:
  `{"replaceBuiltInOptions": true, "options": [{"model", "label", "description"}]}`.
  A bare array is silently discarded with a settings warning, leaving only the
  single `ANTHROPIC_CUSTOM_MODEL_OPTION` row.
- **The "Default (recommended)" row cannot be removed** and always renders its id
  with a bogus `claude-` prefix. It resolves from `availableModels[0]` - not from
  `modelPicker` order and not from `ANTHROPIC_DEFAULT_MODEL` - so keep the
  intended default first in that array. Cosmetic; the labelled rows work.
- **Keep `ANTHROPIC_MODEL` set.** It overrides the `model` key from any settings
  file. Sessions often run with cwd = the home directory, which makes the main
  `~/.claude/settings.json` load as PROJECT settings, and its `"model": "opus"`
  would otherwise win on restart.

### Effort and context window

- **Reasoning effort is a CLIProxyAPI `(level)` suffix on the model id** -
  `grok-4.6(xhigh)`, `gemini-3.8-flash-high(medium)` - handled by the gateway,
  not by Claude Code's `/effort`. So each level is its own picker row. Levels:
  minimal, low, medium, high, xhigh, auto, none.
- **Also set `CLAUDE_CODE_EFFORT_LEVEL`.** The settings.json `effortLevel` key
  does not apply to non-Claude ids; without the env var the banner read
  "Grok 4.6 high with **low** effort".
- **`(level)` and `[1m]` cannot be combined** (the gateway 400s), and `[1m]` is
  moot anyway: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is a hard pin
  ("tokens (from settings)") and overrides the suffix.
- **The window forces two profiles.** Both window vars are process-wide and
  `modelSettings` accepts ONLY `effortLevel` - there is no per-model window key -
  so grok (500k) and gemini (1M) cannot share one process without one
  mis-reporting. Set both `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` per profile. Verified in the TUI: clx
  `Auto-compact window: 500k tokens`, clg `1m tokens`.

### Antigravity

- **A `429 RESOURCE_EXHAUSTED` under `claude -p` is NOT quota exhaustion.** It is
  an upstream fingerprint filter on `cc_entrypoint=sdk-cli` (CLIProxyAPI issue
  #5037): print mode 429s while interactive sessions and a raw
  `POST /v1/messages` succeed on the same account and model. Observed with 96%
  weekly quota remaining, and the native `agy` CLI running the same model fine.
  Verify with a direct POST before telling the owner they are out of credits.
- `gemini-3.8-flash-medium` / `-low` are not registered upstream yet (issue
  #5423, open); only the `-high` route exists. Vary reasoning with the `(level)`
  suffix instead.

### Testing

**`claude -p` is not sufficient verification.** It never exercises the TUI, the
`/model` picker, the status line, or the settings-warning path, and every real
bug in this setup was invisible to it. It is also the one mode Antigravity
rejects, so it actively misreports which Gemini models work.

Use the interactive harness at `~/.cc-bridge/tui_test.py` (pywinpty + pyte drive
a real PTY and render the screen):

    python ~/.cc-bridge/tui_test.py screen      # banner + settings warnings
    python ~/.cc-bridge/tui_test.py picker      # dump the /model picker
    python ~/.cc-bridge/tui_test.py ctx         # read the real context window
    python ~/.cc-bridge/tui_test.py ask "..."   # ask interactively
    CLX_CMD=clg python ~/.cc-bridge/tui_test.py screen   # target clg

Known harness gap: it cannot reliably get a prompt past the composer's
manual-mode queueing, so drive subagent checks by hand.

### Gateway operations

Two traps, both fixed in `~/cliproxyapi/start-gateway.ps1`:

- **Start it detached.** A foreground child shares a console with the task's
  PowerShell wrapper, so any Ctrl+C or console close kills the gateway - seen as
  scheduled-task `lastResult=0xC000013A` (`STATUS_CONTROL_C_EXIT`) with a clean,
  error-free log tail. `Start-Process -PassThru` parents it outside any console.
- **`Stop-ScheduledTask` orphans the process**, which keeps port 8317 and makes
  the next start die on `bind: Only one usage of each socket address`. Use
  `~/cliproxyapi/stop-gateway.ps1`; the start script also clears survivors.

PowerShell 5.1 `*>>` redirection writes UTF-16LE, which turns a log into a binary
blob that `grep`/`tail` cannot read. Use `Add-Content -Encoding utf8`.

## Cursor: attempted and rejected

`cursor-agent` was tried on 2026-09-02 and removed. Do not rebuild it.

1. CLIProxyAPI has **no Cursor provider** (Cursor PRs #5252 / #3651 / #4055 all
   still open; `/v1/models` serves only `xai` + `antigravity`), so it needed a
   second gateway - raine/claude-code-proxy on :18765.
2. Through that proxy **no tools worked, not even `Read`**, which its own docs
   list as bridged. Cursor attempts the call but the proxy emits it as plain
   text: the raw stream carried
   `text_delta: "call-<uuid>-0\nfc_<id>_0"` (Cursor's internal tool-call ids)
   with `stop_reason: end_turn`, never a `tool_use` block. Tested with
   `stream: true`, matching function names and a stable
   `x-claude-code-session-id` - the documented bridge conditions. Read, Bash,
   Grep, Edit and Task all behaved identically.

A session that cannot read, edit, search or spawn subagents is not a coding
agent, so the whole thing was deleted. **Use `cursor-agent`'s own TUI for Cursor
work** - its tool loop is native and complete.

Also settled: Cursor's public API has no inference endpoint at all
(`POST api.cursor.com/v1/chat/completions` and `/v1/messages` both 404 with a
valid `crsr_` key), and that key does not authenticate the agent protocol either
(502 `unauthenticated`).

## Relationship to the 2026-08-15 decommission

This knowingly reverses part of that teardown, on owner instruction. The global
CLAUDE.md line "never point `ANTHROPIC_BASE_URL` or `ANTHROPIC_AUTH_TOKEN` at a
local gateway" predates this and applies to **plain `claude`**, not to `clx` /
`clg`. What is deliberately NOT rebuilt: the `clx`/`cld`/`clg`/`clo` wrapper
sprawl of that era, the `.claude-clx`/`.claude-direct`/`.claude-ollama` triple,
the model-catalog sync scripts, and the SessionStart hooks that ran them. This
setup is stock upstream plus launchers.
