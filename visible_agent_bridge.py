from __future__ import annotations

import atexit
import datetime as _dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("agent-visibility")

HOME = Path.home()


def _resolve_cli(env_var: str, names: tuple[str, ...], *fallbacks: str) -> Path:
    """Resolve a worker CLI cross-platform: env override > PATH > known installs.

    Keeps the original hardcoded Windows paths as last-resort fallbacks so the
    bridge still works verbatim on the original Windows machine, while macOS /
    Linux (and any relocated Windows install) resolve via PATH.
    """
    override = os.environ.get(env_var, "").strip()
    if override:
        return Path(override).expanduser()
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    for fallback in fallbacks:
        candidate = Path(os.path.expandvars(fallback)).expanduser()
        if candidate.exists():
            return candidate
    return Path(names[0])


CODEX = _resolve_cli("BRIDGE_CODEX_CLI", ("codex", "codex.cmd"), r"C:\Users\jonny\AppData\Roaming\npm\codex.cmd")
CLAUDE = _resolve_cli("BRIDGE_CLAUDE_CLI", ("claude", "claude.exe"), "~/.local/bin/claude", r"C:\Users\jonny\.local\bin\claude.exe")
PYTHON = Path(os.environ.get("BRIDGE_PYTHON", "").strip() or sys.executable)
READ_PAST_SESSIONS_SKILL = _resolve_cli(
    "BRIDGE_READ_PAST_SESSIONS",
    ("read-past-sessions-skill-dir-not-a-cli",),
    "~/.claude/skills/read-past-sessions",
    r"C:\Users\jonny\.agents\skills\read-past-sessions",
)
PLAYWRIGHT_NODE_PATH = r"C:\Users\jonny\node_modules;C:\Users\jonny\.codex\playwright-runtime\node_modules"
PLAYWRIGHT_BROWSERS_PATH = Path(r"C:\Users\jonny\AppData\Local\ms-playwright")

CODEX_MODEL = "gpt-5.6-sol"
# gpt-5.6-sol accepts these model_reasoning_effort values. Claude selects the
# effort per task by judged difficulty; for coding work it scales along
# high -> xhigh -> max -> ultra. `ultra` is the highest tier and makes the
# model natively decompose work into cooperative subagents (high token cost,
# preview-gated). The default below is a floor, not a fixed value; any
# caller-supplied effort outside this set falls back to CODEX_REASONING_EFFORT.
CODEX_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")
CODEX_REASONING_EFFORT = "xhigh"
CODEX_SERVICE_TIER = "fast"
CODEX_FULL_TOOL_SANDBOX = "danger-full-access"
CODEX_DEFAULT_SANDBOX = CODEX_FULL_TOOL_SANDBOX
CAPTAIN_HELP_DIR = "captain_help"
CAPTAIN_HELP_REQUESTS_DIR = "requests"
CAPTAIN_HELP_ANSWERED_DIR = "answered"
CAPTAIN_HELP_ESCALATED_DIR = "escalated"
CAPTAIN_REPORTS_DIR = "captain_reports"
CAPTAIN_REPORT_FINAL_JSON = "final.json"
CAPTAIN_REPORT_FINAL_MD = "final.md"
CLAUDE_ADVISOR_MODEL_ENV = "CLAUDE_MANAGES_CODEX_ADVISOR_MODEL"
CLAUDE_ADVISOR_MODEL_UNTIL_ENV = "CLAUDE_MANAGES_CODEX_FABLE_UNTIL"
CLAUDE_ADVISOR_PRIMARY_MODEL = "fable"
CLAUDE_ADVISOR_FALLBACK_MODEL = "opus"
CLAUDE_ADVISOR_PRIMARY_UNTIL = _dt.date(2026, 7, 7)
CLAUDE_EFFORT = "high"
CLAUDE_MAX_BUDGET_USD = "0.50"
CLAUDE_PROMPT_COMPOSER_MODEL = "haiku"
CLAUDE_PROMPT_COMPOSER_EFFORT = "low"
CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD = "1.00"
CODEX_STEER_IDLE_SECONDS = 20
INTERACTIVE_TUI_APPROVAL_POLICY = "on-request"
INTERACTIVE_TUI_MODE = "interactive_tui"
INTERACTIVE_TUI_AUTO_CLOSE_DELAY_SECONDS = 5
# codex.cmd is an npm batch shim, so the whole rendered command line must fit
# cmd.exe's 8191-char limit. Long captain briefs are passed via prompt.md with
# a short bootstrap arg instead of inline. 6000 leaves headroom for the flags.
TUI_INLINE_PROMPT_MAX_CHARS = 6000

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

Runtime requirement: use Codex gpt-5.6-sol and service_tier=fast for root and subagent work in this bridge. Reasoning effort is Claude-selected per task across high, xhigh, max, and ultra; use the effort the captain sets for this run and do not silently downgrade it. At ultra effort, gpt-5.6-sol natively decomposes work into cooperative subagents; stay within the captain's scope and fan-out cap.

Session requirement: do not act as a blank chat. Use caller-provided context first. If the task depends on earlier conversation history, use read-past-sessions before scouting or implementing, then pass compact context into every subagent brief. For broad project/codebase context, use read-past-sessions' Graphify memory flow before brute-force file reading: memory-query first; if the graph is missing or stale, build the curated corpus with memory-corpus plus memory-codex --build-graph, or memory-graph as deterministic fallback.

Tool-access requirement: this bridge gives Codex workers full process/tool access so Python skills, read-past-sessions, SSH, and external CLIs work. Treat Claude's requested sandbox as permission intent. If intent is read-only/no-edit, do not modify files or external state even though tools are available.

Prompt-cost requirement: expect Claude's active manager model to send compact captain briefs. Long Codex worker prompts should be composed by the Haiku/low prompt composer before they reach you.

Captain-help requirement: if you are blocked, confused, or about to make an architectural/safety decision without enough confidence, request help from the same Claude captain through the run's captain-help mailbox. Do not start a separate Claude advisor unless Claude explicitly asked for that. After requesting help, stop the current turn and wait for captain steering. The captain may escalate the question to the owner.

Captain-report requirement: if the caller prompt includes a submit_captain_report tool, a Captain Report Handoff, or a captain_reports path, submit the final outcome through that tool or write the requested report files before stopping. A normal TUI final message is user-visible progress only; it is not a reliable handoff to Claude.

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
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            else:
                try:
                    os.killpg(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


atexit.register(_reap_launched)


def _pid_is_running(pid: str | int) -> bool:
    try:
        pid_int = int(str(pid).strip())
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid_int, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid_int}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    output = (proc.stdout or "").strip()
    return proc.returncode == 0 and output.startswith('"')


def _wait_for_pid_exit(pid: str | int, timeout_sec: float = 5.0) -> bool:
    deadline = time.time() + max(0.0, timeout_sec)
    while time.time() < deadline:
        if not _pid_is_running(pid):
            return True
        time.sleep(0.25)
    return not _pid_is_running(pid)


def _send_ctrl_c_to_console(pid: str | int) -> tuple[bool, str]:
    if os.name != "nt":
        try:
            pid_int = int(str(pid).strip())
        except (TypeError, ValueError):
            return False, f"Invalid pid for SIGINT: {pid!r}"
        try:
            try:
                os.killpg(pid_int, signal.SIGINT)
            except (ProcessLookupError, PermissionError, OSError):
                os.kill(pid_int, signal.SIGINT)
            return True, ""
        except ProcessLookupError:
            return False, f"No such process: {pid_int}"
        except Exception as exc:
            return False, str(exc)
    try:
        pid_int = int(str(pid).strip())
    except (TypeError, ValueError):
        return False, f"Invalid pid for Ctrl+C: {pid!r}"
    script = textwrap.dedent(f"""
    $ErrorActionPreference = 'Continue'
    $TargetPid = {pid_int}
    $source = @"
using System;
using System.Runtime.InteropServices;
public static class BridgeConsoleSignal {{
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint dwProcessId);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handlerRoutine, bool add);
}}
"@
    try {{ Add-Type -TypeDefinition $source -ErrorAction SilentlyContinue | Out-Null }} catch {{}}
    try {{
      [void][BridgeConsoleSignal]::FreeConsole()
      if ([BridgeConsoleSignal]::AttachConsole([uint32]$TargetPid)) {{
        [void][BridgeConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
        [void][BridgeConsoleSignal]::GenerateConsoleCtrlEvent(0, 0)
        Start-Sleep -Milliseconds 500
        [void][BridgeConsoleSignal]::FreeConsole()
        [void][BridgeConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)
        exit 0
      }}
    }} catch {{
      Write-Error $_.Exception.Message
      try {{ [void][BridgeConsoleSignal]::FreeConsole() }} catch {{}}
    }}
    exit 1
    """).strip()
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return False, str(exc)
    output = "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)
    return proc.returncode == 0, output


def _find_codex_thread_file(thread_id: str) -> Path | None:
    value = (thread_id or "").strip()
    if not value:
        return None
    sessions_root = HOME / ".codex" / "sessions"
    if not sessions_root.exists():
        return None
    try:
        matches = [path for path in sessions_root.rglob(f"*{value}.jsonl") if path.is_file()]
    except Exception:
        return None
    if not matches:
        return None
    try:
        return max(matches, key=lambda path: path.stat().st_mtime)
    except Exception:
        return matches[0]


def _wait_for_codex_thread_ready(thread_id: str, timeout_sec: float = 12.0) -> bool:
    deadline = time.time() + max(0.0, timeout_sec)
    while time.time() < deadline:
        path = _find_codex_thread_file(thread_id)
        try:
            if path and path.stat().st_size > 0:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    path = _find_codex_thread_file(thread_id)
    try:
        return bool(path and path.stat().st_size > 0)
    except Exception:
        return False


def _interrupt_visible_run(pid: str | int, graceful_timeout_sec: float = 12.0) -> tuple[bool, str]:
    ctrlc_ok, ctrlc_warning = _send_ctrl_c_to_console(pid)
    if ctrlc_ok and _wait_for_pid_exit(pid, timeout_sec=graceful_timeout_sec):
        return True, ctrlc_warning

    warnings = [ctrlc_warning] if ctrlc_warning else []
    try:
        if os.name == "nt":
            killed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            kill_warning = (killed.stderr or killed.stdout or "").strip()
            if killed.returncode != 0 and kill_warning:
                warnings.append(kill_warning)
        else:
            pid_int = int(str(pid).strip())
            try:
                os.killpg(pid_int, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                os.kill(pid_int, signal.SIGKILL)
    except Exception as exc:
        warnings.append(str(exc))

    if not _wait_for_pid_exit(pid, timeout_sec=5.0):
        return False, "\n".join(warnings).strip()
    return True, "\n".join(warnings).strip()


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
    reasoning_effort: str = CODEX_REASONING_EFFORT,
) -> str:
    context = session_context.strip() or "None supplied."
    reasoning_effort = _normalize_reasoning_effort(reasoning_effort)
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
    - Codex runtime: gpt-5.6-sol, Claude-selected reasoning ({reasoning_effort}; one of high/xhigh/max/ultra), service_tier=fast.

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
    3. For broad project or codebase context, use the read-past-sessions Graphify memory flow before brute-force source reading:
       `python "{sessions_script}" memory-query "<question>" --project "{project_hint}" --budget 12000`
       If no graph exists and durable project context matters, refresh the curated corpus and graph:
       `python "{sessions_script}" memory-corpus "{project_hint}" --run-codex`
       `python "{sessions_script}" memory-codex "{project_hint}" --build-graph`
       If Codex CLI is unavailable for the semantic pass, use the deterministic fallback:
       `python "{sessions_script}" memory-graph "{project_hint}"`
    4. If the skill is needed but not available, run the bundled engine directly:
       `python "{sessions_script}" list "{project_hint}" --limit 5`
       `python "{sessions_script}" show <session-id> --mode briefing --include-subagents --max-chars 120000`
    5. Prefer the newest relevant session for this cwd/task. If a required decision is missing from the briefing, rerun `show` with `--mode full --include-subagents --max-chars 200000`.
    6. Treat the caller-provided context below as authoritative. Use recovered session context to avoid rederiving prior decisions or repeating already-fixed mistakes.
    7. Do not paste full transcripts back unless asked. Return compact evidence, decisions, files, verification, blockers, and questions.

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
    _ensure_captain_report_dir(run_dir)
    return run_dir


def _ensure_captain_help_dirs(run_dir: Path) -> dict[str, Path]:
    root = run_dir / CAPTAIN_HELP_DIR
    requests = root / CAPTAIN_HELP_REQUESTS_DIR
    answered = root / CAPTAIN_HELP_ANSWERED_DIR
    escalated = root / CAPTAIN_HELP_ESCALATED_DIR
    for path in (requests, answered, escalated):
        path.mkdir(parents=True, exist_ok=True)
    return {"root": root, "requests": requests, "answered": answered, "escalated": escalated}


