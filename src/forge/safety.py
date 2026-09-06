"""Candidate and subprocess safety boundaries."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidateReport:
    ok: bool
    code: str
    path: Path
    files: int = 0
    bytes: int = 0


def validate_candidate(candidate: Path, *, workspace_root: Path, max_files: int = 128, max_file_bytes: int = 1_048_576) -> CandidateReport:
    if candidate.is_symlink():
        return CandidateReport(False, "candidate_symlink_forbidden", candidate)
    if not candidate.exists():
        return CandidateReport(False, "candidate_missing", candidate)
    if not candidate.is_dir():
        return CandidateReport(False, "candidate_not_directory", candidate)
    resolved = candidate.resolve()
    root = workspace_root.resolve()
    if root not in resolved.parents and resolved != root:
        return CandidateReport(False, "candidate_outside_workspace", resolved)
    count = 0
    total = 0
    for item in resolved.rglob("*"):
        if item.is_symlink():
            return CandidateReport(False, "candidate_contains_symlink", resolved, count, total)
        if item.is_file():
            count += 1
            size = item.stat().st_size
            total += size
            if size > max_file_bytes:
                return CandidateReport(False, "candidate_file_too_large", resolved, count, total)
            if count > max_files:
                return CandidateReport(False, "candidate_too_many_files", resolved, count, total)
    return CandidateReport(True, "ok", resolved, count, total)


def bounded_run(command: list[str], *, cwd: Path, timeout_s: int = 60, max_output: int = 20_000) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout_s, env={"PATH": "/usr/bin:/bin"})
    proc.stdout = proc.stdout[-max_output:]
    proc.stderr = proc.stderr[-max_output:]
    return proc
