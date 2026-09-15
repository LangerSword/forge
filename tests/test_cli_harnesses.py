from __future__ import annotations

import json
from pathlib import Path

from forge import cli


def test_harnesses_command_serializes_readiness_report(monkeypatch, capsys):
    payload = {
        "agents": [
            {"name": "opencode", "installed": True, "authStatus": "authorized"},
            {"name": "codex", "installed": True, "authStatus": "authorized"},
        ],
        "supported_catalog": ["opencode", "codex"],
        "smoke_tested": {"opencode": True, "codex": True},
    }
    monkeypatch.setattr(cli, "AOClient", lambda: object())
    monkeypatch.setattr(cli, "harness_report", lambda *, ao: cli.build_harness_report(
        payload,
        supported_catalog=payload["supported_catalog"],
        smoke_tested=payload["smoke_tested"],
    ))

    assert cli.main_from_args_for_test(["harnesses"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["cross_harness_pass"] is True
    assert output["authorized_smoke_tested_count"] == 2


def test_harnesses_command_is_read_only_on_ao_error(monkeypatch, capsys):
    class BrokenAO:
        pass

    monkeypatch.setattr(cli, "AOClient", BrokenAO)
    monkeypatch.setattr(cli, "harness_report", lambda *, ao: (_ for _ in ()).throw(RuntimeError("offline")))

    assert cli.main_from_args_for_test(["harnesses"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["error"] == "ao_unavailable"


def test_runner_serialization_is_json_safe(tmp_path: Path):
    # This test keeps the report boundary explicit without touching AO.
    report = cli.build_harness_report(
        {"agents": [{"name": "opencode", "installed": True, "authStatus": "authorized"}]},
        supported_catalog=("opencode",),
        smoke_tested={"opencode": True},
    ).to_dict()
    assert json.loads(json.dumps(report))["schema_version"] == "forge.harness-readiness.v1"


# --------------------------------------------------------------------------
# forge experiment --model-baseline/--model-candidate (model-variant A/B)
# --------------------------------------------------------------------------


def test_cli_experiment_rejects_nonallowlisted_model(capsys) -> None:
    """The CLI must enforce the declared harness policy before running."""
    import json
    import tempfile
    from pathlib import Path

    from forge.cli import main_from_args_for_test

    with tempfile.TemporaryDirectory() as tmp:
        goal = Path(tmp) / "goal.json"
        goal.write_text(json.dumps({
            "goal": "model A/B via CLI",
            "repo": tmp,
            "acceptance": ["done"],
            "harness": "opencode",
        }))
        code = main_from_args_for_test([
            "experiment", "exp-cli-model-bad", str(goal),
            "--model-candidate", "sketchy-model",
        ])
        out = json.loads(capsys.readouterr().out)

    assert code == 1
    assert out["ok"] is False
    assert "model" in out.get("message", "").lower() or out.get("error") == "policy_violation"


def test_cli_experiment_reports_model_condition(capsys) -> None:
    """A policy-clean CLI run records the model condition in its output."""
    import json
    import tempfile
    from pathlib import Path

    from forge.cli import main_from_args_for_test

    with tempfile.TemporaryDirectory() as tmp:
        goal = Path(tmp) / "goal.json"
        goal.write_text(json.dumps({
            "goal": "model A/B via CLI",
            "repo": tmp,
            "acceptance": ["done"],
            "harness": "opencode",
        }))
        code = main_from_args_for_test([
            "experiment", "exp-cli-model-ok", str(goal),
            "--model-candidate", "nvidia/abacusai/dracarys-llama-3.1-70b-instruct",
        ])
        out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
    assert out["model_condition"]["candidate_model"] == "nvidia/abacusai/dracarys-llama-3.1-70b-instruct"
    assert out["model_condition"]["policy_hash"]
