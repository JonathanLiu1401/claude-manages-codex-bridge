from __future__ import annotations

import argparse
import datetime as dt
import inspect
import json
import os
import subprocess
import sys
import time
import tomllib
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


def _assert_model_policy() -> None:
    saved_model = os.environ.get(bridge.CLAUDE_ADVISOR_MODEL_ENV)
    saved_until = os.environ.get(bridge.CLAUDE_ADVISOR_MODEL_UNTIL_ENV)
    try:
        os.environ.pop(bridge.CLAUDE_ADVISOR_MODEL_ENV, None)
        os.environ.pop(bridge.CLAUDE_ADVISOR_MODEL_UNTIL_ENV, None)
        assert bridge._default_claude_advisor_model(dt.date(2026, 7, 7)) == "fable"
        assert bridge._default_claude_advisor_model(dt.date(2026, 7, 8)) == "opus"
        os.environ[bridge.CLAUDE_ADVISOR_MODEL_ENV] = "opus"
        assert bridge._default_claude_advisor_model(dt.date(2026, 7, 1)) == "opus"
    finally:
        if saved_model is None:
            os.environ.pop(bridge.CLAUDE_ADVISOR_MODEL_ENV, None)
        else:
            os.environ[bridge.CLAUDE_ADVISOR_MODEL_ENV] = saved_model
        if saved_until is None:
            os.environ.pop(bridge.CLAUDE_ADVISOR_MODEL_UNTIL_ENV, None)
        else:
            os.environ[bridge.CLAUDE_ADVISOR_MODEL_UNTIL_ENV] = saved_until


def _assert_codex_mcp_tool_allowlists() -> None:
    required = {"request_captain_help", "submit_captain_report"}

    manifest = _read_json(ROOT / "codex-plugin" / ".mcp.json", {})
    manifest_tools = set(
        manifest.get("mcpServers", {})
        .get("agent-visibility", {})
        .get("enabled_tools", [])
    )
    assert required <= manifest_tools, {"source_manifest": sorted(manifest_tools), "missing": sorted(required - manifest_tools)}

    config_path = Path.home() / ".codex" / "config.toml"
    if config_path.exists():
        config = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
        active_tools = set(
            config.get("plugins", {})
            .get("codex-consults-claude@personal", {})
            .get("mcp_servers", {})
            .get("agent-visibility", {})
            .get("enabled_tools", [])
        )
        assert required <= active_tools, {"active_config": sorted(active_tools), "missing": sorted(required - active_tools)}


def case_captain_help_mailbox() -> dict[str, Any]:
    run_dir = bridge._make_run(
        str(ROOT),
        "codex",
        "E2E captain help mailbox",
        "Self-contained mailbox test. Do not launch Codex.",
        {
            "agent": "codex",
            "cwd": str(ROOT),
            "requested_sandbox": "read-only",
            "approval_policy": "never",
        },
    )
    request = bridge.request_captain_help(
        str(run_dir),
        question="Need captain decision between option A and option B.",
        context="Observed facts are self-contained for this mailbox test.",
        urgency="blocked",
        recommended_next="Pick option A for this E2E.",
    )
    assert request["ok"], request
    status = bridge.get_visible_run_status(str(run_dir), tail_lines=5)
    assert status["pending_help_requests"] == 1, status

    response = bridge.respond_to_captain_help_request(
        str(run_dir),
        request["request_id"],
        response="Captain decision: use option A. Continue and report E2E_CAPTAIN_HELP_OK.",
        session_context=SESSION_CONTEXT,
        sandbox="read-only",
        launch_if_closed=False,
    )
    assert response["ok"], response
    assert response["steer"]["mode"] in {"queued", "queued_no_active_runner"}, response
    status = bridge.get_visible_run_status(str(run_dir), tail_lines=5)
    assert status["pending_help_requests"] == 0, status
    assert status["answered_help_requests"] == 1, status
    assert status["pending_steers"] == 1, status
    return {"run_dir": str(run_dir), "request_id": request["request_id"]}


# Deprecated-path regression: the single-worker TUI launcher must remain functional.
def case_interactive_tui_sidecar_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch_interactive_terminal
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 424242

    try:
        bridge._launch_interactive_terminal = fake_launch  # type: ignore[assignment]
        result = bridge.start_interactive_codex_tui(
            prompt="Self-contained interactive TUI dry-run. Do not edit files.",
            cwd=str(ROOT),
            title="E2E interactive Codex TUI dry-run",
            sandbox="read-only",
            approval_policy="on-request",
            session_context=SESSION_CONTEXT,
            no_alt_screen=True,
        )
    finally:
        bridge._launch_interactive_terminal = original_launch  # type: ignore[assignment]

    assert result["ok"], result
    assert result["pid"] == 424242, result
    assert launched_scripts, result
    assert "watch_command" in result and "captain_reports/final.json" in result["watch_command"], result

    run_dir = _run_dir(result)
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    metadata = _read_json(run_dir / "metadata.json", {})
    status = _read_json(run_dir / "status.json", {})

    assert metadata["agent"] == "codex", metadata
    assert metadata["mode"] == "interactive_tui", metadata
    assert metadata["model"] == bridge.CODEX_MODEL, metadata
    assert metadata["reasoning_effort"] == bridge.CODEX_REASONING_EFFORT, metadata
    assert metadata["service_tier"] == bridge.CODEX_SERVICE_TIER, metadata
    assert metadata["requested_sandbox"] == "read-only", metadata
    assert metadata["approval_policy"] == "on-request", metadata
    assert metadata["session_context_supplied"] is True, metadata
    assert metadata["close_on_exit"] is True, metadata
    assert metadata["auto_close_after_report"] is True, metadata
    assert status["status"] == "launched", status

    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    assert "submit_captain_report" in prompt, prompt
    assert str(run_dir) in prompt, prompt
    assert "Do not rely on a normal TUI final answer to reach Claude" in prompt, prompt
    assert "Captain Report Handoff" in prompt, prompt

    assert "codex.cmd" in script, script
    assert "'-m'" in script and "'gpt-5.6-sol'" in script, script
    assert "'-a'" in script and "'on-request'" in script, script
    assert "model_reasoning_effort=`\"xhigh`\"" in script, script
    assert "service_tier=`\"fast`\"" in script, script
    assert "--no-alt-screen" in script, script
    assert "$KeepOpen = $false" in script, script
    assert "$AutoCloseAfterReport = $true" in script, script
    assert "GenerateConsoleCtrlEvent" in script, script
    assert "taskkill.exe" in script, script
    assert "Close-InteractiveTuiTree" in script, script
    assert "captain_reports" in script and "final.json" in script, script
    assert "--json" not in script, script
    assert "exec" not in script.split("$argsList", 1)[1].split("Write-Log", 1)[0], script

    assert (run_dir / "prompt.md").exists(), run_dir
    assert (run_dir / "session_context.md").exists(), run_dir
    assert (run_dir / "notes.md").exists(), run_dir
    assert (run_dir / "display.log").exists(), run_dir
    assert (run_dir / "captain_reports").is_dir(), run_dir

    # Long captain briefs must not be passed inline: codex.cmd is a cmd.exe
    # batch shim capped at 8191 chars of command line, so oversized briefs go
    # through prompt.md with a short bootstrap argument.
    long_scripts: list[Path] = []

    def fake_launch_long(script_path: Path) -> int:
        long_scripts.append(script_path)
        return 424243

    try:
        bridge._launch_interactive_terminal = fake_launch_long  # type: ignore[assignment]
        long_result = bridge.start_interactive_codex_tui(
            prompt="Self-contained interactive TUI long-brief dry-run. Do not edit files.",
            cwd=str(ROOT),
            title="E2E interactive TUI long-brief dry-run",
            sandbox="read-only",
            approval_policy="on-request",
            session_context="LONG-BRIEF-PADDING " * 600,
            no_alt_screen=True,
        )
    finally:
        bridge._launch_interactive_terminal = original_launch  # type: ignore[assignment]
    long_run_dir = _run_dir(long_result)
    long_script = long_scripts[0].read_text(encoding="utf-8-sig")
    assert "too long for the Windows command line" in long_script, long_script
    assert "LONG-BRIEF-PADDING" not in long_script, "long brief leaked into the TUI command line"
    long_prompt = (long_run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    assert "LONG-BRIEF-PADDING" in long_prompt, long_prompt

    original_find_session = bridge._find_recent_codex_session_id
    try:
        bridge._find_recent_codex_session_id = lambda started_at, cwd, limit=50: ""  # type: ignore[assignment]
        report = bridge.submit_captain_report(
            str(run_dir),
            outcome="completed",
            summary="Interactive TUI dry-run report reached the captain sidecar.",
            changed_files=[],
            verification=["dry-run launcher inspected"],
            risks=["none"],
            questions=[],
            close_tui=False,
        )
        reported_status = bridge.get_visible_run_status(str(run_dir), tail_lines=20)
    finally:
        bridge._find_recent_codex_session_id = original_find_session  # type: ignore[assignment]
    assert report["ok"], report
    assert Path(report["report"]).exists(), report
    assert Path(report["report_markdown"]).exists(), report
    assert reported_status["captain_report"]["outcome"] == "completed", reported_status
    assert reported_status["captain_reports_count"] >= 1, reported_status

    fallback_report = {
        "run_dir": str(run_dir),
        "outcome": "completed",
        "summary": "Fallback final.json report is captain-readable.",
        "changed_files": [],
        "verification": ["fallback report inspected"],
        "risks": [],
        "questions": [],
        "close_tui": True,
    }
    (run_dir / "captain_reports" / "final.json").write_text(json.dumps(fallback_report, indent=2), encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"status": "running", "mode": "interactive_tui"}, indent=2), encoding="utf-8")
    try:
        bridge._find_recent_codex_session_id = lambda started_at, cwd, limit=50: ""  # type: ignore[assignment]
        fallback_status = bridge.get_visible_run_status(str(run_dir), tail_lines=20)
    finally:
        bridge._find_recent_codex_session_id = original_find_session  # type: ignore[assignment]
    assert fallback_status["status"]["status"] == "reported", fallback_status
    assert fallback_status["status"]["outcome"] == "completed", fallback_status
    assert fallback_status["captain_reports_count"] >= 1, fallback_status

    find_calls: list[tuple[float, str, int]] = []

    def fake_find_session(started_at: float, cwd: str, limit: int = 50) -> str:
        find_calls.append((started_at, cwd, limit))
        return ""

    try:
        bridge._find_recent_codex_session_id = fake_find_session  # type: ignore[assignment]
        status_result = bridge.get_visible_run_status(str(run_dir), tail_lines=20)
        assert status_result["metadata"]["mode"] == "interactive_tui", status_result
        assert status_result["session_id"] is None, status_result
        assert not (run_dir / "session_id.txt").exists(), run_dir

        listed = bridge.list_visible_runs(str(ROOT), limit=5)
        listed_run = next((item for item in listed if item["run_dir"] == str(run_dir)), None)
        assert listed_run is not None and listed_run["metadata"].get("mode") == "interactive_tui", listed
        assert listed_run["session_id"] is None, listed_run
        assert not (run_dir / "session_id.txt").exists(), run_dir
    finally:
        bridge._find_recent_codex_session_id = original_find_session  # type: ignore[assignment]
    assert find_calls, status_result

    fake_session = run_dir / "fake-session.jsonl"
    fake_session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": "019f-test-session"}}) + "\n",
        encoding="utf-8",
    )
    assert bridge._extract_session_id_from_jsonl(fake_session) == "019f-test-session"

    metadata_path = run_dir / "metadata.json"
    original_metadata = metadata_path.read_text(encoding="utf-8-sig")
    original_write_json = bridge._write_json
    original_path_write_text = Path.write_text

    def assert_best_effort_failure(
        label: str,
        metadata_override: dict[str, Any] | None = None,
        find_session: Any = None,
        write_text: Any = None,
        write_json: Any = None,
    ) -> None:
        if (run_dir / "session_id.txt").exists():
            (run_dir / "session_id.txt").unlink()
        metadata_path.write_text(original_metadata, encoding="utf-8")
        if metadata_override:
            failing_metadata = _read_json(metadata_path, {})
            failing_metadata.update(metadata_override)
            metadata_path.write_text(json.dumps(failing_metadata, indent=2), encoding="utf-8")
        bridge._find_recent_codex_session_id = find_session or (lambda started_at, cwd, limit=50: "")
        bridge._write_json = write_json or original_write_json  # type: ignore[assignment]
        Path.write_text = write_text or original_path_write_text  # type: ignore[assignment]
        try:
            failure_status = bridge.get_visible_run_status(str(run_dir), tail_lines=20)
            assert failure_status["session_id"] is None, (label, failure_status)
            assert not (run_dir / "session_id.txt").exists(), label
            failure_list = bridge.list_visible_runs(str(ROOT), limit=5)
            failure_item = next(item for item in failure_list if item["run_dir"] == str(run_dir))
            assert failure_item["session_id"] is None, (label, failure_item)
            assert not (run_dir / "session_id.txt").exists(), label
        finally:
            bridge._find_recent_codex_session_id = original_find_session  # type: ignore[assignment]
            bridge._write_json = original_write_json  # type: ignore[assignment]
            Path.write_text = original_path_write_text  # type: ignore[assignment]
            if (run_dir / "session_id.txt").exists():
                (run_dir / "session_id.txt").unlink()
            metadata_path.write_text(original_metadata, encoding="utf-8")

    assert_best_effort_failure("invalid started_at", metadata_override={"started_at_epoch": "not-a-float"})

    def raise_discovery(started_at: float, cwd: str, limit: int = 50) -> str:
        raise RuntimeError("discovery failed")

    assert_best_effort_failure("discovery failure", find_session=raise_discovery)

    def raise_session_write(self: Path, *args: Any, **kwargs: Any) -> int:
        if self == run_dir / "session_id.txt":
            raise OSError("session write failed")
        return original_path_write_text(self, *args, **kwargs)

    assert_best_effort_failure(
        "session_id write failure",
        find_session=lambda started_at, cwd, limit=50: "019f-write-failure",
        write_text=raise_session_write,
    )

    def raise_write_json(path: Path, value: Any) -> None:
        raise OSError("metadata write failed")

    assert_best_effort_failure(
        "metadata write failure",
        find_session=lambda started_at, cwd, limit=50: "019f-metadata-failure",
        write_json=raise_write_json,
    )

    return {"run_dir": str(run_dir), "script": str(launched_scripts[0])}


