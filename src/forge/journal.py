"""Append-only project discovery/setback journal.

Human-readable narrative lives in docs/project-journal.md. Runtime events use
JSONL so the dashboard and eval harness can query them without parsing prose.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.I)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "<redacted>" if _SECRET_KEY.search(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class ProjectJournal:
    def __init__(self, project_root: Path):
        self.path = project_root / ".forge" / "ledger" / "journal.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        entry_type: str,
        status: str,
        title: str,
        summary: str,
        evidence: list[str],
        actor: str = "forge",
        scope: list[str] | None = None,
        impact: dict[str, str] | None = None,
        follow_up: str | None = None,
    ) -> dict[str, Any]:
        if not title.strip() or not summary.strip():
            raise ValueError("journal title and summary are required")
        if not evidence:
            raise ValueError("journal entries require at least one evidence reference")
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": entry_type,
            "status": status,
            "title": title,
            "summary": summary,
            "evidence": evidence,
            "actor": actor,
            "scope": scope or [],
            "impact": impact or {},
            "follow_up": follow_up,
        }
        entry = _redact(entry)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