def _ensure_captain_report_dir(run_dir: Path) -> Path:
    root = run_dir / CAPTAIN_REPORTS_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _captain_report_contract(run_dir: Path, auto_close_after_report: bool, close_delay_seconds: int) -> str:
    close_text = (
        f"The bridge will close this TUI about {close_delay_seconds} second(s) after the report file is written."
        if auto_close_after_report
        else "The bridge will leave this TUI open after the report unless the user closes it."
    )
    return textwrap.dedent(f"""
    # Captain Report Handoff

    This is a real interactive Codex TUI. Do not rely on a normal TUI final answer to reach Claude; the captain may not see terminal-only text.

    Run directory: {run_dir}

    At the end of the task, before stopping, call the `submit_captain_report` MCP tool if it is available:

    - `run_dir`: exactly `{run_dir}`
    - `outcome`: one of `completed`, `partial`, `blocked`, or `failed`
    - `summary`: compact captain-facing result
    - `changed_files`: paths changed, or an empty list
    - `verification`: commands/checks run and their results
    - `risks`: remaining risks, or an empty list
    - `questions`: decisions needed from Claude, or an empty list
    - `close_tui`: true unless Claude or the owner explicitly asked you to keep the TUI open

    If `submit_captain_report` is unavailable, write the same report yourself to:

    - `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON}`
    - `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_MD}`

    After the report is submitted, stop working. {close_text}

    If you are blocked before finishing, use `request_captain_help` with the same run directory. The final report is still required when the run reaches a terminal outcome.
    """).strip()


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
    5. Do not ask the human owner directly. The same Claude captain may answer the mailbox or escalate to the owner if needed. Non-interactive workers can receive that answer through queued steering; interactive TUI workers may need direct terminal steering or a resumed TUI session.

    Use `start_visible_claude_advisor` only when Claude explicitly asked you to consult a separate one-shot advisor. The default stuck-worker path is this same-captain mailbox.
    """).strip()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _read_session_id_file(session_path: Path) -> str | None:
    try:
        if session_path.exists():
            value = session_path.read_text(encoding="utf-8-sig").strip()
            return value or None
    except Exception:
        return None
    return None


def _extract_session_id_from_jsonl(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                payload = event.get("payload") if isinstance(event, dict) else None
                if isinstance(payload, dict) and isinstance(payload.get("id"), str):
                    return payload["id"]
                session_meta = event.get("session_meta") if isinstance(event, dict) else None
                if isinstance(session_meta, dict):
                    nested_payload = session_meta.get("payload")
                    if isinstance(nested_payload, dict) and isinstance(nested_payload.get("id"), str):
                        return nested_payload["id"]
    except Exception:
        return ""
    return ""


def _find_recent_codex_session_id(started_at: float, cwd: str, limit: int = 50) -> str:
    sessions_root = HOME / ".codex" / "sessions"
    if not sessions_root.exists():
        return ""
    try:
        files = sorted(
            [path for path in sessions_root.rglob("*.jsonl") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return ""
    cwd_text = str(Path(cwd).resolve()).lower()
    fallback = ""
    for path in files[: max(1, min(limit, 200))]:
        try:
            if path.stat().st_mtime + 2 < started_at:
                continue
        except Exception:
            continue
        session_id = _extract_session_id_from_jsonl(path)
        if not session_id:
            continue
        if not fallback:
            fallback = session_id
        try:
            sample = path.read_text(encoding="utf-8-sig", errors="replace")[:20000].lower()
        except Exception:
            sample = ""
        if cwd_text and cwd_text in sample:
            return session_id
    return fallback


def _record_interactive_session_id(run_dir: Path, metadata: dict[str, Any]) -> str | None:
    session_path = run_dir / "session_id.txt"
    wrote_session_path = False
    try:
        if metadata.get("mode") != INTERACTIVE_TUI_MODE:
            return None
        if session_path.exists():
            return _read_session_id_file(session_path)
        started_at = float(metadata.get("started_at_epoch") or metadata.get("created_at_epoch") or 0.0)
        cwd = str(metadata.get("cwd") or _infer_cwd_from_run_dir(run_dir, metadata))
        if started_at <= 0:
            try:
                started_at = (run_dir / "metadata.json").stat().st_mtime
            except Exception:
                started_at = time.time()
        session_id = _find_recent_codex_session_id(started_at, cwd)
        if not session_id:
            return None
        session_path.write_text(session_id, encoding="utf-8")
        wrote_session_path = True
        updated_metadata = dict(metadata)
        updated_metadata["session_id"] = session_id
        updated_metadata["session_id_detected_at"] = _dt.datetime.now().isoformat()
        _write_json(run_dir / "metadata.json", updated_metadata)
        metadata.clear()
        metadata.update(updated_metadata)
        return session_id
    except Exception:
        if wrote_session_path:
            try:
                session_path.unlink()
            except Exception:
                pass
        return None


def _visible_run_session_id(run_dir: Path, metadata: dict[str, Any]) -> str | None:
    if isinstance(metadata, dict) and metadata.get("mode") == INTERACTIVE_TUI_MODE:
        return _record_interactive_session_id(run_dir, metadata)
    return _read_session_id_file(run_dir / "session_id.txt")


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


def _watch_command(run_dir: Path) -> str:
    """Bash one-liner for the calling Claude to arm as a background task.

    It exits the moment this run reaches a terminal state (or after a 2h
    cap), which wakes the idle Claude session with a completion
    notification. Without it, nothing ever notifies Claude that a Codex
    run finished.
    """
    d = str(run_dir).replace("\\", "/")
    return (
        f"D='{d}'; end=$((SECONDS+7200)); "
        "until grep -qE '\"status\":[[:space:]]*\"(completed|failed|closed)' \"$D/status.json\" 2>/dev/null "
        "|| [ -f \"$D/captain_reports/final.json\" ] || [ $SECONDS -ge $end ]; do sleep 10; done; "
        "echo \"CODEX-RUN-TERMINAL $(basename \"$D\")\"; "
        "grep -o '\"status\":[^,}]*' \"$D/status.json\" 2>/dev/null | head -1"
    )


CAPTAIN_CHECKUP = Path(__file__).resolve().parent / "captain_checkup.py"


def _supervise_command(run_dir: Path, cwd: str | None = None) -> str:
    """Bash one-liner: sleep 10 minutes, print a direction briefing, wake Claude.

    This is the 10-minute supervision alarm. It is not a liveness probe.
    The captain must read the briefing, issue an on-track/off-track verdict,
    steer if needed, then re-arm this command.
    """
    d = str(run_dir).replace("\\", "/")
    script = str(CAPTAIN_CHECKUP).replace("\\", "/")
    py = str(PYTHON).replace("\\", "/")
    cwd_arg = ""
    if cwd:
        cwd_arg = f" --cwd '{str(Path(cwd).expanduser().resolve()).replace(chr(92), '/')}'"
    return (
        f"sleep 600; '{py}' '{script}' --run-dir '{d}'{cwd_arg} --since-minutes 10; "
        f"echo \"CAPTAIN-SUPERVISION-DUE $(basename '{d}')\""
    )


def _launch(script_path: Path) -> int:
    flags = 0x00000010 if os.name == "nt" else 0
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        cwd=str(script_path.parent),
        creationflags=flags,
    )
    _LAUNCHED_PIDS.append(int(proc.pid))
    return int(proc.pid)


def _launch_interactive_terminal(script_path: Path) -> int:
    if os.name != "nt":
        return _launch(script_path)
    command = textwrap.dedent(f"""
    $ErrorActionPreference = 'Stop'
    $argList = @(
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      {_ps(script_path)}
    )
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -WindowStyle Normal -PassThru
    Write-Output $proc.Id
    """).strip()
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=str(script_path.parent),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return int(proc.stdout.strip().splitlines()[-1])


def _normalize_reasoning_effort(value: str) -> str:
    """Return a valid effort tier, defaulting when the request is unknown.

    Claude varies the effort per task across high/xhigh/max/ultra; anything
    else (empty, typo, or a retired tier) falls back to the default floor.
    """
    candidate = (value or "").strip().lower()
    if candidate in CODEX_REASONING_EFFORTS:
        return candidate
    return CODEX_REASONING_EFFORT


def _codex_tui_args(
    cwd: str,
    sandbox: str,
    approval_policy: str,
    prompt: str,
    resume_session_id: str = "",
    no_alt_screen: bool = False,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
) -> list[str]:
    args: list[str] = []
    if resume_session_id.strip():
        args.extend(["resume", resume_session_id.strip()])
    args.extend([
        "-m",
        CODEX_MODEL,
        "-C",
        str(Path(cwd).resolve()),
        "-s",
        sandbox,
        "-a",
        approval_policy or INTERACTIVE_TUI_APPROVAL_POLICY,
        "-c",
        f'model_reasoning_effort="{_normalize_reasoning_effort(reasoning_effort)}"',
        "-c",
        f'service_tier="{CODEX_SERVICE_TIER}"',
    ])
    if no_alt_screen:
        args.append("--no-alt-screen")
    if prompt.strip():
        args.append(prompt.strip())
    return args


def _ps_tui_arg(value: str) -> str:
    if value.startswith(("model_reasoning_effort=", "service_tier=")):
        return '"' + value.replace("`", "``").replace('"', '`"') + '"'
    return _ps(value)


def _interactive_codex_tui_runner(
    run_dir: Path,
    cwd: str,
    sandbox: str,
    approval_policy: str,
    prompt: str,
    resume_session_id: str,
    no_alt_screen: bool,
    close_on_exit: bool,
    auto_close_after_report: bool,
    auto_close_delay_seconds: int,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
) -> str:
    args = _codex_tui_args(
        cwd=cwd,
        sandbox=sandbox,
        approval_policy=approval_policy,
        prompt=prompt,
        resume_session_id=resume_session_id,
        no_alt_screen=no_alt_screen,
        reasoning_effort=reasoning_effort,
    )
    ps_args = "\n".join([f"$argsList += @({_ps_tui_arg(arg)})" for arg in args])
    keep_open = "$true" if not close_on_exit else "$false"
    auto_close = "$true" if auto_close_after_report else "$false"
    delay = max(0, min(int(auto_close_delay_seconds), 600))
    return textwrap.dedent(f"""
    $ErrorActionPreference = 'Continue'
    { _PS_CLEANUP_FN }
    $RunDir = {_ps(run_dir)}
    $Cwd = {_ps(cwd)}
    $StatusPath = Join-Path $RunDir 'status.json'
    $DisplayLog = Join-Path $RunDir 'display.log'
    $ReportsDir = Join-Path $RunDir '{CAPTAIN_REPORTS_DIR}'
    $CodexCmd = {_ps(CODEX)}
    $KeepOpen = {keep_open}
    $AutoCloseAfterReport = {auto_close}
    $AutoCloseDelaySeconds = {delay}

    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $Host.UI.RawUI.WindowTitle = "Codex interactive TUI - $(Split-Path $RunDir -Leaf)"

    function Write-Log([string]$Message) {{
      $line = "[{{0}}] {{1}}" -f (Get-Date).ToString("o"), $Message
      Write-Host $line
      Add-Content -LiteralPath $DisplayLog -Value $line -Encoding UTF8
    }}

    function Set-Status([string]$Status, [int]$ExitCode = 0) {{
      $obj = [ordered]@{{
        status = $Status
        run_id = (Split-Path $RunDir -Leaf)
        updated_at = (Get-Date).ToString("o")
        exit_code = $ExitCode
        mode = "interactive_tui"
      }}
      $json = $obj | ConvertTo-Json -Depth 5
      $tmp = $StatusPath + '.tmp'
      foreach ($attempt in 1..5) {{
        try {{
          Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8 -ErrorAction Stop
          Move-Item -LiteralPath $tmp -Destination $StatusPath -Force -ErrorAction Stop
          return
        }} catch {{
          Start-Sleep -Milliseconds 200
        }}
      }}
      Write-Log "Set-Status failed after 5 attempts: $Status"
    }}

    Set-Location -LiteralPath $Cwd
    Set-Status "running"
    Write-Log "Starting interactive Codex TUI. This terminal is user-steered; display.log is launcher/status only."

    if ($AutoCloseAfterReport) {{
      try {{
        $null = Start-Job -ScriptBlock {{
          param([string]$ReportsDir, [int]$RootPid, [int]$DelaySeconds)
          $finalJson = Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_JSON}'
          $finalMd = Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_MD}'
          function Get-DescendantPids([int]$StartPid) {{
            $result = New-Object System.Collections.ArrayList
            try {{ $all = Get-CimInstance Win32_Process -ErrorAction Stop }} catch {{ return @($StartPid) }}
            $byParent = @{{}}
            foreach ($p in $all) {{
              $parent = [int]$p.ParentProcessId
              if (-not $byParent.ContainsKey($parent)) {{ $byParent[$parent] = New-Object System.Collections.ArrayList }}
              [void]$byParent[$parent].Add([int]$p.ProcessId)
            }}
            $queue = New-Object System.Collections.Queue
            $queue.Enqueue([int]$StartPid)
            while ($queue.Count -gt 0) {{
              $cur = [int]$queue.Dequeue()
              [void]$result.Add($cur)
              if ($byParent.ContainsKey($cur)) {{
                foreach ($child in $byParent[$cur]) {{ $queue.Enqueue([int]$child) }}
              }}
            }}
            return @($result)
          }}
          function Send-CtrlCToConsole([int]$TargetPid) {{
            $source = @"
using System;
using System.Runtime.InteropServices;
public static class BridgeConsoleSignal {{
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint dwProcessId);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
  [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handlerRoutine, bool add);
}}
"@
            try {{ Add-Type -TypeDefinition $source -ErrorAction SilentlyContinue | Out-Null }} catch {{}}
            try {{
              [void][BridgeConsoleSignal]::FreeConsole()
              if ([BridgeConsoleSignal]::AttachConsole([uint32]$TargetPid)) {{
                [void][BridgeConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
                [void][BridgeConsoleSignal]::GenerateConsoleCtrlEvent(0, 0)
                Start-Sleep -Milliseconds 500
                [void][BridgeConsoleSignal]::FreeConsole()
                [void][BridgeConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)
                return $true
              }}
            }} catch {{
              try {{ [void][BridgeConsoleSignal]::FreeConsole() }} catch {{}}
            }}
            return $false
          }}
          function Close-InteractiveTuiTree([int]$TargetPid) {{
            $pids = @(Get-DescendantPids $TargetPid)
            [void](Send-CtrlCToConsole $TargetPid)
            Start-Sleep -Seconds 3
            if (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue) {{
              try {{
                Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', [string]$TargetPid, '/T', '/F') -WindowStyle Hidden | Out-Null
                return
              }} catch {{}}
            }}
            foreach ($target in ($pids | Sort-Object -Descending)) {{
              if ([int]$target -eq [int]$PID) {{ continue }}
              try {{ Stop-Process -Id ([int]$target) -Force -ErrorAction SilentlyContinue }} catch {{}}
            }}
          }}
          while ($true) {{
            if (-not (Get-Process -Id $RootPid -ErrorAction SilentlyContinue)) {{ break }}
            $shouldClose = $false
            if (Test-Path -LiteralPath $finalJson) {{
              try {{
                $report = Get-Content -LiteralPath $finalJson -Raw -Encoding UTF8 | ConvertFrom-Json
                $shouldClose = -not ($report.PSObject.Properties.Name -contains 'close_tui' -and $report.close_tui -eq $false)
              }} catch {{
                $shouldClose = $true
              }}
            }} elseif (Test-Path -LiteralPath $finalMd) {{
              $shouldClose = $true
            }}
            if ($shouldClose) {{
              Start-Sleep -Seconds $DelaySeconds
              Close-InteractiveTuiTree $RootPid
              break
            }}
            if ((Test-Path -LiteralPath $finalJson) -or (Test-Path -LiteralPath $finalMd)) {{ break }}
            Start-Sleep -Seconds 1
          }}
        }} -ArgumentList $ReportsDir, $PID, $AutoCloseDelaySeconds
        Write-Log ("Auto-close watcher armed for captain report; delay=" + $AutoCloseDelaySeconds + "s.")
      }} catch {{
        Write-Log ("Auto-close watcher failed to start: " + $_.Exception.Message)
      }}
    }}

    $argsList = @()
    {ps_args}

    Write-Log ("Command: " + $CodexCmd + " " + ($argsList -join " "))
    & $CodexCmd @argsList
    $exitCode = if ($LASTEXITCODE -eq $null) {{ 0 }} else {{ $LASTEXITCODE }}
    if ($exitCode -eq 0) {{
      Set-Status "closed" $exitCode
      Write-Log "Interactive Codex TUI exited cleanly."
    }} else {{
      Set-Status "failed" $exitCode
      Write-Log ("Interactive Codex TUI exited with code " + $exitCode)
    }}

    if ($KeepOpen) {{
      Write-Host ""
      Read-Host "Codex TUI exited. Press Enter to close this window" | Out-Null
    }}
    """).strip()


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
function Write-AppendShared([string]$Path, [string]$Text) {{
  for ($i = 0; $i -lt 25; $i++) {{
    try {{
      $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
      try {{ $sw = New-Object System.IO.StreamWriter($fs, (New-Object System.Text.UTF8Encoding $false)); $sw.WriteLine($Text); $sw.Flush(); $sw.Dispose() }} finally {{ $fs.Dispose() }}
      return
    }} catch {{ Start-Sleep -Milliseconds 15 }}
  }}
}}

function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Write-AppendShared $DisplayLog $text
  }}
}}

function Set-Status([string]$Status) {{
  $json = @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json
  $tmp = $StatusPath + '.tmp'
  foreach ($attempt in 1..5) {{
    try {{
      Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8 -ErrorAction Stop
      Move-Item -LiteralPath $tmp -Destination $StatusPath -Force -ErrorAction Stop
      return
    }} catch {{
      Start-Sleep -Milliseconds 200
    }}
  }}
  Log-Line "Set-Status failed after 5 attempts: $Status"
}}

function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Write-AppendShared $DisplayLog $line
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
  $rawStream = $null
  $rawWriter = $null
  try {{
    # Open events.jsonl ONCE per turn with FileShare.ReadWrite + AutoFlush (mirrors the Grok
    # runner fix). A per-line Add-Content reopens the file each line, and those rapid
    # open/close cycles race with concurrent readers / AV scans on Windows ("The process
    # cannot access the file ... because it is being used by another process").
    try {{ $rawStream = [System.IO.File]::Open($RawLog, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite); $rawWriter = New-Object System.IO.StreamWriter($rawStream, (New-Object System.Text.UTF8Encoding $false)); $rawWriter.AutoFlush = $true }} catch {{ $rawWriter = $null }}
    $prompt | & $Codex @argsList 2>&1 | ForEach-Object {{
      $line = [string]$_
      if ($null -ne $rawWriter) {{ try {{ $rawWriter.WriteLine($line) }} catch {{}} }}
      else {{ try {{ Add-Content -LiteralPath $RawLog -Encoding UTF8 -Value $line -ErrorAction Stop }} catch {{}} }}
      try {{
        $obj = $line | ConvertFrom-Json -ErrorAction Stop
        Show-JsonEvent $obj
      }} catch {{
        Log-Line $line 'Gray'
      }}
    }}
  }} finally {{
    if ($null -ne $rawWriter) {{ try {{ $rawWriter.Flush(); $rawWriter.Dispose() }} catch {{}} }}
    if ($null -ne $rawStream) {{ try {{ $rawStream.Dispose() }} catch {{}} }}
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
    Write-AppendShared $ComposerRawLog $line
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
    Log-Line "Haiku prompt composer exited with code $composerExitCode; falling back to the raw captain brief." 'Yellow'
    $resultText = ''
  }}
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $resultText = (($assistantChunks | ForEach-Object {{ [string]$_ }}) -join "`n")
  }}
  if ([string]::IsNullOrWhiteSpace($resultText) -and $composerExitCode -eq 0) {{
    Log-Line 'Haiku prompt composer produced an empty Codex prompt; falling back to the raw captain brief.' 'Yellow'
  }}
  $prelude = ''
  if (Test-Path -LiteralPath $CodexPreludePath) {{ $prelude = Get-Content -LiteralPath $CodexPreludePath -Raw }}
  $briefHeading = "`n`n## Haiku-Composed Worker Brief`n`n"
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $briefHeading = "`n`n## Captain Brief (raw; Haiku composer unavailable)`n`n"
    $resultText = Get-Content -LiteralPath $PromptPath -Raw
  }}
  $finalPrompt = ($prelude.TrimEnd() + $briefHeading + $resultText.Trim())
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
function Write-AppendShared([string]$Path, [string]$Text) {{
  for ($i = 0; $i -lt 25; $i++) {{
    try {{
      $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
      try {{ $sw = New-Object System.IO.StreamWriter($fs, (New-Object System.Text.UTF8Encoding $false)); $sw.WriteLine($Text); $sw.Flush(); $sw.Dispose() }} finally {{ $fs.Dispose() }}
      return
    }} catch {{ Start-Sleep -Milliseconds 15 }}
  }}
}}

function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Write-AppendShared $DisplayLog $text
  }}
}}

function Set-Status([string]$Status) {{
  $json = @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json
  $tmp = $StatusPath + '.tmp'
  foreach ($attempt in 1..5) {{
    try {{
      Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8 -ErrorAction Stop
      Move-Item -LiteralPath $tmp -Destination $StatusPath -Force -ErrorAction Stop
      return
    }} catch {{
      Start-Sleep -Milliseconds 200
    }}
  }}
  Log-Line "Set-Status failed after 5 attempts: $Status"
}}
function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Write-AppendShared $DisplayLog $line
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
  Write-AppendShared $RawLog $line
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
    effective_reasoning = _normalize_reasoning_effort(reasoning_effort)
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
            effective_reasoning,
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
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": f"A visible PowerShell window was launched. Codex runs gpt-5.6-sol at Claude-selected {effective_reasoning} reasoning (one of high/xhigh/max/ultra) with service_tier=fast. Effective sandbox is {effective_sandbox}. Haiku prompt composer enabled={compose_with_haiku}. Captain-help mailbox enabled. Hidden model reasoning is not exposed; prompts, events, messages, commands, usage, and diffs are logged.",
    }


@mcp.tool()
def start_visible_haiku_composed_codex_worker(
    prompt_brief: str,
    cwd: str,
    title: str = "Codex worker",
    sandbox: str = "read-only",
    approval_policy: str = "never",
    reasoning_effort: str = CODEX_REASONING_EFFORT,
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
        reasoning_effort=reasoning_effort,
        session_context=session_context,
        resume_session_id=resume_session_id,
        requires_tool_access=requires_tool_access,
        compose_with_haiku=True,
        composer_model=CLAUDE_PROMPT_COMPOSER_MODEL,
        composer_effort=CLAUDE_PROMPT_COMPOSER_EFFORT,
        composer_max_budget_usd=composer_max_budget_usd,
        steer_idle_seconds=steer_idle_seconds,
    )


def _first_mate_prompt(
    goal: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    max_workers: int = 6,
    session_context: str = "",
    requires_tool_access: bool = False,
) -> tuple[str, bool]:
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
    return textwrap.dedent(prompt).strip(), auto_full_tool_access


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
    prompt, auto_full_tool_access = _first_mate_prompt(
        goal=goal,
        scout_areas=scout_areas,
        implementation_items=implementation_items,
        sandbox=sandbox,
        max_workers=max_workers,
        session_context=session_context,
        requires_tool_access=requires_tool_access,
    )
    return start_visible_codex_worker(
        prompt=prompt,
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
def start_interactive_first_mate_codex_tui(
    goal: str,
    cwd: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    approval_policy: str = INTERACTIVE_TUI_APPROVAL_POLICY,
    max_workers: int = 6,
    model: str = CODEX_MODEL,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    no_alt_screen: bool = False,
    close_on_exit: bool = True,
    auto_close_after_report: bool = True,
    auto_close_delay_seconds: int = INTERACTIVE_TUI_AUTO_CLOSE_DELAY_SECONDS,
) -> dict[str, Any]:
    """Deprecated: use start_visible_first_mate_codex_pool by default.

    Launch the first-mate coordinator in the real interactive Codex TUI only for
    an explicit user request for a hands-on terminal.
    """
    prompt, auto_full_tool_access = _first_mate_prompt(
        goal=goal,
        scout_areas=scout_areas,
        implementation_items=implementation_items,
        sandbox=sandbox,
        max_workers=max_workers,
        session_context=session_context,
        requires_tool_access=requires_tool_access,
    )
    return start_interactive_codex_tui(
        prompt=prompt,
        cwd=cwd,
        title="Interactive Codex first mate TUI",
        sandbox=sandbox,
        approval_policy=approval_policy,
        session_context=session_context,
        resume_session_id=resume_session_id,
        requires_tool_access=requires_tool_access or auto_full_tool_access,
        no_alt_screen=no_alt_screen,
        close_on_exit=close_on_exit,
        auto_close_after_report=auto_close_after_report,
        auto_close_delay_seconds=auto_close_delay_seconds,
        model=model,
        reasoning_effort=reasoning_effort,
    )


@mcp.tool()
def start_interactive_codex_tui(
    prompt: str,
    cwd: str,
    title: str = "Interactive Codex TUI",
    sandbox: str = "read-only",
    approval_policy: str = INTERACTIVE_TUI_APPROVAL_POLICY,
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    no_alt_screen: bool = False,
    close_on_exit: bool = True,
    auto_close_after_report: bool = True,
    auto_close_delay_seconds: int = INTERACTIVE_TUI_AUTO_CLOSE_DELAY_SECONDS,
    model: str = CODEX_MODEL,
    reasoning_effort: str = CODEX_REASONING_EFFORT,
    service_tier: str = CODEX_SERVICE_TIER,
) -> dict[str, Any]:
    """Deprecated: use start_visible_haiku_composed_codex_worker for a compact brief
    or start_visible_codex_worker for a final prompt by default.

    Launch the real interactive Codex TUI only for an explicit user request for a
    hands-on terminal; sidecar metadata remains available for compatibility.
    """
    effective_model = CODEX_MODEL
    effective_reasoning = _normalize_reasoning_effort(reasoning_effort)
    effective_service_tier = CODEX_SERVICE_TIER
    auto_full_tool_access = _needs_full_tool_access("\n".join([title, prompt, session_context]))
    effective_sandbox = CODEX_FULL_TOOL_SANDBOX
    requested_approval = approval_policy or INTERACTIVE_TUI_APPROVAL_POLICY
    close_delay = max(0, min(int(auto_close_delay_seconds), 600))
    base_prompt = _with_session_context_bootstrap(
        "\n\n".join([
            _codex_permission_contract(sandbox, effective_sandbox),
            prompt,
        ]),
        cwd,
        "Interactive Codex TUI",
        session_context,
    )
    run_dir = _make_run(cwd, "codex-tui-resume" if resume_session_id else "codex-tui", title, base_prompt, {
        "agent": "codex",
        "mode": INTERACTIVE_TUI_MODE,
        "cwd": str(Path(cwd).resolve()),
        "sandbox": effective_sandbox,
        "requested_sandbox": sandbox,
        "approval_policy": requested_approval,
        "model": effective_model,
        "reasoning_effort": effective_reasoning,
        "service_tier": effective_service_tier,
        "requested_model": model,
        "requested_reasoning_effort": reasoning_effort,
        "requested_service_tier": service_tier,
        "resume_session_id": resume_session_id or None,
        "started_at_epoch": time.time(),
        "session_context_supplied": bool(session_context.strip()),
        "requires_tool_access": requires_tool_access,
        "auto_full_tool_access": auto_full_tool_access,
        "sandbox_bypass_enabled": True,
        "tool_access_default": "full-process-access",
        "no_alt_screen": bool(no_alt_screen),
        "close_on_exit": bool(close_on_exit),
        "auto_close_after_report": bool(auto_close_after_report),
        "auto_close_delay_seconds": close_delay,
    })
    effective_prompt = "\n\n".join([
        _captain_report_contract(run_dir, bool(auto_close_after_report), close_delay),
        _captain_help_contract(run_dir),
        base_prompt,
    ])
    (run_dir / "prompt.md").write_text(effective_prompt, encoding="utf-8")
    (run_dir / "session_context.md").write_text(session_context.strip(), encoding="utf-8")
    (run_dir / "notes.md").write_text(
        "# Interactive Codex TUI Notes\n\n"
        "This run is user-steered through the Codex TUI. display.log contains launcher/status lines, not a full transcript.\n"
        "The captain-facing outcome is written under captain_reports/ by submit_captain_report.\n",
        encoding="utf-8",
    )
    (run_dir / "display.log").write_text("", encoding="utf-8")
    tui_prompt = effective_prompt
    if len(effective_prompt) > TUI_INLINE_PROMPT_MAX_CHARS:
        tui_prompt = (
            "Your full captain brief was too long for the Windows command line, so it was saved to a file.\n"
            f"Read this file FIRST and follow it exactly as this run's task instructions: {run_dir / 'prompt.md'}\n"
            "It contains the captain report contract, the captain-help contract, the session context, and the task brief. "
            "Do not start any other work until you have read that file."
        )
    script = run_dir / "run.ps1"
    script.write_text(
        _interactive_codex_tui_runner(
            run_dir=run_dir,
            cwd=str(Path(cwd).resolve()),
            sandbox=effective_sandbox,
            approval_policy=requested_approval,
            prompt=tui_prompt,
            resume_session_id=resume_session_id,
            no_alt_screen=no_alt_screen,
            close_on_exit=close_on_exit,
            auto_close_after_report=bool(auto_close_after_report),
            auto_close_delay_seconds=close_delay,
            reasoning_effort=effective_reasoning,
        ),
        encoding="utf-8",
    )
    pid = _launch_interactive_terminal(script)
    (run_dir / "launcher_pid.txt").write_text(str(pid), encoding="utf-8")
    status = _read_json(run_dir / "status.json", {})
    status.update({
        "status": "launched",
        "mode": INTERACTIVE_TUI_MODE,
        "pid": pid,
        "updated_at": _dt.datetime.now().isoformat(),
    })
    _write_json(run_dir / "status.json", status)
    return {
        "ok": True,
        "run_id": run_dir.name,
        "pid": pid,
        "run_dir": str(run_dir),
        "prompt": str(run_dir / "prompt.md"),
        "session_context": str(run_dir / "session_context.md"),
        "display_log": str(run_dir / "display.log"),
        "status": str(run_dir / "status.json"),
        "session_id": None,
        "session_id_file": str(run_dir / "session_id.txt"),
        "metadata": str(run_dir / "metadata.json"),
        "captain_reports": str(run_dir / CAPTAIN_REPORTS_DIR),
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": "A real interactive Codex TUI was launched. You can steer it directly in the terminal. Codex must call submit_captain_report or write captain_reports/final.* for Claude handoff; the TUI auto-closes after that report by default.",
    }


@mcp.tool()
def steer_visible_codex_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = True,
    requires_tool_access: bool = False,
) -> dict[str, Any]:
    """Send a Claude steering instruction to a visible Codex run, resuming the same Codex thread if needed.

    Delivery is direct by default: an in-flight turn is interrupted and the same
    Codex thread resumes immediately with the instruction. Workers idle in their
    steering window consume the queue within a second, so they are never
    interrupted. Pass interrupt_current_turn=False to wait for the current turn
    to finish instead of interrupting it.
    """
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

    idle = status_name in ("created", "waiting_for_steer")
    if active and (not interrupt_current_turn or idle):
        if status_name == "waiting_for_steer":
            result["note"] = (
                "Steering was queued for immediate pickup: the worker is idle in its "
                "steering window and polls the queue every second."
            )
        return result

    resume_session_id = thread_id
    resume_mode = "launched_resume"
    resume_note = "The previous visible run was not available for in-window steering, so a visible Codex resume run was launched on the same thread."

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
            interrupted, interrupt_warning = _interrupt_visible_run(pid)
            if not interrupted:
                result["mode"] = "queued_interrupt_failed"
                if interrupt_warning:
                    result["interrupt_warning"] = interrupt_warning
                result["note"] = "Steering was queued, but the active visible run could not be interrupted cleanly."
                return result
            result["interrupted_pid"] = pid
            if interrupt_warning:
                result["interrupt_warning"] = interrupt_warning
            if not _wait_for_codex_thread_ready(thread_id, timeout_sec=12.0):
                resume_session_id = ""
                resume_mode = "launched_restart_after_interrupt"
                resume_note = (
                    "The active run was interrupted, but its Codex thread file was empty. "
                    "A fresh visible Codex follow-up was launched with the saved run context and steering instruction."
                )
                result["resume_warning"] = "Interrupted Codex thread file was empty; codex resume was skipped."
                result["interrupt_warning"] = "\n".join(
                    part for part in [
                        result.get("interrupt_warning", ""),
                        f"Codex thread {thread_id} did not become readable before resume.",
                    ] if part
                )
        except Exception as exc:
            result["mode"] = "queued_interrupt_failed"
            result["interrupt_warning"] = str(exc)
            result["note"] = "Steering was queued, but the active visible run could not be interrupted cleanly."
            return result

    if not launch_if_closed and "interrupted_pid" not in result:
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
        resume_session_id=resume_session_id,
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
    result["mode"] = resume_mode
    result["followup_run"] = followup
    result["note"] = resume_note
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


def _format_report_items(values: list[str] | None) -> str:
    if not values:
        return "- none"
    lines = [f"- {str(value).strip()}" for value in values if str(value).strip()]
    return "\n".join(lines) if lines else "- none"


def _captain_report_markdown(record: dict[str, Any]) -> str:
    return textwrap.dedent(f"""
    # Captain Report

    Report ID: {record["report_id"]}
    Outcome: {record["outcome"]}
    Created: {record["created_at"]}
    Run directory: {record["run_dir"]}
    Close TUI: {record["close_tui"]}

    ## Summary

    {record["summary"] or "None supplied."}

    ## Changed Files

    {_format_report_items(record.get("changed_files") or [])}

    ## Verification

    {_format_report_items(record.get("verification") or [])}

    ## Risks

    {_format_report_items(record.get("risks") or [])}

    ## Questions

    {_format_report_items(record.get("questions") or [])}
    """).strip()


def _latest_captain_report(run_dir: Path) -> dict[str, Any] | None:
    reports_dir = _ensure_captain_report_dir(run_dir)
    final = reports_dir / CAPTAIN_REPORT_FINAL_JSON
    if final.exists():
        report = _read_json(final, {})
        return report or None
    reports = sorted(
        [path for path in reports_dir.glob("*.json") if path.name != CAPTAIN_REPORT_FINAL_JSON],
        key=lambda path: path.name,
        reverse=True,
    )
    for path in reports:
        report = _read_json(path, {})
        if report:
            return report
    return None


def _captain_reports_count(run_dir: Path) -> int:
    reports_dir = _ensure_captain_report_dir(run_dir)
    count = len([path for path in reports_dir.glob("*.json") if path.name != CAPTAIN_REPORT_FINAL_JSON])
    if count == 0 and (reports_dir / CAPTAIN_REPORT_FINAL_JSON).exists():
        return 1
    return count


def _status_with_captain_report(status: dict[str, Any], captain_report: dict[str, Any] | None, run_dir: Path) -> dict[str, Any]:
    if not captain_report:
        return status
    updated = dict(status)
    status_name = _status_name(updated)
    if status_name == "reported":
        updated.setdefault("outcome", captain_report.get("outcome"))
        updated.setdefault("captain_report", str(run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON))
        return updated
    if status_name in {"created", "launched", "running", "unknown"} or status_name.startswith("running"):
        updated["status"] = "reported"
        updated["outcome"] = captain_report.get("outcome")
        updated["captain_report"] = str(run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON)
    return updated


def _list_captain_reports_for_run(run_dir: Path, include_text: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    reports_dir = _ensure_captain_report_dir(run_dir)
    paths = sorted(
        [path for path in reports_dir.glob("*.json") if path.name != CAPTAIN_REPORT_FINAL_JSON],
        key=lambda path: path.name,
        reverse=True,
    )
    if not paths and (reports_dir / CAPTAIN_REPORT_FINAL_JSON).exists():
        paths = [reports_dir / CAPTAIN_REPORT_FINAL_JSON]
    records: list[dict[str, Any]] = []
    for path in paths[: max(1, min(limit, 100))]:
        record = _read_json(path, {})
        if not record:
            continue
        item = {
            "report_id": record.get("report_id"),
            "outcome": record.get("outcome"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "summary": record.get("summary"),
            "run_dir": str(run_dir),
            "report": str(path),
            "report_markdown": str(path.with_suffix(".md")),
        }
        if include_text:
            item["changed_files"] = record.get("changed_files") or []
            item["verification"] = record.get("verification") or []
            item["risks"] = record.get("risks") or []
            item["questions"] = record.get("questions") or []
        records.append(item)
    return records


@mcp.tool()
def submit_captain_report(
    run_dir: str,
    outcome: str,
    summary: str,
    changed_files: list[str] | None = None,
    verification: list[str] | None = None,
    risks: list[str] | None = None,
    questions: list[str] | None = None,
    close_tui: bool = True,
) -> dict[str, Any]:
    """Submit the final captain-facing report for an interactive Codex TUI run."""
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    if metadata.get("agent") not in (None, "codex", "grok", "agy", "claude", "cursor"):
        return {"ok": False, "error": f"run_dir is not a captain-reporting worker run: {path}", "metadata": metadata}
    normalized_outcome = (outcome or "").strip().lower()
    if normalized_outcome not in {"completed", "partial", "blocked", "failed"}:
        return {"ok": False, "error": "outcome must be one of: completed, partial, blocked, failed"}
    reports_dir = _ensure_captain_report_dir(path)
    report_id = f"{_now()}-report-{uuid.uuid4().hex[:8]}"
    now = _dt.datetime.now().isoformat()
    record = {
        "report_id": report_id,
        "status": "submitted",
        "outcome": normalized_outcome,
        "created_at": now,
        "updated_at": now,
        "run_dir": str(path),
        "thread_id": (path / "thread_id.txt").read_text(encoding="utf-8-sig").strip() if (path / "thread_id.txt").exists() else None,
        "session_id": _visible_run_session_id(path, metadata),
        "summary": summary.strip(),
        "changed_files": [str(item).strip() for item in (changed_files or []) if str(item).strip()],
        "verification": [str(item).strip() for item in (verification or []) if str(item).strip()],
        "risks": [str(item).strip() for item in (risks or []) if str(item).strip()],
        "questions": [str(item).strip() for item in (questions or []) if str(item).strip()],
        "close_tui": bool(close_tui),
    }
    report_json = reports_dir / f"{report_id}.json"
    report_md = reports_dir / f"{report_id}.md"
    final_json = reports_dir / CAPTAIN_REPORT_FINAL_JSON
    final_md = reports_dir / CAPTAIN_REPORT_FINAL_MD
    markdown = _captain_report_markdown(record)
    for target in (report_json, final_json):
        target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    for target in (report_md, final_md):
        target.write_text(markdown, encoding="utf-8")
    status = _read_json(path / "status.json", {"status": "unknown"})
    status.update({
        "status": "reported",
        "outcome": normalized_outcome,
        "captain_report_id": report_id,
        "captain_report": str(final_json),
        "updated_at": now,
    })
    _write_json(path / "status.json", status)
    try:
        with (path / "display.log").open("a", encoding="utf-8") as log:
            log.write(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] Captain report submitted: {report_id} ({normalized_outcome})\n")
    except Exception:
        pass
    return {
        "ok": True,
        "report_id": report_id,
        "run_dir": str(path),
        "report": str(final_json),
        "report_markdown": str(final_md),
        "close_tui": bool(close_tui),
        "note": "Captain report recorded. Claude can read it with get_visible_run_status or list_captain_reports.",
    }


@mcp.tool()
def list_captain_reports(
    cwd: str | None = None,
    run_dir: str = "",
    include_text: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List captain reports submitted by interactive Codex TUI runs."""
    if run_dir.strip():
        path = Path(run_dir).expanduser().resolve()
        if not path.exists():
            return []
        return _list_captain_reports_for_run(path, include_text=include_text, limit=limit)
    root = _run_root(cwd)
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for run in sorted(root.glob("*"), key=lambda p: p.name, reverse=True):
        if not run.is_dir():
            continue
        rows.extend(_list_captain_reports_for_run(run, include_text=include_text, limit=limit))
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows[: max(1, min(limit, 100))]


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
    if metadata.get("agent") not in (None, "codex", "grok", "agy", "claude", "cursor"):
        return {"ok": False, "error": f"run_dir is not a captain-help-capable worker run: {path}", "metadata": metadata}
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
    steer = _dispatch_visible_steer(
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
        "note": "Captain response recorded and queued as steering for the same worker run.",
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
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": f"A visible PowerShell window was launched for Claude advisor output. Claude is forced to {effective_model}/high by the central advisor model policy. Hidden model reasoning is not exposed.",
    }


