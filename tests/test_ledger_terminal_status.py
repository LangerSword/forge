from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time

from forge.ledger import Ledger
from forge.verifier import verify_local_smoke


def test_verifier_persists_terminal_status():
    root = Path.cwd()
    run_id = "terminal-status-test"
    result = verify_local_smoke(root, run_id=run_id)
    stored = Ledger(root).get_run(run_id)
    assert result.status == "passed"
    assert stored is not None
    assert stored["status"] == "passed"
    assert stored["events"][-1]["kind"] == "verdict"


def test_ledger_serializes_concurrent_fleet_events(tmp_path: Path):
    from forge.ledger import Ledger

    ledger = Ledger(tmp_path)
    ledger.run("fleet", "parallel tasks", "C0", "forge-controller", "running")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda index: ledger.event("fleet", "task", "worker", {"index": index}), range(20)))
    stored = ledger.get_run("fleet")
    assert stored is not None
    assert len(stored["events"]) == 20


def test_ledger_resume_does_not_replace_run_creation_metadata(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.run("resume", "first goal", "C0", "controller", "running")
    first = ledger.get_run("resume")
    assert first is not None
    time.sleep(0.001)
    ledger.run("resume", "second goal", "controller", "controller", "running")
    second = ledger.get_run("resume")
    assert second is not None
    assert second["created_at"] == first["created_at"]
    assert second["goal"] == "first goal"
    assert second["condition"] == "C0"


def test_ledger_redacts_secret_like_event_payloads(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.run("redaction", "goal", "C0", "controller", "running")
    ledger.event(
        "redaction",
        "diagnostic",
        "controller",
        {"api_key": "secret-value", "nested": {"authorization": "Bearer secret"}, "safe": "kept"},
    )
    event = ledger.get_run("redaction")["events"][-1]["payload"]
    assert event["api_key"] == "<redacted>"
    assert event["nested"]["authorization"] == "<redacted>"
    assert event["safe"] == "kept"


def test_ledger_handles_concurrent_connections_for_worker_events(tmp_path: Path):
    Ledger(tmp_path).run("multi", "goal", "C0", "controller", "running")

    def emit(index: int):
        Ledger(tmp_path).event("multi", "worker_event", f"worker-{index}", {"index": index})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(emit, range(32)))
    events = Ledger(tmp_path).get_run("multi")["events"]
    assert len(events) == 32


def test_ledger_persists_task_attempt_checkpoint_across_connections(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.run("attempt-run", "goal", "C0", "controller", "running")
    ledger.ensure_task_attempt("attempt-run", "task-a", attempt=1, state="pending")
    ledger.update_task_attempt(
        "attempt-run",
        "task-a",
        attempt=1,
        expected_state="pending",
        state="running",
        session_id="session-a",
        worktree="/tmp/worktree-a",
    )
    fresh = Ledger(tmp_path)
    checkpoint = fresh.get_task_attempt("attempt-run", "task-a")
    assert checkpoint is not None
    assert checkpoint["state"] == "running"
    assert checkpoint["session_id"] == "session-a"
    assert checkpoint["worktree"] == "/tmp/worktree-a"


def test_ledger_task_attempt_compare_and_set_rejects_stale_transition(tmp_path: Path):
    ledger = Ledger(tmp_path)
    ledger.run("cas-run", "goal", "C0", "controller", "running")
    ledger.ensure_task_attempt("cas-run", "task-a", attempt=1, state="pending")
    assert ledger.update_task_attempt(
        "cas-run", "task-a", attempt=1, expected_state="pending", state="dispatched"
    )
    assert not ledger.update_task_attempt(
        "cas-run", "task-a", attempt=1, expected_state="pending", state="running"
    )
    assert ledger.get_task_attempt("cas-run", "task-a")["state"] == "dispatched"
