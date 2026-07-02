from __future__ import annotations

import atexit
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
READ_PAST_SESSIONS_SKILL = Path(r"C:\Users\jonny\.agents\skills\read-past-sessions")
PLAYWRIGHT_NODE_PATH = r"C:\Users\jonny\node_modules;C:\Users\jonny\.codex\playwright-runtime\node_modules"
PLAYWRIGHT_BROWSERS_PATH = Path(r"C:\Users\jonny\AppData\Local\ms-playwright")

CODEX_MODEL = "gpt-5.5"
CODEX_REASONING_EFFORT = "xhigh"
CODEX_SERVICE_TIER = "fast"
CODEX_FULL_TOOL_SANDBOX = "danger-full-access"
CODEX_DEFAULT_SANDBOX = CODEX_FULL_TOOL_SANDBOX
CAPTAIN_HELP_DIR = "captain_help"
CAPTAIN_HELP_REQUESTS_DIR = "requests"
CAPTAIN_HELP_ANSWERED_DIR = "answered"
CAPTAIN_HELP_ESCALATED_DIR = "escalated"
CLAUDE_ADVISOR_MODEL_ENV = "CLAUDE_MANAGES_CODEX_ADVISOR_MODEL"
CLAUDE_ADVISOR_MODEL_UNTIL_ENV = "CLAUDE_MANAGES_CODEX_FABLE_UNTIL"
CLAUDE_ADVISOR_PRIMARY_MODEL = "fable"
CLAUDE_ADVISOR_FALLBACK_MODEL = "opus"
CLAUDE_ADVISOR_PRIMARY_UNTIL = _dt.date(2026, 7, 7)
CLAUDE_EFFORT = "high"
CLAUDE_MAX_BUDGET_USD = "0.50"
CLAUDE_PROMPT_COMPOSER_MODEL = "haiku"
CLAUDE_PROMPT_COMPOSER_EFFORT = "low"
CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD = "0.25"
CODEX_STEER_IDLE_SECONDS = 20

TOOL_ACCESS_KEYWORDS = (
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "serial",
    "uart",
    "radxa",
    "router",
    "ethernet",
    "network",
    "ping",
    "nmap",
    "live device",
    "device debugging",
    "hardware bring-up",
    "tool access",
    "external tool",
    "docker",
    "pip install",
    "npm install",
    "package manager",
)


def _advisor_primary_until() -> _dt.date:
    raw = os.environ.get(CLAUDE_ADVISOR_MODEL_UNTIL_ENV, "").strip()
    if raw:
        try:
            return _dt.date.fromisoformat(raw)
        except ValueError:
            pass
    return CLAUDE_ADVISOR_PRIMARY_UNTIL


def _default_claude_advisor_model(today: _dt.date | None = None) -> str:
    override = os.environ.get(CLAUDE_ADVISOR_MODEL_ENV, "").strip()
    if override:
        return override
    today = today or _dt.date.today()
    if today <= _advisor_primary_until():
        return CLAUDE_ADVISOR_PRIMARY_MODEL
    return CLAUDE_ADVISOR_FALLBACK_MODEL


def _claude_advisor_model_policy() -> str:
    override = os.environ.get(CLAUDE_ADVISOR_MODEL_ENV, "").strip()
    if override:
        return f"{CLAUDE_ADVISOR_MODEL_ENV}={override}"
    return (
        f"{CLAUDE_ADVISOR_PRIMARY_MODEL} through {_advisor_primary_until().isoformat()}, "
        f"then {CLAUDE_ADVISOR_FALLBACK_MODEL}; override with {CLAUDE_ADVISOR_MODEL_ENV}"
    )


FIRSTMATE_CONTRACT = """
You are Codex First Mate.
Claude Code is the captain.
The human user is the owner; do not address the owner directly unless Claude explicitly asks you to draft owner-facing text.

Address Claude as "captain" at least once in every response. Keep the address concise and professional.

Runtime requirement: use Codex gpt-5.5, xhigh reasoning, and service_tier=fast for root and subagent work in this bridge.

Session requirement: do not act as a blank chat. Use caller-provided context first. If the task depends on earlier conversation history, use read-past-sessions before scouting or implementing, then pass compact context into every subagent brief.

Tool-access requirement: this bridge gives Codex workers full process/tool access so Python skills, read-past-sessions, SSH, and external CLIs work. Treat Claude's requested sandbox as permission intent. If intent is read-only/no-edit, do not modify files or external state even though tools are available.

Prompt-cost requirement: expect Claude's active manager model to send compact captain briefs. Long Codex worker prompts should be composed by the Haiku/low prompt composer before they reach you.

Captain-help requirement: if you are blocked, confused, or about to make an architectural/safety decision without enough confidence, request help from the same Claude captain through the run's captain-help mailbox. Do not start a separate Claude advisor unless Claude explicitly asked for that. After requesting help, stop the current turn and wait for captain steering. The captain may escalate the question to the owner.

Prime directives:
- Delegate project-specific work to Codex agents when the task benefits from parallelism, cheaper exploration, noisy command/log work, scoped implementation, verification, review, or recovery.
- Keep Claude's context compact. Return decisions, evidence, changed files, verification, blockers, and questions instead of raw transcripts or long excerpts.
- Never change files unless Claude granted write permission and supplied a bounded scope.
- Never use broad, destructive, or security-sensitive actions without stopping for Claude's approval.
- Preserve user changes. Inspect git status before edits when writes are allowed, and do not overwrite unrelated work.
- Report outcomes faithfully. If work failed or verification is incomplete, say so plainly with evidence.

Roles:
- Claude owns architecture, decomposition, acceptance criteria, risk decisions, and final user response.
- You own Codex worker coordination, task assignment, progress synthesis, and return briefs.
- Codex agents own scoped exploration, implementation, verification, and review tasks.

Prefer these agents when available:
- claude-explorer: no-edit codebase scouting, Python/skill use, and context distillation.
- claude-implementer: bounded implementation in assigned files or areas.
- claude-reviewer: read-only correctness, security, regression, and diff review.
- claude-debugger: full-tool SSH, device, network, and command-heavy debugging when Claude explicitly allows full tool access.

Keep fan-out bounded to Claude's requested worker count, or at most 6 workers by default. Do not spawn recursive subagent trees. For parallel write work, assign file-disjoint scopes. If ownership is unclear, stop and ask Claude rather than running parallel writers.

For non-trivial repo work, create or update .claude-codex/BRIDGE.md with the goal, Claude decisions, worker ledger, changed files, open questions, and verification.

Record resumable Codex thread ids and Claude session ids in .claude-codex/BRIDGE.md whenever continuation may matter.

Return compactly with: Outcome, Workers, Changed files, Verification, Risks, and Questions.
""".strip()


