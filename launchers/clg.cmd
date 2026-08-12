@echo off
REM clg = grok-4.6 main-model session through the local CLIProxyAPI proxy.
REM Starts on BARE grok-4.6 (no [1m] suffix). The accurate context window
REM comes from CLAUDE_CODE_MAX_CONTEXT_TOKENS=500000, which is already set
REM in ~/.claude/settings.json env: it applies only to model IDs that do not
REM start with "claude-", is checked after the [1m]/native-1M paths, and
REM gives grok the real ~500k window with default percentage-based
REM autocompaction scheduled against it (live-verified 2026-07-19 on
REM claude 2.1.215: a ~290k-token prompt is client-blocked at the default
REM 200k assumption, sent with the env var set). Claude models in the same
REM process are unaffected. Do NOT type /model grok-4.6[1m] in this window:
REM the [1m] check fires first and would overshoot the window to 1M with no
REM compaction safety. NOTE: the env var is an undocumented internal of the
REM 2.1.21x builds — re-verify after Claude Code version bumps.
claude --model "grok-4.6" %*
