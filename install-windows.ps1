# Install the visible-agent bridge (multi-agentic-harness) on Windows.
# Usage: powershell -ExecutionPolicy Bypass -File install-windows.ps1
#
# Deploys the bridge + cross-platform Claude worker runner to ~\.agent-bridge\,
# installs the captain-doctrine skill, and registers the MCP server with
# Claude Code (user scope).
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeDir = Join-Path $env:USERPROFILE '.agent-bridge'
New-Item -ItemType Directory -Force -Path $BridgeDir | Out-Null

# Python >=3.10 with the `mcp` package.
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Py) { throw 'Python not found on PATH. Install Python 3.10+ first.' }
& $Py -c "import mcp" 2>$null
if ($LASTEXITCODE -ne 0) { & $Py -m pip install --user mcp }

Copy-Item (Join-Path $Here 'visible_agent_bridge.py') $BridgeDir -Force
Copy-Item (Join-Path $Here 'claude_worker_runner.py') $BridgeDir -Force
Copy-Item (Join-Path $Here 'cursor_worker_runner.py') $BridgeDir -Force
Copy-Item (Join-Path $Here 'captain_checkup.py') $BridgeDir -Force

# Captain doctrine skill for the manager session.
$SkillSrc = Join-Path $Here 'plugin\skills\claude-manages-codex'
if (Test-Path $SkillSrc) {
  $SkillDst = Join-Path $env:USERPROFILE '.claude\skills\claude-manages-codex'
  New-Item -ItemType Directory -Force -Path $SkillDst | Out-Null
  Copy-Item (Join-Path $SkillSrc '*') $SkillDst -Recurse -Force
  Write-Host 'Installed skill: claude-manages-codex'
}

# Register the MCP server with Claude Code (user scope; idempotent).
claude mcp remove agent-visibility -s user 2>$null | Out-Null
claude mcp add agent-visibility -s user -- $Py (Join-Path $BridgeDir 'visible_agent_bridge.py')
Write-Host "Registered MCP server 'agent-visibility' (user scope) using $Py"

& $Py -m py_compile (Join-Path $BridgeDir 'visible_agent_bridge.py') (Join-Path $BridgeDir 'claude_worker_runner.py') (Join-Path $BridgeDir 'cursor_worker_runner.py') (Join-Path $BridgeDir 'captain_checkup.py')

# Git Bash cannot see cursor-agent.cmd via `command -v`. Drop an extensionless shim
# on the user PATH that Claude Code's Bash tool actually searches.
$ShimSrc = Join-Path $Here 'shims\cursor-agent'
$LocalBin = Join-Path $env:USERPROFILE '.local\bin'
if (Test-Path $ShimSrc) {
  New-Item -ItemType Directory -Force -Path $LocalBin | Out-Null
  $ShimDst = Join-Path $LocalBin 'cursor-agent'
  $text = [System.IO.File]::ReadAllText($ShimSrc) -replace "`r`n", "`n" -replace "`r", "`n"
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($ShimDst, $text, $utf8)
  Write-Host "Installed Git Bash cursor-agent shim: $ShimDst"
}

Write-Host 'Install complete. Restart Claude Code, then check with the check_worker_backends MCP tool.'
Write-Host ''
Write-Host 'MANUAL STEP: settings.json env block (1M typed aliases, deferred tool loading).'
Write-Host 'Merge the env block from docs\setup\env-vars.md into the "env" object of'
Write-Host '~\.claude\settings.json. Not automated on purpose: settings.json is live user config.'
