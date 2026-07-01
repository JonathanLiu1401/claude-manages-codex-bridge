from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import visible_agent_bridge as bridge


SESSION_CONTEXT = (
    "Self-contained E2E verification for the Claude-Codex visible bridge. "
    "Do not use read-past-sessions. Do not edit files. Return the requested marker exactly."
)


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _run_dir(result: dict[str, Any]) -> Path:
    return Path(result["run_dir"]).resolve()


def _tail(path: Path, lines: int = 120) -> str:
    if not path.exists():
        return "<missing display.log>"
    data = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def _status(run_dir: Path) -> str:
    value = _read_json(run_dir / "status.json", {"status": "missing"})
    return str(value.get("status", "missing"))


def _thread_id(run_dir: Path) -> str:
    path = run_dir / "thread_id.txt"
    return path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""


def _pid_exists(pid: str) -> bool:
    if not pid.strip():
        return False
    check = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return check.returncode == 0


def _assert_launcher_exited(run_dir: Path) -> None:
    pid_path = run_dir / "launcher_pid.txt"
    if not pid_path.exists():
        return
    pid = pid_path.read_text(encoding="utf-8-sig").strip()
    deadline = time.time() + 20
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(1)
    raise AssertionError(f"launcher process still alive after run completion: pid={pid} run={run_dir}")


def _wait_completed(run_dir: Path, markers: list[str], timeout_s: int = 300) -> str:
    display = run_dir / "display.log"
    deadline = time.time() + timeout_s
    last_status = "missing"
    last_text = ""
    while time.time() < deadline:
        last_status = _status(run_dir)
        if display.exists():
            last_text = display.read_text(encoding="utf-8-sig", errors="replace")
        marker_ok = all(marker in last_text for marker in markers)
        if last_status.startswith("failed"):
            raise AssertionError(f"run failed: {run_dir}\nstatus={last_status}\n{_tail(display)}")
        if last_status in {"completed", "completed_budget_capped"} and marker_ok:
            _assert_launcher_exited(run_dir)
            return last_text
        time.sleep(2)
    missing = [marker for marker in markers if marker not in last_text]
    raise AssertionError(
        f"timed out waiting for {run_dir}\nstatus={last_status}\nmissing={missing}\n{_tail(display)}"
    )


def _assert_no_git_changes() -> None:
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    ).stdout.rstrip("\n")
    allowed_paths = {
        "README.md",
        "plugin/skills/claude-manages-codex/SKILL.md",
        "visible_agent_bridge.py",
        "tests/",
    }
    allowed_prefixes = (
        " M README.md",
        "M  README.md",
        "M README.md",
        " M plugin/skills/claude-manages-codex/SKILL.md",
        "M  plugin/skills/claude-manages-codex/SKILL.md",
        "M plugin/skills/claude-manages-codex/SKILL.md",
        " M visible_agent_bridge.py",
        "M  visible_agent_bridge.py",
        "M visible_agent_bridge.py",
        "?? tests/",
    )
    unexpected = [
        line
        for line in status.splitlines()
        if line
        and not any(line.startswith(prefix) for prefix in allowed_prefixes)
        and line[3:] not in allowed_paths
    ]
    if unexpected:
        raise AssertionError(f"unexpected git changes from E2E:\n{status}")


def case_visible_worker_and_queued_steer() -> dict[str, Any]:
    result = bridge.start_visible_codex_worker(
        prompt="Self-contained E2E. Do not edit files. Reply exactly E2E_INITIAL_OK.",
        cwd=str(ROOT),
        title="E2E visible worker queued steering",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        steer_idle_seconds=10,
    )
    run_dir = _run_dir(result)
    steer = bridge.steer_visible_codex_run(
        str(run_dir),
        "Self-contained steering E2E. Reply exactly E2E_STEERED_OK. Do not edit files.",
        title="E2E queued steering",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        launch_if_closed=False,
    )
    assert steer["ok"] and steer["mode"] == "queued", steer
    _wait_completed(run_dir, ["E2E_INITIAL_OK", "E2E_STEERED_OK"], timeout_s=360)
    status = bridge.get_visible_run_status(str(run_dir), tail_lines=30)
    assert status["thread_id"], status
    assert status["pending_steers"] == 0, status
    assert status["completed_steers"] >= 1, status
    return {"run_dir": str(run_dir), "thread_id": status["thread_id"]}


def case_closed_run_resume(previous: dict[str, Any]) -> dict[str, Any]:
    old_run = Path(previous["run_dir"])
    steer = bridge.steer_visible_codex_run(
        str(old_run),
        "Self-contained closed-run resume E2E. Reply exactly E2E_RESUMED_OK. Do not edit files.",
        title="E2E closed run resume",
        sandbox="workspace-write",
        session_context=SESSION_CONTEXT,
        launch_if_closed=True,
    )
    assert steer["ok"] and steer["mode"] == "launched_resume", steer
    run_dir = _run_dir(steer["followup_run"])
    _wait_completed(run_dir, ["E2E_RESUMED_OK"], timeout_s=300)
    assert _thread_id(run_dir) == previous["thread_id"], (run_dir, previous)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata.get("requested_sandbox") == "workspace-write", metadata
    old_status = bridge.get_visible_run_status(str(old_run), tail_lines=10)
    assert old_status["pending_steers"] == 0, old_status
    return {"run_dir": str(run_dir), "thread_id": previous["thread_id"]}


