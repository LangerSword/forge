import json
from pathlib import Path

import pytest

from forge.capture import CaptureConfig, RenderCapture, SourceCloneAttempt, assert_no_source_clone
from forge.schema import CapturePolicy, GoalSpec, RunResult


def test_goal_and_run_result_are_strict():
    goal = GoalSpec(
        goal="reproduce a rendered page",
        repo="/tmp/repro",
        acceptance=["build passes"],
        harness="opencode",
    )
    assert goal.max_minutes == 15
    with pytest.raises(Exception):
        GoalSpec.model_validate({"goal": "x", "repo": "/tmp/x", "acceptance": [], "harness": "x", "unknown": 1})

    result = RunResult(
        run_id="r1", goal="x", condition="C0", harness="opencode",
        status="passed", checks=[], wall_s=1.2,
    )
    assert result.status == "passed"


def test_capture_policy_forbids_source_access():
    policy = CapturePolicy(target_url="https://drawably.dev/")
    policy.assert_safe()
    with pytest.raises(ValueError):
        CapturePolicy(target_url="https://drawably.dev/", no_source_clone=False).assert_safe()


def test_capture_manifest_is_render_only(tmp_path: Path):
    capture = RenderCapture(
        CaptureConfig("https://drawably.dev/", tmp_path),
        chromium="/usr/bin/chromium",
    )
    path = capture.write_manifest()
    manifest = json.loads(path.read_text())
    assert manifest["target_repository_policy"] == "never_clone_or_inspect"
    assert "clone_repository" in manifest["forbidden_actions"]
    assert "read_target_source" in manifest["forbidden_actions"]
    assert not (tmp_path / "repo").exists()


def test_capture_command_rejects_clone_operations():
    with pytest.raises(SourceCloneAttempt):
        assert_no_source_clone(["git", "clone", "https://example.invalid/repo"])
    assert_no_source_clone(["chromium", "--headless", "--dump-dom", "https://drawably.dev/"])
