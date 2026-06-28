from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import textwrap
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("agent-visibility")

HOME = Path.home()
CODEX = Path(r"C:\Users\jonny\AppData\Roaming\npm\codex.cmd")
CLAUDE = Path(r"C:\Users\jonny\.local\bin\claude.exe")
PYTHON = Path(r"C:\Users\jonny\AppData\Local\Python\pythoncore-3.14-64\python.exe")


def _now() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _slug(value: str, fallback: str = "agent") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())[:48].strip("-")
    return value or fallback


def _ps(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_root(cwd: str | None) -> Path:
    if cwd:
        root = Path(cwd).expanduser().resolve()
        return root / ".claude-codex" / "runs"
    return HOME / ".claude-codex" / "runs"


def _make_run(cwd: str | None, prefix: str, title: str, prompt: str, metadata: dict[str, Any]) -> Path:
    run_id = f"{_now()}-{_slug(prefix)}-{uuid.uuid4().hex[:8]}"
    run_dir = _run_root(cwd) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "title": title, **metadata}, indent=2),
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"status": "created", "run_id": run_id, "created_at": _dt.datetime.now().isoformat()}, indent=2),
        encoding="utf-8",
    )
    return run_dir


def _launch(script_path: Path) -> int:
    flags = 0x00000010 if os.name == "nt" else 0
    proc = subprocess.Popen(
        ["powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=str(script_path.parent),
        creationflags=flags,
    )
    return int(proc.pid)


def _codex_runner(run_dir: Path, cwd: str, sandbox: str, approval_policy: str, model: str, reasoning_effort: str) -> str:
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$RawLog = Join-Path $RunDir 'events.jsonl'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$ThreadPath = Join-Path $RunDir 'thread_id.txt'
$Codex = {_ps(CODEX)}
$Cwd = {_ps(cwd)}
$Sandbox = {_ps(sandbox)}
$ApprovalPolicy = {_ps(approval_policy)}
$Model = {_ps(model)}
$ReasoningEffort = {_ps(reasoning_effort)}
$Host.UI.RawUI.WindowTitle = "Codex visible worker - $(Split-Path $RunDir -Leaf)"

function Set-Status([string]$Status) {{
  @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}}

function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Add-Content -LiteralPath $DisplayLog -Encoding UTF8 -Value $line
  Write-Host $line -ForegroundColor $Color
}}

function Show-JsonEvent($obj) {{
  if ($obj.type -eq 'thread.started') {{
    $obj.thread_id | Set-Content -LiteralPath $ThreadPath -Encoding UTF8
    Log-Line "Codex thread: $($obj.thread_id)" 'Cyan'
    return
  }}
  if ($obj.type -eq 'turn.started') {{ Log-Line 'Turn started' 'DarkCyan'; return }}
  if ($obj.type -eq 'turn.failed') {{ Log-Line "Turn failed: $($obj.error.message)" 'Red'; return }}
  if ($obj.type -eq 'error') {{ Log-Line "Error: $($obj.message)" 'Red'; return }}
  if ($obj.type -eq 'turn.completed') {{
    if ($obj.usage) {{
      Log-Line "Turn completed. Tokens in=$($obj.usage.input_tokens) cached=$($obj.usage.cached_input_tokens) out=$($obj.usage.output_tokens) reasoning=$($obj.usage.reasoning_output_tokens)" 'Green'
    }} else {{
      Log-Line 'Turn completed' 'Green'
    }}
    return
  }}
  if ($obj.type -eq 'item.started') {{
    $item = $obj.item
    if ($item.command) {{ Log-Line "Command: $($item.command)" 'Yellow'; return }}
    Log-Line "Started: $($item.type)" 'DarkYellow'
    return
  }}
  if ($obj.type -eq 'item.completed') {{
    $item = $obj.item
    if ($item.type -eq 'agent_message' -and $item.text) {{
      Log-Line 'Agent message:' 'Green'
      $item.text | Tee-Object -FilePath $DisplayLog -Append
      return
    }}
    if ($item.type -eq 'reasoning') {{
      Log-Line 'Reasoning/progress event received. Hidden model reasoning is not displayed.' 'DarkGray'
      return
    }}
    if ($item.command) {{ Log-Line "Command done: $($item.command)" 'Yellow'; return }}
    if ($item.type) {{ Log-Line "Completed: $($item.type)" 'DarkGreen'; return }}
  }}
}}

Clear-Host
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Sandbox: $Sandbox | Approval: $ApprovalPolicy | Model: $Model | Reasoning: $ReasoningEffort" 'Cyan'
Log-Line 'Prompt follows:' 'Magenta'
Get-Content -LiteralPath $PromptPath -Raw | Tee-Object -FilePath $DisplayLog -Append
Log-Line 'Starting Codex. Raw JSONL is saved to events.jsonl.' 'Magenta'

