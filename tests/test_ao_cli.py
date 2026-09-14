import subprocess

from forge.ao_cli import AOCLI, AOCommandResult, parse_spawn_output


def test_spawn_command_uses_documented_flags_without_executing():
    cli = AOCLI(binary="/usr/bin/ao")
    command = cli.spawn_command(project="forge", name="c0-worker", prompt="Do one task.")
    assert command[:3] == ("/usr/bin/ao", "spawn", "--project")
    assert "--harness" in command
    assert "opencode" in command
    assert "--prompt" in command
    assert "Do one task." in command


def test_parse_spawn_output_accepts_live_ao_spawn_line():
    result = parse_spawn_output('spawned session forge-10 "spawn-diagnostic" (idle)\n')
    assert result.session_id == "forge-10"


def test_discover_worktree_matches_observed_ao_session_branch(monkeypatch, tmp_path):
    cli = AOCLI(binary="/usr/bin/ao", cwd=tmp_path)
    porcelain = (
        f"worktree {tmp_path / 'forge-10'}\n"
        "HEAD abc123\n"
        "branch refs/heads/ao/forge-10/root\n\n"
        f"worktree {tmp_path / 'other'}\n"
        "HEAD def456\n"
        "branch refs/heads/ao/other/root\n"
    )

    class Result:
        returncode = 0
        stdout = porcelain
        stderr = ""

    monkeypatch.setattr("forge.ao_cli.subprocess.run", lambda *args, **kwargs: Result())
    assert cli.discover_worktree("forge-10") == tmp_path / "forge-10"


def test_discover_worktree_does_not_pair_branch_from_another_block(monkeypatch, tmp_path):
    cli = AOCLI(binary="/usr/bin/ao", cwd=tmp_path)
    porcelain = (
        f"worktree {tmp_path / 'other'}\n"
        "HEAD def456\n"
        "branch refs/heads/ao/other/root\n\n"
        f"worktree {tmp_path / 'forge-10'}\n"
        "HEAD abc123\n"
        "branch refs/heads/ao/forge-10/root\n"
    )

    class Result:
        returncode = 0
        stdout = porcelain
        stderr = ""

    monkeypatch.setattr("forge.ao_cli.subprocess.run", lambda *args, **kwargs: Result())
    assert cli.discover_worktree("forge-10") == tmp_path / "forge-10"


def test_spawn_name_limit():
    cli = AOCLI(binary="/usr/bin/ao")
    try:
        cli.spawn_command(project="forge", name="x" * 21, prompt="x")
    except ValueError as exc:
        assert "20" in str(exc)
    else:
        raise AssertionError("expected name limit")


def test_spawn_preserves_nonzero_result_for_side_effect_reconciliation(monkeypatch):
    cli = AOCLI(binary="/usr/bin/ao")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            "Spawned session: forge-9\nWorktree: /tmp/ao-worktree\n",
            "daemon returned an error after creating the session",
        ),
    )
    result = cli.spawn(project="forge", name="reconcile", prompt="create artifact")
    assert result.exit_code == 1
    assert "forge-9" in result.stdout


def test_resolve_binary_finds_live_daemon_even_without_appimage(monkeypatch):
    """The /proc scan must not be gated on a hardcoded AppImage path.

    Regression: the scan was nested inside `if candidate.exists()` for
    ~/.local/bin/agent-orchestrator-linux-x64.AppImage, so a machine where AO
    lives elsewhere (~/Applications, hash-suffixed) resolved nothing even with
    the daemon running.
    """
    import os
    from pathlib import Path

    cli = AOCLI()

    class FakeProc:
        def __init__(self, pid: int, exe: str):
            self._dir = Path(f"/proc-self-test-{pid}")
            self._dir.mkdir(exist_ok=True)
            (self._dir / "exe").symlink_to(exe)

    # point the glob at a fixture dir instead of /proc
    import forge.ao_cli as ao_cli_mod

    monkeypatch.setattr(ao_cli_mod.Path, "glob", lambda self, pattern: iter([]))

    # Simulate the live daemon found via /proc: monkeypatch os.readlink over a
    # synthetic entry by globbing a real fixture directory instead.
    fixture = Path("/proc")

    def fake_glob(self, pattern):
        # return one synthetic pid dir whose exe reads as the daemon binary
        return iter([Path("/proc/self")])

    monkeypatch.setattr(Path, "glob", fake_glob)

    def fake_readlink(path):
        if path.name == "exe" and str(path).startswith("/proc/self"):
            return "/tmp/.mount_agent-XXXX/resources/daemon/ao"
        raise OSError("nope")

    monkeypatch.setattr(ao_cli_mod.os, "readlink", fake_readlink)

    resolved = cli.resolve_binary()
    assert resolved == "/tmp/.mount_agent-XXXX/resources/daemon/ao"


def test_resolve_binary_env_override_wins(monkeypatch):
    """AO_CLI_BINARY must beat discovery — an explicit override is never
    second-guessed by the /proc scan."""
    import forge.ao_cli as ao_cli_mod

    monkeypatch.setenv("AO_CLI_BINARY", "/opt/ao/bin/ao")
    cli = AOCLI()
    assert cli.resolve_binary() == "/opt/ao/bin/ao"
