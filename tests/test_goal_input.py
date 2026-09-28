import json

import pytest

from forge.goal_input import GoalInputError, goal_spec_from_markdown, load_goal_spec

PLAN_MD = """---
schema_version: hermes_plan/v1
status: draft
---

# Bad-air day decision layer

Repo: /tmp/repo-x
Harness: opencode
Artifact: docs/SMOKE.md
Max minutes: 30

## 1. Goal

- Give schools a day-level action plan on AQI spike days.
- Alert principals before morning assembly.

## 2. Non-goals

- No hardware builds.
- No dashboard for parents.

## 7. Acceptance criteria

Plan phase:
- AC1 Live AQI ingested with a source citation.
- [ ] AC2 Principal dashboard reachable at a stable URL.
- AC3 Demo video under 3 minutes.
"""


def test_markdown_maps_goal_repo_harness_artifact_and_acceptance(tmp_path):
    spec = goal_spec_from_markdown(PLAN_MD, source="plan.md", root=tmp_path)
    assert "action plan" in spec.goal
    assert "No hardware" not in spec.goal  # non-goals excluded
    assert spec.repo == "/tmp/repo-x"
    assert spec.harness == "opencode"
    assert spec.artifact_path == "docs/SMOKE.md"
    assert spec.max_minutes == 30
    assert spec.max_parallel == 1
    assert spec.acceptance == [
        "AC1 Live AQI ingested with a source citation.",
        "AC2 Principal dashboard reachable at a stable URL.",
        "AC3 Demo video under 3 minutes.",
    ]


def test_markdown_title_is_goal_fallback(tmp_path):
    text = "# Ship the smoke artifact\n\nHarness: opencode\n\n## Acceptance\n\n- Artifact exists.\n"
    spec = goal_spec_from_markdown(text, source="x.md", root=tmp_path)
    assert spec.goal == "Ship the smoke artifact"


def test_markdown_missing_acceptance_is_actionable(tmp_path):
    text = "# Goal\n\n- Do the thing.\n"
    with pytest.raises(GoalInputError) as excinfo:
        goal_spec_from_markdown(text, source="x.md", root=tmp_path)
    assert "acceptance" in str(excinfo.value).lower()


def test_markdown_harness_falls_back_to_policy(tmp_path):
    (tmp_path / ".forge").mkdir()
    (tmp_path / ".forge" / "harness-policy.json").write_text(json.dumps({"harness": "opencode"}))
    text = "# Goal\n\n- Do the thing.\n\n## Acceptance\n\n- It works.\n"
    spec = goal_spec_from_markdown(text, source="x.md", root=tmp_path)
    assert spec.harness == "opencode"
    assert spec.repo == str(tmp_path)


def test_markdown_without_harness_anywhere_fails_loud(tmp_path):
    text = "# Goal\n\n- Do the thing.\n\n## Acceptance\n\n- It works.\n"
    with pytest.raises(GoalInputError) as excinfo:
        goal_spec_from_markdown(text, source="x.md", root=tmp_path)
    assert "harness" in str(excinfo.value).lower()


def test_missing_file_error_names_the_fix(tmp_path):
    with pytest.raises(GoalInputError) as excinfo:
        load_goal_spec(tmp_path / "nope.md", root=tmp_path)
    message = str(excinfo.value)
    assert "not found" in message
    assert "absolute path" in message


def test_unsupported_suffix_fails_loud(tmp_path):
    path = tmp_path / "goal.txt"
    path.write_text("anything")
    with pytest.raises(GoalInputError) as excinfo:
        load_goal_spec(path, root=tmp_path)
    assert ".json" in str(excinfo.value) and ".md" in str(excinfo.value)


def test_invalid_json_goal_names_the_file(tmp_path):
    path = tmp_path / "goal.json"
    path.write_text("{not json")
    with pytest.raises(GoalInputError) as excinfo:
        load_goal_spec(path, root=tmp_path)
    assert "invalid GoalSpec JSON" in str(excinfo.value)


def test_json_goal_still_loads(tmp_path):
    path = tmp_path / "goal.json"
    path.write_text(json.dumps({
        "goal": "smoke",
        "repo": "/tmp/repo-x",
        "acceptance": ["one thing"],
        "harness": "opencode",
    }))
    spec = load_goal_spec(path, root=tmp_path)
    assert spec.goal == "smoke"
    assert spec.acceptance == ["one thing"]


def test_cli_plan_accepts_markdown_plan(tmp_path, monkeypatch, capsys):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_MD)
    monkeypatch.chdir(tmp_path)
    from forge.cli import main

    code = main(["plan", str(plan)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["goal"]["harness"] == "opencode"


def test_cli_plan_missing_file_is_actionable(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    from forge.cli import main

    code = main(["plan", "nope.md"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "not found" in payload["message"]