def case_interrupt_steering() -> dict[str, Any]:
    result = bridge.start_visible_codex_worker(
        prompt=(
            "Self-contained interrupt E2E. Do not edit files. First run "
            "`powershell -NoProfile -Command Start-Sleep -Seconds 120`, then reply SHOULD_NOT_REACH."
        ),
        cwd=str(ROOT),
        title="E2E interrupt steering",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        steer_idle_seconds=5,
    )
    run_dir = _run_dir(result)
    deadline = time.time() + 120
    while time.time() < deadline and not _thread_id(run_dir):
        time.sleep(1)
    assert _thread_id(run_dir), _tail(run_dir / "display.log")
    steer = bridge.steer_visible_codex_run(
        str(run_dir),
        "Interrupt steering E2E. Stop the old sleep turn and reply exactly E2E_INTERRUPTED_OK. Do not edit files.",
        title="E2E interrupt follow-up",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        interrupt_current_turn=True,
        launch_if_closed=True,
    )
    assert steer["ok"], steer
    assert steer["mode"] in {"launched_resume", "queued_interrupt_failed", "queued_no_interrupt_no_pid"}, steer
    if steer["mode"] != "launched_resume":
        raise AssertionError(f"interrupt did not launch resume run: {steer}")
    followup = _run_dir(steer["followup_run"])
    _wait_completed(followup, ["E2E_INTERRUPTED_OK"], timeout_s=300)
    return {"run_dir": str(followup), "thread_id": _thread_id(followup)}


def case_haiku_composed_worker() -> dict[str, Any]:
    result = bridge.start_visible_haiku_composed_codex_worker(
        prompt_brief=(
            "Self-contained E2E. Ask Codex to do no file edits and reply exactly E2E_HAIKU_OK."
        ),
        cwd=str(ROOT),
        title="E2E Haiku composed Codex worker",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        composer_max_budget_usd=bridge.CLAUDE_PROMPT_COMPOSER_MAX_BUDGET_USD,
        steer_idle_seconds=5,
    )
    run_dir = _run_dir(result)
    _wait_completed(run_dir, ["E2E_HAIKU_OK"], timeout_s=360)
    assert (run_dir / "composer_events.jsonl").exists(), run_dir
    assert (run_dir / "composed_prompt.md").exists(), run_dir
    return {"run_dir": str(run_dir), "thread_id": _thread_id(run_dir)}


def case_first_mate_pool() -> dict[str, Any]:
    result = bridge.start_visible_first_mate_codex_pool(
        goal=(
            "Self-contained E2E only. Do not edit files and do not spawn subagents. "
            "Reply exactly E2E_FIRSTMATE_OK."
        ),
        cwd=str(ROOT),
        scout_areas=["No scouting required for this E2E marker test."],
        implementation_items=[],
        sandbox="read-only",
        max_workers=1,
        session_context=SESSION_CONTEXT,
        steer_idle_seconds=5,
    )
    run_dir = _run_dir(result)
    _wait_completed(run_dir, ["E2E_FIRSTMATE_OK"], timeout_s=300)
    return {"run_dir": str(run_dir), "thread_id": _thread_id(run_dir)}


def case_claude_advisor() -> dict[str, Any]:
    result = bridge.start_visible_claude_advisor(
        prompt="Self-contained advisor E2E. Reply exactly E2E_CLAUDE_ADVISOR_OK.",
        cwd=str(ROOT),
        title="E2E Claude advisor",
        max_budget_usd="0.10",
        session_context=SESSION_CONTEXT,
    )
    run_dir = _run_dir(result)
    _wait_completed(run_dir, ["E2E_CLAUDE_ADVISOR_OK"], timeout_s=240)
    assert (run_dir / "session_id.txt").exists(), run_dir
    return {"run_dir": str(run_dir), "session_id": (run_dir / "session_id.txt").read_text(encoding="utf-8-sig").strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-expensive", action="store_true", help="Skip Haiku, first-mate, and Claude advisor cases.")
    args = parser.parse_args()

    results: dict[str, Any] = {}
    print("[1/6] visible worker + queued steer", flush=True)
    results["queued"] = case_visible_worker_and_queued_steer()
    print(json.dumps(results["queued"], indent=2), flush=True)

    print("[2/6] closed run resume + permission override", flush=True)
    results["resume"] = case_closed_run_resume(results["queued"])
    print(json.dumps(results["resume"], indent=2), flush=True)

    print("[3/6] interrupt current turn + resume steering", flush=True)
    results["interrupt"] = case_interrupt_steering()
    print(json.dumps(results["interrupt"], indent=2), flush=True)

    if not args.skip_expensive:
        print("[4/6] Haiku-composed Codex worker", flush=True)
        results["haiku"] = case_haiku_composed_worker()
        print(json.dumps(results["haiku"], indent=2), flush=True)

        print("[5/6] first-mate visible pool", flush=True)
        results["firstmate"] = case_first_mate_pool()
        print(json.dumps(results["firstmate"], indent=2), flush=True)

        print("[6/6] Claude advisor visible run", flush=True)
        results["claude_advisor"] = case_claude_advisor()
        print(json.dumps(results["claude_advisor"], indent=2), flush=True)

    _assert_no_git_changes()
    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)


if __name__ == "__main__":
    main()