@mcp.tool()
def get_visible_run_status(run_dir: str, tail_lines: int = 80) -> dict[str, Any]:
    """Read status and recent visible log lines from a visible agent run directory."""
    path = Path(run_dir)
    status_path = path / "status.json"
    display_path = path / "display.log"
    thread_path = path / "thread_id.txt"
    metadata_path = path / "metadata.json"
    steer_queue = path / "steer_queue"
    steer_done = path / "steer_done"
    help_dirs = _ensure_captain_help_dirs(path)
    status = json.loads(status_path.read_text(encoding="utf-8-sig")) if status_path.exists() else {"status": "unknown"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig")) if metadata_path.exists() else {}
    session_id = _visible_run_session_id(path, metadata)
    captain_report = _latest_captain_report(path)
    status = _status_with_captain_report(status, captain_report, path)
    lines: list[str] = []
    if display_path.exists():
        all_lines = display_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        lines = all_lines[-max(1, min(tail_lines, 500)):]
    return {
        "run_dir": str(path),
        "status": status,
        "metadata": metadata,
        "thread_id": thread_path.read_text(encoding="utf-8-sig").strip() if thread_path.exists() else None,
        "session_id": session_id,
        "pending_steers": len(list(steer_queue.glob("*.md"))) if steer_queue.exists() else 0,
        "completed_steers": len(list(steer_done.glob("*.md"))) if steer_done.exists() else 0,
        "pending_help_requests": len(list(help_dirs["requests"].glob("*.json"))),
        "answered_help_requests": len(list(help_dirs["answered"].glob("*.json"))),
        "escalated_help_requests": len(list(help_dirs["escalated"].glob("*.json"))),
        "help_requests": _summarize_help_requests(path, include_answered=False, limit=10),
        "captain_report": captain_report,
        "captain_reports_count": _captain_reports_count(path),
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
        steer_queue = run / "steer_queue"
        steer_done = run / "steer_done"
        metadata = _read_json(metadata_path, {})
        session_id = _visible_run_session_id(run, metadata)
        captain_report = _latest_captain_report(run)
        status = _read_json(status_path, {"status": "unknown"})
        if not status:
            status = {"status": "unreadable"}
        status = _status_with_captain_report(status, captain_report, run)
        result.append({
            "run_id": run.name,
            "run_dir": str(run),
            "status": status,
            "metadata": metadata,
            "thread_id": thread_path.read_text(encoding="utf-8-sig").strip() if thread_path.exists() else None,
            "session_id": session_id,
            "pending_steers": len(list(steer_queue.glob("*.md"))) if steer_queue.exists() else 0,
            "completed_steers": len(list(steer_done.glob("*.md"))) if steer_done.exists() else 0,
            "captain_report": captain_report,
            "captain_reports_count": _captain_reports_count(run),
        })
    return result


# --- Grok worker backend (added 2026-07-14) ---
# Adds a Grok (grok-4.6) visible worker backend alongside the existing Codex
# backend. Codex is left completely untouched above this line; every symbol
# below is new. See plugin/skills/claude-manages-codex/SKILL.md, section
# "Grok Worker Backend (added 2026-07-14)", for the routing doctrine.

GROK = Path(r"C:\Users\jonny\.grok\bin\grok.exe")
GROK_MODEL = "grok-4.6"
# grok-4.6 xhigh fully supersedes grok 4.5. xhigh is a first-class
# --reasoning-effort value in grok Build CLI. Config default is also
# default_reasoning_effort = "xhigh" in ~/.grok/config.toml.
GROK_CLI_REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
GROK_STEER_IDLE_SECONDS = CODEX_STEER_IDLE_SECONDS


def _grok_effort_flag(requested: str) -> list[str]:
    """Return the --reasoning-effort flag for grok-4.6, or [] to inherit xhigh.

    Returns ["--reasoning-effort", e] iff e.lower() is one of
    low/medium/high/xhigh. Any other value (including "max" or empty)
    returns [], which omits the flag so the grok-4.6 CLI falls back to its
    config default (default_reasoning_effort = "xhigh" in ~/.grok/config.toml).
    """
    candidate = (requested or "").strip().lower()
    if candidate in GROK_CLI_REASONING_EFFORTS:
        return ["--reasoning-effort", candidate]
    return []


def _grok_captain_report_note(run_dir: Path) -> str:
    return textwrap.dedent(f"""
    # Captain Report (Grok)

    Run directory: {run_dir}

    This run's launcher automatically writes a captain report to
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON}` and
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_MD}` from your final
    answer text once this turn ends, so Claude can read your result with
    `get_visible_run_status` or `list_captain_reports` even if you never call a
    tool. If the `agent-visibility` MCP server is reachable in this session,
    also call `submit_captain_report` with a structured outcome/summary before
    stopping, and use `request_captain_help` if you are blocked. Do not rely on
    a plain terminal answer alone if a richer structured report is possible.
    """).strip()


def _grok_rigor_contract() -> str:
    """Mandatory anti-fixation / self-verification contract injected into every
    grok-4.6 worker prompt. grok-4.6 is a fast coder but weak at reasoning and at
    pressure-testing its own work: it tunnel-visions on the first idea, skips edge
    cases and error paths, and declares 'done' without executing anything. This
    contract forces the opposite, and warns it that the captain reviews adversarially."""
    return textwrap.dedent("""
    # Worker Rigor Contract (mandatory — you WILL be graded on this)

    Known failure modes you must actively counter on THIS task (they are why work gets rejected):
    you fixate on the first idea, skip edge/error cases, and claim success from reading code
    without ever running it. Do the opposite, in order:

    1. ENUMERATE before you change anything. Write down at least 2-3 distinct root-cause
       hypotheses or candidate approaches, and the edge cases, error paths, boundary values,
       empty/null/concurrent inputs, and failure scenarios the change must survive. Do NOT tunnel
       on the first thing that seems to work.
    2. PRESSURE-TEST your own change adversarially before reporting. Assume it is wrong and try to
       break it: wrong inputs, the opposite of the happy path, resource contention, partial
       failure, the scenario you were tempted to ignore. Fix what you find. State what you tried
       to break and what survived.
    3. ACTUALLY RUN IT, END TO END. Never declare success from static reading. Execute the real
       path — run the tests, invoke the CLI/endpoint/script, reproduce the original symptom and
       show it is gone — and paste the OBSERVED output as proof. If you genuinely cannot execute
       it, say so explicitly and label the result UNVERIFIED. A confident "done" without executed
       evidence is a FAILURE of this contract, not a completion.
    4. REPORT HONESTLY: what changed, the exact commands you ran and their real output, what you
       did NOT test, and the top 2 ways this could still be wrong.

    The captain (Claude Opus) will review your output ANTAGONISTICALLY — assuming it is buggy until
    your executed evidence proves otherwise, and specifically hunting the edge cases and scenarios
    you skipped. Save a rejection round-trip by proving it yourself first.
    """).strip()


def _grok_competition_contract(max_agents: int) -> str:
    """Parallel-competition capability injected into grok worker prompts. grok-4.6 has native
    parallel subagents; for hard problems the root worker runs a competition INSIDE its single
    turn (one terminal): spawn up to max_agents diverse subagents attempting the full task, then
    act as judge and compile the best solution. This is a grok-4.6 analog of the grok-4.20
    multi-agent harness. Usage is abundant, so competition is encouraged for genuinely hard work.
    Only injected when max_agents >= 2."""
    n = max(2, min(int(max_agents), 16))
    return textwrap.dedent(f"""
    # Parallel Competition Mode (native grok subagents, up to {n} — usage is abundant, resets often)

    You have a native parallel-subagent capability. For any HARD or open-ended problem — a tricky
    bug, a design/architecture decision, an optimization, or any task with a wide solution space or
    real uncertainty about the best approach — run a COMPETITION inside THIS single worker turn
    (no new terminals, everything stays in this one window):

    1. Spawn up to {n} parallel subagents AT ONCE, each independently attempting the FULL task with a
       DIFFERENT strategy or hypothesis. Make them genuinely diverse — not {n} copies of the same
       idea. Let them run concurrently.
    2. Then act as the JUDGE. Critically compare their solutions against the acceptance criteria and
       the edge cases from the Rigor Contract above. Each competitor must have actually run/verified
       its own result; discard any that only claim success without evidence.
    3. COMPILE THE BEST: either select the single strongest solution, or synthesize a superior one
       that combines the best parts of several. Then verify the compiled result end to end yourself.
    4. Report which approaches you ran, why the winner won, and what you rejected.

    Use competition when the task is hard enough to benefit; for simple or mechanical tasks, just
    solve it directly without competitors. Grok usage is abundant and resets often — do not hold
    back on parallelism for genuinely hard problems; many diverse competitors beat one rushed attempt.
    """).strip()


def _grok_work_checker_contract() -> str:
    """Mandatory parallel work-checker gate injected into every grok worker prompt. grok-4.6's
    worst habit is declaring 'done' without testing; this forces a full parallel adversarial audit
    of its OWN finished work (native subagents, one terminal) before it may report done, and to fix
    every proven finding and re-check until clean."""
    return textwrap.dedent("""
    # Mandatory Parallel Work-Checker (run EVERY time, right before you report done)

    When you believe the work is complete, DO NOT declare done yet. First run a full parallel
    work-checker over your OWN finished work: spawn a fleet of parallel checker subagents inside this
    same turn (native subagents — one terminal, no extra windows), each adversarially auditing the
    completed work from a DIFFERENT lens and assuming it is WRONG until it proves otherwise. Cover, in
    parallel, at least:

    - Correctness & logic: does it actually do what was asked? trace the real execution.
    - Edge cases & error paths: empty / null / boundary / oversized / malformed inputs, and every
      failure branch.
    - Did it actually run? RE-EXECUTE the acceptance test / repro end to end and read the real output.
    - Requirements coverage: every stated requirement and acceptance criterion met, nothing skipped.
    - Regressions / blast radius: did the change break an adjacent case, an existing test, or a caller?
    - Security / concurrency / performance where the task touches them.

    Then consolidate the checkers' findings, keep only the ones proven with evidence (no cry-wolf),
    FIX every real issue, and RE-RUN the checkers until they come back clean. Only after a clean
    parallel work-checker pass may you report done, and your report MUST include what the checkers
    found, what you fixed, and the final clean verification output. Skipping this pass — or reporting
    done with unfixed findings — is a failure of this contract. (For a purely trivial informational
    reply with no code or artifacts to check, a full fleet is unnecessary — but you must still
    re-verify your answer is correct before reporting.)
    """).strip()


# PowerShell descendant-reaper scoped to Grok's own process tree, mirroring
# _PS_CLEANUP_FN's shape but targeting grok's process name instead of
# codex/node/claude. Kept as a separate constant so _PS_CLEANUP_FN (used by
# the Codex and Claude runners) stays byte-identical.
_PS_GROK_CLEANUP_FN = r"""
function Stop-GrokRunDescendants {
  param([int]$RootPid)
  $targets = @('grok','node')
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
  Log-Line "Reaped $killed leftover Grok process(es) for this run." 'DarkGray'
}
"""


def _grok_read_only_args(sandbox: str) -> list[str]:
    """Strict read-only enforcement (from faeton/claude-grok-plugin): when the
    caller's permission intent is read-only, strip Grok's file-mutation tools
    (Write, Edit) via --disallowed-tools so the worker truly cannot edit files,
    not merely be asked not to. Bash is intentionally KEPT so read-only
    inspection (Python-backed skills, read-past-sessions, safe read commands)
    still works — the bridge's read-only means 'no edits', not 'no commands'."""
    if (sandbox or "").strip().lower() == "read-only":
        return ["--disallowed-tools", "Write,Edit"]
    return []


def _grok_initial_extra_args(best_of_n: int, self_check: bool) -> list[str]:
    """Headless-only Grok flags applied to the initial task turn only:
    --best-of-n N (run the task N ways in parallel and keep the best; leverages
    SuperGrok Heavy, costs ~Nx tokens; capped 1..6) and --check (append Grok's
    self-verification loop). Not applied to resume/steer turns."""
    args: list[str] = []
    try:
        n = max(1, min(int(best_of_n or 1), 6))
    except (TypeError, ValueError):
        n = 1
    if n > 1:
        args += ["--best-of-n", str(n)]
    if self_check:
        args.append("--check")
    return args


def _grok_runner(
    run_dir: Path,
    cwd: str,
    requested_effort: str,
    resume_session_id: str = "",
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = GROK_STEER_IDLE_SECONDS,
    sandbox: str = "",
    best_of_n: int = 1,
    self_check: bool = False,
) -> str:
    effort_flag = _grok_effort_flag(requested_effort)
    effort_flag_ps = ",".join(_ps(part) for part in effort_flag) if effort_flag else ""
    read_only_args = _grok_read_only_args(sandbox)
    read_only_ps = ",".join(_ps(part) for part in read_only_args) if read_only_args else ""
    initial_extra = _grok_initial_extra_args(best_of_n, self_check)
    initial_extra_ps = ",".join(_ps(part) for part in initial_extra) if initial_extra else ""
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$ComposerPromptPath = Join-Path $RunDir 'composer_prompt.md'
$ComposerRawLog = Join-Path $RunDir 'composer_events.jsonl'
$ComposedPromptPath = Join-Path $RunDir 'composed_prompt.md'
$GrokPreludePath = Join-Path $RunDir 'grok_prelude.md'
$RawLog = Join-Path $RunDir 'events.jsonl'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$SessionPath = Join-Path $RunDir 'session_id.txt'
$SteerQueue = Join-Path $RunDir 'steer_queue'
$SteerDone = Join-Path $RunDir 'steer_done'
$ReportsDir = Join-Path $RunDir '{CAPTAIN_REPORTS_DIR}'
$Grok = {_ps(GROK)}
$Claude = {_ps(CLAUDE)}
$Cwd = {_ps(cwd)}
$Model = {_ps(GROK_MODEL)}
$ResumeSessionId = {_ps(resume_session_id)}
$ComposeWithHaiku = {"$true" if compose_with_haiku else "$false"}
$ComposerModel = {_ps(composer_model)}
$ComposerEffort = {_ps(composer_effort)}
$ComposerMaxBudgetUsd = {_ps(composer_max_budget_usd)}
$SteerIdleSeconds = {max(0, min(int(steer_idle_seconds), 300))}
$EffortArgs = @({effort_flag_ps})
$ReadOnlyArgs = @({read_only_ps})
$InitialExtraArgs = @({initial_extra_ps})
# Force UTF-8 so Grok's UTF-8 stdout/stdin is decoded correctly (mirrors the Codex runner).
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$Host.UI.RawUI.WindowTitle = "Grok visible worker - $(Split-Path $RunDir -Leaf)"

# Append a line to a log file with a share-friendly open + short retry. A plain
# Add-Content reopens the file on every call; on Windows those rapid reopens collide
# with concurrent readers / AV + Search scans (worst on Desktop-indexed paths) and throw
# "The process cannot access the file ... because it is being used by another process".
# FileShare.ReadWrite plus a brief retry loop rides through the scan window; if it still
# cannot open, it silently skips (these logs are diagnostic and never worth crashing or
# spamming the run over).
function Write-AppendShared([string]$Path, [string]$Text) {{
  for ($i = 0; $i -lt 25; $i++) {{
    try {{
      $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
      try {{ $sw = New-Object System.IO.StreamWriter($fs, (New-Object System.Text.UTF8Encoding $false)); $sw.WriteLine($Text); $sw.Flush(); $sw.Dispose() }} finally {{ $fs.Dispose() }}
      return
    }} catch {{ Start-Sleep -Milliseconds 15 }}
  }}
}}

# UTF-8 tee helper (Tee-Object writes UTF-16LE in PowerShell 5.1, corrupting display.log).
function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Write-AppendShared $DisplayLog $text
  }}
}}

