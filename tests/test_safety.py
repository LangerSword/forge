from pathlib import Path

from forge.safety import validate_candidate, bounded_run


def test_candidate_workspace_limits(tmp_path: Path):
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    (candidate / 'c0_target.py').write_text('x=1')
    report = validate_candidate(candidate, workspace_root=tmp_path)
    assert report.ok


def test_candidate_outside_workspace_rejected(tmp_path: Path):
    outside = tmp_path.parent / 'outside-candidate'
    outside.mkdir(exist_ok=True)
    (outside / 'c0_target.py').write_text('x=1')
    report = validate_candidate(outside, workspace_root=tmp_path)
    assert report.code == 'candidate_outside_workspace'


def test_bounded_run_truncates_output(tmp_path: Path):
    proc = bounded_run(['python3', '-c', 'print("x" * 1000)'], cwd=tmp_path, max_output=20)
    assert len(proc.stdout) <= 20
