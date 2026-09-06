from pathlib import Path

from forge.c0_fixture import create_fixture
from forge.repair import repair_until_pass
from forge.tracing import JsonlTraceSink


class OneShotRepair:
    def repair(self, candidate: Path, failure: dict) -> bool:
        (candidate / 'c0_target.py').write_text(
            "def normalize_name(value: str) -> str:\n"
            "    value = value.strip()\n"
            "    if not value: raise ValueError('blank')\n"
            "    return '-'.join(value.lower().split())\n"
        )
        return True


class NeverRepair:
    def repair(self, candidate: Path, failure: dict) -> bool:
        return False


def test_repair_loop_passes_and_writes_trace(tmp_path: Path):
    candidate = create_fixture(tmp_path)
    sink = JsonlTraceSink(tmp_path / 'trace.jsonl')
    result = repair_until_pass(candidate, adapter=OneShotRepair(), sink=sink, run_id='repair-pass')
    assert result.passed is True
    assert result.attempts == 1
    assert result.negative_lesson is None
    assert len(sink.path.read_text().splitlines()) >= 3


def test_repair_loop_is_bounded_and_records_negative_lesson(tmp_path: Path):
    candidate = create_fixture(tmp_path)
    sink = JsonlTraceSink(tmp_path / 'trace.jsonl')
    result = repair_until_pass(candidate, adapter=NeverRepair(), sink=sink, run_id='repair-fail')
    assert result.passed is False
    assert result.attempts == 1
    assert result.negative_lesson.startswith('repair_failed')
