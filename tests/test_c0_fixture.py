from pathlib import Path

from forge.c0_fixture import TASK_ID, create_fixture, run_fixture_verification


def write_solution(fixture: Path):
    (fixture / "c0_target.py").write_text(
        """def normalize_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError('blank name')
    return '-'.join(value.lower().split())
"""
    )


def test_c0_fixture_starts_red(tmp_path: Path):
    fixture = create_fixture(tmp_path)
    result = run_fixture_verification(fixture)
    assert result["task_id"] == TASK_ID
    assert result["passed"] is False
    assert result["exit_code"] != 0
    assert result["test_bundle_sha256"]


def test_c0_fixture_verifies_explicit_candidate(tmp_path: Path):
    fixture = create_fixture(tmp_path)
    write_solution(fixture)
    result = run_fixture_verification(fixture)
    assert result["passed"] is True
    assert result["changed_files"] == ["c0_target.py"]


def test_missing_candidate_does_not_go_green(tmp_path: Path):
    result = run_fixture_verification(tmp_path / "missing")
    assert result["passed"] is False
    assert result["exit_code"] == 2
