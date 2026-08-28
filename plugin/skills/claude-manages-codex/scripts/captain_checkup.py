#!/usr/bin/env python3
"""Captain 10-minute checkup: evidence for an on-track / off-track verdict.

Alive is not on-track. This script does not decide the verdict. It prints
what each worker actually did recently so the captain can steer or stop them.

Usage:
  python captain_checkup.py --run-dir <run> [--cwd <repo>] [--since-minutes 10]
  python captain_checkup.py --cwd <repo> --active [--since-minutes 10]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

TERMINAL_PREFIXES = ("completed", "failed", "closed")
TOOL_TYPES = {"tool", "tool_use", "tool_call", "function_call", "tool_result"}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: object) -> object:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _status_name(run_dir: Path) -> str:
    status = _read_json(run_dir / "status.json", {})
    if isinstance(status, dict):
        return str(status.get("status") or "unknown")
    return str(status or "unknown")


def _is_terminal(status: str) -> bool:
    lowered = (status or "").strip().lower()
    return any(lowered == p or lowered.startswith(p) for p in TERMINAL_PREFIXES)


def _pid_alive(pid_text: str) -> bool | None:
    pid_text = (pid_text or "").strip()
    if not pid_text.isdigit():
        return None
    pid = int(pid_text)
    if os.name == "nt":
        check = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, timeout=10,
        )
        return str(pid) in (check.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _mtime_age_seconds(path: Path) -> float | None:
    try:
        return max(0.0, dt.datetime.now().timestamp() - path.stat().st_mtime)
    except OSError:
        return None


def _tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return []
    return data[-max(1, lines):]


def _extract_tools(events_path: Path, limit: int = 20) -> list[str]:
    if not events_path.exists():
        return []
    found: list[str] = []
    try:
        raw_lines = events_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return []
    for line in raw_lines[-400:]:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        otype = str(obj.get("type") or "")
        name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
        if otype in TOOL_TYPES and name:
            found.append(str(name))
        message = obj.get("message")
        if isinstance(message, dict):
            for item in message.get("content") or []:
                if isinstance(item, dict) and item.get("type") in TOOL_TYPES:
                    found.append(str(item.get("name") or item.get("tool") or item.get("type")))
    # last unique, keep order
    seen: set[str] = set()
    out: list[str] = []
    for name in reversed(found):
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= limit:
            break
    out.reverse()
    return out


def _git_snapshot(cwd: str) -> str:
    root = Path(cwd)
    if not root.is_dir():
        return "(cwd missing)"
    parts = []
    for args in (["status", "--short"], ["diff", "--stat"]):
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as exc:
            return f"(git unavailable: {exc})"
        text = (proc.stdout or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else "(clean or not a git checkout)"


def _help_questions(run_dir: Path, limit: int = 5) -> list[str]:
    req = run_dir / "captain_help" / "requests"
    if not req.is_dir():
        return []
    questions: list[str] = []
    for path in sorted(req.glob("*.json"))[-limit:]:
        data = _read_json(path, {})
        if isinstance(data, dict):
            q = str(data.get("question") or data.get("summary") or path.name)
            questions.append(q.strip() or path.name)
    return questions


def _discover_runs(cwd: Path | None, run_dir: Path | None, active_only: bool) -> list[Path]:
    if run_dir:
        return [run_dir]
    roots: list[Path] = []
    if cwd:
        roots.append(cwd / ".claude-codex" / "runs")
    roots.append(Path.home() / ".claude-codex" / "runs")
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
            if not child.is_dir() or child in seen:
                continue
            if not (child / "metadata.json").exists():
                continue
            seen.add(child)
            if active_only and _is_terminal(_status_name(child)):
                continue
            found.append(child)
    return found[:30]


def _brief_run(run_dir: Path, since_minutes: int, extra_cwd: str | None) -> str:
    metadata = _read_json(run_dir / "metadata.json", {})
    if not isinstance(metadata, dict):
        metadata = {}
    status = _status_name(run_dir)
    agent = str(metadata.get("agent") or "unknown")
    title = str(metadata.get("title") or run_dir.name)
    model = str(metadata.get("model") or "")
    sandbox = str(metadata.get("requested_sandbox") or metadata.get("sandbox") or "")
    cwd = str(metadata.get("cwd") or extra_cwd or "")
    pid_text = ""
    pid_path = run_dir / "launcher_pid.txt"
    if pid_path.exists():
        pid_text = pid_path.read_text(encoding="utf-8-sig").strip()
    alive = _pid_alive(pid_text) if pid_text else None
    display = run_dir / "display.log"
    age = _mtime_age_seconds(display)
    session = ""
    for name in ("session_id.txt", "thread_id.txt"):
        p = run_dir / name
        if p.exists():
            session = p.read_text(encoding="utf-8-sig").strip()
            if session:
                break
    pending_steer = len(list((run_dir / "steer_queue").glob("*.md"))) if (run_dir / "steer_queue").is_dir() else 0
    pending_help = len(list((run_dir / "captain_help" / "requests").glob("*.json"))) if (run_dir / "captain_help" / "requests").is_dir() else 0
    report = _read_json(run_dir / "captain_reports" / "final.json", {})
    report_summary = ""
    if isinstance(report, dict) and report:
        report_summary = str(report.get("summary") or report.get("outcome") or "")[:500]

    flags: list[str] = []
    running = (not _is_terminal(status)) and status != "unknown"
    if running and alive is False:
        flags.append("PID_DEAD_STATUS_STILL_RUNNING")
    if running and (age is None):
        flags.append("NO_OUTPUT_YET")
    elif running and age is not None and age > since_minutes * 60:
        flags.append(f"STALE_OUTPUT_{int(age // 60)}m")
    if pending_help:
        flags.append("PENDING_HELP")
    if pending_steer:
        flags.append("STEER_QUEUED_UNCONSUMED")
    if _is_terminal(status):
        flags.append("TERMINAL")
    if running and not flags:
        flags.append("ALIVE_ONLY_NOT_A_VERDICT")

    tail = _tail(display, 80)
    tools = _extract_tools(run_dir / "events.jsonl")
    help_qs = _help_questions(run_dir)
    git_text = _git_snapshot(cwd) if cwd else "(no cwd in metadata)"

    lines = [
        f"## Run: {run_dir.name} ({agent})",
        f"- title: {title}",
        f"- run_dir: {run_dir}",
        f"- status: {status}",
        f"- pid: {pid_text or 'none'} ({'alive' if alive else 'dead' if alive is False else 'unknown'})",
        f"- model: {model or '(unset)'}",
        f"- requested_sandbox: {sandbox or '(unset)'}",
        f"- session: {session or '(none yet)'}",
        f"- display_age_s: {int(age) if age is not None else 'n/a'}",
        f"- pending_help: {pending_help}  pending_steer: {pending_steer}",
        f"- flags: {', '.join(flags)}",
        "",
        f"### Recent work (tail of display.log, last ~{since_minutes}m window is the captain's focus)",
    ]
    if tail:
        lines.extend(f"    {line}" for line in tail[-60:])
    else:
        lines.append("    (no display.log yet)")
    lines.extend(["", "### Tools / commands seen in events.jsonl"])
    if tools:
        lines.extend(f"- {name}" for name in tools)
    else:
        lines.append("- (none parsed — read the tail; they may still be doing the wrong work)")
    lines.extend(["", "### Git snapshot", git_text, "", "### Latest captain report"])
    lines.append(report_summary or "(none)")
    lines.extend(["", "### Unanswered captain-help"])
    if help_qs:
        lines.extend(f"- {q}" for q in help_qs)
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "### Captain verdict (script cannot fill this)",
        "Pick one after reading the recent work. A status of running is not on-track.",
        "- [ ] on-track — say so, optionally request a compact checkpoint",
        "- [ ] off-track — steer now; quote a specific line from Recent work",
        "- [ ] blocked — answer captain-help or ask the owner",
        "- [ ] done — review the diff and accept or reject",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Captain 10-minute worker checkup (not a liveness probe).")
    parser.add_argument("--run-dir", default="", help="Single run directory to brief.")
    parser.add_argument("--cwd", default="", help="Repo whose .claude-codex/runs should be scanned.")
    parser.add_argument("--active", action="store_true", help="Brief every non-terminal run under --cwd.")
    parser.add_argument("--since-minutes", type=int, default=10)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else None
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else None
    if run_dir is None and cwd is None:
        print("captain_checkup.py: pass --run-dir and/or --cwd", file=sys.stderr)
        return 2

    runs = _discover_runs(cwd, run_dir, active_only=args.active and run_dir is None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"# Captain checkup {_now()}")
    print("ALIVE != ON-TRACK. This briefing is evidence for a verdict, not a green light.")
    print("A liveness or status-only poll never counts. Read the recent work, then verdict and steer.")
    print(f"since_minutes={args.since_minutes}  runs={len(runs)}")
    print()
    if not runs:
        print("No matching runs. If you expected workers, list `.claude-codex/runs` under --cwd.")
        print("CAPTAIN-SUPERVISION-EMPTY")
        return 0
    for path in runs:
        print(_brief_run(path, args.since_minutes, str(cwd) if cwd else None))
    print("CAPTAIN-SUPERVISION-DUE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
