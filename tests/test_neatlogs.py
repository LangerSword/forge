import json
from pathlib import Path

from forge.neatlogs import LocalFirstTraceSink, NeatlogsAdapter
from forge.tracing import JsonlTraceSink, trace


def test_local_first_trace_is_durable_without_neatlogs(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('NEATLOGS_API_KEY', raising=False)
    local = JsonlTraceSink(tmp_path / 'trace.jsonl')
    sink = LocalFirstTraceSink(local, NeatlogsAdapter())
    envelope = sink.emit(trace('r1', 'verification', 'verifier', {'passed': True}))
    assert envelope.schema_version == 'forge.trace.v1'
    data = json.loads((tmp_path / 'trace.jsonl').read_text())
    assert data['payload']['source'] == 'forge'
    assert data['payload']['payload']['passed'] is True


def test_neatlogs_transport_failure_does_not_break_local(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('NEATLOGS_API_KEY', 'test-only')
    local = JsonlTraceSink(tmp_path / 'trace.jsonl')
    mirror = NeatlogsAdapter()
    LocalFirstTraceSink(local, mirror).emit(trace('r2', 'negative_lesson', 'repair', {'x': 1}))
    assert (tmp_path / 'trace.jsonl').exists()
    assert mirror.failures == 1