$argsList = @('exec','--json','-C',$Cwd,'--sandbox',$Sandbox,'-c',"approval_policy=`"$ApprovalPolicy`"")
if ($Model -and $Model -ne '') {{ $argsList += @('-m',$Model) }}
if ($ReasoningEffort -and $ReasoningEffort -ne '') {{ $argsList += @('-c', "model_reasoning_effort=`"$ReasoningEffort`"") }}
$argsList += '-'

$prompt = Get-Content -LiteralPath $PromptPath -Raw
$prompt | & $Codex @argsList 2>&1 | ForEach-Object {{
  $line = [string]$_
  Add-Content -LiteralPath $RawLog -Encoding UTF8 -Value $line
  try {{
    $obj = $line | ConvertFrom-Json -ErrorAction Stop
    Show-JsonEvent $obj
  }} catch {{
    Log-Line $line 'Gray'
  }}
}}

$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {{ Set-Status 'completed' }} else {{ Set-Status "failed:$exitCode" }}
Log-Line "Codex exited with code $exitCode" $(if ($exitCode -eq 0) {{ 'Green' }} else {{ 'Red' }})

try {{
  Log-Line 'Git status:' 'Cyan'
  & git -C $Cwd status --short | Tee-Object -FilePath $DisplayLog -Append
  Log-Line 'Git diff stat:' 'Cyan'
  & git -C $Cwd diff --stat | Tee-Object -FilePath $DisplayLog -Append
}} catch {{
  Log-Line "Git summary unavailable: $($_.Exception.Message)" 'DarkGray'
}}
Log-Line 'Window left open for inspection. Close it when finished.' 'Magenta'
"""


def _claude_runner(run_dir: Path, cwd: str, model: str, effort: str) -> str:
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$RawLog = Join-Path $RunDir 'events.jsonl'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$Claude = {_ps(CLAUDE)}
$Cwd = {_ps(cwd)}
$Model = {_ps(model)}
$Effort = {_ps(effort)}
$Host.UI.RawUI.WindowTitle = "Claude visible advisor - $(Split-Path $RunDir -Leaf)"

function Set-Status([string]$Status) {{
  @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}}
function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Add-Content -LiteralPath $DisplayLog -Encoding UTF8 -Value $line
  Write-Host $line -ForegroundColor $Color
}}
function Show-ClaudeEvent($obj) {{
  if ($obj.type -eq 'assistant' -and $obj.message) {{
    foreach ($c in $obj.message.content) {{
      if ($c.type -eq 'text') {{ $c.text | Tee-Object -FilePath $DisplayLog -Append }}
    }}
    return
  }}
  if ($obj.type -eq 'result') {{
    Log-Line "Claude result: subtype=$($obj.subtype) cost=$($obj.total_cost_usd) duration_ms=$($obj.duration_ms)" 'Green'
    if ($obj.result) {{ $obj.result | Tee-Object -FilePath $DisplayLog -Append }}
    return
  }}
  if ($obj.type -eq 'system') {{ Log-Line "Claude system: $($obj.subtype)" 'DarkCyan'; return }}
  if ($obj.type -eq 'tool_use' -or $obj.type -eq 'tool_result') {{ Log-Line "Claude tool event: $($obj.type)" 'Yellow'; return }}
}}

Clear-Host
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Model: $Model | Effort: $Effort | Permission mode: plan" 'Cyan'
Log-Line 'Prompt follows:' 'Magenta'
Get-Content -LiteralPath $PromptPath -Raw | Tee-Object -FilePath $DisplayLog -Append
Log-Line 'Starting Claude advisor. Raw stream JSON is saved to events.jsonl.' 'Magenta'

$argsList = @('-p','--output-format','stream-json','--permission-mode','plan','--add-dir',$Cwd)
if ($Model -and $Model -ne '') {{ $argsList += @('--model',$Model) }}
if ($Effort -and $Effort -ne '') {{ $argsList += @('--effort',$Effort) }}

$prompt = Get-Content -LiteralPath $PromptPath -Raw
$prompt | & $Claude @argsList 2>&1 | ForEach-Object {{
  $line = [string]$_
  Add-Content -LiteralPath $RawLog -Encoding UTF8 -Value $line
  try {{
    $obj = $line | ConvertFrom-Json -ErrorAction Stop
    Show-ClaudeEvent $obj
  }} catch {{
    Log-Line $line 'Gray'
  }}
}}
$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {{ Set-Status 'completed' }} else {{ Set-Status "failed:$exitCode" }}
Log-Line "Claude exited with code $exitCode" $(if ($exitCode -eq 0) {{ 'Green' }} else {{ 'Red' }})
Log-Line 'Window left open for inspection. Close it when finished.' 'Magenta'
"""


@mcp.tool()
def start_visible_codex_worker(
    prompt: str,
    cwd: str,
    title: str = "Codex worker",
    sandbox: str = "read-only",
    approval_policy: str = "never",
    model: str = "gpt-5.5",
    reasoning_effort: str = "xhigh",
) -> dict[str, Any]:
    """Launch a visible Codex exec worker in a separate PowerShell window and save logs."""
    run_dir = _make_run(cwd, "codex", title, prompt, {
        "agent": "codex",
        "sandbox": sandbox,
        "approval_policy": approval_policy,
        "model": model,
        "reasoning_effort": reasoning_effort,
    })
    script = run_dir / "run.ps1"
    script.write_text(_codex_runner(run_dir, str(Path(cwd).resolve()), sandbox, approval_policy, model, reasoning_effort), encoding="utf-8")
    pid = _launch(script)
    return {
        "run_id": run_dir.name,
        "pid": pid,
        "run_dir": str(run_dir),
        "prompt": str(run_dir / "prompt.md"),
        "display_log": str(run_dir / "display.log"),
        "raw_events": str(run_dir / "events.jsonl"),
        "status": str(run_dir / "status.json"),
        "note": "A visible PowerShell window was launched. Hidden model reasoning is not exposed; prompts, events, messages, commands, usage, and diffs are logged.",
    }


@mcp.tool()
def start_visible_first_mate_codex_pool(
    goal: str,
    cwd: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    max_workers: int = 6,
    model: str = "gpt-5.5",
    reasoning_effort: str = "xhigh",
) -> dict[str, Any]:
    """Launch a visible Codex root session instructed to act as first mate and manage parallel Codex subagents."""
    scout_areas = scout_areas or []
    implementation_items = implementation_items or []
    prompt = f"""
You are Codex First Mate, managed by Claude Code.

Goal:
{goal}

Operating rules:
- Claude is the senior developer and owns architecture, risk decisions, and final review.
- You are the Codex coordinator. Use Codex subagents to reduce Claude token use.
- Prefer `claude-explorer` for read-only codebase/context scouting.
- Use `claude-implementer` only for bounded implementation after Claude has provided scope and this run has write permission.
- Use `claude-reviewer` for read-only review.
- Keep fan-out bounded to at most {max_workers} workers.
- Do not spawn recursive subagent trees.
- Return compact summaries, changed files, verification results, blockers, and questions for Claude.
- Update `.claude-codex/BRIDGE.md` with worker assignments, status, changed files, and verification.
- Hidden model reasoning is not visible to the user; expose useful progress through concise summaries and logs.

Scout areas:
{chr(10).join(f"- {x}" for x in scout_areas) if scout_areas else "- Map the codebase at a high level, identify relevant modules, tests, and risk areas."}

Implementation items:
{chr(10).join(f"- {x}" for x in implementation_items) if implementation_items else "- None unless Claude provided explicit scope."}

Sandbox for this root run: {sandbox}
If sandbox is read-only, do not attempt implementation. Scout and summarize.
"""
    return start_visible_codex_worker(
        prompt=textwrap.dedent(prompt).strip(),
        cwd=cwd,
        title="Codex first mate pool",
        sandbox=sandbox,
        approval_policy="never",
        model=model,
        reasoning_effort=reasoning_effort,
    )


@mcp.tool()
def start_visible_claude_advisor(
    prompt: str,
    cwd: str,
    title: str = "Claude advisor",
    model: str = "sonnet",
    effort: str = "high",
) -> dict[str, Any]:
    """Launch a visible Claude Code advisor run in a separate PowerShell window and save stream logs."""
    run_dir = _make_run(cwd, "claude", title, prompt, {
        "agent": "claude",
        "model": model,
        "effort": effort,
        "permission_mode": "plan",
    })
    script = run_dir / "run.ps1"
    script.write_text(_claude_runner(run_dir, str(Path(cwd).resolve()), model, effort), encoding="utf-8")
    pid = _launch(script)
    return {
        "run_id": run_dir.name,
        "pid": pid,
        "run_dir": str(run_dir),
        "prompt": str(run_dir / "prompt.md"),
        "display_log": str(run_dir / "display.log"),
        "raw_events": str(run_dir / "events.jsonl"),
        "status": str(run_dir / "status.json"),
        "note": "A visible PowerShell window was launched for Claude advisor output. Hidden model reasoning is not exposed.",
    }


@mcp.tool()
def get_visible_run_status(run_dir: str, tail_lines: int = 80) -> dict[str, Any]:
    """Read status and recent visible log lines from a visible agent run directory."""
    path = Path(run_dir)
    status_path = path / "status.json"
    display_path = path / "display.log"
    thread_path = path / "thread_id.txt"
    metadata_path = path / "metadata.json"
    status = json.loads(status_path.read_text(encoding="utf-8-sig")) if status_path.exists() else {"status": "unknown"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
    lines: list[str] = []
    if display_path.exists():
        all_lines = display_path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = all_lines[-max(1, min(tail_lines, 500)):]
    return {
        "run_dir": str(path),
        "status": status,
        "metadata": metadata,
        "thread_id": thread_path.read_text(encoding="utf-8").strip() if thread_path.exists() else None,
        "tail": "\n".join(lines),
    }


@mcp.tool()
def list_visible_runs(cwd: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """List recent visible agent run directories."""
    root = _run_root(cwd)
    if not root.exists():
        return []
    runs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)[: max(1, min(limit, 100))]
    result = []
    for run in runs:
        status_path = run / "status.json"
        metadata_path = run / "metadata.json"
        result.append({
            "run_id": run.name,
            "run_dir": str(run),
            "status": json.loads(status_path.read_text(encoding="utf-8-sig")) if status_path.exists() else {"status": "unknown"},
            "metadata": json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {},
        })
    return result


if __name__ == "__main__":
    mcp.run()