# Deprecated-path regression: the first-mate TUI launcher must remain functional.
def case_interactive_first_mate_tui_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch_interactive_terminal
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 424243

    try:
        bridge._launch_interactive_terminal = fake_launch  # type: ignore[assignment]
        result = bridge.start_interactive_first_mate_codex_tui(
            goal="Self-contained interactive first-mate TUI dry-run. Do not edit files.",
            cwd=str(ROOT),
            scout_areas=["Confirm this dry-run keeps the first-mate prompt contract."],
            implementation_items=[],
            sandbox="read-only",
            approval_policy="on-request",
            max_workers=2,
            session_context=SESSION_CONTEXT,
            no_alt_screen=True,
        )
    finally:
        bridge._launch_interactive_terminal = original_launch  # type: ignore[assignment]

    assert result["ok"], result
    assert result["pid"] == 424243, result
    assert launched_scripts, result

    run_dir = _run_dir(result)
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    metadata = _read_json(run_dir / "metadata.json", {})

    assert metadata["mode"] == "interactive_tui", metadata
    assert metadata["approval_policy"] == "on-request", metadata
    assert metadata["requested_sandbox"] == "read-only", metadata
    assert metadata["model"] == bridge.CODEX_MODEL, metadata
    assert metadata["auto_close_after_report"] is True, metadata
    assert "Use the `firstmate` skill" in prompt, prompt
    assert "submit_captain_report" in prompt, prompt
    assert "Captain Report Handoff" in prompt, prompt
    assert "Keep fan-out bounded to at most 2 workers." in prompt, prompt
    assert "Claude-requested permission intent: read-only" in prompt, prompt
    assert "Self-contained interactive first-mate TUI dry-run" in prompt, prompt
    assert "Confirm this dry-run keeps the first-mate prompt contract." in prompt, prompt
    assert "codex.cmd" in script, script
    assert "--no-alt-screen" in script, script
    assert "--json" not in script, script
    assert "exec" not in script.split("$argsList", 1)[1].split("Write-Log", 1)[0], script
    return {"run_dir": str(run_dir), "script": str(launched_scripts[0])}


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
        " M tests/",
        "M  tests/",
        "M tests/",
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
        interrupt_current_turn=False,
    )
    assert steer["ok"] and steer["mode"] == "queued", steer
    assert "watch_command" in result and "CODEX-RUN-TERMINAL" in result["watch_command"], result
    _wait_completed(run_dir, ["E2E_INITIAL_OK", "E2E_STEERED_OK"], timeout_s=360)
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    watch = subprocess.run(
        [git_bash if os.path.exists(git_bash) else "bash", "-c", result["watch_command"]],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert watch.returncode == 0 and "CODEX-RUN-TERMINAL" in watch.stdout, watch.stdout
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
    launched_modes = {"launched_resume", "launched_restart_after_interrupt"}
    assert steer["mode"] in launched_modes | {"queued_interrupt_failed", "queued_no_interrupt_no_pid"}, steer
    if steer["mode"] not in launched_modes:
        raise AssertionError(f"interrupt did not launch follow-up run: {steer}")
    followup = _run_dir(steer["followup_run"])
    _wait_completed(followup, ["E2E_INTERRUPTED_OK"], timeout_s=300)
    return {"run_dir": str(followup), "mode": steer["mode"], "thread_id": _thread_id(followup)}


def case_supervision_review_cycle() -> dict[str, Any]:
    skill_text = (
        ROOT / "plugin" / "skills" / "claude-manages-codex" / "SKILL.md"
    ).read_text(encoding="utf-8")
    required_contract = (
        "## Mandatory 10-Minute Direct Supervision",
        "not a liveness probe",
        "on-track / off-track verdict",
        "A steer issued without first reading the recent work is not supervision",
        "A liveness or status-only poll never counts.",
        "always spawns as a non-interactive visible CLI worker by default",
        "The interactive TUI tools are deprecated because they can flash-close",
        "cannot receive programmatic steering in an open TUI",
        "Use a TUI only when the user explicitly asks for a hands-on interactive Codex terminal",
        "when in doubt, spawn the non-interactive worker",
        "## Parallel Fan-Out Contract",
        "Serial spawning is a manager error, not a bridge limit.",
        "spawn every non-interactive worker first, before reading any result",
        "## Completion Watcher Contract",
        "Never end a turn waiting for Codex without a watcher armed",
        "## Codex Run Ownership and Subagent Handoff",
        "exactly one owner: the main Claude manager loop",
        "Codex runs handed off",
    )
    for phrase in required_contract:
        assert phrase in skill_text, phrase

    result = bridge.start_visible_codex_worker(
        prompt=(
            'Self-contained supervision E2E. Do not edit files. Reply with exactly '
            '"SUPERVISION_PHASE_1 current-assumption: awaiting captain review" and '
            "nothing else, then stop."
        ),
        cwd=str(ROOT),
        title="E2E supervision review cycle",
        sandbox="read-only",
        session_context=SESSION_CONTEXT,
        steer_idle_seconds=90,
    )
    run_dir = _run_dir(result)
    display = run_dir / "display.log"
    deadline = time.time() + 240
    reviewed_line = ""
    while time.time() < deadline:
        if display.exists():
            lines = display.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            reviewed_line = next((line for line in lines if "SUPERVISION_PHASE_1" in line), "")
        if reviewed_line:
            break
        time.sleep(2)
    if not reviewed_line:
        raise AssertionError(f"timed out waiting for SUPERVISION_PHASE_1: {run_dir}\n{_tail(display)}")

    steer = bridge.steer_visible_codex_run(
        run_dir=str(run_dir),
        instruction=(
            f'Captain supervision pass. I reviewed your latest output: "{reviewed_line}". '
            "Verdict: on-track. Now reply with exactly SUPERVISION_PASS_OK and nothing else."
        ),
        interrupt_current_turn=False,
    )
    assert steer["ok"], steer
    steer_sig = inspect.signature(bridge.steer_visible_codex_run)
    assert (
        steer_sig.parameters["interrupt_current_turn"].default is True
    ), "steer_visible_codex_run must deliver directly (interrupt) by default"
    _wait_completed(run_dir, ["SUPERVISION_PHASE_1", "SUPERVISION_PASS_OK"], timeout_s=360)

    steer_files = sorted((run_dir / "steer_done").glob("*.md"))
    if not steer_files:
        steer_files = sorted((run_dir / "steer_queue").glob("*.md"))
    assert steer_files, steer
    steer_text = steer_files[-1].read_text(encoding="utf-8")
    assert "SUPERVISION_PHASE_1" in steer_text, steer_text
    return {"run_dir": str(run_dir), "reviewed_line": reviewed_line}


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


# --- Grok worker backend + availability-check E2E cases (added 2026-07-14) ---
# Additive only: no existing case_* function above this point is modified.
# Run in isolation with `python tests/e2e_visible_bridge.py --grok-only
# [--skip-expensive]` so a broken Codex login (existing cases 5+ require a
# live Codex login) never blocks these from running to completion.

GROK_SESSION_CONTEXT = (
    "Self-contained Grok E2E verification for the claude-manages-codex bridge Grok backend. "
    "Do not use read-past-sessions. Do not edit files. Return the requested marker exactly."
)


def _wait_grok_completed(run_dir: Path, markers: list[str], timeout_s: int = 240) -> str:
    """Same polling contract as _wait_completed, kept separate so a Grok-specific
    timeout/marker-set can be tuned without touching the Codex case's helper.

    Unlike _wait_completed, this tolerates a transient PermissionError on
    display.log: the PowerShell runner's Add-Content call briefly holds an
    exclusive handle while appending a line, and polling can race that handle
    open on Windows. A transient failure here just keeps last_text stale for
    one poll tick instead of crashing the whole E2E run."""
    display = run_dir / "display.log"
    deadline = time.time() + timeout_s
    last_status = "missing"
    last_text = ""
    while time.time() < deadline:
        last_status = _status(run_dir)
        if display.exists():
            try:
                last_text = display.read_text(encoding="utf-8-sig", errors="replace")
            except PermissionError:
                pass
        marker_ok = all(marker in last_text for marker in markers)
        if last_status.startswith("failed"):
            raise AssertionError(f"grok run failed: {run_dir}\nstatus={last_status}\n{_tail(display)}")
        if last_status in {"completed", "completed_budget_capped"} and marker_ok:
            _assert_launcher_exited(run_dir)
            return last_text
        time.sleep(2)
    missing = [marker for marker in markers if marker not in last_text]
    raise AssertionError(
        f"timed out waiting for grok run {run_dir}\nstatus={last_status}\nmissing={missing}\n{_tail(display)}"
    )


def case_grok_effort_unit() -> dict[str, Any]:
    assert bridge._grok_effort_flag("xhigh") == [], bridge._grok_effort_flag("xhigh")
    assert bridge._grok_effort_flag("max") == [], bridge._grok_effort_flag("max")
    assert bridge._grok_effort_flag("") == [], bridge._grok_effort_flag("")
    assert bridge._grok_effort_flag("high") == ["--reasoning-effort", "high"], bridge._grok_effort_flag("high")
    assert bridge._grok_effort_flag("MEDIUM") == ["--reasoning-effort", "medium"], bridge._grok_effort_flag("MEDIUM")
    assert bridge._grok_effort_flag("low") == ["--reasoning-effort", "low"], bridge._grok_effort_flag("low")
    assert bridge._grok_effort_flag("bogus") == [], bridge._grok_effort_flag("bogus")
    return {"ok": True}


def case_grok_borrowed_flags() -> dict[str, Any]:
    """Flags borrowed from the surveyed grok/Claude plugins (2026-07-15):
    strict read-only enforcement (--disallowed-tools Write,Edit), --best-of-n,
    and --check self-verification. Unit-checks the helpers plus the rendered
    run.ps1 for each config; deterministic, no live Grok."""
    # Helpers
    assert bridge._grok_read_only_args("read-only") == ["--disallowed-tools", "Write,Edit"], bridge._grok_read_only_args("read-only")
    assert bridge._grok_read_only_args("workspace-write") == [], bridge._grok_read_only_args("workspace-write")
    assert bridge._grok_read_only_args("") == [], bridge._grok_read_only_args("")
    assert bridge._grok_initial_extra_args(1, False) == [], bridge._grok_initial_extra_args(1, False)
    assert bridge._grok_initial_extra_args(3, False) == ["--best-of-n", "3"], bridge._grok_initial_extra_args(3, False)
    assert bridge._grok_initial_extra_args(99, False) == ["--best-of-n", "6"], "best_of_n must cap at 6"
    assert bridge._grok_initial_extra_args(1, True) == ["--check"], bridge._grok_initial_extra_args(1, True)
    assert bridge._grok_initial_extra_args(2, True) == ["--best-of-n", "2", "--check"], bridge._grok_initial_extra_args(2, True)

    # Rendered run.ps1
    rd = ROOT
    ro = bridge._grok_runner(rd, str(rd), "", sandbox="read-only")
    assert "--disallowed-tools" in ro and "Write,Edit" in ro, "read-only must strip Write,Edit"
    bo = bridge._grok_runner(rd, str(rd), "", sandbox="workspace-write", best_of_n=3)
    assert "--best-of-n" in bo and "'3'" in bo, "best_of_n=3 must render --best-of-n 3"
    sc = bridge._grok_runner(rd, str(rd), "", sandbox="workspace-write", self_check=True)
    assert "--check" in sc, "self_check must render --check"
    plain = bridge._grok_runner(rd, str(rd), "", sandbox="workspace-write")
    assert "--disallowed-tools" not in plain and "--best-of-n" not in plain and "--check" not in plain, "default worker must carry none of the borrowed flags"
    # best-of-n/check are gated to the fresh initial turn only (not resume/steer)
    assert "$TurnLabel -eq 'initial'" in bo, "best-of-n must be gated to the initial turn"
    return {"ok": True}


def case_grok_dry_run_args() -> dict[str, Any]:
    original_launch = bridge._launch
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 313131

    try:
        bridge._launch = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_grok_worker(
            prompt="Self-contained E2E dry-run. Do not edit files. Reply exactly DRY_RUN_UNUSED.",
            cwd=str(ROOT),
            title="E2E Grok dry-run",
            sandbox="read-only",
            session_context=GROK_SESSION_CONTEXT,
        )
    finally:
        bridge._launch = original_launch  # type: ignore[assignment]

    assert result["pid"] == 313131, result
    assert launched_scripts, result
    assert "watch_command" in result and result["watch_command"], result

    run_dir = _run_dir(result)
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    metadata = _read_json(run_dir / "metadata.json", {})

    assert metadata["agent"] == "grok", metadata
    assert metadata["model"] == bridge.GROK_MODEL, metadata
    assert metadata["requested_sandbox"] == "read-only", metadata
    assert metadata["sandbox"] == bridge.CODEX_FULL_TOOL_SANDBOX, metadata
    assert metadata["session_context_supplied"] is True, metadata
    assert metadata["captain_help_enabled"] is True, metadata
    assert metadata["captain_report_auto_write"] is True, metadata

    assert "grok.exe" in script or "grok" in script, script
    assert "--output-format" in script and "streaming-json" in script, script
    assert "-m" in script and bridge.GROK_MODEL in script, script
    assert "--prompt-file" in script, script
    assert "--permission-mode" in script and "bypassPermissions" in script, script
    assert "--reasoning-effort xhigh" not in script, script
    assert "--reasoning-effort max" not in script, script
    # -p/--single must never be combined with --prompt-file (confirmed live:
    # grok errors "a value is required for '--single <PROMPT>'" if it is).
    assert "'-p',$GrokPromptPath" not in script.replace(" ", ""), script
    assert "'-p','--prompt-file'" not in script.replace(" ", ""), script

    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    assert "submit_captain_report" in prompt, prompt
    assert "request_captain_help" in prompt, prompt
    assert str(run_dir) in prompt, prompt
    # grok-4.5 rigor contract (2026-07-15) must be injected into every grok prompt.
    assert "Worker Rigor Contract" in prompt, prompt
    assert "ACTUALLY RUN IT" in prompt and "UNVERIFIED" in prompt, "rigor contract must mandate e2e execution with proof"
    assert "ANTAGONISTICALLY" in prompt, "rigor contract must warn of adversarial captain review"
    # Parallel Competition Mode (default competition_agents=16) must be present + single-terminal.
    assert "Parallel Competition Mode" in prompt, prompt
    assert "up to 16" in prompt and "no new terminals" in prompt, "competition mode must offer up to 16 in-turn competitors"
    assert metadata["competition_agents"] == 16, metadata
    # Mandatory Parallel Work-Checker gate must be present on EVERY grok prompt.
    assert "Mandatory Parallel Work-Checker" in prompt, prompt
    assert "RE-RUN the checkers until they come back clean" in prompt, "work-checker must fix + re-run until clean before done"

    return {"run_dir": str(run_dir), "script": str(launched_scripts[0])}


def case_grok_haiku_composed_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 313132

    try:
        bridge._launch = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_haiku_composed_grok_worker(
            prompt_brief="Self-contained E2E dry-run brief. Ask Grok to reply exactly DRY_RUN_UNUSED and not edit files.",
            cwd=str(ROOT),
            title="E2E Grok Haiku composed dry-run",
            sandbox="read-only",
            session_context=GROK_SESSION_CONTEXT,
        )
    finally:
        bridge._launch = original_launch  # type: ignore[assignment]

    assert launched_scripts, result
    run_dir = _run_dir(result)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata["compose_with_haiku"] is True, metadata
    assert (run_dir / "composer_prompt.md").exists(), run_dir
    assert (run_dir / "grok_prelude.md").exists(), run_dir
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    assert "$ComposeWithHaiku = $true" in script, script
    return {"run_dir": str(run_dir)}


def case_grok_captain_report_gate() -> dict[str, Any]:
    """Deterministic proof that the shared captain callback tools accept Grok runs.
    The allowlist in submit_captain_report / request_captain_help was widened from
    (None, "codex") to (None, "codex", "grok", "agy") so non-Codex CLI workers can
    report back to Claude, while the codex-only steer gate is left codex-specific.
    A Grok run (metadata.agent == "grok") must now be accepted by both tools."""
    run_dir = bridge._make_run(
        str(ROOT),
        "grok",
        "E2E captain report gate probe",
        "Self-contained gate probe. Do not launch Grok.",
        {
            "agent": "grok",
            "cwd": str(ROOT),
            "requested_sandbox": "read-only",
        },
    )
    report = bridge.submit_captain_report(
        str(run_dir),
        outcome="completed",
        summary="Grok run should be accepted by the widened allowlist.",
    )
    assert report["ok"] is True, report
    assert (run_dir / "captain_reports" / "final.json").exists(), report

    help_request = bridge.request_captain_help(
        str(run_dir),
        question="Grok run should be accepted by the same widened allowlist.",
    )
    assert help_request["ok"] is True, help_request

    # The backend-agnostic read tools carry no such gate and work for any agent.
    status = bridge.get_visible_run_status(str(run_dir), tail_lines=5)
    assert status["metadata"]["agent"] == "grok", status
    listed = bridge.list_visible_runs(str(ROOT), limit=50)
    assert any(item["run_dir"] == str(run_dir) for item in listed), listed
    return {"run_dir": str(run_dir), "submit_captain_report_accepted": True, "request_captain_help_accepted": True}


def case_check_worker_backends() -> dict[str, Any]:
    cheap = bridge.check_worker_backends(cwd=str(ROOT), deep=False)
    for key in ("claude_sonnet", "grok", "codex", "agy", "cursor_agent"):
        assert key in cheap, cheap
        for field in ("available", "reason", "detail"):
            assert field in cheap[key], (key, cheap)
    assert cheap["claude_sonnet"]["available"] is True, cheap

    # deep=True is required for an accurate Codex verdict on this machine: the
    # local access-token JWT is well-formed and unexpired, and `codex login
    # status` itself exits 0 ("Logged in using ChatGPT"), even though the
    # ChatGPT session was actually revoked server-side (observed live: HTTP 401
    # token_invalidated / refresh_token_invalidated). Only the deep live probe
    # catches that.
    deep = bridge.check_worker_backends(cwd=str(ROOT), deep=True)
    assert deep["claude_sonnet"]["available"] is True, deep
    assert deep["codex"]["available"] is False, deep
    assert deep["codex"]["reason"], deep
    return {"cheap": cheap, "deep": deep}


def case_grok_live_roundtrip_and_mcp_callback() -> dict[str, Any]:
    """LIVE (expensive). One live grok-4.5 call does double duty: proves the
    GROK_E2E_OK round trip (Layer 1 auto-report) and attempts a live
    submit_captain_report MCP callback (Layer 2), reporting back the raw tool
    result so this assertion is a real observed outcome, not a guess."""
    result = bridge.start_visible_grok_worker(
        prompt=(
            "Self-contained E2E. Do not edit files. First, call the submit_captain_report "
            "MCP tool if it is available (from the agent-visibility MCP server), with "
            "run_dir set to the exact run directory named in your permission contract above, "
            'outcome="completed", summary="GROK_E2E_OK". Report back the raw JSON result of '
            "that tool call, prefixed exactly with MCP_RESULT:. If the tool is not available, "
            "write MCP_RESULT: unavailable instead. Then, on its own line, reply with exactly "
            "GROK_E2E_OK and nothing else."
        ),
        cwd=str(ROOT),
        title="E2E Grok live roundtrip + MCP callback",
        sandbox="read-only",
        session_context=GROK_SESSION_CONTEXT,
        steer_idle_seconds=10,
        competition_agents=1,  # trivial token-reply task: keep it single-agent + deterministic
    )
    run_dir = _run_dir(result)
    text = _wait_grok_completed(run_dir, ["GROK_E2E_OK"], timeout_s=240)

    events_path = run_dir / "events.jsonl"
    events_text = events_path.read_text(encoding="utf-8-sig", errors="replace")
    assert '"type":"end"' in events_text or '"type": "end"' in events_text, events_text[-2000:]

    session_id_path = run_dir / "session_id.txt"
    assert session_id_path.exists(), run_dir
    session_id = session_id_path.read_text(encoding="utf-8-sig").strip()
    assert session_id, "session_id.txt was empty"

    final_md = (run_dir / "captain_reports" / "final.md").read_text(encoding="utf-8-sig")
    assert "GROK_E2E_OK" in final_md, final_md
    final_json = _read_json(run_dir / "captain_reports" / "final.json", {})
    assert final_json.get("outcome") == "completed", final_json
    # After the callback-gate fix, a grok worker's live submit_captain_report is
    # accepted, so its explicit report is authoritative and the runner defers its
    # own auto-report (the Test-WorkerReportSince guard). Accept either the
    # worker's report (Layer 2 live callback) or the runner auto-report (Layer 1
    # fallback, used when the model did not call the tool this turn).
    is_worker_report = final_json.get("auto_generated") is not True and "-report-" in str(final_json.get("report_id", ""))
    is_auto_report = final_json.get("auto_generated") is True and final_json.get("agent") == "grok"
    assert is_worker_report or is_auto_report, final_json
    summary_text = str(final_json.get("summary", "")) + str(final_json.get("text", ""))
    assert "GROK_E2E_OK" in summary_text, final_json

    # The deterministic case_grok_captain_report_gate hard-proves the widened
    # allowlist accepts a grok run; here we additionally record whether the live
    # worker's own callback won (is_worker_report) vs the auto-report fallback.
    return {
        "run_dir": str(run_dir),
        "session_id": session_id,
        "live_callback_won": is_worker_report,
    }


def case_grok_live_steer_resume(previous: dict[str, Any]) -> dict[str, Any]:
    """LIVE (expensive). Steers the completed run from
    case_grok_live_roundtrip_and_mcp_callback with a trivial follow-up and
    confirms a second turn actually ran (new events appended, new end event,
    session id unchanged)."""
    run_dir = Path(previous["run_dir"])
    events_before = (run_dir / "events.jsonl").read_text(encoding="utf-8-sig", errors="replace")
    end_count_before = events_before.count('"type":"end"') + events_before.count('"type": "end"')

    steer = bridge.steer_visible_grok_run(
        str(run_dir),
        "Self-contained steering E2E. Reply with exactly GROK_STEERED_OK and nothing else. Do not edit files.",
        title="E2E Grok steer follow-up",
        sandbox="read-only",
        session_context=GROK_SESSION_CONTEXT,
        launch_if_closed=True,
        interrupt_current_turn=False,
    )
    assert steer["ok"], steer

    if steer["mode"] == "launched_resume":
        followup_dir = _run_dir(steer["followup_run"])
        _wait_grok_completed(followup_dir, ["GROK_STEERED_OK"], timeout_s=240)
        followup_session = (followup_dir / "session_id.txt").read_text(encoding="utf-8-sig").strip()
        assert followup_session == previous["session_id"], (followup_session, previous["session_id"])
        return {"run_dir": str(followup_dir), "mode": steer["mode"], "session_id": followup_session}

    # queued modes: the same run_dir picks up the steer file in its idle window.
    _wait_grok_completed(run_dir, ["GROK_E2E_OK", "GROK_STEERED_OK"], timeout_s=240)
    events_after = (run_dir / "events.jsonl").read_text(encoding="utf-8-sig", errors="replace")
    end_count_after = events_after.count('"type":"end"') + events_after.count('"type": "end"')
    assert end_count_after > end_count_before, (end_count_after, end_count_before)
    return {"run_dir": str(run_dir), "mode": steer["mode"], "session_id": previous["session_id"]}


def run_grok_suite(skip_expensive: bool) -> dict[str, Any]:
    results: dict[str, Any] = {}

    print("[grok 1/8] effort flag unit", flush=True)
    results["effort_unit"] = case_grok_effort_unit()

    print("[grok 1b/8] borrowed flags (read-only enforce / best-of-n / self-check)", flush=True)
    results["borrowed_flags"] = case_grok_borrowed_flags()

    print("[grok 2/8] dry-run arg assertions", flush=True)
    results["dry_run"] = case_grok_dry_run_args()
    print(json.dumps(results["dry_run"], indent=2), flush=True)

    print("[grok 3/8] Haiku-composed dry-run", flush=True)
    results["haiku_dry_run"] = case_grok_haiku_composed_dry_run()
    print(json.dumps(results["haiku_dry_run"], indent=2), flush=True)

    print("[grok 4/8] captain report / help gate (deterministic)", flush=True)
    results["captain_report_gate"] = case_grok_captain_report_gate()
    print(json.dumps(results["captain_report_gate"], indent=2), flush=True)

    print("[grok 5/8] check_worker_backends (cheap + deep)", flush=True)
    results["availability"] = case_check_worker_backends()
    print(json.dumps(results["availability"], indent=2), flush=True)

    if skip_expensive:
        print("[grok 6-7/8] SKIPPED (--skip-expensive): live roundtrip + steer", flush=True)
        results["live_roundtrip"] = "skipped"
        results["live_steer"] = "skipped"
    else:
        print("[grok 6/8] LIVE roundtrip + MCP callback attempt", flush=True)
        results["live_roundtrip"] = case_grok_live_roundtrip_and_mcp_callback()
        print(json.dumps(results["live_roundtrip"], indent=2), flush=True)

        print("[grok 7/8] LIVE steer/resume", flush=True)
        results["live_steer"] = case_grok_live_steer_resume(results["live_roundtrip"])
        print(json.dumps(results["live_steer"], indent=2), flush=True)

    print("[grok 8/8] done", flush=True)
    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)
    return results