function Set-Status([string]$Status) {{
  $json = @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json
  $tmp = $StatusPath + '.tmp'
  foreach ($attempt in 1..5) {{
    try {{
      Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8 -ErrorAction Stop
      Move-Item -LiteralPath $tmp -Destination $StatusPath -Force -ErrorAction Stop
      return
    }} catch {{
      Start-Sleep -Milliseconds 200
    }}
  }}
  Log-Line "Set-Status failed after 5 attempts: $Status"
}}

function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Write-AppendShared $DisplayLog $line
  Write-Host $line -ForegroundColor $Color
}}

function Get-NextSteerFile {{
  if (-not (Test-Path -LiteralPath $SteerQueue)) {{ return $null }}
  $next = Get-ChildItem -LiteralPath $SteerQueue -Filter '*.md' -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
  return $next
}}

function Write-AutoCaptainReport([string]$Outcome, [string]$SummaryText, [string]$SessionId) {{
  $reportId = "$(Split-Path $RunDir -Leaf)-auto"
  $now = (Get-Date).ToString('o')
  $sessionValue = $null
  if ($SessionId -and $SessionId -ne '') {{ $sessionValue = $SessionId }}
  $record = [ordered]@{{
    report_id = $reportId
    status = 'submitted'
    outcome = $Outcome
    created_at = $now
    updated_at = $now
    run_dir = $RunDir
    thread_id = $null
    session_id = $sessionValue
    summary = $SummaryText
    changed_files = @()
    verification = @()
    risks = @()
    questions = @()
    close_tui = $true
    auto_generated = $true
    agent = 'grok'
  }}
  New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
  $json = $record | ConvertTo-Json -Depth 6
  Set-Content -LiteralPath (Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_JSON}') -Value $json -Encoding UTF8
  $md = "# Captain Report`n`nReport ID: $reportId`nOutcome: $Outcome`nCreated: $now`nRun directory: $RunDir`nClose TUI: True`n`n## Summary`n`n$SummaryText`n`n## Changed Files`n`n- none`n`n## Verification`n`n- none`n`n## Risks`n`n- none`n`n## Questions`n`n- none"
  Set-Content -LiteralPath (Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_MD}') -Value $md -Encoding UTF8
}}

function Get-ReportBaseline {{
  $fp = Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_JSON}'
  if (Test-Path -LiteralPath $fp) {{ return (Get-Item -LiteralPath $fp).LastWriteTimeUtc }}
  return [datetime]::MinValue
}}

function Test-WorkerReportSince([datetime]$baseline) {{
  # True when the worker wrote its own captain report (via submit_captain_report)
  # during the turn. In that case the runner must NOT overwrite it with the
  # auto-report; the worker's explicit report is authoritative.
  $fp = Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_JSON}'
  if (-not (Test-Path -LiteralPath $fp)) {{ return $false }}
  return ((Get-Item -LiteralPath $fp).LastWriteTimeUtc -gt $baseline)
}}

function Invoke-GrokPrompt {{
  param(
    [string]$GrokPromptPath,
    [string]$SessionId,
    [string]$TurnLabel
  )
  Set-Status "running:$TurnLabel"
  if ($SessionId -and $SessionId -ne '') {{
    Log-Line "Starting Grok resume turn: $TurnLabel | session: $SessionId" 'Magenta'
  }} else {{
    Log-Line "Starting Grok new turn: $TurnLabel" 'Magenta'
  }}
  Log-Line 'Raw streaming-json is saved to events.jsonl.' 'Magenta'

  # NOTE: -p/--single and --prompt-file are alternative ways to supply the single-turn
  # prompt (confirmed live against grok --help: "-p, --single <PROMPT>" requires an
  # inline value and errors ("a value is required for '--single <PROMPT>'") if combined
  # with --prompt-file). --prompt-file alone triggers headless single-turn mode.
  $argsList = @('--prompt-file',$GrokPromptPath,'--output-format','streaming-json','--cwd',$Cwd,'--permission-mode','bypassPermissions','-m',$Model)
  foreach ($e in $EffortArgs) {{ $argsList += $e }}
  foreach ($e in $ReadOnlyArgs) {{ $argsList += $e }}
  if ($TurnLabel -eq 'initial' -and (-not ($SessionId -and $SessionId -ne ''))) {{ foreach ($e in $InitialExtraArgs) {{ $argsList += $e }} }}
  if ($SessionId -and $SessionId -ne '') {{ $argsList += @('-r',$SessionId) }}

  $script:turnText = New-Object System.Collections.ArrayList
  $script:turnEndSeen = $false
  $script:turnErrorSeen = $false
  $script:turnErrorMessage = ''
  $script:turnSessionId = $SessionId
  $script:thoughtNoted = $false

  Push-Location $Cwd
  $rawStream = $null
  $rawWriter = $null
  try {{
    # Open events.jsonl ONCE per turn with FileShare.ReadWrite + AutoFlush. Grok streams
    # many small JSON lines; a per-line Add-Content reopens the file each time, and those
    # rapid open/close cycles collide with concurrent readers / AV scans on Windows
    # ("The process cannot access the file ... because it is being used by another process").
    # A single shared, auto-flushing writer removes the race while still letting readers tail it.
    try {{ $rawStream = [System.IO.File]::Open($RawLog, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite); $rawWriter = New-Object System.IO.StreamWriter($rawStream, (New-Object System.Text.UTF8Encoding $false)); $rawWriter.AutoFlush = $true }} catch {{ $rawWriter = $null }}
    & $Grok @argsList 2>&1 | ForEach-Object {{
      $line = [string]$_
      if ($null -ne $rawWriter) {{ try {{ $rawWriter.WriteLine($line) }} catch {{}} }}
      else {{ try {{ Add-Content -LiteralPath $RawLog -Encoding UTF8 -Value $line -ErrorAction Stop }} catch {{}} }}
      $obj = $null
      try {{ $obj = $line | ConvertFrom-Json -ErrorAction Stop }} catch {{ $obj = $null }}
      if ($null -eq $obj) {{
        Log-Line $line 'Gray'
        return
      }}
      switch ($obj.type) {{
        'thought' {{
          if (-not $script:thoughtNoted) {{
            Log-Line 'Model is reasoning (hidden reasoning tokens are not shown; the coherent answer block follows when the turn ends).' 'DarkGray'
            $script:thoughtNoted = $true
          }}
        }}
        'text' {{
          if ($obj.data) {{
            [void]$script:turnText.Add([string]$obj.data)
            Write-Host ([string]$obj.data) -NoNewline
          }}
        }}
        'end' {{
          $script:turnEndSeen = $true
          if ($obj.sessionId) {{
            $script:turnSessionId = [string]$obj.sessionId
            $obj.sessionId | Set-Content -LiteralPath $SessionPath -Encoding UTF8
          }}
          Log-Line "Turn ended: stopReason=$($obj.stopReason) sessionId=$($obj.sessionId)" 'Green'
        }}
        'error' {{
          $script:turnErrorSeen = $true
          $script:turnErrorMessage = [string]$obj.message
          Set-Status "failed:$($obj.message)"
          Log-Line "Error: $($obj.message)" 'Red'
        }}
        default {{
          Log-Line "Event: $($obj.type)" 'DarkYellow'
        }}
      }}
    }}
  }} finally {{
    if ($null -ne $rawWriter) {{ try {{ $rawWriter.Flush(); $rawWriter.Dispose() }} catch {{}} }}
    if ($null -ne $rawStream) {{ try {{ $rawStream.Dispose() }} catch {{}} }}
    Pop-Location
  }}

  $code = $LASTEXITCODE
  $answer = ($script:turnText -join '').Trim()
  if ($answer.Length -gt 0) {{
    Write-Host ''
    Write-AppendShared $DisplayLog ("`n===== Grok answer ($TurnLabel) =====`n" + $answer + "`n===== end Grok answer =====`n")
  }}
  if ($code -eq 0 -and $script:turnErrorSeen) {{ $code = 1 }}
  Log-Line "Grok turn '$TurnLabel' exited with code $code" $(if ($code -eq 0) {{ 'Green' }} else {{ 'Red' }})
  Stop-GrokRunDescendants -RootPid $PID
  return $code
}}

{_PS_GROK_CLEANUP_FN}
Clear-Host
New-Item -ItemType Directory -Force -Path $SteerQueue | Out-Null
New-Item -ItemType Directory -Force -Path $SteerDone | Out-Null
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Model: $Model | Effort args: $($EffortArgs -join ' ') (empty means omitted -> inherits Grok config default xhigh)" 'Cyan'
if ($ResumeSessionId -and $ResumeSessionId -ne '') {{ Log-Line "Resuming Grok session: $ResumeSessionId" 'Cyan' }}
$GrokPromptPath = $PromptPath
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
    Write-AppendShared $ComposerRawLog $line
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
    Log-Line "Haiku prompt composer exited with code $composerExitCode; falling back to the raw captain brief." 'Yellow'
    $resultText = ''
  }}
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $resultText = (($assistantChunks | ForEach-Object {{ [string]$_ }}) -join "`n")
  }}
  if ([string]::IsNullOrWhiteSpace($resultText) -and $composerExitCode -eq 0) {{
    Log-Line 'Haiku prompt composer produced an empty Grok prompt; falling back to the raw captain brief.' 'Yellow'
  }}
  $prelude = ''
  if (Test-Path -LiteralPath $GrokPreludePath) {{ $prelude = Get-Content -LiteralPath $GrokPreludePath -Raw }}
  $briefHeading = "`n`n## Haiku-Composed Worker Brief`n`n"
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $briefHeading = "`n`n## Captain Brief (raw; Haiku composer unavailable)`n`n"
    $resultText = Get-Content -LiteralPath $PromptPath -Raw
  }}
  $finalPrompt = ($prelude.TrimEnd() + $briefHeading + $resultText.Trim())
  $finalPrompt | Set-Content -LiteralPath $ComposedPromptPath -Encoding UTF8
  $GrokPromptPath = $ComposedPromptPath
  Log-Line 'Composed Grok prompt follows:' 'Magenta'
  Get-Content -LiteralPath $GrokPromptPath -Raw | Write-Raw
}} else {{
  Log-Line 'Prompt follows:' 'Magenta'
  Get-Content -LiteralPath $PromptPath -Raw | Write-Raw
}}

