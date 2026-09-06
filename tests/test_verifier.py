from pathlib import Path

from forge.verifier import verify_local_smoke


def test_local_smoke_verifier_passes():
    result = verify_local_smoke(Path.cwd(), run_id="test-c0")
    assert result.status == "passed"
    assert all(check.passed for check in result.checks)
    assert result.condition == "C0"
