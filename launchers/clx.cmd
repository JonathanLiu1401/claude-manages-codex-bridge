@echo off
REM clx = multi-provider Claude Code through the local CLIProxyAPI gateway,
REM using the isolated ~/.claude-clx config dir (model unpinned; /model
REM grok-4.6 etc. works freely). API-key mode -> no Remote Control.
REM The loopback key is per-machine: read it from proxy-key.txt at launch,
REM NEVER hardcode or commit it.
set "ANTHROPIC_BASE_URL=http://127.0.0.1:8317"
set /p ANTHROPIC_AUTH_TOKEN=<"%USERPROFILE%\CLIProxyAPI\proxy-key.txt"
set "ANTHROPIC_API_KEY="
set "CLAUDE_CONFIG_DIR=%USERPROFILE%\.claude-clx"
claude %*