# --- Antigravity (agy) worker backend E2E cases (added 2026-07-14) ---
# Additive only: no existing case_* function above this point is modified,
# including the Grok cases just above. Run in isolation with
# `python tests/e2e_visible_bridge.py --agy-only [--skip-expensive]` so a
# broken Codex login or missing Grok auth never blocks these from running to
# completion.

AGY_SESSION_CONTEXT = (
    "Self-contained Antigravity (agy) E2E verification for the claude-manages-codex bridge agy backend. "
    "Do not use read-past-sessions. Do not edit files. Return the requested marker exactly."
)


def _wait_agy_completed(run_dir: Path, markers: list[str], timeout_s: int = 180) -> str:
    """Same polling contract as _wait_grok_completed, kept separate so an
    agy-specific timeout/marker-set can be tuned independently. agy turns are
    single blocking CLI calls (no incremental streaming; see _agy_runner), so
    display.log only gains new content once each turn's process exits."""
    display = run_dir / "display.log"
    deadline = time.time() + timeout_s
    last_status = "missing"
    last_text = ""
    while time.time() < deadline:
        last_status = _status(run_dir)
        if display.exists():
            try:
                last_text = display.read_text(encoding="utf-8-sig", errors="replace")
            except PermissionError:
                pass
        marker_ok = all(marker in last_text for marker in markers)
        if last_status.startswith("failed"):
            raise AssertionError(f"agy run failed: {run_dir}\nstatus={last_status}\n{_tail(display)}")
        if last_status in {"completed", "completed_budget_capped"} and marker_ok:
            _assert_launcher_exited(run_dir)
            return last_text
        time.sleep(2)
    missing = [marker for marker in markers if marker not in last_text]
    raise AssertionError(
        f"timed out waiting for agy run {run_dir}\nstatus={last_status}\nmissing={missing}\n{_tail(display)}"
    )


