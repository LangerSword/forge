import json

import pytest

from forge import cli


def test_bare_forge_launches_tui(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "launch_tui", lambda: calls.append("tui") or 0)
    assert cli.main([]) == 0
    assert calls == ["tui"]


def test_forge_tui_subcommand_launches_tui(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "launch_tui", lambda: calls.append("tui") or 0)
    assert cli.main(["tui"]) == 0
    assert calls == ["tui"]


def test_launch_tui_non_interactive_is_actionable(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_is_interactive", lambda: False)
    code = cli.launch_tui()
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "not_a_tty"


def test_launch_tui_missing_binary_is_actionable(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    code = cli.launch_tui()
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "forge_tui_missing"
    assert "forge-tui" in payload["message"]


def test_launch_tui_execs_the_binary(monkeypatch):
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/forge-tui")
    captured = {}

    class ExecDone(Exception):
        pass

    def fake_exec(path, argv):
        captured["path"] = path
        captured["argv"] = argv
        raise ExecDone()

    monkeypatch.setattr(cli.os, "execv", fake_exec)
    with pytest.raises(ExecDone):
        cli.launch_tui()
    assert captured == {"path": "/usr/bin/forge-tui", "argv": ["/usr/bin/forge-tui"]}