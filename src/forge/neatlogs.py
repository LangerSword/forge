"""Trace sinks: local-first, optional Neatlogs mirror."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .tracing import JsonlTraceSink, TraceRecord, TraceSink


@dataclass(frozen=True)
class ForgeTraceEnvelope:
    schema_version: str
    trace_id: str
    span_id: str
    event: str
    actor: str
    timestamp: str
    payload: dict[str, Any]
    source: str = "forge"


class NeatlogsAdapter:
    """Optional mirror boundary; does not claim delivery without SDK/key."""
    def __init__(self):
        self.enabled = bool(os.environ.get("NEATLOGS_API_KEY"))
        self.delivered = 0
        self.failures = 0

    def emit(self, record: TraceRecord) -> None:
        if not self.enabled:
            return
        # SDK/endpoint remains intentionally unconfigured until credentials and
        # exact ingestion contract are supplied. Never silently fake delivery.
        self.failures += 1
        raise RuntimeError("neatlogs transport not configured")


class LocalFirstTraceSink:
    def __init__(self, local: JsonlTraceSink, mirror: NeatlogsAdapter | None = None):
        self.local = local
        self.mirror = mirror

    def emit(self, record: TraceRecord) -> ForgeTraceEnvelope:
        envelope = ForgeTraceEnvelope(
            schema_version="forge.trace.v1",
            trace_id=record.run_id,
            span_id=f"{record.run_id}:{record.event}",
            event=record.event,
            actor=record.actor,
            timestamp=record.timestamp,
            payload=record.payload,
        )
        normalized = TraceRecord(
            run_id=envelope.trace_id,
            event=envelope.event,
            actor=envelope.actor,
            payload=asdict(envelope),
            timestamp=envelope.timestamp,
        )
        self.local.emit(normalized)
        if self.mirror:
            try:
                self.mirror.emit(normalized)
            except Exception:
                # Local evidence remains authoritative; telemetry cannot alter run outcome.
                pass
        return envelope