def case_agy_effort_unit() -> dict[str, Any]:
    assert bridge._agy_model_for_effort("high") == "Gemini 3.7 Flash (High)", bridge._agy_model_for_effort("high")
    assert bridge._agy_model_for_effort("HIGH") == "Gemini 3.7 Flash (High)", bridge._agy_model_for_effort("HIGH")
    assert bridge._agy_model_for_effort("medium") == "Gemini 3.7 Flash (Medium)", bridge._agy_model_for_effort("medium")
    assert bridge._agy_model_for_effort("low") == "Gemini 3.7 Flash (Low)", bridge._agy_model_for_effort("low")
    assert bridge._agy_model_for_effort("") == bridge.AGY_DEFAULT_MODEL, bridge._agy_model_for_effort("")
    assert bridge._agy_model_for_effort("xhigh") == bridge.AGY_DEFAULT_MODEL, bridge._agy_model_for_effort("xhigh")
    assert bridge._agy_model_for_effort("bogus") == bridge.AGY_DEFAULT_MODEL, bridge._agy_model_for_effort("bogus")
    assert bridge.AGY_DEFAULT_MODEL == "Gemini 3.7 Flash (High)", bridge.AGY_DEFAULT_MODEL
    assert bridge.AGY_MODELS_BY_EFFORT == {
        "high": "Gemini 3.7 Flash (High)",
        "medium": "Gemini 3.7 Flash (Medium)",
        "low": "Gemini 3.7 Flash (Low)",
    }, bridge.AGY_MODELS_BY_EFFORT
    return {"ok": True}


