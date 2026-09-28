import json
from pathlib import Path

import pytest

from forge.ao_cli import AOCommandError, find_appimage, install_cli


def _fake_appimage(root: Path) -> Path:
    fake = root / "Applications" / "agent-orchestrator-linux-x64_deadbeef.AppImage"
    fake.parent.mkdir(parents=True)
    fake.write_text("not really an appimage")
    return fake


def _fake_extractor(source: Path, workdir: Path) -> Path:
    extracted = workdir / "squashfs-root" / "resources" / "daemon" / "ao"
    extracted.parent.mkdir(parents=True)
    extracted.write_text("#!/bin/sh\necho ao\n")
    return extracted


def test_find_appimage_prefers_applications_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    preferred = _fake_appimage(tmp_path)
    also = tmp_path / ".local" / "bin" / "agent-orchestrator-linux-x64.AppImage"
    also.parent.mkdir(parents=True)
    also.write_text("x")
    assert find_appimage() == preferred


def test_find_appimage_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert find_appimage() is None


def test_install_cli_extracts_to_stable_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    source = _fake_appimage(tmp_path)
    dest = tmp_path / ".local" / "bin" / "ao"
    result = install_cli(dest=dest, appimage=source, extractor=_fake_extractor)
    assert result["status"] == "installed"
    assert result["path"] == str(dest)
    assert result["source"] == str(source)
    assert dest.is_file()
    assert dest.stat().st_mode & 0o111
    assert len(result["sha256"]) == 64


def test_install_cli_second_run_is_up_to_date(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    source = _fake_appimage(tmp_path)
    dest = tmp_path / ".local" / "bin" / "ao"
    install_cli(dest=dest, appimage=source, extractor=_fake_extractor)
    second = install_cli(dest=dest, appimage=source, extractor=_fake_extractor)
    assert second["status"] == "up_to_date"


def test_install_cli_force_recopies(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    source = _fake_appimage(tmp_path)
    dest = tmp_path / ".local" / "bin" / "ao"
    calls = {"count": 0}

    def counting_extractor(appimage: Path, workdir: Path) -> Path:
        calls["count"] += 1
        return _fake_extractor(appimage, workdir)

    install_cli(dest=dest, appimage=source, extractor=counting_extractor)
    forced = install_cli(dest=dest, appimage=source, extractor=counting_extractor, force=True)
    assert calls["count"] == 2
    assert forced["status"] == "updated"


def test_install_cli_missing_appimage_is_actionable(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(AOCommandError) as excinfo:
        install_cli(dest=tmp_path / "ao")
    assert "AppImage" in str(excinfo.value)


def test_ao_install_cli_command_reports_failure_as_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    from forge.cli import main

    code = main(["ao", "install-cli"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "AppImage" in payload["message"]


def test_ao_install_cli_command_success(monkeypatch, capsys):
    from forge import cli

    monkeypatch.setattr(
        cli,
        "install_cli",
        lambda *, force=False: {
            "status": "installed",
            "path": "/tmp/ao",
            "sha256": "0" * 64,
            "source": "/tmp/agent-orchestrator.AppImage",
            "app_version": "0.12.11",
        },
    )
    code = cli.main(["ao", "install-cli"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "installed"
    assert payload["app_version"] == "0.12.11"