$reportBaseline = Get-ReportBaseline
$exitCode = Invoke-GrokPrompt -GrokPromptPath $GrokPromptPath -SessionId $ResumeSessionId -TurnLabel 'initial'
$finalText = ($script:turnText -join '')
$finalSessionId = $script:turnSessionId

if ($exitCode -eq 0) {{
  if ([string]::IsNullOrWhiteSpace($finalText)) {{
    $finalText = '(grok worker completed the turn with no text answer; see events.jsonl for detail)'
  }}
  if (-not (Test-WorkerReportSince $reportBaseline)) {{ Write-AutoCaptainReport -Outcome 'completed' -SummaryText $finalText -SessionId $finalSessionId }}
}} else {{
  $errText = if ($script:turnErrorMessage) {{ $script:turnErrorMessage }} elseif ($finalText) {{ $finalText }} else {{ '(grok turn failed before producing a text answer; see events.jsonl for detail)' }}
  if (-not (Test-WorkerReportSince $reportBaseline)) {{ Write-AutoCaptainReport -Outcome 'failed' -SummaryText $errText -SessionId $finalSessionId }}
}}

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

  if (-not $finalSessionId -or $finalSessionId -eq '') {{
    Set-Status 'failed:steer-no-session'
    Log-Line "Cannot apply steering because no Grok session id has been recorded yet: $($steerFile.FullName)" 'Red'
    $exitCode = 1
    break
  }}

  Log-Line "Applying queued Claude steering: $($steerFile.Name)" 'Magenta'
  Get-Content -LiteralPath $steerFile.FullName -Raw | Write-Raw
  $reportBaseline = Get-ReportBaseline
  $exitCode = Invoke-GrokPrompt -GrokPromptPath $steerFile.FullName -SessionId $finalSessionId -TurnLabel "steer:$($steerFile.BaseName)"
  $finalText = ($script:turnText -join '')
  $finalSessionId = $script:turnSessionId
  if ($exitCode -eq 0) {{
    if ([string]::IsNullOrWhiteSpace($finalText)) {{
      $finalText = '(grok worker completed the turn with no text answer; see events.jsonl for detail)'
    }}
    if (-not (Test-WorkerReportSince $reportBaseline)) {{ Write-AutoCaptainReport -Outcome 'completed' -SummaryText $finalText -SessionId $finalSessionId }}
  }} else {{
    $errText = if ($script:turnErrorMessage) {{ $script:turnErrorMessage }} elseif ($finalText) {{ $finalText }} else {{ '(grok turn failed before producing a text answer; see events.jsonl for detail)' }}
    if (-not (Test-WorkerReportSince $reportBaseline)) {{ Write-AutoCaptainReport -Outcome 'failed' -SummaryText $errText -SessionId $finalSessionId }}
  }}
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
Stop-GrokRunDescendants -RootPid $PID
Log-Line 'Grok agent for this run has been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
Start-Sleep -Seconds 5
exit
"""


@mcp.tool()
def start_visible_grok_worker(
    prompt: str,
    cwd: str,
    title: str = "Grok worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "",
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = GROK_STEER_IDLE_SECONDS,
    best_of_n: int = 1,
    self_check: bool = False,
    competition_agents: int = 16,
) -> dict[str, Any]:
    """Launch a visible Grok (grok-4.6) exec worker in a separate PowerShell window and save logs.

    sandbox="read-only" strictly enforces no-edit by stripping Grok's Write/Edit
    tools (Bash kept for inspection). best_of_n>1 runs the initial task N ways in
    parallel and keeps the best (SuperGrok Heavy lever; ~Nx tokens; capped 6).
    self_check=True appends Grok's self-verification loop to the initial turn.
    competition_agents (2-16, default 16) enables Parallel Competition Mode: the
    prompt lets the worker spawn up to that many diverse subagents competing on hard
    problems inside its single turn (one terminal), then compile the best; set 1 to disable."""
    effort_flag = _grok_effort_flag(reasoning_effort)
    effective_reasoning = effort_flag[1] if effort_flag else "inherited-config-default-xhigh"
    auto_full_tool_access = _needs_full_tool_access("\n".join([title, prompt, session_context]))
    effective_sandbox = CODEX_FULL_TOOL_SANDBOX
    prompt_with_permissions = "\n\n".join([
        _codex_permission_contract(sandbox, effective_sandbox),
        prompt,
    ])
    if compose_with_haiku:
        effective_prompt = prompt.strip()
    else:
        effective_prompt = _with_session_context_bootstrap(prompt_with_permissions, cwd, "Grok worker", session_context)
    run_dir = _make_run(cwd, "grok-resume" if resume_session_id else "grok", title, effective_prompt, {
        "agent": "grok",
        "cwd": str(Path(cwd).resolve()),
        "sandbox": effective_sandbox,
        "requested_sandbox": sandbox,
        "model": GROK_MODEL,
        "requested_reasoning_effort": reasoning_effort,
        "effective_reasoning_effort": effective_reasoning,
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
        "captain_report_auto_write": True,
        "read_only_enforced": bool(_grok_read_only_args(sandbox)),
        "best_of_n": max(1, min(int(best_of_n or 1), 6)),
        "self_check": bool(self_check),
        "competition_agents": max(1, min(int(competition_agents or 1), 16)),
    })
    competition_note = _grok_competition_contract(competition_agents) if int(competition_agents or 1) >= 2 else ""
    if not compose_with_haiku:
        _parts = [_grok_rigor_contract()]
        if competition_note:
            _parts.append(competition_note)
        _parts.append(_grok_work_checker_contract())
        _parts += [_grok_captain_report_note(run_dir), _captain_help_contract(run_dir), effective_prompt]
        effective_prompt = "\n\n".join(_parts)
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
            effective_reasoning if effective_reasoning in CODEX_REASONING_EFFORTS else CODEX_REASONING_EFFORT,
        )
        (run_dir / "composer_prompt.md").write_text(composer_prompt, encoding="utf-8")
        _prelude_parts = [_grok_rigor_contract()]
        if competition_note:
            _prelude_parts.append(competition_note)
        _prelude_parts.append(_grok_work_checker_contract())
        _prelude_parts += [
            _grok_captain_report_note(run_dir),
            _captain_help_contract(run_dir),
            _codex_permission_contract(sandbox, effective_sandbox),
        ]
        grok_prelude = _with_session_context_bootstrap(
            "\n\n".join(_prelude_parts),
            cwd,
            "Grok worker",
            session_context,
        )
        (run_dir / "grok_prelude.md").write_text(grok_prelude, encoding="utf-8")
    script = run_dir / "run.ps1"
    script.write_text(
        _grok_runner(
            run_dir,
            str(Path(cwd).resolve()),
            reasoning_effort,
            resume_session_id,
            compose_with_haiku,
            composer_model,
            composer_effort,
            composer_max_budget_usd,
            steer_idle_seconds,
            sandbox=sandbox,
            best_of_n=best_of_n,
            self_check=self_check,
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
        "captain_reports": str(run_dir / CAPTAIN_REPORTS_DIR),
        "session_id_file": str(run_dir / "session_id.txt"),
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": (
            f"A visible PowerShell window was launched. Grok runs {GROK_MODEL} at requested "
            f"reasoning '{reasoning_effort or 'unset'}' (effective: {effective_reasoning}; the CLI "
            "flag only accepts low/medium/high, so it is omitted for xhigh/max/empty and Grok's "
            "config default (xhigh) applies). Effective sandbox is "
            f"{effective_sandbox} (permission intent conveyed via the prompt contract, matching the "
            f"Codex path). Haiku prompt composer enabled={compose_with_haiku}. The runner "
            "auto-writes captain_reports/final.json+final.md from Grok's answer text after every "
            "turn, independent of whether the live agent-visibility MCP callback is reachable."
        ),
    }


@mcp.tool()
def start_visible_haiku_composed_grok_worker(
    prompt_brief: str,
    cwd: str,
    title: str = "Grok worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "",
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = GROK_STEER_IDLE_SECONDS,
    best_of_n: int = 1,
    self_check: bool = False,
    competition_agents: int = 16,
) -> dict[str, Any]:
    """Launch a visible Grok worker from a compact Claude brief expanded by Claude Haiku."""
    return start_visible_grok_worker(
        prompt=prompt_brief,
        cwd=cwd,
        title=title,
        sandbox=sandbox,
        reasoning_effort=reasoning_effort,
        session_context=session_context,
        resume_session_id=resume_session_id,
        requires_tool_access=requires_tool_access,
        compose_with_haiku=True,
        composer_model=CLAUDE_PROMPT_COMPOSER_MODEL,
        composer_effort=CLAUDE_PROMPT_COMPOSER_EFFORT,
        composer_max_budget_usd=composer_max_budget_usd,
        steer_idle_seconds=steer_idle_seconds,
        best_of_n=best_of_n,
        self_check=self_check,
        competition_agents=competition_agents,
    )


@mcp.tool()
def start_visible_first_mate_grok_pool(
    goal: str,
    cwd: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    max_workers: int = 6,
    session_context: str = "",
    requires_tool_access: bool = False,
    reasoning_effort: str = "",
) -> dict[str, Any]:
    """Launch a visible Grok root session with native subagents enabled to act as first mate.

    Unlike the Codex first-mate pool (which fans out to separate Codex CLI
    subagent processes), this launches a single grok-4.6 process with its
    native subagent capability left enabled (no --no-subagents flag), so Grok
    itself manages any internal fan-out.
    """
    prompt, auto_full_tool_access = _first_mate_prompt(
        goal=goal,
        scout_areas=scout_areas,
        implementation_items=implementation_items,
        sandbox=sandbox,
        max_workers=max_workers,
        session_context=session_context,
        requires_tool_access=requires_tool_access,
    )
    return start_visible_grok_worker(
        prompt=prompt,
        cwd=cwd,
        title="Grok first mate pool",
        sandbox=sandbox,
        reasoning_effort=reasoning_effort,
        session_context=session_context,
        requires_tool_access=requires_tool_access or auto_full_tool_access,
    )


@mcp.tool()
def steer_visible_grok_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = True,
    requires_tool_access: bool = False,
) -> dict[str, Any]:
    """Send a Claude steering instruction to a visible Grok run, resuming the same Grok session if needed.

    Mirrors steer_visible_codex_run. An idle worker (in its steering window)
    consumes the queued instruction within a second. An active worker is
    interrupted best-effort via the same Ctrl+C/taskkill path used for Codex
    when a launcher pid is known, then a Grok resume run (`grok -r
    <sessionId>`) is launched with the instruction. Grok has no on-disk
    equivalent of Codex's session-readiness probe, so after an interrupt this
    always launches the resume run directly on the last recorded session id
    rather than polling for session-file readiness first; queued-at-idle
    delivery is the primary, most reliable path for v1.
    """
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    status = _read_json(path / "status.json", {"status": "unknown"})
    status_name = _status_name(status)
    if metadata.get("agent") not in (None, "grok"):
        return {"ok": False, "error": f"run_dir is not a Grok visible run: {path}", "metadata": metadata}

    requested_sandbox = sandbox.strip()
    permission_contract = (
        _codex_permission_contract(requested_sandbox, CODEX_FULL_TOOL_SANDBOX)
        if requested_sandbox
        else ""
    )
    steer_path = _write_steer_file(path, instruction, session_context, title, permission_contract)
    session_id = _visible_run_session_id(path, metadata) or ""
    active = status_name == "created" or status_name == "waiting_for_steer" or status_name.startswith("running")
    result: dict[str, Any] = {
        "ok": True,
        "mode": "queued",
        "run_dir": str(path),
        "status": status,
        "session_id": session_id or None,
        "steer_file": str(steer_path),
        "note": "Steering was queued. The visible Grok window will consume it after the current turn, or during its steering idle window.",
    }

    idle = status_name in ("created", "waiting_for_steer")
    if active and (not interrupt_current_turn or idle):
        if status_name == "waiting_for_steer":
            result["note"] = (
                "Steering was queued for immediate pickup: the worker is idle in its "
                "steering window and polls the queue every second."
            )
        return result

    resume_session_id = session_id
    resume_mode = "launched_resume"
    resume_note = "The previous visible Grok run was not available for in-window steering, so a visible Grok resume run was launched on the same session id."

    if interrupt_current_turn and active:
        if not session_id:
            result["mode"] = "queued_no_interrupt_no_thread"
            result["note"] = "Steering was queued, but the current turn was not interrupted because no Grok session id is available yet."
            return result
        pid_path = path / "launcher_pid.txt"
        if not pid_path.exists():
            result["mode"] = "queued_no_interrupt_no_pid"
            result["note"] = "Steering was queued, but the current turn was not interrupted because the launcher pid is unavailable."
            return result
        try:
            pid = pid_path.read_text(encoding="utf-8-sig").strip()
            interrupted, interrupt_warning = _interrupt_visible_run(pid)
            if not interrupted:
                result["mode"] = "queued_interrupt_failed"
                if interrupt_warning:
                    result["interrupt_warning"] = interrupt_warning
                result["note"] = "Steering was queued, but the active visible Grok run could not be interrupted cleanly."
                return result
            result["interrupted_pid"] = pid
            if interrupt_warning:
                result["interrupt_warning"] = interrupt_warning
        except Exception as exc:
            result["mode"] = "queued_interrupt_failed"
            result["interrupt_warning"] = str(exc)
            result["note"] = "Steering was queued, but the active visible Grok run could not be interrupted cleanly."
            return result

    if not launch_if_closed and "interrupted_pid" not in result:
        result["mode"] = "queued_no_active_runner"
        result["note"] = "Steering was queued, but the visible Grok run is not active and launch_if_closed is false."
        return result

    if not session_id:
        result["mode"] = "queued_no_resume_thread"
        result["note"] = "Steering was queued, but no Grok session id is available to launch a resume run."
        return result

    cwd = _infer_cwd_from_run_dir(path, metadata)
    steer_prompt = steer_path.read_text(encoding="utf-8")
    resume_context = "\n\n".join(
        part for part in [
            f"Previous visible run: {path}",
            f"Previous status: {status_name}",
            f"Previous Grok session id: {session_id}",
            session_context.strip(),
        ] if part
    )
    followup = start_visible_grok_worker(
        prompt=steer_prompt,
        cwd=cwd,
        title=title,
        sandbox=requested_sandbox or metadata.get("requested_sandbox") or "read-only",
        reasoning_effort=metadata.get("requested_reasoning_effort") or "",
        session_context=resume_context,
        resume_session_id=resume_session_id,
        requires_tool_access=bool(requires_tool_access or metadata.get("requires_tool_access") or metadata.get("auto_full_tool_access")),
        compose_with_haiku=False,
        steer_idle_seconds=int(metadata.get("steer_idle_seconds") or GROK_STEER_IDLE_SECONDS),
    )
    try:
        done_dir = path / "steer_done"
        done_dir.mkdir(parents=True, exist_ok=True)
        steer_path.replace(done_dir / steer_path.name)
    except Exception:
        pass
    result["mode"] = resume_mode
    result["followup_run"] = followup
    result["note"] = resume_note
    return result


# --- Antigravity (agy / Gemini) worker backend (added 2026-07-14) ---
# Adds an Antigravity (agy) visible worker backend alongside the existing
# Codex and Grok backends. Codex and Grok are left completely untouched
# above this line; every symbol below is new. See
# plugin/skills/claude-manages-codex/SKILL.md, section "Antigravity / Gemini
# (agy) Worker Backend (added 2026-07-14)", for the routing doctrine.
#
# agy (Google's Antigravity CLI, Gemini backend) differs from grok/codex in
# ways that shape this whole section:
#   1. PLAIN TEXT stdout. There is no --output-format json/streaming flag, so
#      the runner cannot parse structured "text"/"end"/"error" events the way
#      the grok and codex runners do. It captures raw stdout/stderr as-is.
#   2. Effort is baked into the --model name, not a separate flag (no
#      --reasoning-effort). AGY_MODELS_BY_EFFORT below is the mapping.
#   3. agy never prints a session id, but `agy --help` does expose
#      `--conversation <id>` (resume a specific conversation) alongside
#      `--continue`/`-c` (resume the MOST RECENT conversation for the
#      current working directory). Because no id is ever surfaced in stdout
#      to capture, this backend only uses the cwd-scoped `--continue` form;
#      `--conversation <id>` is unusable without a way to learn `<id>`.
#      steer_visible_agy_run therefore never tracks a session id at all -- it
#      only needs to invoke agy again in the same cwd with `--continue`,
#      which is a best-effort "most recent conversation" resume, not a
#      thread-specific one.
#   4. No live MCP callback is wired for agy (checked live on this machine):
#      `agy --help` exposes no `mcp` subcommand, and the only MCP-shaped file
#      found, ~/.gemini/config/mcp_config.json, is 0 bytes with no schema
#      documented anywhere reachable -- editing it blindly would risk the
#      owner's real authenticated agy config for an unverified guess. Layer 1
#      (the runner's own auto-report to captain_reports/final.json+final.md)
#      is therefore the ONLY result-callback path for agy; see SKILL.md.

AGY_MODELS_BY_EFFORT = {
    "high": "Gemini 3.7 Flash (High)",
    "medium": "Gemini 3.7 Flash (Medium)",
    "low": "Gemini 3.7 Flash (Low)",
}
AGY_DEFAULT_MODEL = "Gemini 3.7 Flash (High)"
AGY_STEER_IDLE_SECONDS = CODEX_STEER_IDLE_SECONDS


def _agy_model_for_effort(effort: str) -> str:
    """Return the agy --model name for a requested reasoning effort.

    agy has no --reasoning-effort flag; effort is encoded in the model name
    itself (see AGY_MODELS_BY_EFFORT). Any value that is not exactly
    low/medium/high (case-insensitive) falls back to AGY_DEFAULT_MODEL (the
    "high" model), matching the owner's stated default.
    """
    candidate = (effort or "").strip().lower()
    return AGY_MODELS_BY_EFFORT.get(candidate, AGY_DEFAULT_MODEL)


def _agy_captain_report_note(run_dir: Path) -> str:
    return textwrap.dedent(f"""
    # Captain Report (Antigravity / agy)

    Run directory: {run_dir}

    This run's launcher automatically writes a captain report to
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON}` and
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_MD}` from your raw
    stdout once this turn ends, so Claude can read your result with
    `get_visible_run_status` or `list_captain_reports` even if you never call
    a tool. agy has no live agent-visibility MCP callback wired yet (see
    SKILL.md), so this automatic report is the ONLY way your result reaches
    Claude. Print your real answer to stdout; do not assume any tool call
    will be seen.
    """).strip()


# PowerShell descendant-reaper scoped to agy's own process tree, mirroring
# _PS_GROK_CLEANUP_FN's shape but targeting agy's process name. agy.exe is a
# standalone executable (not an npm/node CLI shim like codex/grok's), but
# 'node' is kept in the target list defensively in case internal tooling it
# shells out to spawns one.
_PS_AGY_CLEANUP_FN = r"""
function Stop-AgyRunDescendants {
  param([int]$RootPid)
  $targets = @('agy','node')
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
  Log-Line "Reaped $killed leftover Antigravity (agy) process(es) for this run." 'DarkGray'
}
"""


def _agy_runner(
    run_dir: Path,
    cwd: str,
    model: str,
    initial_continue: bool = False,
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = AGY_STEER_IDLE_SECONDS,
) -> str:
    return f"""
