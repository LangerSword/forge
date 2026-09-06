"""Deterministic C0 fixture with immutable acceptance tests."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
import neatlogs
from .safety import validate_candidate

TASK_ID = "c0-name-normalizer-v1"
TARGET = """def normalize_name(value: str) -> str:
    raise NotImplementedError
"""
TESTS = """import pytest
from c0_target import normalize_name

@pytest.mark.parametrize("value, expected", [
    ("Ada Lovelace", "ada-lovelace"),
    ("  Grace   Hopper ", "grace-hopper"),
    ("UPPER_case", "upper_case"),
])
def test_normalize(value, expected):
    assert normalize_name(value) == expected

def test_blank_rejected():
    with pytest.raises(ValueError):
        normalize_name("   ")
"""


def create_fixture(root: Path) -> Path:
    fixture = root / TASK_ID
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "c0_target.py").write_text(TARGET)
    return fixture


def _frozen_test_hash(source: str = TESTS) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


@neatlogs.span(kind="TOOL", name="run_fixture_verification")
def run_fixture_verification(candidate: Path, *, frozen_tests: str = TESTS, max_output_chars: int = 20000) -> dict:
    """Verify an explicit candidate against tests copied from a trusted bundle.

    The candidate cannot modify the source test bundle: tests are copied to a
    separate temporary directory and imported from the candidate by path.
    """
    report = validate_candidate(candidate, workspace_root=candidate.parent)
    if not report.ok:
        return {"task_id": TASK_ID, "exit_code": 2, "passed": False,
                "failure_code": report.code, "stdout": "", "stderr": report.code,
                "changed_files": [], "test_bundle_sha256": _frozen_test_hash(frozen_tests)}
    candidate = report.path
    if not (candidate / "c0_target.py").is_file():
        return {"task_id": TASK_ID, "exit_code": 2, "passed": False,
                "failure_code": "candidate_missing", "stdout": "", "stderr": "candidate_missing:c0_target.py",
                "changed_files": [], "test_bundle_sha256": _frozen_test_hash(frozen_tests)}
    before = {p.relative_to(candidate).as_posix() for p in candidate.rglob("*") if p.is_file()}
    with tempfile.TemporaryDirectory(prefix="forge-c0-verify-") as sandbox_dir:
        sandbox = Path(sandbox_dir)
        shutil.copy2(candidate / "c0_target.py", sandbox / "c0_target.py")
        test_file = sandbox / "forge_frozen_test.py"
        test_file.write_text(frozen_tests)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", test_file.name],
            cwd=sandbox, capture_output=True, text=True, timeout=60,
            env={"PATH": str(Path(sys.executable).parent), "PYTHONPATH": str(sandbox)},
        )
    after = {p.relative_to(candidate).as_posix() for p in candidate.rglob("*") if p.is_file()}
    generated = {".pytest_cache", "__pycache__"}
    changed = sorted(p for p in (after | before)
                     if not any(part in generated for part in Path(p).parts)
                     and not p.endswith(".pyc")
                     )
    return {
        "task_id": TASK_ID, "exit_code": proc.returncode, "passed": proc.returncode == 0,
        "stdout": proc.stdout[-max_output_chars:], "stderr": proc.stderr[-max_output_chars:], "changed_files": changed,
        "failure_code": None if proc.returncode == 0 else "test_failure",
        "test_bundle_sha256": _frozen_test_hash(frozen_tests),
    }
