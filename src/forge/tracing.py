"""Offline-first trace sink; external Neatlogs transport is optional."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TraceRecord:
    run_id: str
    event: str
    actor: str
    payload: dict[str, Any]
    timestamp: str


class TraceSink:
    def emit(self, record: TraceRecord) -> None: ...


class JsonlTraceSink:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: TraceRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def trace(run_id: str, event: str, actor: str, payload: dict[str, Any]) -> TraceRecord:
    return TraceRecord(run_id, event, actor, payload, datetime.now(timezone.utc).isoformat())


def configured_neatlogs() -> bool:
    return bool(os.environ.get("NEATLOGS_API_KEY"))


def emit_trace(sink: TraceSink, run_id: str, event: str, actor: str, payload: dict[str, Any]) -> None:
    """Emit locally; never claims Neatlogs delivery."""
    sink.emit(trace(run_id, event, actor, payload))