def case_agy_dry_run_args() -> dict[str, Any]:
    original_launch = bridge._launch
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 515151

    try:
        bridge._launch = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_agy_worker(
            prompt="Self-contained E2E dry-run. Do not edit files. Reply exactly DRY_RUN_UNUSED.",
            cwd=str(ROOT),
            title="E2E Antigravity dry-run",
            sandbox="read-only",
            session_context=AGY_SESSION_CONTEXT,
        )
    finally:
        bridge._launch = original_launch  # type: ignore[assignment]

    assert result["pid"] == 515151, result
    assert launched_scripts, result
    assert "watch_command" in result and result["watch_command"], result

    run_dir = _run_dir(result)
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    metadata = _read_json(run_dir / "metadata.json", {})

    assert metadata["agent"] == "agy", metadata
    assert metadata["model"] == bridge.AGY_DEFAULT_MODEL, metadata
    assert metadata["effective_reasoning_effort"] == "high", metadata
    assert metadata["requested_sandbox"] == "read-only", metadata
    assert metadata["sandbox"] == bridge.CODEX_FULL_TOOL_SANDBOX, metadata
    assert metadata["session_context_supplied"] is True, metadata
    assert metadata["captain_report_auto_write"] is True, metadata
    assert metadata["no_session_id"] is True, metadata
    assert metadata["resume_continue"] is False, metadata

    assert "agy" in script, script
    assert "Gemini 3.7 Flash (High)" in script, script
    assert "--dangerously-skip-permissions" in script, script
    assert "--add-dir" in script, script

    # The two lines that build agy's OWN $argsList (initial turn + the
    # --continue turn) must never include --reasoning-effort or
    # --output-format: agy has neither flag (see agy --help). The unrelated
    # Haiku prompt-composer sub-block further down the script legitimately
    # uses --output-format for ITS OWN call to $Claude when
    # compose_with_haiku=True; that block does not touch $argsList and is
    # checked separately in case_agy_haiku_composed_dry_run.
    argslist_lines = [line for line in script.splitlines() if "$argsList" in line and "@(" in line]
    assert len(argslist_lines) == 2, script
    for line in argslist_lines:
        assert "--reasoning-effort" not in line, line
        assert "--output-format" not in line, line
    assert "--reasoning-effort" not in script, script
    assert "--prompt-file" not in script, script

    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    assert str(run_dir) in prompt, prompt
    # agy has no live MCP callback wired; the prompt must not falsely tell
    # the worker to call submit_captain_report/request_captain_help (unlike
    # the Codex/Grok prompts, which do include that contract).
    assert "submit_captain_report" not in prompt, prompt
    assert "request_captain_help" not in prompt, prompt

    return {"run_dir": str(run_dir), "script": str(launched_scripts[0])}