# PowerShell function injected into every run script. When a run finishes it reaps the
# leftover child runtimes (codex / node / codex-windows-sandbox-setup / claude) that Codex
# leaves behind. It is scoped *strictly* to descendants of this run's own PowerShell window
# ($PID), so it can never touch the long-lived MCP servers or Claude Code itself — those are
# launched by a different parent and are not descendants of this console.
_PS_CLEANUP_FN = r"""
function Stop-RunDescendants {
  param([int]$RootPid)
  $targets = @('codex','codex-windows-sandbox-setup','node','claude')
  try { $all = Get-CimInstance Win32_Process -ErrorAction Stop } catch { return }
  $byParent = @{}
  foreach ($p in $all) {
    $k = [int]$p.ParentProcessId
    if (-not $byParent.ContainsKey($k)) { $byParent[$k] = New-Object System.Collections.ArrayList }
    [void]$byParent[$k].Add($p)
  }
  $descendants = New-Object System.Collections.ArrayList
  $queue = New-Object System.Collections.Queue
  $queue.Enqueue([int]$RootPid)
  while ($queue.Count -gt 0) {
    $cur = [int]$queue.Dequeue()
    if ($byParent.ContainsKey($cur)) {
      foreach ($child in $byParent[$cur]) {
        [void]$descendants.Add($child)
        $queue.Enqueue([int]$child.ProcessId)
      }
    }
  }
  $killed = 0
  foreach ($proc in ($descendants | Sort-Object ProcessId -Descending)) {
    if ([int]$proc.ProcessId -eq [int]$RootPid) { continue }
    $base = ($proc.Name -replace '\.exe$','').ToLower()
    if ($targets -contains $base) {
      try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; $killed++ } catch {}
    }
  }
  Log-Line "Reaped $killed leftover agent process(es) for this run." 'DarkGray'
}
"""


# PIDs of visible-run PowerShell windows this server has launched, so they (and their whole
# codex/node/sandbox process trees) can be torn down when the MCP server exits at session end.
_LAUNCHED_PIDS: list[int] = []


def _reap_launched() -> None:
    for pid in _LAUNCHED_PIDS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass


atexit.register(_reap_launched)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _slug(value: str, fallback: str = "agent") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())[:48].strip("-")
    return value or fallback


def _needs_full_tool_access(value: str) -> bool:
    lower = value.lower()
    return any(keyword in lower for keyword in TOOL_ACCESS_KEYWORDS)


def _codex_permission_contract(requested_sandbox: str, effective_sandbox: str) -> str:
    requested = (requested_sandbox or "read-only").strip()
    if requested == "read-only":
        intent = "NO-EDIT inspection. You may run Python, skills, search tools, and safe read-only commands, but you must not modify files or external state."
    elif requested == "workspace-write":
        intent = "SCOPED workspace edits only. Change files only inside Claude's stated scope, preserve unrelated user work, and ask Claude before expanding scope."
    elif requested == "danger-full-access":
        intent = "FULL-TOOL debugging or implementation. Start with safe inspection, report commands and results, and ask Claude before destructive, persistent, credential, service, firmware, or data-loss actions."
    else:
        intent = f"Custom intent `{requested}`. Follow Claude's written scope exactly and ask before acting outside it."
    return textwrap.dedent(f"""
    # Codex Permission Contract

    Actual process sandbox: {effective_sandbox}
    Claude-requested permission intent: {requested}

    {intent}

    The full process sandbox exists so Python-based skills, read-past-sessions, SSH, external CLIs, and developer tooling work. It is not blanket permission to edit files or mutate external systems.
    """).strip()


def _haiku_codex_prompt_composer_prompt(
    brief: str,
    cwd: str,
    title: str,
    requested_sandbox: str,
    session_context: str,
    resume_session_id: str,
    requires_tool_access: bool,
) -> str:
    context = session_context.strip() or "None supplied."
    return textwrap.dedent(f"""
    You are Claude Haiku acting as a cheap prompt composer for a Claude manager -> Codex bridge.

    Your job is ONLY to turn the compact captain brief into a clear Codex worker prompt.
    Do not make architectural decisions, choose a different plan, ask questions, read files, run tools, or add broad new scope.
    Preserve Claude's decisions and constraints exactly.

    Output only the final Codex prompt in markdown. Do not wrap it in code fences.

    The Codex prompt must include, in this order:
    1. Objective and success criteria.
    2. Session context summary and any previous run/thread ids.
    3. Permission intent and tool-access boundaries.
    4. Files/areas to inspect or edit, if supplied.
    5. Step-by-step task instructions.
    6. Verification commands or checks.
    7. Required final response format for Codex.

    Keep the prompt complete enough that Codex does not need the manager model to restate it, but avoid filler and raw transcript.

    Runtime facts:
    - Title: {title}
    - CWD: {cwd}
    - Requested permission intent: {requested_sandbox}
    - Requires full tool/debug access: {requires_tool_access}
    - Resume session/thread id: {resume_session_id or "none"}
    - Codex runtime: gpt-5.5, xhigh reasoning, service_tier=fast.

    Caller-provided session context:
    {context}

    Compact captain brief to expand:
    {brief}
    """).strip()


def _ps(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _with_session_context_bootstrap(prompt: str, cwd: str, agent_role: str, session_context: str = "") -> str:
    supplied_context = session_context.strip() or (
        "None supplied by the caller. Reconstruct context before acting."
    )
    sessions_script = READ_PAST_SESSIONS_SKILL / "scripts" / "sessions.py"
    project_hint = Path(cwd).name or "current-project"
    return textwrap.dedent(f"""
    # Session Context Bootstrap

    You are starting as a spawned {agent_role}, not a blank chat. Before acting:

    1. Read the caller-provided context below first. If it is sufficient and explicitly says the task is self-contained, do not spend time recovering old transcripts.
    2. Use the `read-past-sessions` skill when the task depends on prior conversation, previous run ids, compacted context, earlier decisions, or unresolved mistakes from this project.
    3. If the skill is needed but not available, run the bundled engine directly:
       `python "{sessions_script}" list "{project_hint}" --limit 5`
       `python "{sessions_script}" show <session-id> --mode briefing --include-subagents --max-chars 120000`
    4. Prefer the newest relevant session for this cwd/task. If a required decision is missing from the briefing, rerun `show` with `--mode full --include-subagents --max-chars 200000`.
    5. Treat the caller-provided context below as authoritative. Use recovered session context to avoid rederiving prior decisions or repeating already-fixed mistakes.
    6. Do not paste full transcripts back unless asked. Return compact evidence, decisions, files, verification, blockers, and questions.

    CWD: {cwd}

    ## Caller-Provided Session Context

    {supplied_context}

    ## Assigned Task

    {prompt.strip()}
    """).strip()


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
    _ensure_captain_help_dirs(run_dir)
    return run_dir


def _ensure_captain_help_dirs(run_dir: Path) -> dict[str, Path]:
    root = run_dir / CAPTAIN_HELP_DIR
    requests = root / CAPTAIN_HELP_REQUESTS_DIR
    answered = root / CAPTAIN_HELP_ANSWERED_DIR
    escalated = root / CAPTAIN_HELP_ESCALATED_DIR
    for path in (requests, answered, escalated):
        path.mkdir(parents=True, exist_ok=True)
    return {"root": root, "requests": requests, "answered": answered, "escalated": escalated}


def _captain_help_contract(run_dir: Path) -> str:
    return textwrap.dedent(f"""
    # Captain Help Callback

    This visible run has a same-captain help mailbox.

    Run directory: {run_dir}

    If you are blocked, confused, unsure about architecture, unsure whether writes are safe, or stuck after one focused repair attempt:

    1. Use the `request_captain_help` MCP tool if available.
    2. Pass `run_dir` exactly as shown above.
    3. Include the question, observed facts, commands/results, files involved, options considered, and your recommended next step.
    4. After submitting the request, stop the current turn with `Outcome: blocked_waiting_for_captain`.
    5. Do not ask the human owner directly. The same Claude captain may answer you via `steer_visible_codex_run` or escalate to the owner if needed.

    Use `start_visible_claude_advisor` only when Claude explicitly asked you to consult a separate one-shot advisor. The default stuck-worker path is this same-captain mailbox.
    """).strip()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _infer_cwd_from_run_dir(run_dir: Path, metadata: dict[str, Any]) -> str:
    cwd = metadata.get("cwd")
    if cwd:
        return str(Path(cwd).expanduser().resolve())
    # Normal layout: <cwd>/.claude-codex/runs/<run-id>
    try:
        if run_dir.parent.name == "runs" and run_dir.parent.parent.name == ".claude-codex":
            return str(run_dir.parent.parent.parent.resolve())
    except Exception:
        pass
    return str(HOME)


def _status_name(status: Any) -> str:
    if isinstance(status, dict):
        return str(status.get("status", "unknown"))
    return str(status or "unknown")


def _write_steer_file(
    run_dir: Path,
    instruction: str,
    session_context: str = "",
    title: str = "Claude steering",
    permission_contract: str = "",
) -> Path:
    steer_queue = run_dir / "steer_queue"
    steer_queue.mkdir(parents=True, exist_ok=True)
    steer_id = f"{_now()}-steer-{uuid.uuid4().hex[:8]}.md"
    context = session_context.strip() or "No extra session_context supplied with this steering note."
    permission_section = (
        f"## Updated Permission Intent\n\n{permission_contract.strip()}\n\n"
        if permission_contract.strip()
        else ""
    )
    prompt = textwrap.dedent(f"""
    # Claude Captain Steering

    You are continuing the same Codex thread for a visible Claude-managed run.
    Do not restart from scratch. Apply this steering instruction to the current task, preserve prior context, and keep Claude's role as captain.

    Title: {title}
    Original run: {run_dir}

    ## New Steering Instruction

    {instruction.strip()}

    {permission_section}\
    ## Additional Session Context

    {context}

    ## Required Response

    Address Claude as captain. Return only the delta since the prior turn: what changed, current state, files touched, verification, risks, and any decisions needed from Claude.
    """).strip()
    steer_path = steer_queue / steer_id
    steer_path.write_text(prompt, encoding="utf-8")
    return steer_path


def _launch(script_path: Path) -> int:
    flags = 0x00000010 if os.name == "nt" else 0
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=str(script_path.parent),
        creationflags=flags,
    )
    _LAUNCHED_PIDS.append(int(proc.pid))
    return int(proc.pid)