$ErrorActionPreference = 'Continue'
$RunDir = {_ps(run_dir)}
$PromptPath = Join-Path $RunDir 'prompt.md'
$ComposerPromptPath = Join-Path $RunDir 'composer_prompt.md'
$ComposerRawLog = Join-Path $RunDir 'composer_events.jsonl'
$ComposedPromptPath = Join-Path $RunDir 'composed_prompt.md'
$AgyPreludePath = Join-Path $RunDir 'agy_prelude.md'
$OutputPath = Join-Path $RunDir 'output.txt'
$DisplayLog = Join-Path $RunDir 'display.log'
$StatusPath = Join-Path $RunDir 'status.json'
$SteerQueue = Join-Path $RunDir 'steer_queue'
$SteerDone = Join-Path $RunDir 'steer_done'
$ReportsDir = Join-Path $RunDir '{CAPTAIN_REPORTS_DIR}'
$Agy = {_ps(AGY)}
$Claude = {_ps(CLAUDE)}
$Cwd = {_ps(cwd)}
$Model = {_ps(model)}
$InitialContinue = {"$true" if initial_continue else "$false"}
$ComposeWithHaiku = {"$true" if compose_with_haiku else "$false"}
$ComposerModel = {_ps(composer_model)}
$ComposerEffort = {_ps(composer_effort)}
$ComposerMaxBudgetUsd = {_ps(composer_max_budget_usd)}
$SteerIdleSeconds = {max(0, min(int(steer_idle_seconds), 300))}
# Force UTF-8 so agy's UTF-8 stdout/stdin is decoded correctly (mirrors the Codex/Grok runners).
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
$Host.UI.RawUI.WindowTitle = "Antigravity (agy) visible worker - $(Split-Path $RunDir -Leaf)"

# UTF-8 tee helper (Tee-Object writes UTF-16LE in PowerShell 5.1, corrupting display.log).
function Write-AppendShared([string]$Path, [string]$Text) {{
  for ($i = 0; $i -lt 25; $i++) {{
    try {{
      $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
      try {{ $sw = New-Object System.IO.StreamWriter($fs, (New-Object System.Text.UTF8Encoding $false)); $sw.WriteLine($Text); $sw.Flush(); $sw.Dispose() }} finally {{ $fs.Dispose() }}
      return
    }} catch {{ Start-Sleep -Milliseconds 15 }}
  }}
}}

function Write-Raw {{
  param([Parameter(ValueFromPipeline=$true)] $InputObject)
  process {{
    $text = [string]$InputObject
    Write-Host $text
    Write-AppendShared $DisplayLog $text
  }}
}}

function Set-Status([string]$Status) {{
  $json = @{{ status=$Status; updated_at=(Get-Date).ToString('o'); run_dir=$RunDir }} | ConvertTo-Json
  $tmp = $StatusPath + '.tmp'
  foreach ($attempt in 1..5) {{
    try {{
      Set-Content -LiteralPath $tmp -Value $json -Encoding UTF8 -ErrorAction Stop
      Move-Item -LiteralPath $tmp -Destination $StatusPath -Force -ErrorAction Stop
      return
    }} catch {{
      Start-Sleep -Milliseconds 200
    }}
  }}
  Log-Line "Set-Status failed after 5 attempts: $Status"
}}

function Log-Line([string]$Text, [string]$Color = 'Gray') {{
  $stamp = Get-Date -Format 'HH:mm:ss'
  $line = "[$stamp] $Text"
  Write-AppendShared $DisplayLog $line
  Write-Host $line -ForegroundColor $Color
}}

function Get-NextSteerFile {{
  if (-not (Test-Path -LiteralPath $SteerQueue)) {{ return $null }}
  $next = Get-ChildItem -LiteralPath $SteerQueue -Filter '*.md' -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
  return $next
}}

function Write-AutoCaptainReport([string]$Outcome, [string]$Text) {{
  $reportId = "$(Split-Path $RunDir -Leaf)-auto"
  $now = (Get-Date).ToString('o')
  $record = [ordered]@{{
    report_id = $reportId
    status = 'submitted'
    outcome = $Outcome
    created_at = $now
    updated_at = $now
    run_dir = $RunDir
    thread_id = $null
    session_id = $null
    summary = $Text
    text = $Text
    model = $Model
    changed_files = @()
    verification = @()
    risks = @()
    questions = @()
    close_tui = $true
    auto_generated = $true
    agent = 'agy'
  }}
  New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
  $json = $record | ConvertTo-Json -Depth 6
  Set-Content -LiteralPath (Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_JSON}') -Value $json -Encoding UTF8
  $md = "# Captain Report`n`nReport ID: $reportId`nOutcome: $Outcome`nModel: $Model`nCreated: $now`nRun directory: $RunDir`nClose TUI: True`n`n## Summary (full agy stdout for this turn)`n`n$Text`n`n## Changed Files`n`n- none`n`n## Verification`n`n- none`n`n## Risks`n`n- none`n`n## Questions`n`n- none"
  Set-Content -LiteralPath (Join-Path $ReportsDir '{CAPTAIN_REPORT_FINAL_MD}') -Value $md -Encoding UTF8
}}

function Invoke-AgyPrompt {{
  param(
    [string]$PromptText,
    [bool]$Continue,
    [string]$TurnLabel
  )
  Set-Status "running:$TurnLabel"
  if ($Continue) {{
    Log-Line "Starting Antigravity resume turn (--continue, cwd-scoped, no session id): $TurnLabel" 'Magenta'
  }} else {{
    Log-Line "Starting Antigravity new turn: $TurnLabel" 'Magenta'
  }}
  Log-Line 'agy has no streaming JSON; its full stdout for this turn is captured once the process exits and appended to output.txt.' 'Magenta'

  $argsList = @('-p',$PromptText,'--model',$Model,'--dangerously-skip-permissions','--add-dir',$Cwd)
  if ($Continue) {{ $argsList = @('-p',$PromptText,'--continue','--model',$Model,'--dangerously-skip-permissions','--add-dir',$Cwd) }}

  $stdoutTmp = Join-Path $RunDir 'turn_stdout.tmp'
  $stderrTmp = Join-Path $RunDir 'turn_stderr.tmp'

  Push-Location $Cwd
  try {{
    & $Agy @argsList 1> $stdoutTmp 2> $stderrTmp
  }} finally {{
    Pop-Location
  }}
  $code = $LASTEXITCODE

  $script:turnText = ''
  if (Test-Path -LiteralPath $stdoutTmp) {{
    $out = Get-Content -LiteralPath $stdoutTmp -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($out) {{ $script:turnText = $out }}
  }}
  if ($script:turnText) {{
    Write-AppendShared $OutputPath $script:turnText
    $script:turnText | Write-Raw
  }}

  $errText = ''
  if (Test-Path -LiteralPath $stderrTmp) {{
    $errOut = Get-Content -LiteralPath $stderrTmp -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($errOut) {{ $errText = $errOut }}
  }}
  if ($errText) {{
    Log-Line 'stderr (display.log only; not appended to output.txt/captain report):' 'DarkYellow'
    $errText | Write-Raw
  }}
  try {{ Remove-Item -LiteralPath $stdoutTmp -Force -ErrorAction SilentlyContinue }} catch {{}}
  try {{ Remove-Item -LiteralPath $stderrTmp -Force -ErrorAction SilentlyContinue }} catch {{}}

  Log-Line "Antigravity turn '$TurnLabel' exited with code $code" $(if ($code -eq 0) {{ 'Green' }} else {{ 'Red' }})
  Stop-AgyRunDescendants -RootPid $PID
  return $code
}}

{_PS_AGY_CLEANUP_FN}
Clear-Host
New-Item -ItemType Directory -Force -Path $SteerQueue | Out-Null
New-Item -ItemType Directory -Force -Path $SteerDone | Out-Null
Set-Status 'running'
Log-Line "Run directory: $RunDir" 'Cyan'
Log-Line "CWD: $Cwd" 'Cyan'
Log-Line "Model: $Model (effort is baked into the model name; agy has no separate reasoning-effort CLI flag)" 'Cyan'
Log-Line 'agy never emits a session id. Steering/resume uses --continue, which resumes the MOST RECENT conversation for this cwd (best-effort, not a specific thread).' 'Cyan'

$PromptText = ''
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
    Write-AppendShared $ComposerRawLog $line
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
    Log-Line "Haiku prompt composer exited with code $composerExitCode; falling back to the raw captain brief." 'Yellow'
    $resultText = ''
  }}
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $resultText = (($assistantChunks | ForEach-Object {{ [string]$_ }}) -join "`n")
  }}
  if ([string]::IsNullOrWhiteSpace($resultText) -and $composerExitCode -eq 0) {{
    Log-Line 'Haiku prompt composer produced an empty Antigravity prompt; falling back to the raw captain brief.' 'Yellow'
  }}
  $prelude = ''
  if (Test-Path -LiteralPath $AgyPreludePath) {{ $prelude = Get-Content -LiteralPath $AgyPreludePath -Raw }}
  $briefHeading = "`n`n## Haiku-Composed Worker Brief`n`n"
  if ([string]::IsNullOrWhiteSpace($resultText)) {{
    $briefHeading = "`n`n## Captain Brief (raw; Haiku composer unavailable)`n`n"
    $resultText = Get-Content -LiteralPath $PromptPath -Raw
  }}
  $finalPrompt = ($prelude.TrimEnd() + $briefHeading + $resultText.Trim())
  $finalPrompt | Set-Content -LiteralPath $ComposedPromptPath -Encoding UTF8
  $PromptText = $finalPrompt
  Log-Line 'Composed Antigravity prompt follows:' 'Magenta'
  $PromptText | Write-Raw
}} else {{
  Log-Line 'Prompt follows:' 'Magenta'
  $PromptText = Get-Content -LiteralPath $PromptPath -Raw
  $PromptText | Write-Raw
}}

$exitCode = Invoke-AgyPrompt -PromptText $PromptText -Continue $InitialContinue -TurnLabel 'initial'
if ($exitCode -eq 0) {{
  $reportText = $(if ([string]::IsNullOrWhiteSpace($script:turnText)) {{ '(agy worker completed the turn with no stdout text; see output.txt for detail)' }} else {{ $script:turnText }})
  Write-AutoCaptainReport -Outcome 'completed' -Text $reportText
}} else {{
  $reportText = $(if ([string]::IsNullOrWhiteSpace($script:turnText)) {{ '(agy turn failed before producing stdout text; see output.txt/display.log for detail)' }} else {{ $script:turnText }})
  Write-AutoCaptainReport -Outcome 'failed' -Text $reportText
}}

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

  Log-Line "Applying queued Claude steering: $($steerFile.Name)" 'Magenta'
  $steerText = Get-Content -LiteralPath $steerFile.FullName -Raw
  $steerText | Write-Raw
  $exitCode = Invoke-AgyPrompt -PromptText $steerText -Continue $true -TurnLabel "steer:$($steerFile.BaseName)"
  if ($exitCode -eq 0) {{
    $reportText = $(if ([string]::IsNullOrWhiteSpace($script:turnText)) {{ '(agy worker completed the turn with no stdout text; see output.txt for detail)' }} else {{ $script:turnText }})
    Write-AutoCaptainReport -Outcome 'completed' -Text $reportText
  }} else {{
    $reportText = $(if ([string]::IsNullOrWhiteSpace($script:turnText)) {{ '(agy turn failed before producing stdout text; see output.txt/display.log for detail)' }} else {{ $script:turnText }})
    Write-AutoCaptainReport -Outcome 'failed' -Text $reportText
  }}
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
Stop-AgyRunDescendants -RootPid $PID
Log-Line 'Antigravity (agy) agent for this run has been closed. This window will close in 5 seconds; logs remain in the run directory.' 'Magenta'
Start-Sleep -Seconds 5
exit
"""


@mcp.tool()
def start_visible_agy_worker(
    prompt: str,
    cwd: str,
    title: str = "Antigravity worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "high",
    session_context: str = "",
    requires_tool_access: bool = False,
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = AGY_STEER_IDLE_SECONDS,
    resume_continue: bool = False,
) -> dict[str, Any]:
    """Launch a visible Antigravity (agy / Gemini) exec worker in a separate PowerShell window and save logs.

    agy is PLAIN TEXT (no JSON/streaming), has no --reasoning-effort flag
    (effort is baked into --model via AGY_MODELS_BY_EFFORT), and never emits
    a session id. `resume_continue` is an internal knob used by
    steer_visible_agy_run to launch a follow-up run whose FIRST turn is
    itself an `agy --continue` call (cwd-scoped resume of the most recent
    agy conversation); direct callers should normally leave it False.
    """
    effort_key = (reasoning_effort or "").strip().lower()
    if effort_key not in AGY_MODELS_BY_EFFORT:
        effort_key = "high"
    model = AGY_MODELS_BY_EFFORT[effort_key]
    auto_full_tool_access = _needs_full_tool_access("\n".join([title, prompt, session_context]))
    effective_sandbox = CODEX_FULL_TOOL_SANDBOX
    prompt_with_permissions = "\n\n".join([
        _codex_permission_contract(sandbox, effective_sandbox),
        prompt,
    ])
    if compose_with_haiku:
        effective_prompt = prompt.strip()
    else:
        effective_prompt = _with_session_context_bootstrap(prompt_with_permissions, cwd, "Antigravity worker", session_context)
    run_dir = _make_run(cwd, "agy", title, effective_prompt, {
        "agent": "agy",
        "cwd": str(Path(cwd).resolve()),
        "sandbox": effective_sandbox,
        "requested_sandbox": sandbox,
        "model": model,
        "requested_reasoning_effort": reasoning_effort,
        "effective_reasoning_effort": effort_key,
        "resume_continue": resume_continue,
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
        "captain_help_enabled": False,
        "captain_report_auto_write": True,
        "no_session_id": True,
        "resume_mechanism": "--continue (cwd-scoped, most-recent-conversation; agy has no session id to resume by thread)",
    })
    if not compose_with_haiku:
        effective_prompt = "\n\n".join([
            _agy_captain_report_note(run_dir),
            effective_prompt,
        ])
        (run_dir / "prompt.md").write_text(effective_prompt, encoding="utf-8")
    if compose_with_haiku:
        composer_prompt = _haiku_codex_prompt_composer_prompt(
            prompt,
            cwd,
            title,
            sandbox,
            session_context,
            "",
            requires_tool_access or auto_full_tool_access,
            effort_key,
        )
        (run_dir / "composer_prompt.md").write_text(composer_prompt, encoding="utf-8")
        agy_prelude = _with_session_context_bootstrap(
            "\n\n".join([
                _agy_captain_report_note(run_dir),
                _codex_permission_contract(sandbox, effective_sandbox),
            ]),
            cwd,
            "Antigravity worker",
            session_context,
        )
        (run_dir / "agy_prelude.md").write_text(agy_prelude, encoding="utf-8")
    script = run_dir / "run.ps1"
    script.write_text(
        _agy_runner(
            run_dir,
            str(Path(cwd).resolve()),
            model,
            resume_continue,
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
        "output": str(run_dir / "output.txt"),
        "status": str(run_dir / "status.json"),
        "steer_queue": str(run_dir / "steer_queue"),
        "captain_reports": str(run_dir / CAPTAIN_REPORTS_DIR),
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": (
            f"A visible PowerShell window was launched. Antigravity runs model '{model}' for "
            f"requested reasoning effort '{reasoning_effort or 'high'}' (effective: '{effort_key}'; "
            "effort is baked into the model name -- agy has no --reasoning-effort flag). Effective "
            f"sandbox is {effective_sandbox} (permission intent conveyed via the prompt contract, "
            f"matching the Codex/Grok path). Haiku prompt composer enabled={compose_with_haiku}. agy "
            "NEVER emits a session id, so resume/steer only works via --continue, which resumes the "
            "MOST RECENT conversation for this cwd -- a best-effort guarantee, not thread-specific. "
            "agy has NO live agent-visibility MCP callback wired (undocumented/empty "
            "~/.gemini/config/mcp_config.json, no `agy mcp` subcommand); the runner's Layer-1 "
            "auto-report to captain_reports/final.json+final.md from agy's raw stdout is the ONLY "
            "result path for this backend."
        ),
    }


@mcp.tool()
def start_visible_haiku_composed_agy_worker(
    prompt_brief: str,
    cwd: str,
    title: str = "Antigravity worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "high",
    session_context: str = "",
    requires_tool_access: bool = False,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = AGY_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible Antigravity worker from a compact Claude brief expanded by Claude Haiku."""
    return start_visible_agy_worker(
        prompt=prompt_brief,
        cwd=cwd,
        title=title,
        sandbox=sandbox,
        reasoning_effort=reasoning_effort,
        session_context=session_context,
        requires_tool_access=requires_tool_access,
        compose_with_haiku=True,
        composer_model=CLAUDE_PROMPT_COMPOSER_MODEL,
        composer_effort=CLAUDE_PROMPT_COMPOSER_EFFORT,
        composer_max_budget_usd=composer_max_budget_usd,
        steer_idle_seconds=steer_idle_seconds,
    )


@mcp.tool()
def steer_visible_agy_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = True,
    requires_tool_access: bool = False,
) -> dict[str, Any]:
    """Send a Claude steering instruction to a visible Antigravity (agy) run.

    agy never emits a session id, so unlike steer_visible_grok_run /
    steer_visible_codex_run this never tracks or resumes a specific
    thread/session id:
    - If the run's PowerShell window is still open and idle in its steering
      window, the instruction is queued to steer_queue and picked up within
      a second, running `agy --continue` in the SAME window/process tree.
    - If the window is closed (or an active turn is interrupted) and
      launch_if_closed is true, a brand-new start_visible_agy_worker run is
      launched with resume_continue=True, so its first turn is itself an
      `agy --continue` call. Because --continue is cwd-scoped (resumes the
      most recent agy conversation for that working directory, not a
      specific run/thread id), this reaches the same underlying agy
      conversation as long as no other agy conversation has started in that
      cwd since -- a best-effort guarantee, not a hard one.
    """
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    status = _read_json(path / "status.json", {"status": "unknown"})
    status_name = _status_name(status)
    if metadata.get("agent") not in (None, "agy"):
        return {"ok": False, "error": f"run_dir is not an Antigravity (agy) visible run: {path}", "metadata": metadata}

    requested_sandbox = sandbox.strip()
    permission_contract = (
        _codex_permission_contract(requested_sandbox, CODEX_FULL_TOOL_SANDBOX)
        if requested_sandbox
        else ""
    )
    steer_path = _write_steer_file(path, instruction, session_context, title, permission_contract)
    result: dict[str, Any] = {
        "ok": True,
        "mode": "queued",
        "run_dir": str(path),
        "status": status,
        "steer_file": str(steer_path),
        "note": (
            "Steering was queued. The visible Antigravity window will consume it after the "
            "current turn (via agy --continue), or during its steering idle window. agy has no "
            "session id, so this is always a cwd-scoped --continue, never a thread-specific resume."
        ),
    }

    active = status_name == "created" or status_name == "waiting_for_steer" or status_name.startswith("running")
    idle = status_name in ("created", "waiting_for_steer")
    if active and (not interrupt_current_turn or idle):
        if status_name == "waiting_for_steer":
            result["note"] = (
                "Steering was queued for immediate pickup: the worker is idle in its "
                "steering window and polls the queue every second."
            )
        return result

    if interrupt_current_turn and active:
        pid_path = path / "launcher_pid.txt"
        if not pid_path.exists():
            result["mode"] = "queued_no_interrupt_no_pid"
            result["note"] = "Steering was queued, but the current turn was not interrupted because the launcher pid is unavailable."
            return result
        try:
            pid = pid_path.read_text(encoding="utf-8-sig").strip()
            interrupted, interrupt_warning = _interrupt_visible_run(pid)
            if not interrupted:
                result["mode"] = "queued_interrupt_failed"
                if interrupt_warning:
                    result["interrupt_warning"] = interrupt_warning
                result["note"] = "Steering was queued, but the active visible Antigravity run could not be interrupted cleanly."
                return result
            result["interrupted_pid"] = pid
            if interrupt_warning:
                result["interrupt_warning"] = interrupt_warning
        except Exception as exc:
            result["mode"] = "queued_interrupt_failed"
            result["interrupt_warning"] = str(exc)
            result["note"] = "Steering was queued, but the active visible Antigravity run could not be interrupted cleanly."
            return result

    if not launch_if_closed and "interrupted_pid" not in result:
        result["mode"] = "queued_no_active_runner"
        result["note"] = "Steering was queued, but the visible Antigravity run is not active and launch_if_closed is false."
        return result

    cwd = _infer_cwd_from_run_dir(path, metadata)
    steer_prompt = steer_path.read_text(encoding="utf-8")
    resume_context = "\n\n".join(
        part for part in [
            f"Previous visible run: {path}",
            f"Previous status: {status_name}",
            "No agy session id is available; this follow-up resumes via --continue (cwd-scoped, most-recent-conversation, best-effort).",
            session_context.strip(),
        ] if part
    )
    followup = start_visible_agy_worker(
        prompt=steer_prompt,
        cwd=cwd,
        title=title,
        sandbox=requested_sandbox or metadata.get("requested_sandbox") or "read-only",
        reasoning_effort=metadata.get("requested_reasoning_effort") or "high",
        session_context=resume_context,
        requires_tool_access=bool(requires_tool_access or metadata.get("requires_tool_access") or metadata.get("auto_full_tool_access")),
        compose_with_haiku=False,
        steer_idle_seconds=int(metadata.get("steer_idle_seconds") or AGY_STEER_IDLE_SECONDS),
        resume_continue=True,
    )
    try:
        done_dir = path / "steer_done"
        done_dir.mkdir(parents=True, exist_ok=True)
        steer_path.replace(done_dir / steer_path.name)
    except Exception:
        pass
    result["mode"] = "launched_resume"
    result["followup_run"] = followup
    result["note"] = (
        "The previous visible Antigravity run was not available for in-window steering, so a "
        "visible Antigravity follow-up run was launched with `agy --continue` (cwd-scoped, "
        "most-recent-conversation resume; best-effort since agy has no session id)."
    )
    return result