def case_agy_haiku_composed_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch
    launched_scripts: list[Path] = []

    def fake_launch(script_path: Path) -> int:
        launched_scripts.append(script_path)
        return 515152

    try:
        bridge._launch = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_haiku_composed_agy_worker(
            prompt_brief="Self-contained E2E dry-run brief. Ask Antigravity to reply exactly DRY_RUN_UNUSED and not edit files.",
            cwd=str(ROOT),
            title="E2E Antigravity Haiku composed dry-run",
            sandbox="read-only",
            session_context=AGY_SESSION_CONTEXT,
        )
    finally:
        bridge._launch = original_launch  # type: ignore[assignment]

    assert launched_scripts, result
    run_dir = _run_dir(result)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata["compose_with_haiku"] is True, metadata
    assert (run_dir / "composer_prompt.md").exists(), run_dir
    assert (run_dir / "agy_prelude.md").exists(), run_dir
    script = launched_scripts[0].read_text(encoding="utf-8-sig")
    assert "$ComposeWithHaiku = $true" in script, script
    # This IS the one place --output-format legitimately appears: the Haiku
    # composer's own call to $Claude, not agy's argsList (checked negatively
    # in case_agy_dry_run_args).
    assert "--output-format" in script, script
    assert "'stream-json'" in script, script
    return {"run_dir": str(run_dir)}


def case_agy_captain_report_gate() -> dict[str, Any]:
    """Deterministic proof that the shared captain callback tools accept agy runs.
    The allowlist in submit_captain_report / request_captain_help was widened to
    (None, "codex", "grok", "agy"), so a metadata.agent == "agy" run must be
    accepted by both tools. This only proves the allowlist gate -- agy cannot
    reach these tools on its own mid-run until a live MCP callback is wired
    (deferred; see SKILL.md and case_agy_dry_run_args's prompt assertions)."""
    run_dir = bridge._make_run(
        str(ROOT),
        "agy",
        "E2E captain report gate probe",
        "Self-contained gate probe. Do not launch Antigravity.",
        {
            "agent": "agy",
            "cwd": str(ROOT),
            "requested_sandbox": "read-only",
        },
    )
    report = bridge.submit_captain_report(
        str(run_dir),
        outcome="completed",
        summary="Antigravity (agy) run should be accepted by the widened allowlist.",
    )
    assert report["ok"] is True, report
    assert (run_dir / "captain_reports" / "final.json").exists(), report

    help_request = bridge.request_captain_help(
        str(run_dir),
        question="Antigravity (agy) run should be accepted by the same widened allowlist.",
    )
    assert help_request["ok"] is True, help_request

    status = bridge.get_visible_run_status(str(run_dir), tail_lines=5)
    assert status["metadata"]["agent"] == "agy", status
    listed = bridge.list_visible_runs(str(ROOT), limit=50)
    assert any(item["run_dir"] == str(run_dir) for item in listed), listed
    return {"run_dir": str(run_dir), "submit_captain_report_accepted": True, "request_captain_help_accepted": True}


def case_agy_live_roundtrip() -> dict[str, Any]:
    """LIVE (expensive). Proves the AGY_E2E_OK round trip through Layer 1
    (the runner's own auto-report to captain_reports/final.json+final.md),
    since agy has no live MCP callback wired (Layer 2 is not attempted)."""
    result = bridge.start_visible_agy_worker(
        prompt=(
            "Self-contained E2E. Do not edit files. Reply with exactly AGY_E2E_OK and nothing else."
        ),
        cwd=str(ROOT),
        title="E2E Antigravity live roundtrip",
        sandbox="read-only",
        session_context=AGY_SESSION_CONTEXT,
        steer_idle_seconds=10,
    )
    run_dir = _run_dir(result)
    text = _wait_agy_completed(run_dir, ["AGY_E2E_OK"], timeout_s=180)

    output_path = run_dir / "output.txt"
    assert output_path.exists(), run_dir
    assert "AGY_E2E_OK" in output_path.read_text(encoding="utf-8-sig", errors="replace"), text

    final_md = (run_dir / "captain_reports" / "final.md").read_text(encoding="utf-8-sig")
    assert "AGY_E2E_OK" in final_md, final_md
    final_json = _read_json(run_dir / "captain_reports" / "final.json", {})
    assert final_json.get("outcome") == "completed", final_json
    assert final_json.get("agent") == "agy", final_json
    assert final_json.get("auto_generated") is True, final_json
    assert final_json.get("model") == bridge.AGY_DEFAULT_MODEL, final_json
    assert "AGY_E2E_OK" in (final_json.get("text") or ""), final_json

    return {"run_dir": str(run_dir)}


def case_agy_live_steer_resume(previous: dict[str, Any]) -> dict[str, Any]:
    """LIVE (expensive). Steers the run from case_agy_live_roundtrip and
    confirms a second turn actually ran, mirroring the adaptive branch in
    case_grok_live_steer_resume rather than assuming a specific pre-state.

    case_agy_live_roundtrip's own wait loop only returns once status.json
    says "completed", which for agy only happens AFTER the full
    steer_idle_seconds idle window has already elapsed and the PowerShell
    window has closed (agy has no mid-run structured "turn ended, now idle"
    signal to catch mid-flight the way grok's JSON stream does). So by the
    time this case runs, the window is essentially always already closed --
    polling for a transient "waiting_for_steer" state here would be racing
    a window that already exited. Instead this calls steer_visible_agy_run
    with launch_if_closed=True and branches on the returned mode, exactly
    like the Grok case does, so it is correct whether the window is still
    open (mode="queued", picked up via the SAME window's idle --continue
    loop) or already closed (mode="launched_resume", a brand-new agy
    --continue call in the same cwd -- verified live to correctly recall
    context from the first turn)."""
    run_dir = Path(previous["run_dir"])

    steer = bridge.steer_visible_agy_run(
        str(run_dir),
        "Self-contained steering E2E. Reply with exactly AGY_STEERED_OK and nothing else. Do not edit files.",
        title="E2E Antigravity steer follow-up",
        sandbox="read-only",
        launch_if_closed=True,
        interrupt_current_turn=False,
    )
    assert steer["ok"], steer
    assert steer["mode"] in {"queued", "launched_resume"}, steer

    if steer["mode"] == "launched_resume":
        followup_dir = _run_dir(steer["followup_run"])
        _wait_agy_completed(followup_dir, ["AGY_STEERED_OK"], timeout_s=180)
        followup_output = (followup_dir / "output.txt").read_text(encoding="utf-8-sig", errors="replace")
        assert "AGY_STEERED_OK" in followup_output, followup_output
        followup_metadata = _read_json(followup_dir / "metadata.json", {})
        assert followup_metadata.get("resume_continue") is True, followup_metadata
        return {"run_dir": str(followup_dir), "mode": steer["mode"]}

    # Queued mode: the same run_dir picks up the steer file in its idle window.
    _wait_agy_completed(run_dir, ["AGY_E2E_OK", "AGY_STEERED_OK"], timeout_s=180)
    output_text = (run_dir / "output.txt").read_text(encoding="utf-8-sig", errors="replace")
    assert "AGY_E2E_OK" in output_text and "AGY_STEERED_OK" in output_text, output_text
    return {"run_dir": str(run_dir), "mode": steer["mode"]}


def run_agy_suite(skip_expensive: bool) -> dict[str, Any]:
    results: dict[str, Any] = {}

    print("[agy 1/7] effort->model unit", flush=True)
    results["effort_unit"] = case_agy_effort_unit()

    print("[agy 2/7] dry-run arg assertions", flush=True)
    results["dry_run"] = case_agy_dry_run_args()
    print(json.dumps(results["dry_run"], indent=2), flush=True)

    print("[agy 3/7] Haiku-composed dry-run", flush=True)
    results["haiku_dry_run"] = case_agy_haiku_composed_dry_run()
    print(json.dumps(results["haiku_dry_run"], indent=2), flush=True)

    print("[agy 4/7] captain report / help gate (deterministic)", flush=True)
    results["captain_report_gate"] = case_agy_captain_report_gate()
    print(json.dumps(results["captain_report_gate"], indent=2), flush=True)

    print("[agy 5/7] check_worker_backends (cheap + deep)", flush=True)
    results["availability"] = case_check_worker_backends()
    print(json.dumps(results["availability"], indent=2), flush=True)

    if skip_expensive:
        print("[agy 6-7/7] SKIPPED (--skip-expensive): live roundtrip + steer", flush=True)
        results["live_roundtrip"] = "skipped"
        results["live_steer"] = "skipped"
    else:
        print("[agy 6/7] LIVE roundtrip", flush=True)
        results["live_roundtrip"] = case_agy_live_roundtrip()
        print(json.dumps(results["live_roundtrip"], indent=2), flush=True)

        print("[agy 7/7] LIVE queued steer/resume", flush=True)
        results["live_steer"] = case_agy_live_steer_resume(results["live_roundtrip"])
        print(json.dumps(results["live_steer"], indent=2), flush=True)

    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)
    return results


# --- Cursor agent worker backend cases (added 2026-08-26) ---

CURSOR_SESSION_CONTEXT = (
    "Self-contained Cursor-agent E2E verification for the multi-agentic harness. "
    "Do not use read-past-sessions. Do not edit files. Return the requested marker exactly."
)


def case_cursor_effort_unit() -> dict[str, Any]:
    assert bridge._cursor_model_for_effort("") == bridge.CURSOR_DEFAULT_MODEL
    assert bridge._cursor_model_for_effort("xhigh") == "cursor-grok-4.6-xhigh-fast"
    assert bridge._cursor_model_for_effort("high") == "cursor-grok-4.6-high-fast"
    assert bridge._cursor_model_for_effort("low") == "cursor-grok-4.6-low-fast"
    assert bridge._cursor_model_for_effort("medium") == "cursor-grok-4.6-medium-fast"
    assert bridge._cursor_model_for_effort("xhigh", "composer-2.5-fast") == "composer-2.5-fast"
    argv = bridge._resolve_cursor_agent_argv()
    assert argv, argv
    return {"ok": True, "argv": argv, "default_model": bridge.CURSOR_DEFAULT_MODEL}