def _codex_runner(
    run_dir: Path,
    cwd: str,
    sandbox: str,
    approval_policy: str,
    model: str,
    reasoning_effort: str,
    service_tier: str,
    resume_session_id: str = "",
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = CODEX_STEER_IDLE_SECONDS,
) -> str:
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$ComposerPromptPath = Join-Path $RunDir 'composer_prompt.md'
$ComposerRawLog = Join-Path $RunDir 'composer_events.jsonl'
$ComposedPromptPath = Join-Path $RunDir 'composed_prompt.md'
$CodexPreludePath = Join-Path $RunDir 'codex_prelude.md'
$RawLog = Join-Path $RunDir 'events.jsonl'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$ThreadPath = Join-Path $RunDir 'thread_id.txt'
$SteerQueue = Join-Path $RunDir 'steer_queue'
$SteerDone = Join-Path $RunDir 'steer_done'
$Codex = {_ps(CODEX)}
$Claude = {_ps(CLAUDE)}
$Cwd = {_ps(cwd)}
$Sandbox = {_ps(sandbox)}
$ApprovalPolicy = {_ps(approval_policy)}
$Model = {_ps(model)}
$ReasoningEffort = {_ps(reasoning_effort)}
$ServiceTier = {_ps(service_tier)}
$ResumeSessionId = {_ps(resume_session_id)}
$ComposeWithHaiku = {"$true" if compose_with_haiku else "$false"}
$ComposerModel = {_ps(composer_model)}
$ComposerEffort = {_ps(composer_effort)}
$ComposerMaxBudgetUsd = {_ps(composer_max_budget_usd)}
$SteerIdleSeconds = {max(0, min(int(steer_idle_seconds), 300))}
$PlaywrightNodePath = {_ps(PLAYWRIGHT_NODE_PATH)}
$PlaywrightBrowsersPath = {_ps(PLAYWRIGHT_BROWSERS_PATH)}
# Force UTF-8 so Codex's UTF-8 stdout/stdin is decoded correctly (avoids mojibake like the
# right-single-quote turning into "ΓÇÖ" when PowerShell falls back to the OEM code page).
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$env:NODE_PATH = $PlaywrightNodePath
$env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
$Host.UI.RawUI.WindowTitle = "Codex visible worker - $(Split-Path $RunDir -Leaf)"

# UTF-8 tee helper. Tee-Object in Windows PowerShell 5.1 has no -Encoding param and writes
# UTF-16LE, which corrupts display.log with NUL bytes; this appends UTF-8 instead.
function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Add-Content -LiteralPath $DisplayLog -Encoding UTF8 -Value $text
  }}
}}

function Set-Status([string]$Status) {{
  @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8
}}

function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Add-Content -LiteralPath $DisplayLog -Encoding UTF8 -Value $line
  Write-Host $line -ForegroundColor $Color
}}

function Get-CurrentThreadId {{
  if (Test-Path -LiteralPath $ThreadPath) {{
    return (Get-Content -LiteralPath $ThreadPath -Raw).Trim()
  }}
  return $ResumeSessionId
}}

