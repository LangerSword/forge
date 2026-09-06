import os
from pathlib import Path

from forge.c0_fixture import create_fixture, run_fixture_verification


def test_symlink_candidate_rejected(tmp_path: Path):
    target = create_fixture(tmp_path / 'real')
    link = tmp_path / 'link'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return
    result = run_fixture_verification(link)
    assert result['passed'] is False
    assert result['failure_code'] == 'candidate_symlink_forbidden'


def test_failure_output_is_bounded(tmp_path: Path):
    candidate = create_fixture(tmp_path)
    result = run_fixture_verification(candidate, max_output_chars=100)
    assert len(result['stdout']) <= 100
    assert result['failure_code'] == 'test_failure'
