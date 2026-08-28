#!/usr/bin/env python3
"""Cross-platform headless runner for visible-bridge Claude Code workers.

Launched by visible_agent_bridge.py as:  python claude_worker_runner.py <run_dir>

Everything else (model, effort, permission mode, steer window,
resume session id) is read from <run_dir>/metadata.json, so this file needs no
per-run templating and behaves identically on Windows, macOS, and Linux.

It mirrors the Grok PowerShell runner's state machine:
  initial turn -> auto captain report -> steer-queue loop -> git summary -> exit
with the same run-directory protocol (events.jsonl, display.log, status.json,
session_id.txt, steer_queue/, steer_done/, captain_reports/final.json+final.md)
so every existing bridge tool (get_visible_run_status, steer, captain help,
list_captain_reports, watchers) works on these runs unchanged.

Stdlib only. UTF-8 everywhere (no PowerShell 5.1 BOM/UTF-16 hazards).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CAPTAIN_REPORTS_DIR = "captain_reports"
FINAL_JSON = "final.json"
FINAL_MD = "final.md"


def _now_iso() -> str:
    return _dt.datetime.now().isoformat()


class Run:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8-sig"))
        self.prompt_path = run_dir / "prompt.md"
        self.events_path = run_dir / "events.jsonl"
        self.display_path = run_dir / "display.log"
        self.status_path = run_dir / "status.json"
        self.session_path = run_dir / "session_id.txt"
        self.steer_queue = run_dir / "steer_queue"
        self.steer_done = run_dir / "steer_done"
        self.reports_dir = run_dir / CAPTAIN_REPORTS_DIR
        self.steer_queue.mkdir(parents=True, exist_ok=True)
        self.steer_done.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.cwd = str(self.metadata.get("cwd") or Path.cwd())
        self.session_id: str = (self.metadata.get("resume_session_id") or "").strip()

    # -- logging ---------------------------------------------------------
    def _append(self, path: Path, text: str) -> None:
        # Append with a short retry: Windows AV/indexer scans can briefly hold
        # the file. CPython opens with FILE_SHARE_READ|WRITE, so concurrent
        # bridge readers tailing the log never block us in the common case.
        for _ in range(25):
            try:
                with path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(text + "\n")
                return
            except OSError:
                time.sleep(0.015)

    def raw(self, line: str) -> None:
        self._append(self.events_path, line)

    def display(self, text: str) -> None:
        self._append(self.display_path, text)

    def log(self, text: str) -> None:
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.display(f"[{stamp}] {text}")

    def set_status(self, status: str) -> None:
        payload = json.dumps(
            {"status": status, "updated_at": _now_iso(), "run_dir": str(self.run_dir)},
            indent=2,
        )
        tmp = self.status_path.with_suffix(".json.tmp")
        for _ in range(5):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, self.status_path)  # atomic on POSIX and Windows
                return
            except OSError:
                time.sleep(0.2)
        self.log(f"Set-Status failed after 5 attempts: {status}")

    # -- captain report --------------------------------------------------
    def _report_mtime(self) -> float:
        fp = self.reports_dir / FINAL_JSON
        try:
            return fp.stat().st_mtime
        except OSError:
            return 0.0

    def auto_captain_report(self, outcome: str, summary: str, baseline: float) -> None:
        """Write final.json/final.md from the answer text unless the worker
        already submitted its own richer report during the turn."""
        if self._report_mtime() > baseline:
            return  # worker's explicit submit_captain_report is authoritative
        now = _now_iso()
        record = {
            "report_id": f"{self.run_dir.name}-auto",
            "status": "submitted",
            "outcome": outcome,
            "created_at": now,
            "updated_at": now,
            "run_dir": str(self.run_dir),
            "thread_id": None,
            "session_id": self.session_id or None,
            "summary": summary,
            "changed_files": [],
            "verification": [],
            "risks": [],
            "questions": [],
            "close_tui": True,
            "auto_generated": True,
            "agent": "claude",
        }
        (self.reports_dir / FINAL_JSON).write_text(json.dumps(record, indent=2), encoding="utf-8")
        md = (
            f"# Captain Report\n\nReport ID: {record['report_id']}\nOutcome: {outcome}\n"
            f"Created: {now}\nRun directory: {self.run_dir}\n\n## Summary\n\n{summary}\n"
        )
        (self.reports_dir / FINAL_MD).write_text(md, encoding="utf-8")

    # -- claude invocation -----------------------------------------------
    def _claude_args(self, resume: str) -> list[str]:
        md = self.metadata
        claude_cli = md.get("claude_cli") or "claude"
        args = [
            claude_cli,
            "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--permission-mode", md.get("permission_mode", "plan"),
            "--add-dir", self.cwd,
        ]
        model = (md.get("model") or "").strip()
        if model:
            args += ["--model", model]
        effort = (md.get("effort") or "").strip()
        if effort:
            args += ["--effort", effort]
        if md.get("read_only_enforced"):
            args += ["--disallowed-tools", "Write,Edit"]
        max_budget = (md.get("max_budget_usd") or "").strip()
        if max_budget:
            args += ["--max-budget-usd", max_budget]
        if resume:
            args += ["--resume", resume]
        return args

    def _turn_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def run_turn(self, prompt_text: str, resume: str, label: str) -> tuple[int, str]:
        self.set_status(f"running:{label}")
        self.log(
            f"Starting Claude {'resume ' if resume else ''}turn: {label}"
            + (f" | session: {resume}" if resume else "")
        )
        args = self._claude_args(resume)
        self.log("Command: " + " ".join(args))
        chunks: list[str] = []
        result_text = ""
        error_seen = ""
        try:
            proc = subprocess.Popen(
                args,
                cwd=self.cwd,
                env=self._turn_env(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.set_status(f"failed:spawn:{exc}")
            return 1, f"failed to spawn claude CLI: {exc}"
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(prompt_text)
            proc.stdin.close()
        except OSError:
            pass
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            self.raw(line)
            try:
                obj = json.loads(line)
            except ValueError:
                self.log(line)
                continue
            if not isinstance(obj, dict):
                continue
            sid = obj.get("session_id")
            if isinstance(sid, str) and sid:
                if sid != self.session_id:
                    self.session_id = sid
                    self.session_path.write_text(sid, encoding="utf-8")
            otype = obj.get("type")
            if otype == "assistant" and isinstance(obj.get("message"), dict):
                for c in obj["message"].get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                        chunks.append(str(c["text"]))
                        self.display(str(c["text"]))
            elif otype == "result":
                self.log(
                    f"Claude result: subtype={obj.get('subtype')} "
                    f"cost={obj.get('total_cost_usd')} duration_ms={obj.get('duration_ms')}"
                )
                if obj.get("is_error"):
                    error_seen = str(obj.get("result") or obj.get("subtype") or "error")
                if obj.get("result"):
                    result_text = str(obj["result"])
            elif otype == "system":
                self.log(f"Claude system: {obj.get('subtype')}")
        code = proc.wait()
        answer = (result_text or "".join(chunks)).strip()
        if answer:
            self.display(f"\n===== Claude answer ({label}) =====\n{answer}\n===== end Claude answer =====\n")
        if code == 0 and error_seen:
            code = 1
        self.log(f"Claude turn '{label}' exited with code {code}")
        if code != 0 and not answer:
            answer = error_seen or "(claude turn failed before producing a text answer; see events.jsonl)"
        return code, answer

    # -- steer loop ------------------------------------------------------
    def next_steer_file(self) -> Path | None:
        try:
            files = sorted(p for p in self.steer_queue.glob("*.md") if p.is_file())
        except OSError:
            return None
        return files[0] if files else None

    def main(self) -> int:
        md = self.metadata
        steer_idle = max(0, min(int(md.get("steer_idle_seconds") or 20), 300))
        self.set_status("running")
        self.log(f"Run directory: {self.run_dir}")
        self.log(f"CWD: {self.cwd}")
        self.log(
            f"Model: {md.get('model')} | Effort: {md.get('effort') or 'default'} | "
            f"Permission mode: {md.get('permission_mode')} | "
            f"Routing: direct Anthropic"
        )
        prompt_text = self.prompt_path.read_text(encoding="utf-8-sig")

        baseline = self._report_mtime()
        code, answer = self.run_turn(prompt_text, self.session_id, "initial")
        if code == 0:
            self.auto_captain_report("completed", answer or "(no text answer; see events.jsonl)", baseline)
        else:
            self.auto_captain_report("failed", answer, baseline)

        while code == 0:
            waited = 0
            steer = self.next_steer_file()
            while steer is None and waited < steer_idle:
                if waited == 0:
                    self.set_status("waiting_for_steer")
                    self.log(f"Waiting up to {steer_idle}s for queued Claude steering before closing.")
                time.sleep(1)
                waited += 1
                steer = self.next_steer_file()
            if steer is None:
                break
            if not self.session_id:
                self.set_status("failed:steer-no-session")
                self.log(f"Cannot steer without a recorded session id: {steer}")
                code = 1
                break
            self.log(f"Applying queued Claude steering: {steer.name}")
            steer_text = steer.read_text(encoding="utf-8-sig")
            self.display(steer_text)
            baseline = self._report_mtime()
            code, answer = self.run_turn(steer_text, self.session_id, f"steer:{steer.stem}")
            if code == 0:
                self.auto_captain_report("completed", answer or "(no text answer; see events.jsonl)", baseline)
            else:
                self.auto_captain_report("failed", answer, baseline)
            try:
                steer.replace(self.steer_done / steer.name)
            except OSError:
                pass

        self.set_status("completed" if code == 0 else f"failed:{code}")
        try:
            for git_args, label in ((["status", "--short"], "Git status:"), (["diff", "--stat"], "Git diff stat:")):
                out = subprocess.run(
                    ["git", "-C", self.cwd, *git_args],
                    capture_output=True, text=True, timeout=15,
                )
                self.log(label)
                if out.stdout.strip():
                    self.display(out.stdout.rstrip())
        except Exception as exc:  # git summary is best-effort
            self.log(f"Git summary unavailable: {exc}")
        self.log("Claude worker run finished; logs remain in the run directory.")
        return code


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: claude_worker_runner.py <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1]).expanduser().resolve()
    if not (run_dir / "metadata.json").exists():
        print(f"no metadata.json in {run_dir}", file=sys.stderr)
        return 2
    run = Run(run_dir)
    try:
        return run.main()
    except Exception as exc:  # never leave status stuck on 'running'
        run.set_status(f"failed:runner:{exc}")
        run.log(f"Runner crashed: {exc!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
