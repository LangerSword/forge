from forge.ao_cli import AOCLI


def test_spawn_command_uses_documented_flags_without_executing():
    cli = AOCLI(binary="/usr/bin/ao")
    command = cli.spawn_command(project="forge", name="c0-worker", prompt="Do one task.")
    assert command[:3] == ("/usr/bin/ao", "spawn", "--project")
    assert "--harness" in command
    assert "opencode" in command
    assert "--prompt" in command
    assert "Do one task." in command


def test_spawn_name_limit():
    cli = AOCLI(binary="/usr/bin/ao")
    try:
        cli.spawn_command(project="forge", name="x" * 21, prompt="x")
    except ValueError as exc:
        assert "20" in str(exc)
    else:
        raise AssertionError("expected name limit")
