"""Small append-only SQLite event ledger for Forge runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, root: Path):
        self.path = root / ".forge" / "ledger" / "ledger.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
          run_id TEXT PRIMARY KEY, goal TEXT NOT NULL, condition TEXT NOT NULL,
          harness TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          ts TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL,
          payload TEXT NOT NULL
        );
        """)
        self.db.commit()

    def run(self, run_id: str, goal: str, condition: str, harness: str | None, status: str = "created") -> None:
        self.db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, goal, condition, harness, status, utc_now()))
        self.db.commit()

    def event(self, run_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO events(run_id,ts,kind,actor,payload) VALUES (?, ?, ?, ?, ?)",
                        (run_id, utc_now(), kind, actor, json.dumps(payload, sort_keys=True)))
        self.db.commit()

    def counts(self) -> dict[str, int]:
        runs = self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        events = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"runs": runs, "events": events}

    def update_run_status(self, run_id: str, status: str) -> None:
        self.db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
        self.db.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self.db.execute("""
            SELECT r.*, COUNT(e.id) AS event_count, MAX(e.ts) AS last_event_at
            FROM runs r LEFT JOIN events e ON e.run_id = r.run_id
            GROUP BY r.run_id ORDER BY r.created_at DESC, r.run_id ASC
        """).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        summary = self.db.execute("SELECT COUNT(*) AS event_count, MAX(ts) AS last_event_at FROM events WHERE run_id=?", (run_id,)).fetchone()
        result["event_count"] = summary["event_count"]
        result["last_event_at"] = summary["last_event_at"]
        events = []
        for event in self.db.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall():
            item = dict(event)
            try:
                item["payload"] = json.loads(item["payload"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt event payload for {run_id} event {item['id']}") from exc
            events.append(item)
        result["events"] = events
        return result
