from pathlib import Path

from forge.c0_fixture import create_fixture
from forge.c0_run import run_c0


def test_c0_run_requires_explicit_candidate(tmp_path: Path):
    try:
        run_c0(tmp_path, run_id="test-c0-ledger")
    except ValueError as exc:
        assert "candidate path is required" in str(exc)
    else:
        raise AssertionError("expected explicit candidate requirement")


def test_c0_run_persists_candidate_verdict(tmp_path: Path):
    fixture = create_fixture(tmp_path)
    (fixture / "c0_target.py").write_text(
        "def normalize_name(value: str) -> str:\n"
        "    value = value.strip()\n"
        "    if not value: raise ValueError('blank')\n"
        "    return '-'.join(value.lower().split())\n"
    )
    result = run_c0(tmp_path, run_id="test-c0-ledger", candidate=fixture)
    assert result["baseline"]["passed"] is False
    assert result["result"]["passed"] is True
    assert result["ledger"]["runs"] == 1