# --- Worker backend availability check (added 2026-07-14) ---
# Verifies whether each worker backend is usable before Claude delegates to
# it. claude_sonnet is always available (in-process Agent tool). grok/codex/
# agy are probed via their CLI path + local auth-file state. Codex's local
# JWT can look valid (unexpired `exp` claim, `codex login status` exits 0)
# even after the server has revoked the refresh token, so a false positive
# is possible from the cheap default probe; pass deep=True to additionally
# run one short live `codex exec` round trip that reveals server-side
# revocation (observed live on this machine: HTTP 401 token_invalidated /
# refresh_token_invalidated, despite a locally well-formed, unexpired token).

AGY = Path(r"C:\Users\jonny\AppData\Local\agy\bin\agy.exe")


def _read_json_file(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return None, f"cannot read {path.name}: {exc}"
    try:
        return json.loads(raw), ""
    except Exception as exc:
        return None, f"cannot parse {path.name}: {exc}"


def _decode_jwt_exp(token: str) -> float | None:
    try:
        import base64 as _base64
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(_base64.urlsafe_b64decode(payload))
        exp = data.get("exp") if isinstance(data, dict) else None
        return float(exp) if exp is not None else None
    except Exception:
        return None


def _check_claude_sonnet_backend() -> dict[str, Any]:
    return {
        "available": True,
        "reason": "in-process Agent tool; no external CLI or auth file required",
        "detail": "Claude Sonnet subagents run via the Agent tool inside this Claude Code session.",
    }


def _check_grok_backend(deep: bool = False) -> dict[str, Any]:
    if not GROK.exists():
        return {"available": False, "reason": f"grok CLI not found at {GROK}", "detail": ""}
    auth_path = HOME / ".grok" / "auth.json"
    if not auth_path.exists():
        return {"available": False, "reason": "grok CLI present but ~/.grok/auth.json is missing (not logged in)", "detail": str(auth_path)}
    data, err = _read_json_file(auth_path)
    if data is None:
        return {"available": False, "reason": f"grok auth.json unreadable: {err}", "detail": str(auth_path)}
    entries = [value for value in data.values() if isinstance(value, dict)] if isinstance(data, dict) else []
    if not entries:
        return {"available": False, "reason": "grok auth.json has no credential entries", "detail": str(auth_path)}
    entry = entries[0]
    expires_at_raw = entry.get("expires_at")
    has_refresh = bool(entry.get("refresh_token"))
    expires_future = False
    if isinstance(expires_at_raw, str):
        try:
            expires_dt = _dt.datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
            expires_future = expires_dt > _dt.datetime.now(_dt.timezone.utc)
        except Exception:
            expires_future = False
    if expires_future or has_refresh:
        return {
            "available": True,
            "reason": "grok auth.json present with a non-expired token or a refresh_token",
            "detail": f"expires_at={expires_at_raw}, has_refresh_token={has_refresh}",
        }
    return {
        "available": False,
        "reason": "grok auth.json present but the token is expired and no refresh_token is stored",
        "detail": f"expires_at={expires_at_raw}",
    }


def _check_codex_backend(deep: bool = False, cwd: str | None = None) -> dict[str, Any]:
    if not CODEX.exists():
        return {"available": False, "reason": f"codex CLI not found at {CODEX}", "detail": ""}
    auth_path = HOME / ".codex" / "auth.json"
    if not auth_path.exists():
        return {"available": False, "reason": "codex CLI present but ~/.codex/auth.json is missing (not logged in)", "detail": str(auth_path)}
    data, err = _read_json_file(auth_path)
    if data is None:
        return {"available": False, "reason": f"codex auth.json unreadable: {err}", "detail": str(auth_path)}
    access_token = (data.get("tokens") or {}).get("access_token") if isinstance(data, dict) else None
    if not access_token:
        return {"available": False, "reason": "codex auth.json present but has no access_token (not logged in)", "detail": str(auth_path)}
    exp = _decode_jwt_exp(access_token)
    locally_valid = exp is None or exp > time.time()
    if not deep:
        if not locally_valid:
            return {"available": False, "reason": "codex access_token is locally expired", "detail": f"exp={exp}"}
        return {
            "available": True,
            "reason": (
                "codex auth.json present with a locally well-formed, unexpired access_token "
                "(NOT verified against the server; server-side token revocation is invisible to "
                "this cheap check -- pass deep=True for a live probe)"
            ),
            "detail": f"exp={exp}",
        }
    try:
        probe_cwd = str(Path(cwd).resolve()) if cwd else str(HOME)
        proc = subprocess.run(
            [
                str(CODEX), "exec", "--json", "-C", probe_cwd,
                "-c", 'approval_policy="never"',
                "--dangerously-bypass-approvals-and-sandbox",
                "-m", CODEX_MODEL,
                "-c", 'model_reasoning_effort="low"',
                "-c", 'service_tier="fast"',
                "-",
            ],
            input="Reply with exactly PROBE_OK and nothing else. Do not use tools.",
            capture_output=True,
            text=True,
            timeout=40,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if "token_invalidated" in combined or "refresh_token_invalidated" in combined:
            return {
                "available": False,
                "reason": "codex not logged in (ChatGPT login lost / token revoked server-side)",
                "detail": "live `codex exec` probe returned HTTP 401 token_invalidated / refresh_token_invalidated",
            }
        if "PROBE_OK" in combined:
            return {"available": True, "reason": "codex live probe round-tripped successfully", "detail": "PROBE_OK observed in probe output"}
        return {
            "available": False,
            "reason": "codex live probe did not complete cleanly (no PROBE_OK observed)",
            "detail": combined[-500:],
        }
    except Exception as exc:
        return {"available": False, "reason": f"codex live probe failed: {exc}", "detail": ""}


def _check_agy_backend(deep: bool = False) -> dict[str, Any]:
    if not AGY.exists():
        return {"available": False, "reason": f"agy CLI not found at {AGY}", "detail": ""}
    creds_path = HOME / ".gemini" / "oauth_creds.json"
    if not creds_path.exists():
        return {"available": False, "reason": "agy CLI present but ~/.gemini/oauth_creds.json is missing (not logged in)", "detail": str(creds_path)}
    data, err = _read_json_file(creds_path)
    if data is None:
        return {"available": False, "reason": f"agy oauth_creds.json unreadable: {err}", "detail": str(creds_path)}
    expiry_ms = data.get("expiry_date") if isinstance(data, dict) else None
    has_refresh = bool(data.get("refresh_token")) if isinstance(data, dict) else False
    expires_future = isinstance(expiry_ms, (int, float)) and (expiry_ms / 1000.0) > time.time()
    if expires_future or has_refresh:
        return {
            "available": True,
            "reason": (
                "agy oauth_creds.json present with a non-expired token or a refresh_token "
                "(NOT deeply verified against Google; deep=True does not add a live ping for agy "
                "to avoid spending a real prompt turn)"
            ),
            "detail": f"expiry_date={expiry_ms}, has_refresh_token={has_refresh}",
        }
    return {
        "available": False,
        "reason": "agy oauth_creds.json present but the token is expired and no refresh_token is stored",
        "detail": f"expiry_date={expiry_ms}",
    }


@mcp.tool()
def check_worker_backends(cwd: str | None = None, deep: bool = False) -> dict[str, Any]:
    """Probe availability of worker backends before delegating to a non-default one.

    Cheap by default: file existence + auth-file/JWT inspection, no network
    calls. codex's cheap check can be a false positive (see module notes
    above this function) because server-side token revocation does not
    change the local JWT's `exp` claim; pass deep=True to additionally run
    one short live `codex exec` probe that catches that case. Manager
    doctrine: call this before delegating to a non-default backend (codex,
    grok, agy, or cursor-agent) and fall back to a Claude Sonnet subagent
    if unavailable.
    """
    return {
        "claude_sonnet": _check_claude_sonnet_backend(),
        "claude_worker": _check_claude_worker_backend(),
        "grok": _check_grok_backend(deep=deep),
        "codex": _check_codex_backend(deep=deep, cwd=cwd),
        "agy": _check_agy_backend(deep=deep),
        "cursor_agent": _check_cursor_agent_backend(),
    }


# ============================================================================
# Claude Code worker backend (headless, cross-platform, multi-provider)
# ============================================================================
# Spawns worker agents NATIVELY as headless Claude Code CLI processes
# (`claude -p --output-format stream-json`) instead of opening a visible
# terminal/TUI per agent. Workers run direct-Anthropic on the local `claude`
# CLI's own credentials, so `model` must be an Anthropic model the CLI serves
# (claude-opus-5, claude-sonnet-5, ...); it is selected per spawn via the
# `model` argument, which is genuinely honored (unlike the Codex backend's
# recorded-but-ignored pattern).
# The runner (claude_worker_runner.py, deployed beside this file) is plain
# stdlib Python, so the same backend works on Windows, macOS, and Linux with
# the full run-directory protocol: steering, captain help/report, watchers.

CLAUDE_WORKER_RUNNER = Path(__file__).resolve().parent / "claude_worker_runner.py"
CLAUDE_WORKER_DEFAULT_MODEL = os.environ.get("BRIDGE_CLAUDE_WORKER_MODEL", "").strip() or "claude-opus-5"
CLAUDE_WORKER_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _claude_worker_effort(requested: str) -> str:
    candidate = (requested or "").strip().lower()
    return candidate if candidate in CLAUDE_WORKER_EFFORTS else ""


def _claude_worker_permission_mode(sandbox: str) -> tuple[str, bool]:
    """Map the bridge's permission-intent vocabulary onto Claude Code CLI modes.

    Returns (permission_mode, enforce_read_only). read-only additionally strips
    Write/Edit via --disallowed-tools so no-edit is enforced, not just requested
    (same policy as the Grok backend's _grok_read_only_args).
    """
    requested = (sandbox or "read-only").strip().lower()
    if requested == "read-only":
        return "plan", True
    if requested == "workspace-write":
        return "acceptEdits", False
    return "bypassPermissions", False


def _claude_worker_report_note(run_dir: Path) -> str:
    return textwrap.dedent(f"""
    # Captain Report (Claude worker)

    Run directory: {run_dir}

    This run's launcher automatically writes a captain report to
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON}` and
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_MD}` from your final
    answer text once this turn ends, so the captain can read your result with
    `get_visible_run_status` or `list_captain_reports` even if you never call a
    tool. If the `agent-visibility` MCP server is reachable in this session,
    also call `submit_captain_report` with a structured outcome/summary before
    stopping, and use `request_captain_help` if you are blocked.
    """).strip()


def _claude_worker_rigor_note() -> str:
    return textwrap.dedent("""
    # Worker Rigor Contract (mandatory)

    1. ENUMERATE candidate approaches and the edge/error cases the change must
       survive before changing anything; do not tunnel on the first idea.
    2. PRESSURE-TEST your own work adversarially before reporting; fix what you find.
    3. ACTUALLY RUN IT end to end and paste observed output as proof. If you cannot
       execute it, label the result UNVERIFIED explicitly.
    4. REPORT HONESTLY: what changed, exact commands and real output, what you did
       NOT test, and the top ways this could still be wrong.

    The captain reviews antagonistically; unexecuted "done" claims are failures.
    """).strip()


def _launch_headless_python(script_path: Path, run_dir: Path, env: dict[str, str] | None = None) -> int:
    """Launch the stdlib runner headless and detached, cross-platform."""
    log_handle = (run_dir / "launcher.log").open("ab")
    kwargs: dict[str, Any] = {
        "cwd": str(run_dir),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": log_handle,
        "env": env,
    }
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: no console window at all.
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True  # own process group for clean SIGINT/SIGTERM
    proc = subprocess.Popen([str(PYTHON), str(script_path), str(run_dir)], **kwargs)
    _LAUNCHED_PIDS.append(int(proc.pid))
    return int(proc.pid)


def _launch_visible_python(script_path: Path, run_dir: Path, env: dict[str, str] | None = None) -> int:
    """Launch a stdlib runner in a new console window (Windows) so the owner can watch it."""
    kwargs: dict[str, Any] = {
        "cwd": str(run_dir),
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000010  # CREATE_NEW_CONSOLE
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(PYTHON), str(script_path), str(run_dir)], **kwargs)
    _LAUNCHED_PIDS.append(int(proc.pid))
    return int(proc.pid)


@mcp.tool()
def start_claude_worker(
    prompt: str,
    cwd: str,
    title: str = "Claude worker",
    model: str = CLAUDE_WORKER_DEFAULT_MODEL,
    sandbox: str = "read-only",
    effort: str = "",
    session_context: str = "",
    resume_session_id: str = "",
    max_budget_usd: str = "",
    steer_idle_seconds: int = CODEX_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Spawn a native headless Claude Code CLI worker on ANY provider's model.

    No terminal/TUI window is opened: the worker runs as a detached headless
    `claude -p` process whose stream-json output is captured into the standard
    run directory (events.jsonl, display.log, status.json, captain_reports/).
    The worker always runs direct-Anthropic on the local `claude` CLI's own
    credentials, so `model` must be an Anthropic model that CLI serves
    (e.g. claude-opus-5, claude-sonnet-5, claude-fable-5), and it is honored
    exactly as passed. Steering, captain-help, and captain-report tooling work
    identically to the other backends. Cross-platform.
    """
    effective_model = (model or "").strip() or CLAUDE_WORKER_DEFAULT_MODEL
    effective_effort = _claude_worker_effort(effort)
    permission_mode, read_only_enforced = _claude_worker_permission_mode(sandbox)
    prompt_with_permissions = "\n\n".join([
        _codex_permission_contract(sandbox, "native-claude-code-permission-mode:" + permission_mode),
        prompt,
    ])
    effective_prompt = _with_session_context_bootstrap(
        prompt_with_permissions, cwd, "Claude worker", session_context
    )
    run_dir = _make_run(cwd, "claude-resume" if resume_session_id else "claude", title, effective_prompt, {
        "agent": "claude",
        "cwd": str(Path(cwd).resolve()),
        "sandbox": sandbox,
        "permission_mode": permission_mode,
        "read_only_enforced": read_only_enforced,
        "model": effective_model,
        "requested_model": model,
        "effort": effective_effort,
        "requested_effort": effort,
        "max_budget_usd": max_budget_usd,
        "resume_session_id": resume_session_id or None,
        "session_context_supplied": bool(session_context.strip()),
        "steer_idle_seconds": max(0, min(int(steer_idle_seconds), 300)),
        "captain_help_enabled": True,
        "captain_report_auto_write": True,
        "claude_cli": str(CLAUDE),
        "mode": "headless_native",
    })
    effective_prompt = "\n\n".join([
        _claude_worker_rigor_note(),
        _claude_worker_report_note(run_dir),
        _captain_help_contract(run_dir),
        effective_prompt,
    ])
    (run_dir / "prompt.md").write_text(effective_prompt, encoding="utf-8")
    launch_env = dict(os.environ)
    pid = _launch_headless_python(CLAUDE_WORKER_RUNNER, run_dir, env=launch_env)
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
        "captain_reports": str(run_dir / CAPTAIN_REPORTS_DIR),
        "session_id_file": str(run_dir / "session_id.txt"),
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": (
            f"A headless native Claude Code worker was spawned (no terminal window). "
            f"Model: {effective_model} via direct Anthropic | "
            f"permission mode: {permission_mode}"
            f"{' | read-only enforced (Write/Edit stripped)' if read_only_enforced else ''} | "
            f"effort: {effective_effort or 'CLI default'}. The runner auto-writes "
            "captain_reports/final.json+final.md from the answer text after every turn "
            "and honors queued steering during its idle window."
        ),
    }


@mcp.tool()
def steer_claude_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = False,
) -> dict[str, Any]:
    """Steer a headless Claude worker run, resuming its session if it already closed.

    An idle worker (in its steering window) consumes the queued instruction
    within a second. If the run has exited and launch_if_closed=True, a new
    headless worker is spawned resuming the same Claude session id with the
    same model/permission settings. interrupt_current_turn uses SIGINT on
    POSIX / console Ctrl+C on Windows, best-effort.
    """
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    if metadata.get("agent") not in (None, "claude"):
        return {"ok": False, "error": f"run_dir is not a Claude worker run: {path}", "metadata": metadata}
    status = _read_json(path / "status.json", {"status": "unknown"})
    status_name = _status_name(status)
    requested_sandbox = sandbox.strip()
    permission_contract = (
        _codex_permission_contract(requested_sandbox, "native-claude-code-permission-mode")
        if requested_sandbox
        else ""
    )
    steer_path = _write_steer_file(path, instruction, session_context, title, permission_contract)
    session_id = _read_session_id_file(path / "session_id.txt") or ""
    result: dict[str, Any] = {
        "ok": True,
        "mode": "queued",
        "run_dir": str(path),
        "status": status,
        "session_id": session_id or None,
        "steer_file": str(steer_path),
        "note": "Steering was queued. The worker will consume it after the current turn or during its steering idle window.",
    }
    active = status_name in ("created", "waiting_for_steer") or status_name.startswith("running")
    if active and not interrupt_current_turn:
        if status_name == "waiting_for_steer":
            result["note"] = "Steering was queued for immediate pickup: the worker polls the queue every second while idle."
        return result
    if active and interrupt_current_turn:
        pid_path = path / "launcher_pid.txt"
        if pid_path.exists():
            pid = pid_path.read_text(encoding="utf-8-sig").strip()
            interrupted, warning = _interrupt_visible_run(pid)
            result["interrupted_pid" if interrupted else "interrupt_warning"] = pid if interrupted else warning
            if not interrupted:
                result["mode"] = "queued_interrupt_failed"
                return result
        else:
            result["mode"] = "queued_no_interrupt_no_pid"
            return result
    if not launch_if_closed:
        result["mode"] = "queued_no_active_runner"
        result["note"] = "Steering was queued, but the run is not active and launch_if_closed is false."
        return result
    if not session_id:
        result["mode"] = "queued_no_resume_session"
        result["note"] = "Steering was queued, but no Claude session id is recorded to resume."
        return result
    cwd = _infer_cwd_from_run_dir(path, metadata)
    resume = start_claude_worker(
        prompt=steer_path.read_text(encoding="utf-8-sig"),
        cwd=cwd,
        title=f"{title} (resume)",
        model=str(metadata.get("model") or CLAUDE_WORKER_DEFAULT_MODEL),
        sandbox=requested_sandbox or str(metadata.get("sandbox") or "read-only"),
        effort=str(metadata.get("effort") or ""),
        session_context=session_context,
        resume_session_id=session_id,
        steer_idle_seconds=int(metadata.get("steer_idle_seconds") or CODEX_STEER_IDLE_SECONDS),
    )
    result["mode"] = "launched_resume"
    result["resume_run"] = resume
    result["note"] = "A new headless Claude worker was launched resuming the same session id with the steering instruction."
    return result


def _check_claude_worker_backend() -> dict[str, Any]:
    claude_found = shutil.which(str(CLAUDE)) or (CLAUDE.exists() and str(CLAUDE))
    if not claude_found:
        return {"available": False, "reason": f"claude CLI not found at {CLAUDE}", "detail": ""}
    if not CLAUDE_WORKER_RUNNER.exists():
        return {"available": False, "reason": f"claude_worker_runner.py missing at {CLAUDE_WORKER_RUNNER}", "detail": ""}
    return {
        "available": True,
        "reason": "claude CLI + runner present; workers run direct-Anthropic on the claude CLI's own credentials",
        "detail": f"{CLAUDE}",
    }


# ============================================================================
# Cursor Agent worker backend (visible window, added 2026-08-26)
# ============================================================================
# cursor-agent CLI in a visible console, default model cursor-grok-4.6-xhigh-fast
# (owner routing: grok 4.6 xhigh Max Mode fast). Same run-dir protocol as the
# other backends. Print mode has no --prompt-file and rejects stdin, so the
# runner passes a short bootstrap that Reads prompt.md when the brief is long.
# Resume is `--resume <session_id>` (session_id is stable across turns).

CURSOR_WORKER_RUNNER = Path(__file__).resolve().parent / "cursor_worker_runner.py"
CURSOR_DEFAULT_MODEL = "cursor-grok-4.6-xhigh-fast"
CURSOR_MODELS_BY_EFFORT = {
    "low": "cursor-grok-4.6-low-fast",
    "medium": "cursor-grok-4.6-medium-fast",
    "high": "cursor-grok-4.6-high-fast",
    "xhigh": "cursor-grok-4.6-xhigh-fast",
}
CURSOR_STEER_IDLE_SECONDS = CODEX_STEER_IDLE_SECONDS


def _resolve_cursor_agent_argv() -> list[str]:
    """Prefer versioned node.exe + index.js so long argv never hits cmd.exe's 8191 limit."""
    override = os.environ.get("BRIDGE_CURSOR_AGENT_CLI", "").strip()
    if override:
        return [override]
    localapp = Path(os.environ.get("LOCALAPPDATA", "") or "")
    versions = localapp / "cursor-agent" / "versions"
    if versions.is_dir():
        dirs = sorted((d for d in versions.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
        for directory in dirs:
            node = directory / "node.exe"
            index = directory / "index.js"
            if node.exists() and index.exists():
                return [str(node), str(index)]
    found = shutil.which("cursor-agent") or shutil.which("agent")
    if found:
        return [found]
    fallback = localapp / "cursor-agent" / "cursor-agent.cmd"
    if fallback.exists():
        return [str(fallback)]
    return []


def _cursor_model_for_effort(requested: str, model: str = "") -> str:
    explicit = (model or "").strip()
    if explicit:
        return explicit
    candidate = (requested or "").strip().lower()
    if candidate in CURSOR_MODELS_BY_EFFORT:
        return CURSOR_MODELS_BY_EFFORT[candidate]
    if candidate in CURSOR_MODELS_BY_EFFORT.values() or candidate.startswith("cursor-"):
        return (requested or "").strip()
    return CURSOR_DEFAULT_MODEL


def _ensure_cursor_max_mode() -> dict[str, Any]:
    """Keep Cursor Max Mode on so the default worker is Extra High Fast · MAX."""
    path = HOME / ".cursor" / "cli-config.json"
    try:
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        changed = False
        if data.get("maxMode") is not True:
            data["maxMode"] = True
            changed = True
        model = data.get("model")
        if isinstance(model, dict) and model.get("maxMode") is not True:
            model["maxMode"] = True
            changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(path), "changed": changed, "maxMode": True}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


def _ensure_cursor_mcp_config() -> dict[str, Any]:
    """Merge agent-visibility into ~/.cursor/mcp.json so a worker can call Layer 2 tools."""
    path = HOME / ".cursor" / "mcp.json"
    deployed = HOME / ".agent-bridge" / "visible_agent_bridge.py"
    bridge_py = deployed if deployed.is_file() else Path(__file__).resolve()
    server = {
        "command": str(PYTHON),
        "args": [str(bridge_py)],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
            data["mcpServers"] = servers
        existing = servers.get("agent-visibility")
        if existing == server:
            return {"ok": True, "path": str(path), "changed": False}
        servers["agent-visibility"] = server
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(path), "changed": True}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


def _cursor_captain_report_note(run_dir: Path) -> str:
    return textwrap.dedent(f"""
    # Captain Report (Cursor agent)

    Run directory: {run_dir}

    This run's launcher automatically writes a captain report to
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_JSON}` and
    `{run_dir / CAPTAIN_REPORTS_DIR / CAPTAIN_REPORT_FINAL_MD}` from your final
    answer text once this turn ends, so Claude can read your result with
    `get_visible_run_status` or `list_captain_reports` even if you never call a
    tool. If the `agent-visibility` MCP server is reachable in this session,
    also call `submit_captain_report` with a structured outcome/summary before
    stopping, and use `request_captain_help` if you are blocked.
    """).strip()


def _check_cursor_agent_backend() -> dict[str, Any]:
    argv = _resolve_cursor_agent_argv()
    if not argv:
        return {
            "available": False,
            "reason": "cursor-agent CLI not found on PATH or under %LOCALAPPDATA%\\cursor-agent",
            "detail": "",
        }
    if not CURSOR_WORKER_RUNNER.exists():
        return {
            "available": False,
            "reason": f"cursor_worker_runner.py missing at {CURSOR_WORKER_RUNNER}",
            "detail": " ".join(argv),
        }
    cfg = _read_json(HOME / ".cursor" / "cli-config.json", {})
    email = ""
    if isinstance(cfg, dict):
        auth = cfg.get("authInfo")
        if isinstance(auth, dict):
            email = str(auth.get("email") or "").strip()
    max_mode = cfg.get("maxMode") is True if isinstance(cfg, dict) else False
    max_note = "maxMode=true" if max_mode else "maxMode not true (harness will set it on start)"
    if email:
        return {
            "available": True,
            "reason": f"cursor-agent CLI present; cli-config.json authInfo.email={email}; {max_note}",
            "detail": " ".join(argv),
        }
    return {
        "available": True,
        "reason": f"cursor-agent CLI present (no authInfo.email in ~/.cursor/cli-config.json; login is still required); {max_note}",
        "detail": " ".join(argv),
    }


@mcp.tool()
def start_visible_cursor_worker(
    prompt: str,
    cwd: str,
    title: str = "Cursor worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "xhigh",
    model: str = "",
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    compose_with_haiku: bool = False,
    composer_model: str = CLAUDE_PROMPT_COMPOSER_MODEL,
    composer_effort: str = CLAUDE_PROMPT_COMPOSER_EFFORT,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = CURSOR_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible cursor-agent worker in a new console window and save logs.

    Default model is always cursor-grok-4.6-xhigh-fast (Cursor Grok 4.6 Extra
    High Fast · MAX) unless the owner names another model. reasoning_effort
    selects among cursor-grok-4.6-{{low,medium,high,xhigh}}-fast unless `model`
    is an explicit Cursor model id. sandbox=read-only maps to `--mode plan`;
    writes use `--force`. `--trust` and `--approve-mcps` always. Max Mode is
    turned on in ~/.cursor/cli-config.json on start.
    """
    argv = _resolve_cursor_agent_argv()
    if not argv:
        return {"ok": False, "error": "cursor-agent CLI not found"}
    if not CURSOR_WORKER_RUNNER.exists():
        return {"ok": False, "error": f"cursor_worker_runner.py missing at {CURSOR_WORKER_RUNNER}"}
    effective_model = _cursor_model_for_effort(reasoning_effort, model)
    auto_full_tool_access = _needs_full_tool_access("\n".join([title, prompt, session_context]))
    effective_sandbox = CODEX_FULL_TOOL_SANDBOX
    prompt_with_permissions = "\n\n".join([
        _codex_permission_contract(sandbox, effective_sandbox),
        prompt,
    ])
    if compose_with_haiku:
        effective_prompt = prompt.strip()
    else:
        effective_prompt = _with_session_context_bootstrap(
            prompt_with_permissions, cwd, "Cursor worker", session_context
        )
    mcp_status = _ensure_cursor_mcp_config()
    max_mode_status = _ensure_cursor_max_mode()
    run_dir = _make_run(cwd, "cursor-resume" if resume_session_id else "cursor", title, effective_prompt, {
        "agent": "cursor",
        "cwd": str(Path(cwd).resolve()),
        "sandbox": effective_sandbox,
        "requested_sandbox": sandbox,
        "model": effective_model,
        "requested_model": model or None,
        "requested_reasoning_effort": reasoning_effort,
        "effective_reasoning_effort": (reasoning_effort or "xhigh").strip().lower() or "xhigh",
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
        "captain_report_auto_write": True,
        "cursor_agent_argv": argv,
        "claude_cli": str(CLAUDE),
        "mcp_config": mcp_status,
        "max_mode": max_mode_status,
        "mode": "visible_cursor_agent",
    })
    if not compose_with_haiku:
        effective_prompt = "\n\n".join([
            _claude_worker_rigor_note(),
            _cursor_captain_report_note(run_dir),
            _captain_help_contract(run_dir),
            effective_prompt,
        ])
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
            "xhigh",
        )
        (run_dir / "composer_prompt.md").write_text(composer_prompt, encoding="utf-8")
        prelude = _with_session_context_bootstrap(
            "\n\n".join([
                _claude_worker_rigor_note(),
                _cursor_captain_report_note(run_dir),
                _captain_help_contract(run_dir),
                _codex_permission_contract(sandbox, effective_sandbox),
            ]),
            cwd,
            "Cursor worker",
            session_context,
        )
        (run_dir / "cursor_prelude.md").write_text(prelude, encoding="utf-8")
    launch_env = dict(os.environ)
    launch_env.setdefault("PYTHONIOENCODING", "utf-8")
    launch_env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        from cursor_worker_runner import apply_git_bash_env as _apply_git_bash_env
        launch_env = _apply_git_bash_env(launch_env)
    except Exception:
        pass
    pid = _launch_visible_python(CURSOR_WORKER_RUNNER, run_dir, env=launch_env)
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
        "captain_reports": str(run_dir / CAPTAIN_REPORTS_DIR),
        "session_id_file": str(run_dir / "session_id.txt"),
        "watch_command": _watch_command(run_dir),
        "supervise_command": _supervise_command(run_dir),
        "note": (
            f"A visible console window was launched. cursor-agent runs {effective_model} "
            f"(requested effort '{reasoning_effort or 'xhigh'}'). Requested sandbox "
            f"{sandbox} maps to {'--mode plan' if (sandbox or '').strip().lower() == 'read-only' else '--force'}; "
            f"process sandbox is disabled for full tool access. Haiku prompt composer "
            f"enabled={compose_with_haiku}. The runner auto-writes captain_reports/final.json+"
            "final.md from the answer text after every turn."
        ),
    }


@mcp.tool()
def start_visible_haiku_composed_cursor_worker(
    prompt_brief: str,
    cwd: str,
    title: str = "Cursor worker",
    sandbox: str = "read-only",
    reasoning_effort: str = "xhigh",
    model: str = "",
    session_context: str = "",
    resume_session_id: str = "",
    requires_tool_access: bool = False,
    composer_max_budget_usd: str = CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
    steer_idle_seconds: int = CURSOR_STEER_IDLE_SECONDS,
) -> dict[str, Any]:
    """Launch a visible cursor-agent worker from a compact Claude brief expanded by Claude Haiku."""
    return start_visible_cursor_worker(
        prompt=prompt_brief,
        cwd=cwd,
        title=title,
        sandbox=sandbox,
        reasoning_effort=reasoning_effort,
        model=model,
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
def start_visible_first_mate_cursor_pool(
    goal: str,
    cwd: str,
    scout_areas: list[str] | None = None,
    implementation_items: list[str] | None = None,
    sandbox: str = "read-only",
    max_workers: int = 6,
    session_context: str = "",
    requires_tool_access: bool = False,
    reasoning_effort: str = "xhigh",
    model: str = "",
) -> dict[str, Any]:
    """Launch a visible cursor-agent root with native Task subagents left enabled to act as first mate."""
    prompt, auto_full_tool_access = _first_mate_prompt(
        goal=goal,
        scout_areas=scout_areas,
        implementation_items=implementation_items,
        sandbox=sandbox,
        max_workers=max_workers,
        session_context=session_context,
        requires_tool_access=requires_tool_access,
    )
    return start_visible_cursor_worker(
        prompt=prompt,
        cwd=cwd,
        title="Cursor first mate pool",
        sandbox=sandbox,
        reasoning_effort=reasoning_effort,
        model=model,
        session_context=session_context,
        requires_tool_access=requires_tool_access or auto_full_tool_access,
    )


@mcp.tool()
def steer_visible_cursor_run(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
    interrupt_current_turn: bool = True,
    requires_tool_access: bool = False,
) -> dict[str, Any]:
    """Send a Claude steering instruction to a visible cursor-agent run, resuming the same session if needed."""
    path = Path(run_dir).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"run_dir does not exist: {path}"}
    metadata = _read_json(path / "metadata.json", {})
    status = _read_json(path / "status.json", {"status": "unknown"})
    status_name = _status_name(status)
    if metadata.get("agent") not in (None, "cursor"):
        return {"ok": False, "error": f"run_dir is not a Cursor visible run: {path}", "metadata": metadata}

    requested_sandbox = sandbox.strip()
    permission_contract = (
        _codex_permission_contract(requested_sandbox, CODEX_FULL_TOOL_SANDBOX)
        if requested_sandbox
        else ""
    )
    steer_path = _write_steer_file(path, instruction, session_context, title, permission_contract)
    session_id = _visible_run_session_id(path, metadata) or ""
    active = status_name == "created" or status_name == "waiting_for_steer" or status_name.startswith("running")
    result: dict[str, Any] = {
        "ok": True,
        "mode": "queued",
        "run_dir": str(path),
        "status": status,
        "session_id": session_id or None,
        "steer_file": str(steer_path),
        "note": "Steering was queued. The visible Cursor window will consume it after the current turn, or during its steering idle window.",
    }

    idle = status_name in ("created", "waiting_for_steer")
    if active and (not interrupt_current_turn or idle):
        if status_name == "waiting_for_steer":
            result["note"] = (
                "Steering was queued for immediate pickup: the worker is idle in its "
                "steering window and polls the queue every second."
            )
        return result

    resume_session_id = session_id
    resume_mode = "launched_resume"
    resume_note = "The previous visible Cursor run was not available for in-window steering, so a visible Cursor resume run was launched on the same session id."

    if interrupt_current_turn and active:
        if not session_id:
            result["mode"] = "queued_no_interrupt_no_thread"
            result["note"] = "Steering was queued, but the current turn was not interrupted because no Cursor session id is available yet."
            return result
        pid_path = path / "launcher_pid.txt"
        if not pid_path.exists():
            result["mode"] = "queued_no_interrupt_no_pid"
            result["note"] = "Steering was queued, but the current turn was not interrupted because the launcher pid is unavailable."
            return result
        try:
            pid = pid_path.read_text(encoding="utf-8-sig").strip()
            interrupted, interrupt_warning = _interrupt_visible_run(pid)
            if not interrupted:
                result["mode"] = "queued_interrupt_failed"
                if interrupt_warning:
                    result["interrupt_warning"] = interrupt_warning
                result["note"] = "Steering was queued, but the active visible Cursor run could not be interrupted cleanly."
                return result
            result["interrupted_pid"] = pid
            if interrupt_warning:
                result["interrupt_warning"] = interrupt_warning
        except Exception as exc:
            result["mode"] = "queued_interrupt_failed"
            result["interrupt_warning"] = str(exc)
            result["note"] = "Steering was queued, but the active visible Cursor run could not be interrupted cleanly."
            return result

    if not launch_if_closed and "interrupted_pid" not in result:
        result["mode"] = "queued_no_active_runner"
        result["note"] = "Steering was queued, but the visible Cursor run is not active and launch_if_closed is false."
        return result

    if not session_id:
        result["mode"] = "queued_no_resume_thread"
        result["note"] = "Steering was queued, but no Cursor session id is available to launch a resume run."
        return result

    cwd = _infer_cwd_from_run_dir(path, metadata)
    steer_prompt = steer_path.read_text(encoding="utf-8")
    resume_context = "\n\n".join(
        part for part in [
            f"Previous visible run: {path}",
            f"Previous status: {status_name}",
            f"Previous Cursor session id: {session_id}",
            session_context.strip(),
        ] if part
    )
    followup = start_visible_cursor_worker(
        prompt=steer_prompt,
        cwd=cwd,
        title=title,
        sandbox=requested_sandbox or metadata.get("requested_sandbox") or "read-only",
        reasoning_effort=str(metadata.get("requested_reasoning_effort") or "xhigh"),
        model=str(metadata.get("model") or ""),
        session_context=resume_context,
        resume_session_id=resume_session_id,
        requires_tool_access=bool(requires_tool_access or metadata.get("requires_tool_access") or metadata.get("auto_full_tool_access")),
        compose_with_haiku=False,
        steer_idle_seconds=int(metadata.get("steer_idle_seconds") or CURSOR_STEER_IDLE_SECONDS),
    )
    try:
        done_dir = path / "steer_done"
        done_dir.mkdir(parents=True, exist_ok=True)
        steer_path.replace(done_dir / steer_path.name)
    except Exception:
        pass
    result["mode"] = resume_mode
    result["followup_run"] = followup
    result["note"] = resume_note
    return result


def _dispatch_visible_steer(
    run_dir: str,
    instruction: str,
    title: str = "Claude steering",
    session_context: str = "",
    sandbox: str = "",
    launch_if_closed: bool = True,
) -> dict[str, Any]:
    """Route captain-help steering to the matching backend instead of always Codex."""
    path = Path(run_dir).expanduser().resolve()
    agent = _read_json(path / "metadata.json", {}).get("agent")
    kwargs = {
        "title": title,
        "session_context": session_context,
        "sandbox": sandbox,
        "launch_if_closed": launch_if_closed,
    }
    if agent == "grok":
        return steer_visible_grok_run(run_dir, instruction, **kwargs)
    if agent == "agy":
        return steer_visible_agy_run(run_dir, instruction, **kwargs)
    if agent == "claude":
        return steer_claude_run(run_dir, instruction, **kwargs)
    if agent == "cursor":
        return steer_visible_cursor_run(run_dir, instruction, **kwargs)
    return steer_visible_codex_run(run_dir, instruction, **kwargs)


if __name__ == "__main__":
    mcp.run()