def case_cursor_dry_run_args() -> dict[str, Any]:
    original_launch = bridge._launch_visible_python
    launched: list[Path] = []

    def fake_launch(script_path: Path, run_dir: Path, env: dict[str, str] | None = None) -> int:
        launched.append(script_path)
        return 414141

    try:
        bridge._launch_visible_python = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_cursor_worker(
            prompt="Self-contained E2E dry-run. Do not edit files. Reply exactly DRY_RUN_UNUSED.",
            cwd=str(ROOT),
            title="E2E Cursor dry-run",
            sandbox="read-only",
            session_context=CURSOR_SESSION_CONTEXT,
        )
    finally:
        bridge._launch_visible_python = original_launch  # type: ignore[assignment]

    assert result.get("pid") == 414141, result
    assert launched, result
    assert launched[0] == bridge.CURSOR_WORKER_RUNNER, launched
    assert "watch_command" in result and result["watch_command"], result
    assert "supervise_command" in result and "captain_checkup.py" in result["supervise_command"], result
    assert "sleep 600" in result["supervise_command"], result

    run_dir = _run_dir(result)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata["agent"] == "cursor", metadata
    assert metadata["model"] == bridge.CURSOR_DEFAULT_MODEL, metadata
    assert metadata["requested_sandbox"] == "read-only", metadata
    assert metadata["captain_help_enabled"] is True, metadata
    assert metadata["captain_report_auto_write"] is True, metadata
    assert metadata.get("cursor_agent_argv"), metadata
    assert metadata.get("max_mode", {}).get("ok") is True, metadata
    assert metadata.get("max_mode", {}).get("maxMode") is True, metadata

    prompt = (run_dir / "prompt.md").read_text(encoding="utf-8-sig")
    assert "submit_captain_report" in prompt, prompt
    assert "request_captain_help" in prompt, prompt
    assert str(run_dir) in prompt, prompt
    assert "Worker Rigor Contract" in prompt, prompt

    runner = bridge.CURSOR_WORKER_RUNNER.read_text(encoding="utf-8")
    assert "--output-format" in runner and "stream-json" in runner, runner
    assert "--mode" in runner and "plan" in runner, runner
    assert "--resume" in runner, runner
    return {"run_dir": str(run_dir), "script": str(launched[0])}


def case_cursor_haiku_composed_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch_visible_python
    launched: list[Path] = []

    def fake_launch(script_path: Path, run_dir: Path, env: dict[str, str] | None = None) -> int:
        launched.append(script_path)
        return 414142

    try:
        bridge._launch_visible_python = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_haiku_composed_cursor_worker(
            prompt_brief="Self-contained E2E dry-run brief. Ask the worker to reply exactly DRY_RUN_UNUSED.",
            cwd=str(ROOT),
            title="E2E Cursor Haiku composed dry-run",
            sandbox="read-only",
            session_context=CURSOR_SESSION_CONTEXT,
        )
    finally:
        bridge._launch_visible_python = original_launch  # type: ignore[assignment]

    assert launched, result
    run_dir = _run_dir(result)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata["compose_with_haiku"] is True, metadata
    assert (run_dir / "composer_prompt.md").exists(), run_dir
    assert (run_dir / "cursor_prelude.md").exists(), run_dir
    return {"run_dir": str(run_dir)}