function Get-NextSteerFile {{
  if (-not (Test-Path -LiteralPath $SteerQueue)) {{ return $null }}
  $next = Get-ChildItem -LiteralPath $SteerQueue -Filter '*.md' -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
  return $next
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
    if ($item.type -eq 'error') {{
      Log-Line "Nonfatal Codex event error: $($item.message)" 'DarkYellow'
      return
    }}
    if ($item.type -eq 'agent_message' -and $item.text) {{
      Log-Line 'Agent message:' 'Green'
      $item.text | Write-Raw
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

function Invoke-CodexPrompt {{
  param(
    [string]$CodexPromptPath,
    [string]$ThreadId,
    [string]$TurnLabel
  )
  $turnThread = ''
  if ($ThreadId) {{ $turnThread = $ThreadId.Trim() }}
  Set-Status "running:$TurnLabel"
  if ($turnThread -and $turnThread -ne '') {{
    Log-Line "Starting Codex resume turn: $TurnLabel | thread: $turnThread" 'Magenta'
  }} else {{
    Log-Line "Starting Codex new turn: $TurnLabel" 'Magenta'
  }}
  Log-Line 'Raw JSONL is saved to events.jsonl.' 'Magenta'

  $argsList = @('exec')
  $UseSandboxBypass = $Sandbox -eq 'danger-full-access'
  if ($turnThread -and $turnThread -ne '') {{
    $argsList += @('resume','--json','-c',"approval_policy=`"$ApprovalPolicy`"")
    if ($UseSandboxBypass) {{ $argsList += '--dangerously-bypass-approvals-and-sandbox' }}
  }} else {{
    $argsList += @('--json','-C',$Cwd,'-c',"approval_policy=`"$ApprovalPolicy`"")
    if ($UseSandboxBypass) {{
      $argsList += '--dangerously-bypass-approvals-and-sandbox'
    }} else {{
      $argsList += @('--sandbox',$Sandbox)
    }}
  }}
  if ($Model -and $Model -ne '') {{ $argsList += @('-m',$Model) }}
  if ($ReasoningEffort -and $ReasoningEffort -ne '') {{ $argsList += @('-c', "model_reasoning_effort=`"$ReasoningEffort`"") }}
  if ($ServiceTier -and $ServiceTier -ne '') {{ $argsList += @('-c', "service_tier=`"$ServiceTier`"") }}
  if ($turnThread -and $turnThread -ne '') {{ $argsList += $turnThread }}
  $argsList += '-'

  $prompt = Get-Content -LiteralPath $CodexPromptPath -Raw
  Push-Location $Cwd
  try {{
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
  }} finally {{
    Pop-Location
  }}

  $code = $LASTEXITCODE
  Log-Line "Codex turn '$TurnLabel' exited with code $code" $(if ($code -eq 0) {{ 'Green' }} else {{ 'Red' }})
  Stop-RunDescendants -RootPid $PID
  return $code
}}

{_PS_CLEANUP_FN}
Clear-Host
New-Item -ItemType Directory -Force -Path $SteerQueue | Out-Null
New-Item -ItemType Directory -Force -Path $SteerDone | Out-Null
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Sandbox: $Sandbox | Approval: $ApprovalPolicy | Model: $Model | Reasoning: $ReasoningEffort | Service tier: $ServiceTier" 'Cyan'
Log-Line "Playwright: NODE_PATH=$env:NODE_PATH | PLAYWRIGHT_BROWSERS_PATH=$env:PLAYWRIGHT_BROWSERS_PATH" 'Cyan'
if ($ResumeSessionId -and $ResumeSessionId -ne '') {{ Log-Line "Resuming Codex session/thread: $ResumeSessionId" 'Cyan' }}
$CodexPromptPath = $PromptPath
if ($ComposeWithHaiku) {{
  Log-Line "Haiku prompt composer enabled. Model: $ComposerModel | Effort: $ComposerEffort | Max budget USD: $ComposerMaxBudgetUsd" 'Magenta'
  Log-Line 'Compact captain brief follows:' 'Magenta'
  Get-Content -LiteralPath $PromptPath -Raw | Write-Raw
  Log-Line 'Starting Haiku prompt composer. Raw stream JSON is saved to composer_events.jsonl.' 'Magenta'

  $composerArgs = @('-p','--safe-mode','--no-session-persistence','--prompt-suggestions','false','--verbose','--output-format','stream-json','--permission-mode','plan','--max-budget-usd',$ComposerMaxBudgetUsd)
  if ($ComposerModel -and $ComposerModel -ne '') {{ $composerArgs += @('--model',$ComposerModel) }}
  if ($ComposerEffort -and $ComposerEffort -ne '') {{ $composerArgs += @('--effort',$ComposerEffort) }}

  $assistantChunks = New-Object System.Collections.ArrayList
  $resultText = ''
  $composerPrompt = Get-Content -LiteralPath $ComposerPromptPath -Raw
  $composerPrompt | & $Claude @composerArgs 2>&1 | ForEach-Object {{
    $line = [string]$_
    Add-Content -LiteralPath $ComposerRawLog -Encoding UTF8 -Value $line
    try {{
      $obj = $line | ConvertFrom-Json -ErrorAction Stop
      if ($obj.type -eq 'assistant' -and $obj.message) {{
        foreach ($c in $obj.message.content) {{
          if ($c.type -eq 'text' -and $c.text) {{ [void]$assistantChunks.Add([string]$c.text) }}
        }}
        return
      }}
      if ($obj.type -eq 'result') {{
        Log-Line "Haiku composer result: subtype=$($obj.subtype) cost=$($obj.total_cost_usd) duration_ms=$($obj.duration_ms)" 'Green'
        if ($obj.result) {{ $resultText = [string]$obj.result }}
        return
      }}
      if ($obj.type -eq 'system') {{
        if ($obj.session_id) {{ Log-Line "Haiku composer session: $($obj.session_id)" 'Cyan' }}
        Log-Line "Haiku composer system: $($obj.subtype)" 'DarkCyan'
        return
      }}
    }} catch {{
      Log-Line $line 'Gray'
    }}
  }}
  $composerExitCode = $LASTEXITCODE
  if ($composerExitCode -ne 0) {{
    Set-Status "failed:haiku-composer:$composerExitCode"
    Log-Line "Haiku prompt composer exited with code $composerExitCode" 'Red'
    Stop-RunDescendants -RootPid $PID
    Log-Line 'Agents for this run have been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
    Start-Sleep -Seconds 5
    exit
  }}
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $resultText = (($assistantChunks | ForEach-Object {{ [string]$_ }}) -join "`n")
  }}
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    Set-Status 'failed:haiku-composer-empty'
    Log-Line 'Haiku prompt composer produced an empty Codex prompt.' 'Red'
    Stop-RunDescendants -RootPid $PID
    Log-Line 'Agents for this run have been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
    Start-Sleep -Seconds 5
    exit
  }}
  $prelude = ''
  if (Test-Path -LiteralPath $CodexPreludePath) {{ $prelude = Get-Content -LiteralPath $CodexPreludePath -Raw }}
  $finalPrompt = ($prelude.TrimEnd() + "`n`n## Haiku-Composed Worker Brief`n`n" + $resultText.Trim())
  $finalPrompt | Set-Content -LiteralPath $ComposedPromptPath -Encoding UTF8
  $CodexPromptPath = $ComposedPromptPath
  Log-Line 'Composed Codex prompt follows:' 'Magenta'
  Get-Content -LiteralPath $CodexPromptPath -Raw | Write-Raw
}} else {{
  Log-Line 'Prompt follows:' 'Magenta'
  Get-Content -LiteralPath $PromptPath -Raw | Write-Raw
}}
$exitCode = Invoke-CodexPrompt -CodexPromptPath $CodexPromptPath -ThreadId $ResumeSessionId -TurnLabel 'initial'

while ($exitCode -eq 0) {{
  $waited = 0
  $steerFile = Get-NextSteerFile
  while ($null -eq $steerFile -and $waited -lt $SteerIdleSeconds) {{
    Set-Status 'waiting_for_steer'
    if ($waited -eq 0) {{
      Log-Line "Waiting up to $SteerIdleSeconds second(s) for queued Claude steering before closing." 'DarkCyan'
    }}
    Start-Sleep -Seconds 1
    $waited++
    $steerFile = Get-NextSteerFile
  }}
  if ($null -eq $steerFile) {{ break }}

  $currentThread = Get-CurrentThreadId
  if (-not $currentThread -or $currentThread -eq '') {{
    Set-Status 'failed:steer-no-thread'
    Log-Line "Cannot apply steering because no Codex thread id has been recorded yet: $($steerFile.FullName)" 'Red'
    $exitCode = 1
    break
  }}

  Log-Line "Applying queued Claude steering: $($steerFile.Name)" 'Magenta'
  Get-Content -LiteralPath $steerFile.FullName -Raw | Write-Raw
  $exitCode = Invoke-CodexPrompt -CodexPromptPath $steerFile.FullName -ThreadId $currentThread -TurnLabel "steer:$($steerFile.BaseName)"
  $donePath = Join-Path $SteerDone $steerFile.Name
  try {{ Move-Item -LiteralPath $steerFile.FullName -Destination $donePath -Force }} catch {{}}
}}

if ($exitCode -eq 0) {{ Set-Status 'completed' }} else {{ Set-Status "failed:$exitCode" }}

try {{
  Log-Line 'Git status:' 'Cyan'
  & git -C $Cwd status --short | Write-Raw
  Log-Line 'Git diff stat:' 'Cyan'
  & git -C $Cwd diff --stat | Write-Raw
}} catch {{
  Log-Line "Git summary unavailable: $($_.Exception.Message)" 'DarkGray'
}}
Stop-RunDescendants -RootPid $PID
Log-Line 'Agents for this run have been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
Start-Sleep -Seconds 5
exit
"""


def _claude_runner(
    run_dir: Path,
    cwd: str,
    model: str,
    effort: str,
    max_budget_usd: str,
    resume_session_id: str = "",
) -> str:
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$RawLog = Join-Path $RunDir 'events.jsonl'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$SessionPath = Join-Path $RunDir 'session_id.txt'
$Claude = {_ps(CLAUDE)}
$Cwd = {_ps(cwd)}
$Model = {_ps(model)}
$Effort = {_ps(effort)}
$MaxBudgetUsd = {_ps(max_budget_usd)}
$ResumeSessionId = {_ps(resume_session_id)}
# Force UTF-8 so the child process stdout/stdin is decoded correctly (avoids OEM-codepage mojibake).
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$Host.UI.RawUI.WindowTitle = "Claude visible advisor - $(Split-Path $RunDir -Leaf)"

# UTF-8 tee helper (Tee-Object writes UTF-16LE in PowerShell 5.1, corrupting display.log).
function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Add-Content -LiteralPath $DisplayLog -Encoding UTF8 -Value $text
  }}
}}

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
  if ($obj.session_id) {{
    $obj.session_id | Set-Content -LiteralPath $SessionPath -Encoding UTF8
  }}
  if ($obj.type -eq 'assistant' -and $obj.message) {{
    foreach ($c in $obj.message.content) {{
      if ($c.type -eq 'text') {{
        $script:ClaudeHadResult = $true
        $c.text | Write-Raw
      }}
    }}
    return
  }}
  if ($obj.type -eq 'result') {{
    Log-Line "Claude result: subtype=$($obj.subtype) cost=$($obj.total_cost_usd) duration_ms=$($obj.duration_ms)" 'Green'
    if ($obj.subtype -eq 'error_max_budget_usd') {{ $script:ClaudeBudgetCapped = $true }}
    if ($obj.result) {{
      $script:ClaudeHadResult = $true
      $obj.result | Write-Raw
    }}
    return
  }}
  if ($obj.type -eq 'system') {{
    if ($obj.session_id) {{ Log-Line "Claude session: $($obj.session_id)" 'Cyan' }}
    Log-Line "Claude system: $($obj.subtype)" 'DarkCyan'
    return
  }}
  if ($obj.type -eq 'tool_use' -or $obj.type -eq 'tool_result') {{ Log-Line "Claude tool event: $($obj.type)" 'Yellow'; return }}
}}

{_PS_CLEANUP_FN}
Clear-Host
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Model: $Model | Effort: $Effort | Max budget USD: $MaxBudgetUsd | Permission mode: plan | Session persistence enabled for resume" 'Cyan'
if ($ResumeSessionId -and $ResumeSessionId -ne '') {{ Log-Line "Resuming Claude session: $ResumeSessionId" 'Cyan' }}
Log-Line 'Prompt follows:' 'Magenta'
Get-Content -LiteralPath $PromptPath -Raw | Write-Raw
Log-Line 'Starting Claude advisor. Raw stream JSON is saved to events.jsonl.' 'Magenta'

$script:ClaudeHadResult = $false
$script:ClaudeBudgetCapped = $false
$argsList = @('-p','--safe-mode','--prompt-suggestions','false','--verbose','--output-format','stream-json','--permission-mode','plan','--max-budget-usd',$MaxBudgetUsd,'--add-dir',$Cwd)
if ($ResumeSessionId -and $ResumeSessionId -ne '') {{ $argsList += @('--resume',$ResumeSessionId) }}
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
if ($exitCode -eq 0) {{
  Set-Status 'completed'
}} elseif ($script:ClaudeBudgetCapped -and $script:ClaudeHadResult) {{
  Set-Status 'completed_budget_capped'
}} else {{
  Set-Status "failed:$exitCode"
}}
Log-Line "Claude exited with code $exitCode" $(if ($exitCode -eq 0) {{ 'Green' }} else {{ 'Red' }})
Stop-RunDescendants -RootPid $PID
Log-Line 'Agents for this run have been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
Start-Sleep -Seconds 5
exit
"""


@mcp.tool()
def start_visible_codex_worker(
    prompt: str,
    cwd: str,
    title: str = "Codex worker",
    sandbox: str = CODEX_DEFAULT_SANDBOX,
    approval_policy: str = "never",
    model: str = CODEX_MODEL,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = CODEX_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible Codex exec worker in a separate PowerShell window and save logs."""
    effective_model = CODEX_MODEL
    effective_reasoning = CODEX_REASONING_EFFORT
    effective_service_tier = CODEX_SERVICE_TIER
    auto_full_tool_access = _needs_full_tool_access("\n".join([title, prompt, session_context]))
    effective_sandbox = CODEX_FULL_TOOL_SANDBOX
    prompt_with_permissions = "\n\n".join([
        _codex_permission_contract(sandbox, effective_sandbox),
        prompt,
    ])
    if compose_with_haiku:
        effective_prompt = prompt.strip()
    else:
        effective_prompt = _with_session_context_bootstrap(prompt_with_permissions, cwd, "Codex worker", session_context)
    run_dir = _make_run(cwd, "codex-resume" if resume_session_id else "codex", title, effective_prompt, {
        "agent": "codex",
        "cwd": str(Path(cwd).resolve()),
        "sandbox": effective_sandbox,
        "requested_sandbox": sandbox,
        "approval_policy": approval_policy,
        "model": effective_model,
        "reasoning_effort": effective_reasoning,
        "service_tier": effective_service_tier,
        "requested_model": model,
        "requested_reasoning_effort": reasoning_effort,
        "resume_session_id": resume_session_id or None,
        "session_context_supplied": bool(session_context.strip()),
        "requires_tool_access": requires_tool_access,
        "auto_full_tool_access": auto_full_tool_access,
        "sandbox_bypass_enabled": True,
        "tool_access_default": "full-process-access",
        "compose_with_haiku": compose_with_haiku,
        "prompt_composer_model": composer_model if compose_with_haiku else None,
        "prompt_composer_effort": composer_effort if compose_with_haiku else None,
        "prompt_composer_max_budget_usd": composer_max_budget_usd if compose_with_haiku else None,
        "steer_idle_seconds": max(0, min(int(steer_idle_seconds), 300)),
        "captain_help_enabled": True,
    })
    if not compose_with_haiku:
        effective_prompt = "\n\n".join([_captain_help_contract(run_dir), effective_prompt])
        (run_dir / "prompt.md").write_text(effective_prompt, encoding="utf-8")
    if compose_with_haiku:
        composer_prompt = _haiku_codex_prompt_composer_prompt(
            prompt,
            cwd,
            title,
            sandbox,
            session_context,
            resume_session_id,
            requires_tool_access or auto_full_tool_access,
        )
        (run_dir / "composer_prompt.md").write_text(composer_prompt, encoding="utf-8")
        codex_prelude = _with_session_context_bootstrap(
            "\n\n".join([
                _captain_help_contract(run_dir),
                _codex_permission_contract(sandbox, effective_sandbox),
            ]),
            cwd,
            "Codex worker",
            session_context,
        )
        (run_dir / "codex_prelude.md").write_text(codex_prelude, encoding="utf-8")
    script = run_dir / "run.ps1"
    script.write_text(
        _codex_runner(
            run_dir,
            str(Path(cwd).resolve()),
            effective_sandbox,
            approval_policy,
            effective_model,
            effective_reasoning,
            effective_service_tier,
            resume_session_id,
            compose_with_haiku,
            composer_model,
            composer_effort,
            composer_max_budget_usd,
            steer_idle_seconds,
        ),
        encoding="utf-8",
    )
    pid = _launch(script)
    (run_dir / "launcher_pid.txt").write_text(str(pid), encoding="utf-8")
    return {
        "run_id": run_dir.name,
        "pid": pid,
        "run_dir": str(run_dir),
        "prompt": str(run_dir / "prompt.md"),
        "display_log": str(run_dir / "display.log"),
        "raw_events": str(run_dir / "events.jsonl"),
        "status": str(run_dir / "status.json"),
        "steer_queue": str(run_dir / "steer_queue"),
        "captain_help": str(run_dir / CAPTAIN_HELP_DIR),
        "note": f"A visible PowerShell window was launched. Codex is forced to gpt-5.5/xhigh/service_tier=fast. Effective sandbox is {effective_sandbox}. Haiku prompt composer enabled={compose_with_haiku}. Captain-help mailbox enabled. Hidden model reasoning is not exposed; prompts, events, messages, commands, usage, and diffs are logged.",
    }


@mcp.tool()
def start_visible_haiku_composed_codex_worker(
    prompt_brief: str,
    cwd: str,
    title: str = "Codex worker",
    sandbox: str = "read-only",
    approval_policy: str = "never",
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = CODEX_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible Codex worker from a compact Claude brief expanded by Claude Haiku."""
    return start_visible_codex_worker(
        prompt=prompt_brief,
        cwd=cwd,
        title=title,
        sandbox=sandbox,
        approval_policy=approval_policy,
        model=CODEX_MODEL,
        reasoning_effort=CODEX_REASONING_EFFORT,
        session_context=session_context,
        resume_session_id=resume_session_id,
        requires_tool_access=requires_tool_access,
        compose_with_haiku=True,
        composer_model=CLAUDE_PROMPT_COMPOSER_MODEL,
        composer_effort=CLAUDE_PROMPT_COMPOSER_EFFORT,
        composer_max_budget_usd=composer_max_budget_usd,
        steer_idle_seconds=steer_idle_seconds,
    )


@mcp.tool()
def start_visible_first_mate_codex_pool(
    goal: str,
    cwd: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    max_workers: int = 6,
    model: str = CODEX_MODEL,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    steer_idle_seconds: int = CODEX_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible Codex root session instructed to act as first mate and manage parallel Codex subagents."""
    scout_areas = scout_areas or []
    implementation_items = implementation_items or []
    auto_full_tool_access = _needs_full_tool_access("\n".join([goal, session_context, *scout_areas, *implementation_items]))
    effective_root_sandbox = CODEX_FULL_TOOL_SANDBOX
    if sandbox == "read-only" and not (requires_tool_access or auto_full_tool_access):
        tool_access_instructions = "- Full process/tool access is enabled so Python skills, read-past-sessions, rg, and other developer tools work. Claude's permission intent is no-edit scouting; do not modify files or external state."
    elif requires_tool_access or auto_full_tool_access or sandbox == "danger-full-access":
        tool_access_instructions = "- Full tool, SSH, network, and live-device access is required for this run. Use claude-debugger or inherited full-access workers for command-heavy debugging; do not dispatch no-tool/no-edit scouts for tasks that need those tools."
    else:
        tool_access_instructions = "- Full process/tool access is enabled. Stay within Claude's scoped write intent and ask before expanding scope."
    prompt = f"""
Use the `firstmate` skill if it is available, then follow this embedded Firstmate contract:

{FIRSTMATE_CONTRACT}

Goal:
{goal}

Run-specific limits:
- Keep fan-out bounded to at most {max_workers} workers.
- Hidden model reasoning is not visible to the user; expose useful progress through concise summaries and logs.
{tool_access_instructions}

Scout areas:
{chr(10).join(f"- {x}" for x in scout_areas) if scout_areas else "- Map the codebase at a high level, identify relevant modules, tests, and risk areas."}

Implementation items:
{chr(10).join(f"- {x}" for x in implementation_items) if implementation_items else "- None unless Claude provided explicit scope."}

Actual process sandbox for this root run: {effective_root_sandbox}
Claude-requested permission intent: {sandbox}
If the intent is read-only/no-edit, do not attempt implementation. Scout and summarize.
"""
    return start_visible_codex_worker(
        prompt=textwrap.dedent(prompt).strip(),
        cwd=cwd,
        title="Codex first mate pool",
        sandbox=sandbox,
        approval_policy="never",
        model=model,
        reasoning_effort=reasoning_effort,
        session_context=session_context,
        resume_session_id=resume_session_id,
        requires_tool_access=requires_tool_access or auto_full_tool_access,
        steer_idle_seconds=steer_idle_seconds,
    )


@mcp.tool()
def steer_visible_codex_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = False,
    requires_tool_access: bool = False,
) -> dict[str, Any]:
    """Send a Claude steering instruction to a visible Codex run, resuming the same Codex thread if needed."""
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    status = _read_json(path / "status.json", {"status": "unknown"})
    status_name = _status_name(status)
    if metadata.get("agent") not in (None, "codex"):
        return {"ok": False, "error": f"run_dir is not a Codex visible run: {path}", "metadata": metadata}

    requested_sandbox = sandbox.strip()
    permission_contract = (
        _codex_permission_contract(requested_sandbox, CODEX_FULL_TOOL_SANDBOX)
        if requested_sandbox
        else ""
    )
    steer_path = _write_steer_file(path, instruction, session_context, title, permission_contract)
    thread_path = path / "thread_id.txt"
    thread_id = thread_path.read_text(encoding="utf-8-sig").strip() if thread_path.exists() else ""
    active = status_name == "created" or status_name == "waiting_for_steer" or status_name.startswith("running")
    result: dict[str, Any] = {
        "ok": True,
        "mode": "queued",
        "run_dir": str(path),
        "status": status,
        "thread_id": thread_id or None,
        "steer_file": str(steer_path),
        "note": "Steering was queued. The visible Codex window will consume it after the current turn, or during its steering idle window.",
    }

    if active and not interrupt_current_turn:
        return result

    if interrupt_current_turn and active:
        if not thread_id:
            result["mode"] = "queued_no_interrupt_no_thread"
            result["note"] = "Steering was queued, but the current turn was not interrupted because no Codex thread id is available yet."
            return result
        pid_path = path / "launcher_pid.txt"
        if not pid_path.exists():
            result["mode"] = "queued_no_interrupt_no_pid"
            result["note"] = "Steering was queued, but the current turn was not interrupted because the launcher pid is unavailable."
            return result
        try:
            pid = pid_path.read_text(encoding="utf-8-sig").strip()
            killed = subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True, timeout=10)
            if killed.returncode != 0:
                result["mode"] = "queued_interrupt_failed"
                result["interrupt_warning"] = (killed.stderr or killed.stdout or "").strip()
                result["note"] = "Steering was queued, but the active visible run could not be interrupted cleanly."
                return result
            result["interrupted_pid"] = pid
        except Exception as exc:
            result["mode"] = "queued_interrupt_failed"
            result["interrupt_warning"] = str(exc)
            result["note"] = "Steering was queued, but the active visible run could not be interrupted cleanly."
            return result

    if not launch_if_closed and not interrupt_current_turn:
        result["mode"] = "queued_no_active_runner"
        result["note"] = "Steering was queued, but the visible run is not active and launch_if_closed is false."
        return result

    if not thread_id:
        result["mode"] = "queued_no_resume_thread"
        result["note"] = "Steering was queued, but no Codex thread id is available to launch a resume run."
        return result

    cwd = _infer_cwd_from_run_dir(path, metadata)
    steer_prompt = steer_path.read_text(encoding="utf-8")
    resume_context = "\n\n".join(
        part for part in [
            f"Previous visible run: {path}",
            f"Previous status: {status_name}",
            f"Previous Codex thread id: {thread_id}",
            session_context.strip(),
        ] if part
    )
    followup = start_visible_codex_worker(
        prompt=steer_prompt,
        cwd=cwd,
        title=title,
        sandbox=requested_sandbox or metadata.get("requested_sandbox") or "read-only",
        approval_policy=metadata.get("approval_policy") or "never",
        session_context=resume_context,
        resume_session_id=thread_id,
        requires_tool_access=bool(requires_tool_access or metadata.get("requires_tool_access") or metadata.get("auto_full_tool_access")),
        compose_with_haiku=False,
        steer_idle_seconds=int(metadata.get("steer_idle_seconds") or CODEX_STEER_IDLE_SECONDS),
    )
    try:
        done_dir = path / "steer_done"
        done_dir.mkdir(parents=True, exist_ok=True)
        steer_path.replace(done_dir / steer_path.name)
    except Exception:
        pass
    result["mode"] = "launched_resume"
    result["followup_run"] = followup
    result["note"] = "The previous visible run was not available for in-window steering, so a visible Codex resume run was launched on the same thread."
    return result


def _help_record_path(run_dir: Path, request_id: str) -> Path | None:
    dirs = _ensure_captain_help_dirs(run_dir)
    for key in ("requests", "answered", "escalated"):
        candidate = dirs[key] / f"{request_id}.json"
        if candidate.exists():
            return candidate
    return None


def _help_markdown(record: dict[str, Any]) -> str:
    return textwrap.dedent(f"""
    # Captain Help Request

    Request ID: {record["request_id"]}
    Status: {record["status"]}
    Urgency: {record["urgency"]}
    Blocks progress: {record["blocks_progress"]}
    Created: {record["created_at"]}

    ## Question

    {record["question"]}

    ## Context

    {record["context"] or "None supplied."}

    ## Recommended Next Step

    {record["recommended_next"] or "None supplied."}
    """).strip()


def _summarize_help_requests(run_dir: Path, include_answered: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    dirs = _ensure_captain_help_dirs(run_dir)
    paths = list(dirs["requests"].glob("*.json")) + list(dirs["escalated"].glob("*.json"))
    if include_answered:
        paths += list(dirs["answered"].glob("*.json"))
    records: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda p: p.name, reverse=True):
        record = _read_json(path, {})
        if not record:
            continue
        records.append({
            "request_id": record.get("request_id"),
            "status": record.get("status"),
            "urgency": record.get("urgency"),
            "blocks_progress": record.get("blocks_progress"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "question": record.get("question"),
            "recommended_next": record.get("recommended_next"),
            "run_dir": str(run_dir),
        })
        if len(records) >= max(1, min(limit, 100)):
            break
    return records


@mcp.tool()
def request_captain_help(
    run_dir: str,
    question: str,
    context: str = "",
    urgency: str = "normal",
    recommended_next: str = "",
    blocks_progress: bool = True,
) -> dict[str, Any]:
    """Create a help request for the same Claude captain that spawned a visible Codex run."""
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    if metadata.get("agent") not in (None, "codex"):
        return {"ok": False, "error": f"run_dir is not a Codex visible run: {path}", "metadata": metadata}
    if not question.strip():
        return {"ok": False, "error": "question is required"}
    dirs = _ensure_captain_help_dirs(path)
    request_id = f"{_now()}-help-{uuid.uuid4().hex[:8]}"
    now = _dt.datetime.now().isoformat()
    record = {
        "request_id": request_id,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "run_dir": str(path),
        "thread_id": (path / "thread_id.txt").read_text(encoding="utf-8-sig").strip() if (path / "thread_id.txt").exists() else None,
        "urgency": urgency.strip() or "normal",
        "blocks_progress": bool(blocks_progress),
        "question": question.strip(),
        "context": context.strip(),
        "recommended_next": recommended_next.strip(),
    }
    json_path = dirs["requests"] / f"{request_id}.json"
    md_path = dirs["requests"] / f"{request_id}.md"
    json_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    md_path.write_text(_help_markdown(record), encoding="utf-8")
    try:
        with (path / "display.log").open("a", encoding="utf-8") as log:
            log.write(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] Captain help requested: {request_id} ({record['urgency']})\n")
    except Exception:
        pass
    return {
        "ok": True,
        "request_id": request_id,
        "run_dir": str(path),
        "request": str(json_path),
        "request_markdown": str(md_path),
        "note": "Help request recorded for the same Claude captain. Stop this Codex turn and wait for captain steering.",
    }


@mcp.tool()
def list_captain_help_requests(
    cwd: str | None = None,
    run_dir: str = "",
    include_answered: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List pending or recent captain-help requests for visible Codex runs."""
    if run_dir.strip():
        path = Path(run_dir).expanduser().resolve()
        if not path.exists():
            return []
        return _summarize_help_requests(path, include_answered=include_answered, limit=limit)
    root = _run_root(cwd)
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for run in sorted(root.glob("*"), key=lambda p: p.name, reverse=True):
        if not run.is_dir():
            continue
        rows.extend(_summarize_help_requests(run, include_answered=include_answered, limit=limit))
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows[: max(1, min(limit, 100))]


@mcp.tool()
def respond_to_captain_help_request(
    run_dir: str,
    request_id: str,
    response: str = "",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    escalate_to_user: bool = False,
    user_question: str = "",
) -> dict[str, Any]:
    """Answer a visible Codex worker's captain-help request, or mark it as escalated to the user."""
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    record_path = _help_record_path(path, request_id)
    if record_path is None:
        return {"ok": False, "error": f"help request not found: {request_id}"}
    record = _read_json(record_path, {})
    if not record:
        return {"ok": False, "error": f"help request is unreadable: {request_id}"}
    dirs = _ensure_captain_help_dirs(path)
    now = _dt.datetime.now().isoformat()
    if escalate_to_user and not response.strip():
        record.update({
            "status": "escalated_to_user",
            "updated_at": now,
            "user_question": user_question.strip() or record.get("question") or "",
        })
        target = dirs["escalated"] / f"{request_id}.json"
        target.write_text(json.dumps(record, indent=2), encoding="utf-8")
        (dirs["escalated"] / f"{request_id}.md").write_text(_help_markdown(record), encoding="utf-8")
        try:
            record_path.unlink(missing_ok=True)
            record_path.with_suffix(".md").unlink(missing_ok=True)
        except Exception:
            pass
        return {
            "ok": True,
            "request_id": request_id,
            "status": "escalated_to_user",
            "user_question": record["user_question"],
            "note": "Ask the user this question, then call respond_to_captain_help_request again with the user's decision.",
        }
    if not response.strip():
        return {"ok": False, "error": "response is required unless escalate_to_user=true"}
    record.update({
        "status": "answered",
        "updated_at": now,
        "response": response.strip(),
        "session_context": session_context.strip(),
    })
    target = dirs["answered"] / f"{request_id}.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    (dirs["answered"] / f"{request_id}.md").write_text(_help_markdown(record) + f"\n\n## Captain Response\n\n{response.strip()}\n", encoding="utf-8")
    try:
        record_path.unlink(missing_ok=True)
        record_path.with_suffix(".md").unlink(missing_ok=True)
    except Exception:
        pass
    instruction = textwrap.dedent(f"""
    Captain response to help request `{request_id}`.

    Original worker question:
    {record.get("question") or ""}

    Captain response:
    {response.strip()}

    Continue the same task using this decision. If this response says the user must decide, stop and report that you are waiting for the owner through Claude. Do not ask the owner directly.
    """).strip()
    steer = steer_visible_codex_run(
        str(path),
        instruction,
        title=f"Captain help response {request_id}",
        session_context=session_context,
        sandbox=sandbox,
        launch_if_closed=launch_if_closed,
    )
    return {
        "ok": True,
        "request_id": request_id,
        "status": "answered",
        "steer": steer,
        "note": "Captain response recorded and queued as steering for the same Codex run/thread.",
    }


@mcp.tool()
def start_visible_claude_advisor(
    prompt: str,
    cwd: str,
    title: str = "Claude advisor",
    model: str = "",
    effort: str = CLAUDE_EFFORT,
    max_budget_usd: str = CLAUDE_MAX_BUDGET_USD,
    session_context: str = "",
    resume_session_id: str = "",
) -> dict[str, Any]:
    """Launch a visible, budget-capped, one-shot Claude Code advisor run in a separate PowerShell window."""
    effective_model = _default_claude_advisor_model()
    effective_effort = CLAUDE_EFFORT
    effective_budget = max_budget_usd or CLAUDE_MAX_BUDGET_USD
    bounded_prompt = f"""
You are Claude Code acting as an expensive, one-shot executive advisor to Codex.

Budget rules:
- Be concise. Target under 500 words unless critical details require more.
- Do not start an extended back-and-forth.
- Do not perform broad codebase reading. Rely on the distilled context Codex provided.
- Ask at most 3 clarifying questions only if no safe recommendation is possible.
- Prefer a direct decision, risks, and specific instructions for Codex.
- Do not write implementation code. Provide architecture, acceptance criteria, review findings, and next worker instructions.

Advisor request:
{prompt}
""".strip()
    effective_prompt = _with_session_context_bootstrap(bounded_prompt, cwd, "Claude advisor", session_context)
    run_dir = _make_run(cwd, "claude-resume" if resume_session_id else "claude", title, effective_prompt, {
        "agent": "claude",
        "model": effective_model,
        "effort": effective_effort,
        "max_budget_usd": effective_budget,
        "requested_model": model,
        "requested_effort": effort,
        "model_policy": _claude_advisor_model_policy(),
        "resume_session_id": resume_session_id or None,
        "session_context_supplied": bool(session_context.strip()),
        "permission_mode": "plan",
    })
    script = run_dir / "run.ps1"
    script.write_text(
        _claude_runner(
            run_dir,
            str(Path(cwd).resolve()),
            effective_model,
            effective_effort,
            effective_budget,
            resume_session_id,
        ),
        encoding="utf-8",
    )
    pid = _launch(script)
    return {
        "run_id": run_dir.name,
        "pid": pid,
        "run_dir": str(run_dir),
        "prompt": str(run_dir / "prompt.md"),
        "display_log": str(run_dir / "display.log"),
        "raw_events": str(run_dir / "events.jsonl"),
        "status": str(run_dir / "status.json"),
        "note": f"A visible PowerShell window was launched for Claude advisor output. Claude is forced to {effective_model}/high by the central advisor model policy. Hidden model reasoning is not exposed.",
    }


@mcp.tool()
def get_visible_run_status(run_dir: str, tail_lines: int = 80) -> dict[str, Any]:
    """Read status and recent visible log lines from a visible agent run directory."""
    path = Path(run_dir)
    status_path = path / "status.json"
    display_path = path / "display.log"
    thread_path = path / "thread_id.txt"
    session_path = path / "session_id.txt"
    metadata_path = path / "metadata.json"
    steer_queue = path / "steer_queue"
    steer_done = path / "steer_done"
    help_dirs = _ensure_captain_help_dirs(path)
    status = json.loads(status_path.read_text(encoding="utf-8-sig")) if status_path.exists() else {"status": "unknown"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
    lines: list[str] = []
    if display_path.exists():
        all_lines = display_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        lines = all_lines[-max(1, min(tail_lines, 500)):]
    return {
        "run_dir": str(path),
        "status": status,
        "metadata": metadata,
        "thread_id": thread_path.read_text(encoding="utf-8-sig").strip() if thread_path.exists() else None,
        "session_id": session_path.read_text(encoding="utf-8-sig").strip() if session_path.exists() else None,
        "pending_steers": len(list(steer_queue.glob("*.md"))) if steer_queue.exists() else 0,
        "completed_steers": len(list(steer_done.glob("*.md"))) if steer_done.exists() else 0,
        "pending_help_requests": len(list(help_dirs["requests"].glob("*.json"))),
        "answered_help_requests": len(list(help_dirs["answered"].glob("*.json"))),
        "escalated_help_requests": len(list(help_dirs["escalated"].glob("*.json"))),
        "help_requests": _summarize_help_requests(path, include_answered=False, limit=10),
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
        thread_path = run / "thread_id.txt"
        session_path = run / "session_id.txt"
        steer_queue = run / "steer_queue"
        steer_done = run / "steer_done"
        result.append({
            "run_id": run.name,
            "run_dir": str(run),
            "status": json.loads(status_path.read_text(encoding="utf-8-sig")) if status_path.exists() else {"status": "unknown"},
            "metadata": json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {},
            "thread_id": thread_path.read_text(encoding="utf-8-sig").strip() if thread_path.exists() else None,
            "session_id": session_path.read_text(encoding="utf-8-sig").strip() if session_path.exists() else None,
            "pending_steers": len(list(steer_queue.glob("*.md"))) if steer_queue.exists() else 0,
            "completed_steers": len(list(steer_done.glob("*.md"))) if steer_done.exists() else 0,
        })
    return result


if __name__ == "__main__":
    mcp.run()
