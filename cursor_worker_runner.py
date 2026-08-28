#!/usr/bin/env python3
"""Visible-window runner for cursor-agent workers in the multi-agentic harness.

Launched by visible_agent_bridge.py as:  python cursor_worker_runner.py <run_dir>

Mirrors claude_worker_runner.py's state machine (initial turn -> auto captain
report -> steer-queue loop -> git summary -> exit) so get_visible_run_status,
steer, captain-help, and watchers work unchanged.

cursor-agent specifics (probed live 2026-08-26):
  - Print mode is `cursor-agent -p --output-format stream-json`.
  - Events are Claude-compatible NDJSON: system/init, assistant, result,
    plus thinking deltas. Every event carries session_id.
  - `--resume <session_id>` continues the same chat (session_id is stable).
  - stdin is NOT a prompt source ("No prompt provided for print mode"), and
    there is no --prompt-file, so the runner passes a short bootstrap that
    tells the worker to Read prompt.md / the steer file.
  - Read-only maps to `--mode plan`. Writes use `--force`. `--trust` and
    `--approve-mcps` always, `--sandbox disabled` for full process access.
  - On Windows the Shell tool only accepts Git Bash when MSYSTEM is set
    (cursor-agent's Mt() returns early otherwise) and `bash` on PATH must
    not be the WSL/WindowsApps stub. The runner injects Git Bash env.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CAPTAIN_REPORTS_DIR = "captain_reports"
FINAL_JSON = "final.json"
FINAL_MD = "final.md"
INLINE_PROMPT_MAX_CHARS = 16000
GIT_BASH_ROOTS = (
    os.environ.get("GIT_INSTALL_ROOT", ""),
    r"C:\Program Files\Git",
    r"C:\Program Files (x86)\Git",
)


def _git_install_root() -> Path | None:
    for raw in GIT_BASH_ROOTS:
        if not raw:
            continue
        root = Path(raw)
        if (root / "bin" / "bash.exe").is_file():
            return root
    git_exe = shutil.which("git")
    if not git_exe:
        return None
    git_path = Path(git_exe)
    # Git\cmd\git.exe or Git\bin\git.exe
    for candidate in (git_path.parent.parent, git_path.parent):
        if (candidate / "bin" / "bash.exe").is_file():
            return candidate
    return None


def apply_git_bash_env(env: dict[str, str]) -> dict[str, str]:
    """Make cursor-agent's Shell tool use Git Bash instead of WSL bash.

    cursor-agent (2026.08.25) only probes Git\\bin\\bash.exe when MSYSTEM is
    set. A node.exe launch from Python has no MSYSTEM, so it falls through
    to `bash` on PATH, which on this machine is System32/WindowsApps WSL
    stubs that cannot spawn. Prepend Git bin and set MSYSTEM/EXEPATH/SHELL.
    """
    if os.name != "nt":
        return env
    git_root = _git_install_root()
    if git_root is None:
        return env
    bash = git_root / "bin" / "bash.exe"
    prepend = [str(git_root / "bin"), str(git_root / "usr" / "bin"), str(git_root / "cmd")]
    current = env.get("PATH") or env.get("Path") or ""
    parts = [p for p in current.split(os.pathsep) if p and p not in prepend]
    env["PATH"] = os.pathsep.join(prepend + parts)
    env["Path"] = env["PATH"]
    env["MSYSTEM"] = env.get("MSYSTEM") or "MINGW64"
    env["EXEPATH"] = str(git_root)
    env["SHELL"] = str(bash)
    return env


def _now_iso() -> str:
    return _dt.datetime.now().isoformat()


def _set_console_title(title: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


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
        if self.session_id:
            self.session_path.write_text(self.session_id, encoding="utf-8")

    def _append(self, path: Path, text: str) -> None:
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

    def emit(self, text: str) -> None:
        self.display(text)
        print(text, flush=True)

    def log(self, text: str) -> None:
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.emit(f"[{stamp}] {text}")

    def set_status(self, status: str) -> None:
        payload = json.dumps(
            {"status": status, "updated_at": _now_iso(), "run_dir": str(self.run_dir)},
            indent=2,
        )
        tmp = self.status_path.with_suffix(".json.tmp")
        for _ in range(5):
            try:
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, self.status_path)
                return
            except OSError:
                time.sleep(0.2)
        self.log(f"Set-Status failed after 5 attempts: {status}")

    def _report_mtime(self) -> float:
        fp = self.reports_dir / FINAL_JSON
        try:
            return fp.stat().st_mtime
        except OSError:
            return 0.0

    def auto_captain_report(self, outcome: str, summary: str, baseline: float) -> None:
        if self._report_mtime() > baseline:
            return
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
            "agent": "cursor",
        }
        (self.reports_dir / FINAL_JSON).write_text(json.dumps(record, indent=2), encoding="utf-8")
        md = (
            f"# Captain Report\n\nReport ID: {record['report_id']}\nOutcome: {outcome}\n"
            f"Created: {now}\nRun directory: {self.run_dir}\n\n## Summary\n\n{summary}\n"
        )
        (self.reports_dir / FINAL_MD).write_text(md, encoding="utf-8")

    def _cursor_argv(self) -> list[str]:
        stored = self.metadata.get("cursor_agent_argv")
        if isinstance(stored, list) and stored:
            return [str(part) for part in stored if str(part).strip()]
        return ["cursor-agent"]

    def _prompt_arg(self, prompt_path: Path, prompt_text: str) -> str:
        """cursor-agent print mode rejects stdin and has no --prompt-file.

        Short prompts go inline. Longer briefs (session context + contracts)
        are executed via a bootstrap that Reads the already-written file,
        which lives under the workspace `.claude-codex/runs/` tree.
        """
        text = prompt_text or ""
        if len(text) <= INLINE_PROMPT_MAX_CHARS and "\x00" not in text:
            return text
        return (
            "Read the complete assigned task from this exact file path, then execute it. "
            "The file is the full captain brief or steering note. Do not wait for a restatement.\n\n"
            f"{prompt_path}"
        )

    def _cursor_args(self, prompt_path: Path, prompt_text: str, resume: str) -> list[str]:
        md = self.metadata
        args = list(self._cursor_argv())
        args += [
            "-p",
            "--output-format", "stream-json",
            "--trust",
            "--approve-mcps",
            "--sandbox", "disabled",
            "--workspace", self.cwd,
        ]
        model = (md.get("model") or "").strip()
        if model:
            args += ["--model", model]
        requested = str(md.get("requested_sandbox") or "read-only").strip().lower()
        if requested == "read-only":
            args += ["--mode", "plan"]
        else:
            args += ["--force"]
        if resume:
            args += ["--resume", resume]
        args.append(self._prompt_arg(prompt_path, prompt_text))
        return args

    def _turn_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUNBUFFERED", "1")
        return apply_git_bash_env(env)

    def _ingest_event(self, obj: dict, chunks: list[str], thought_noted: list[bool]) -> str:
        """Return result text if this is a terminal result event, else ''."""
        sid = obj.get("session_id") or obj.get("sessionId")
        if isinstance(sid, str) and sid and sid != self.session_id:
            self.session_id = sid
            self.session_path.write_text(sid, encoding="utf-8")
        otype = obj.get("type")
        if otype == "thinking":
            if not thought_noted[0]:
                self.log("Model is reasoning (thinking deltas are hidden; the answer follows).")
                thought_noted[0] = True
            return ""
        if otype == "assistant" and isinstance(obj.get("message"), dict):
            for c in obj["message"].get("content") or []:
                if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                    text = str(c["text"])
                    chunks.append(text)
                    print(text, end="", flush=True)
                    self.display(text)
            return ""
        if otype == "result":
            print("", flush=True)
            self.log(
                f"Cursor result: subtype={obj.get('subtype')} "
                f"duration_ms={obj.get('duration_ms')} is_error={obj.get('is_error')}"
            )
            if obj.get("is_error"):
                return str(obj.get("result") or obj.get("subtype") or "error")
            if obj.get("result"):
                return str(obj["result"])
            return ""
        if otype == "system":
            self.log(f"Cursor system: {obj.get('subtype')} model={obj.get('model')}")
            return ""
        return ""

    def run_turn(self, prompt_path: Path, prompt_text: str, resume: str, label: str) -> tuple[int, str]:
        self.set_status(f"running:{label}")
        self.log(
            f"Starting Cursor {'resume ' if resume else ''}turn: {label}"
            + (f" | session: {resume}" if resume else "")
        )
        args = self._cursor_args(prompt_path, prompt_text, resume)
        logged = [a if a is not args[-1] or len(a) < 200 else f"<prompt {len(a)} chars>" for a in args]
        self.log("Command: " + " ".join(logged))
        chunks: list[str] = []
        result_text = ""
        error_seen = ""
        thought_noted = [False]
        try:
            proc = subprocess.Popen(
                args,
                cwd=self.cwd,
                env=self._turn_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.set_status(f"failed:spawn:{exc}")
            return 1, f"failed to spawn cursor-agent CLI: {exc}"
        assert proc.stdout is not None
        decoder = json.JSONDecoder()
        buf = ""
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            self.raw(line)
            buf += line
            idx = 0
            n = len(buf)
            while idx < n:
                while idx < n and buf[idx].isspace():
                    idx += 1
                if idx >= n:
                    buf = ""
                    break
                try:
                    obj, end = decoder.raw_decode(buf, idx)
                except ValueError:
                    buf = buf[idx:]
                    break
                idx = end
                if isinstance(obj, dict):
                    got = self._ingest_event(obj, chunks, thought_noted)
                    if got:
                        if obj.get("is_error"):
                            error_seen = got
                        else:
                            result_text = got
                if idx >= n:
                    buf = ""
                    break
            else:
                continue
        code = proc.wait()
        answer = (result_text or "".join(chunks)).strip()
        if answer:
            self.emit(f"\n===== Cursor answer ({label}) =====\n{answer}\n===== end Cursor answer =====\n")
        if code == 0 and error_seen:
            code = 1
            answer = answer or error_seen
        self.log(f"Cursor turn '{label}' exited with code {code}")
        if code != 0 and not answer:
            answer = error_seen or "(cursor-agent turn failed before producing a text answer; see events.jsonl)"
        return code, answer

    def _compose_with_haiku(self) -> Path:
        """Expand composer_prompt.md via claude -p; fall back to the raw brief."""
        composer_prompt_path = self.run_dir / "composer_prompt.md"
        composed_path = self.run_dir / "composed_prompt.md"
        prelude_path = self.run_dir / "cursor_prelude.md"
        if not composer_prompt_path.exists():
            return self.prompt_path
        claude = str(self.metadata.get("claude_cli") or "claude")
        composer_model = str(self.metadata.get("prompt_composer_model") or "haiku")
        composer_effort = str(self.metadata.get("prompt_composer_effort") or "low")
        composer_budget = str(self.metadata.get("prompt_composer_max_budget_usd") or "1.00")
        self.log(
            f"Haiku prompt composer enabled. Model: {composer_model} | "
            f"Effort: {composer_effort} | Max budget USD: {composer_budget}"
        )
        args = [
            claude, "-p", "--safe-mode", "--no-session-persistence",
            "--prompt-suggestions", "false", "--verbose",
            "--output-format", "stream-json", "--permission-mode", "plan",
            "--max-budget-usd", composer_budget,
            "--model", composer_model, "--effort", composer_effort,
        ]
        prompt = composer_prompt_path.read_text(encoding="utf-8-sig")
        chunks: list[str] = []
        result_text = ""
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
            self.log(f"Haiku composer spawn failed ({exc}); falling back to the raw captain brief.")
            return self.prompt_path
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass
        composer_log = self.run_dir / "composer_events.jsonl"
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            self._append(composer_log, line)
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") == "assistant" and isinstance(obj.get("message"), dict):
                for c in obj["message"].get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                        chunks.append(str(c["text"]))
            elif obj.get("type") == "result" and obj.get("result"):
                result_text = str(obj["result"])
        code = proc.wait()
        if code != 0:
            self.log(f"Haiku prompt composer exited with code {code}; falling back to the raw captain brief.")
            result_text = ""
        if not result_text.strip():
            result_text = "\n".join(chunks)
        if not result_text.strip():
            self.log("Haiku prompt composer produced an empty prompt; falling back to the raw captain brief.")
            result_text = self.prompt_path.read_text(encoding="utf-8-sig")
            heading = "\n\n## Captain Brief (raw; Haiku composer unavailable)\n\n"
        else:
            heading = "\n\n## Haiku-Composed Worker Brief\n\n"
        prelude = prelude_path.read_text(encoding="utf-8-sig") if prelude_path.exists() else ""
        final_prompt = prelude.rstrip() + heading + result_text.strip()
        composed_path.write_text(final_prompt, encoding="utf-8")
        self.log("Composed Cursor prompt follows:")
        self.emit(final_prompt)
        return composed_path

    def next_steer_file(self) -> Path | None:
        try:
            files = sorted(p for p in self.steer_queue.glob("*.md") if p.is_file())
        except OSError:
            return None
        return files[0] if files else None

    def main(self) -> int:
        md = self.metadata
        steer_idle = max(0, min(int(md.get("steer_idle_seconds") or 20), 300))
        _set_console_title(f"Cursor visible worker - {self.run_dir.name}")
        self.set_status("running")
        self.log(f"Run directory: {self.run_dir}")
        self.log(f"CWD: {self.cwd}")
        self.log(
            f"Model: {md.get('model')} | Requested sandbox: {md.get('requested_sandbox')} | "
            f"Effort: {md.get('effective_reasoning_effort') or md.get('requested_reasoning_effort') or 'xhigh'}"
        )
        if self.session_id:
            self.log(f"Resuming Cursor session: {self.session_id}")

        if md.get("compose_with_haiku"):
            prompt_path = self._compose_with_haiku()
        else:
            prompt_path = self.prompt_path
            self.log("Prompt follows:")
            self.emit(prompt_path.read_text(encoding="utf-8-sig"))
        prompt_text = prompt_path.read_text(encoding="utf-8-sig")

        baseline = self._report_mtime()
        code, answer = self.run_turn(prompt_path, prompt_text, self.session_id, "initial")
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
            self.emit(steer_text)
            baseline = self._report_mtime()
            code, answer = self.run_turn(steer, steer_text, self.session_id, f"steer:{steer.stem}")
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
                    self.emit(out.stdout.rstrip())
        except Exception as exc:
            self.log(f"Git summary unavailable: {exc}")
        self.log("Cursor agent for this run has finished. This window will close in 5 seconds; logs remain in the run directory.")
        time.sleep(5)
        return code


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: cursor_worker_runner.py <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1]).expanduser().resolve()
    if not (run_dir / "metadata.json").exists():
        print(f"no metadata.json in {run_dir}", file=sys.stderr)
        return 2
    run = Run(run_dir)
    try:
        return run.main()
    except Exception as exc:
        run.set_status(f"failed:runner:{exc}")
        run.log(f"Runner crashed: {exc!r}")
        time.sleep(5)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