def case_captain_checkup_script() -> dict[str, Any]:
    """The 10-minute captain script must brief recent work, not just liveness."""
    script = ROOT / "captain_checkup.py"
    assert script.is_file(), script
    run_dir = bridge._make_run(
        str(ROOT),
        "cursor",
        "E2E captain checkup",
        "Implement the wrong file on purpose so the captain has something to judge.",
        {"agent": "cursor", "cwd": str(ROOT), "model": bridge.CURSOR_DEFAULT_MODEL, "requested_sandbox": "workspace-write"},
    )
    (run_dir / "display.log").write_text(
        "Starting Cursor turn: initial\nEdit src/wrong_file.py\npytest not run\n",
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(
        json.dumps({"type": "tool_use", "name": "Edit"}) + "\n"
        + json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}})
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"status": "running:initial"}),
        encoding="utf-8",
    )
    (run_dir / "launcher_pid.txt").write_text("1", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), "--run-dir", str(run_dir), "--cwd", str(ROOT), "--since-minutes", "10"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for phrase in (
        "ALIVE != ON-TRACK",
        "A liveness or status-only poll never counts",
        "wrong_file.py",
        "Edit",
        "Captain verdict",
        "off-track",
        "CAPTAIN-SUPERVISION-DUE",
        run_dir.name,
    ):
        assert phrase in out, (phrase, out[-2000:])
    skill_text = (ROOT / "plugin" / "skills" / "claude-manages-codex" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in (
        "captain_checkup.py",
        "supervise_command",
        "Alive is not on-track",
        "A liveness or status-only poll never counts",
    ):
        assert phrase in skill_text, phrase
    return {"run_dir": str(run_dir), "ok": True}


def case_cursor_captain_report_gate() -> dict[str, Any]:
    run_dir = bridge._make_run(
        str(ROOT),
        "cursor",
        "E2E captain report gate probe",
        "Self-contained gate probe. Do not launch cursor-agent.",
        {
            "agent": "cursor",
            "cwd": str(ROOT),
            "requested_sandbox": "read-only",
        },
    )
    report = bridge.submit_captain_report(
        str(run_dir),
        outcome="completed",
        summary="Cursor run should be accepted by the widened allowlist.",
    )
    assert report["ok"] is True, report
    help_request = bridge.request_captain_help(
        str(run_dir),
        question="Cursor run should be accepted by the same widened allowlist.",
    )
    assert help_request["ok"] is True, help_request
    status = bridge.get_visible_run_status(str(run_dir), tail_lines=5)
    assert status["metadata"]["agent"] == "cursor", status
    return {
        "run_dir": str(run_dir),
        "submit_captain_report_accepted": True,
        "request_captain_help_accepted": True,
    }


CURSOR_LIVE_MARKER = "CURSOR_E2E_OK"
CURSOR_STEER_MARKER = "CURSOR_STEERED_OK"


def _wait_cursor_completed(run_dir: Path, markers: list[str], timeout_s: int = 300) -> str:
    """Poll a visible cursor-agent run until it completes with the expected markers."""
    display = run_dir / "display.log"
    deadline = time.time() + timeout_s
    last_status = "missing"
    last_text = ""
    while time.time() < deadline:
        last_status = _status(run_dir)
        if display.exists():
            try:
                last_text = display.read_text(encoding="utf-8-sig", errors="replace")
            except PermissionError:
                pass
        marker_ok = all(marker in last_text for marker in markers)
        if last_status.startswith("failed"):
            raise AssertionError(
                f"cursor run failed: {run_dir}\nstatus={last_status}\n{_tail(display)}"
            )
        if last_status in {"completed", "completed_budget_capped"} and marker_ok:
            _assert_launcher_exited(run_dir)
            return last_text
        time.sleep(2)
    missing = [marker for marker in markers if marker not in last_text]
    raise AssertionError(
        f"timed out waiting for cursor run {run_dir}\nstatus={last_status}\nmissing={missing}\n{_tail(display)}"
    )


def case_cursor_deployed_bridge_in_sync() -> dict[str, Any]:
    """The Claude Code MCP process loads ~/.agent-bridge, not the git checkout."""
    deployed_bridge = Path.home() / ".agent-bridge" / "visible_agent_bridge.py"
    deployed_runner = Path.home() / ".agent-bridge" / "cursor_worker_runner.py"
    assert deployed_bridge.is_file(), deployed_bridge
    assert deployed_runner.is_file(), deployed_runner
    assert deployed_runner.read_bytes() == bridge.CURSOR_WORKER_RUNNER.read_bytes(), (
        "cursor_worker_runner.py in ~/.agent-bridge is stale vs the git checkout"
    )
    return {
        "deployed_bridge": str(deployed_bridge),
        "deployed_runner": str(deployed_runner),
        "runner_in_sync": True,
    }


def case_cursor_live_roundtrip() -> dict[str, Any]:
    """LIVE. Opens a console, runs cursor-agent print mode, asserts Layer 1 report."""
    result = bridge.start_visible_cursor_worker(
        prompt=(
            "Self-contained E2E. Do not edit files. Do not spawn subagents. "
            f"Reply with exactly {CURSOR_LIVE_MARKER} and nothing else."
        ),
        cwd=str(ROOT),
        title="E2E Cursor live roundtrip",
        sandbox="read-only",
        session_context=CURSOR_SESSION_CONTEXT,
        steer_idle_seconds=8,
    )
    assert result.get("pid"), result
    run_dir = _run_dir(result)
    metadata = _read_json(run_dir / "metadata.json", {})
    assert metadata.get("model") == bridge.CURSOR_DEFAULT_MODEL, metadata
    text = _wait_cursor_completed(run_dir, [CURSOR_LIVE_MARKER], timeout_s=600)

    events_path = run_dir / "events.jsonl"
    assert events_path.exists(), run_dir
    events_text = events_path.read_text(encoding="utf-8-sig", errors="replace")
    assert '"type":"result"' in events_text or '"type": "result"' in events_text, events_text[-2000:]

    session_id_path = run_dir / "session_id.txt"
    assert session_id_path.exists(), run_dir
    session_id = session_id_path.read_text(encoding="utf-8-sig").strip()
    assert session_id, "session_id.txt was empty"

    final_md = (run_dir / "captain_reports" / "final.md").read_text(encoding="utf-8-sig")
    assert CURSOR_LIVE_MARKER in final_md, final_md
    final_json = _read_json(run_dir / "captain_reports" / "final.json", {})
    assert final_json.get("outcome") == "completed", final_json
    assert final_json.get("agent") == "cursor", final_json
    summary_text = str(final_json.get("summary", "")) + str(final_json.get("text", ""))
    assert CURSOR_LIVE_MARKER in summary_text, final_json
    return {
        "run_dir": str(run_dir),
        "session_id": session_id,
        "pid": result.get("pid"),
        "model": bridge.CURSOR_DEFAULT_MODEL,
    }


def case_cursor_live_steer_resume(previous: dict[str, Any]) -> dict[str, Any]:
    """LIVE. Steer the completed cursor run; --resume must keep the same session id."""
    run_dir = Path(previous["run_dir"])
    events_before = (run_dir / "events.jsonl").read_text(encoding="utf-8-sig", errors="replace")
    result_count_before = events_before.count('"type":"result"') + events_before.count('"type": "result"')

    steer = bridge.steer_visible_cursor_run(
        str(run_dir),
        f"Self-contained steering E2E. Reply with exactly {CURSOR_STEER_MARKER} and nothing else. Do not edit files.",
        title="E2E Cursor steer follow-up",
        sandbox="read-only",
        session_context=CURSOR_SESSION_CONTEXT,
        launch_if_closed=True,
        interrupt_current_turn=False,
    )
    assert steer["ok"], steer

    if steer["mode"] == "launched_resume":
        followup_dir = _run_dir(steer["followup_run"])
        _wait_cursor_completed(followup_dir, [CURSOR_STEER_MARKER], timeout_s=600)
        followup_session = (followup_dir / "session_id.txt").read_text(encoding="utf-8-sig").strip()
        assert followup_session == previous["session_id"], (followup_session, previous["session_id"])
        return {"run_dir": str(followup_dir), "mode": steer["mode"], "session_id": followup_session}

    _wait_cursor_completed(run_dir, [CURSOR_LIVE_MARKER, CURSOR_STEER_MARKER], timeout_s=600)
    events_after = (run_dir / "events.jsonl").read_text(encoding="utf-8-sig", errors="replace")
    result_count_after = events_after.count('"type":"result"') + events_after.count('"type": "result"')
    assert result_count_after > result_count_before, (result_count_after, result_count_before)
    return {"run_dir": str(run_dir), "mode": steer["mode"], "session_id": previous["session_id"]}


def case_cursor_write_sandbox_dry_run() -> dict[str, Any]:
    original_launch = bridge._launch_visible_python

    def fake_launch(script_path: Path, run_dir: Path, env: dict[str, str] | None = None) -> int:
        return 414143

    try:
        bridge._launch_visible_python = fake_launch  # type: ignore[assignment]
        result = bridge.start_visible_cursor_worker(
            prompt="Self-contained write-sandbox dry-run.",
            cwd=str(ROOT),
            title="E2E Cursor write dry-run",
            sandbox="workspace-write",
            session_context=CURSOR_SESSION_CONTEXT,
        )
    finally:
        bridge._launch_visible_python = original_launch  # type: ignore[assignment]
    metadata = _read_json(_run_dir(result) / "metadata.json", {})
    assert metadata["requested_sandbox"] == "workspace-write", metadata
    return {"run_dir": result["run_dir"]}


def run_cursor_suite(skip_expensive: bool) -> dict[str, Any]:
    results: dict[str, Any] = {}
    print("[cursor 1/8] effort->model unit", flush=True)
    results["effort_unit"] = case_cursor_effort_unit()
    print("[cursor 2/8] dry-run arg assertions", flush=True)
    results["dry_run"] = case_cursor_dry_run_args()
    print(json.dumps(results["dry_run"], indent=2), flush=True)
    print("[cursor 3/8] Haiku-composed dry-run", flush=True)
    results["haiku_dry_run"] = case_cursor_haiku_composed_dry_run()
    print("[cursor 4/8] captain report / help gate + 10-min checkup script", flush=True)
    results["captain_report_gate"] = case_cursor_captain_report_gate()
    results["captain_checkup"] = case_captain_checkup_script()
    print("[cursor 5/8] write-sandbox dry-run + availability", flush=True)
    results["write_sandbox"] = case_cursor_write_sandbox_dry_run()
    results["availability"] = case_check_worker_backends()
    assert results["availability"]["cheap"]["cursor_agent"]["available"] is True, results["availability"]
    print("[cursor 6/8] deployed ~/.agent-bridge in sync", flush=True)
    results["deployed_in_sync"] = case_cursor_deployed_bridge_in_sync()
    if skip_expensive:
        print("[cursor 7-8/8] SKIPPED (--skip-expensive): live roundtrip + steer", flush=True)
        results["live_roundtrip"] = "skipped"
        results["live_steer"] = "skipped"
    else:
        print("[cursor 7/8] LIVE roundtrip (cursor-grok-4.6-xhigh-fast · MAX, visible window)", flush=True)
        results["live_roundtrip"] = case_cursor_live_roundtrip()
        print(json.dumps(results["live_roundtrip"], indent=2), flush=True)
        print("[cursor 8/8] LIVE steer/resume", flush=True)
        results["live_steer"] = case_cursor_live_steer_resume(results["live_roundtrip"])
        print(json.dumps(results["live_steer"], indent=2), flush=True)
    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-expensive", action="store_true", help="Skip Haiku, first-mate, and Claude advisor cases.")
    parser.add_argument(
        "--grok-only",
        action="store_true",
        help="Run only the Grok backend + availability-check cases (added 2026-07-14), skipping all Codex cases. Lets the Grok suite run to completion even when Codex is not logged in.",
    )
    parser.add_argument(
        "--agy-only",
        action="store_true",
        help="Run only the Antigravity (agy) backend + availability-check cases (added 2026-07-14), skipping all Codex and Grok cases. Lets the agy suite run to completion even when Codex/Grok are not logged in.",
    )
    parser.add_argument(
        "--cursor-only",
        action="store_true",
        help="Run only the cursor-agent backend + availability-check cases (added 2026-08-26).",
    )
    args = parser.parse_args()

    if args.grok_only:
        run_grok_suite(skip_expensive=args.skip_expensive)
        return

    if args.agy_only:
        run_agy_suite(skip_expensive=args.skip_expensive)
        return

    if args.cursor_only:
        run_cursor_suite(skip_expensive=args.skip_expensive)
        return

    results: dict[str, Any] = {}
    print("[0/11] advisor model policy", flush=True)
    _assert_model_policy()

    print("[1/11] Codex MCP tool allowlists", flush=True)
    _assert_codex_mcp_tool_allowlists()

    print("[2/11] captain help mailbox", flush=True)
    results["captain_help"] = case_captain_help_mailbox()
    print(json.dumps(results["captain_help"], indent=2), flush=True)

    print("[3/11] deprecated interactive TUI sidecar dry-run", flush=True)
    results["interactive_tui"] = case_interactive_tui_sidecar_dry_run()
    print(json.dumps(results["interactive_tui"], indent=2), flush=True)

    print("[4/11] deprecated interactive first-mate TUI dry-run", flush=True)
    results["interactive_firstmate_tui"] = case_interactive_first_mate_tui_dry_run()
    print(json.dumps(results["interactive_firstmate_tui"], indent=2), flush=True)

    print("[5/11] visible worker + queued steer", flush=True)
    results["queued"] = case_visible_worker_and_queued_steer()
    print(json.dumps(results["queued"], indent=2), flush=True)

    print("[6/11] closed run resume + permission override", flush=True)
    results["resume"] = case_closed_run_resume(results["queued"])
    print(json.dumps(results["resume"], indent=2), flush=True)

    print("[7/11] interrupt current turn + resume steering", flush=True)
    results["interrupt"] = case_interrupt_steering()
    print(json.dumps(results["interrupt"], indent=2), flush=True)

    print("[8/11] mandatory supervision review cycle", flush=True)
    results["supervision"] = case_supervision_review_cycle()
    print(json.dumps(results["supervision"], indent=2), flush=True)

    if not args.skip_expensive:
        print("[9/11] Haiku-composed Codex worker", flush=True)
        results["haiku"] = case_haiku_composed_worker()
        print(json.dumps(results["haiku"], indent=2), flush=True)

        print("[10/11] first-mate visible pool", flush=True)
        results["firstmate"] = case_first_mate_pool()
        print(json.dumps(results["firstmate"], indent=2), flush=True)

        print("[11/11] Claude advisor visible run", flush=True)
        results["claude_advisor"] = case_claude_advisor()
        print(json.dumps(results["claude_advisor"], indent=2), flush=True)

    _assert_no_git_changes()
    print(json.dumps({"ok": True, "results": results}, indent=2), flush=True)


if __name__ == "__main__":
    main()
