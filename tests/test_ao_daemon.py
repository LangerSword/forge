import json
from pathlib import Path

import pytest

from forge.ao import AOTransportError
from forge.ao_cli import AOCommandError, AOCommandResult
from forge.ao_daemon import daemon_status, start_daemon, stop_daemon


class FakeCLI:
    def __init__(self, statuses=None, status_raw=None, binary="/usr/bin/ao"):
        self.calls: list[tuple] = []
        self._statuses = list(statuses or [{"state": "stopped"}])
        self._status_raw = status_raw
        self._binary = binary
        self.status_calls = 0

    def resolve_binary(self) -> str:
        return self._binary

    def run(self, args, *, timeout: int = 30) -> AOCommandResult:
        self.calls.append(tuple(args))
        if args[0] == "status":
            self.status_calls += 1
            if self._status_raw is not None:
                return AOCommandResult(("ao", *args), 0, self._status_raw, "")
            index = min(self.status_calls - 1, len(self._statuses) - 1)
            return AOCommandResult(("ao", *args), 0, json.dumps(self._statuses[index]), "")
        if args[0] == "stop":
            return AOCommandResult(("ao", *args), 0, "AO daemon stopped\n", "")
        raise AssertionError(f"unexpected ao command: {args}")


class FakeClient:
    def __init__(self, *, ready_failures=0, health_failures=0):
        self._ready_failures = ready_failures
        self._health_failures = health_failures
        self.ready_calls = 0
        self.health_calls = 0

    def ready(self):
        self.ready_calls += 1
        if self.ready_calls <= self._ready_failures:
            raise AOTransportError("connection refused")
        return {"status": "ready"}

    def health(self):
        self.health_calls += 1
        if self.health_calls <= self._health_failures:
            raise AOTransportError("connection refused")
        return {"status": "ok"}


class FakePopen:
    def __init__(self):
        self.calls: list[tuple] = []
        self.pid = 4242

    def __call__(self, command, **kwargs):
        self.calls.append((tuple(command), kwargs))
        return self


def test_daemon_status_parses_ao_status_json():
    cli = FakeCLI(statuses=[{"state": "ready", "pid": 1, "port": 3001}])
    assert daemon_status(cli=cli) == {"state": "ready", "pid": 1, "port": 3001}


def test_daemon_status_rejects_non_json_output():
    cli = FakeCLI(status_raw="AO daemon: stopped (human text)")
    with pytest.raises(AOCommandError) as excinfo:
        daemon_status(cli=cli)
    assert "non-JSON" in str(excinfo.value)


def test_start_daemon_already_ready_is_noop():
    cli = FakeCLI(statuses=[{"state": "ready", "pid": 1}])
    popen = FakePopen()
    result = start_daemon(cli=cli, client=FakeClient(), popen=popen)
    assert result["status"] == "already_running"
    assert popen.calls == []


def test_start_daemon_spawns_headless_and_waits(tmp_path):
    cli = FakeCLI(statuses=[{"state": "stopped"}, {"state": "ready", "pid": 4242}])
    client = FakeClient(ready_failures=2)
    popen = FakePopen()
    result = start_daemon(
        cli=cli, client=client, popen=popen, timeout_s=2.0, poll_s=0.01, log_path=tmp_path / "daemon.log"
    )
    assert result["status"] == "started"
    assert result["daemon"] == {"state": "ready", "pid": 4242}
    assert len(popen.calls) == 1
    command, kwargs = popen.calls[0]
    assert command == ("/usr/bin/ao", "daemon")
    assert kwargs["start_new_session"] is True
    assert client.ready_calls == 3  # two refusals, then ready


def test_start_daemon_timeout_raises_with_log_tail(tmp_path):
    cli = FakeCLI(statuses=[{"state": "stopped"}])
    client = FakeClient(ready_failures=10**9)
    log = tmp_path / "daemon.log"
    log.write_text("boom: daemon failed to bind\n")
    with pytest.raises(AOCommandError) as excinfo:
        start_daemon(
            cli=cli, client=client, popen=FakePopen(), timeout_s=0.05, poll_s=0.01, log_path=log
        )
    message = str(excinfo.value)
    assert "did not become ready" in message
    assert "bind" in message


def test_stop_daemon_when_not_running_is_noop():
    cli = FakeCLI(statuses=[{"state": "stopped"}])
    result = stop_daemon(cli=cli, client=FakeClient())
    assert result["status"] == "not_running"
    assert all(call[0] != "stop" for call in cli.calls)


def test_stop_daemon_stops_and_verifies_port_closes():
    cli = FakeCLI(statuses=[{"state": "ready", "pid": 1}, {"state": "stopped"}])
    client = FakeClient(health_failures=1)
    result = stop_daemon(cli=cli, client=client)
    assert result["status"] == "stopped"
    assert ("stop", "--timeout", "15s") in cli.calls
    assert result["daemon"] == {"state": "stopped"}


def test_ao_status_command_reports_daemon_json(monkeypatch, capsys):
    from forge import cli

    monkeypatch.setattr(cli, "daemon_status", lambda: {"state": "stopped", "runFile": "/x"})
    code = cli.main(["ao", "status"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["daemon"]["state"] == "stopped"


def test_ao_start_command_failure_is_actionable(monkeypatch, capsys):
    from forge import cli
    from forge.ao_cli import AOCommandError as CliError

    def boom():
        raise CliError("AO CLI binary not resolved: run `forge ao install-cli` or set AO_CLI_BINARY.")

    monkeypatch.setattr(cli, "start_daemon", boom)
    code = cli.main(["ao", "start"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "start_failed"
    assert "install-cli" in payload["message"]


def test_ao_stop_command_reports_result(monkeypatch, capsys):
    from forge import cli

    monkeypatch.setattr(cli, "stop_daemon", lambda: {"status": "stopped", "message": "AO daemon stopped"})
    code = cli.main(["ao", "stop"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "stopped"


def _goal_file(tmp_path) -> "Path":
    goal = tmp_path / "goal.json"
    goal.write_text(json.dumps({
        "goal": "smoke",
        "repo": str(tmp_path),
        "acceptance": ["one bounded change"],
        "harness": "opencode",
    }))
    return goal


def test_fleet_live_requires_ready_daemon(monkeypatch, tmp_path, capsys):
    from forge import cli
    import forge.ao_daemon as ao_daemon

    monkeypatch.setattr(ao_daemon, "daemon_status", lambda **kwargs: {"state": "stopped"})
    code = cli.main(["fleet", str(_goal_file(tmp_path))])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "forge ao start" in payload["message"]


def test_fleet_dry_run_skips_daemon_preflight(monkeypatch, tmp_path, capsys):
    from forge import cli

    def boom():
        raise AssertionError("preflight must not run on --dry-run")

    monkeypatch.setattr(cli, "require_ao_ready", boom)
    monkeypatch.setattr(cli, "root", lambda: tmp_path)
    code = cli.main(["fleet", str(_goal_file(tmp_path)), "--dry-run"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "planned"