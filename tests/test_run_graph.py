import json

from forge import cli
from forge.ao_cli import AOCommandError
from forge.graph import NodeResult

GOAL_MD = """# Doc task

Repo: /home/lakshaya/forge
Harness: opencode
Artifact: docs/QUICKSTART.md

## Goal

Write docs/QUICKSTART.md.

## Acceptance

- docs/QUICKSTART.md exists.

## Verification

- `test -s docs/QUICKSTART.md`
- `grep -q "uv tool install" docs/QUICKSTART.md`
"""


def _write_goal(tmp_path, name="goal.md", content=GOAL_MD):
    path = tmp_path / name
    path.write_text(content)
    return path


def test_run_graph_dry_run_compiles_without_daemon(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    goal = _write_goal(tmp_path)
    code = cli.main(["run-graph", str(goal), "--dry-run"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["counts"]["node_count"] == 2
    assert len(payload["goal"]["verifier_commands"]) == 2


class FakeResult:
    def __init__(self, status):
        self.status = status
        self.node_results = (
            NodeResult(node_id="goal", status=status, evidence_refs=("run:x",)),
            NodeResult(node_id="goal-verify", status=status, evidence_refs=("run:y",)),
        )


def _fake_scheduler(status):
    captured = {}

    class Scheduler:
        def __init__(self, root, *, runner_factory):
            captured["root"] = root
            captured["runner_factory"] = runner_factory

        def run(self, graph, *, graph_id, goal=None, depth=0, resume=False):
            captured["graph_id"] = graph_id
            return FakeResult(status)

    return Scheduler, captured


def test_run_graph_live_passes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "require_ao_ready", lambda: {"state": "ready"})
    Scheduler, captured = _fake_scheduler("passed")
    monkeypatch.setattr(cli, "GraphScheduler", Scheduler)
    goal = _write_goal(tmp_path)
    code = cli.main(["run-graph", str(goal)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["run_id"].startswith("graph-")
    assert len(payload["node_results"]) == 2
    assert callable(captured["runner_factory"])


def test_run_graph_failing_graph_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "require_ao_ready", lambda: {"state": "ready"})
    Scheduler, _ = _fake_scheduler("failed")
    monkeypatch.setattr(cli, "GraphScheduler", Scheduler)
    goal = _write_goal(tmp_path)
    code = cli.main(["run-graph", str(goal)])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status"] == "failed"


def test_run_graph_without_verifier_commands_fails_loud(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    goal = tmp_path / "goal.json"
    goal.write_text(json.dumps({
        "goal": "x", "repo": "/tmp/repo-x", "acceptance": ["y"], "harness": "opencode",
    }))
    code = cli.main(["run-graph", str(goal)])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "missing_verifier"


def test_run_graph_requires_ready_daemon(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def boom():
        raise AOCommandError("AO daemon is not ready (state=stopped); start it with `forge ao start`")

    monkeypatch.setattr(cli, "require_ao_ready", boom)
    goal = _write_goal(tmp_path)
    code = cli.main(["run-graph", str(goal)])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "ao_not_ready"
    assert "forge ao start" in payload["message"]