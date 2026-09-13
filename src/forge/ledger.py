"""Small append-only SQLite event ledger for Forge runs."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .journal import _redact


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, root: Path):
        self.path = root / ".forge" / "ledger" / "ledger.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Fleet tasks may emit evidence concurrently. SQLite remains the
        # source of truth, but access through this object is serialized so a
        # bounded controller does not fail on thread affinity or write races.
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
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
        CREATE TABLE IF NOT EXISTS task_attempts(
          run_id TEXT NOT NULL,
          task_id TEXT NOT NULL,
          attempt INTEGER NOT NULL,
          state TEXT NOT NULL,
          session_id TEXT,
          worktree TEXT,
          artifact_path TEXT,
          artifact_digest TEXT,
          verification_passed INTEGER,
          lease_owner TEXT,
          lease_expires_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(run_id, task_id, attempt)
        );
        CREATE INDEX IF NOT EXISTS task_attempts_latest
          ON task_attempts(run_id, task_id, attempt DESC);
        """)
        self.db.commit()

    def run(self, run_id: str, goal: str, condition: str, harness: str | None, status: str = "created") -> None:
        with self._lock:
            existing = self.db.execute(
                "SELECT run_id FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if existing is None:
                self.db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, goal, condition, harness, status, utc_now()),
                )
            else:
                self.db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
            self.db.commit()

    def event(self, run_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        with self._lock:
            safe_payload = _redact(payload)
            self.db.execute("INSERT INTO events(run_id,ts,kind,actor,payload) VALUES (?, ?, ?, ?, ?)",
                            (run_id, utc_now(), kind, actor, json.dumps(safe_payload, sort_keys=True)))
            self.db.commit()

    def counts(self) -> dict[str, int]:
        with self._lock:
            runs = self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            events = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            return {"runs": runs, "events": events}

    def update_run_status(self, run_id: str, status: str) -> None:
        with self._lock:
            self.db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
            self.db.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute("""
                SELECT r.*, COUNT(e.id) AS event_count, MAX(e.ts) AS last_event_at
                FROM runs r LEFT JOIN events e ON e.run_id = r.run_id
                GROUP BY r.run_id ORDER BY r.created_at DESC, r.run_id ASC
            """).fetchall()
            return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
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

    def events_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Read decoded events for a run without requiring a parent run row."""
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)
            ).fetchall()
            events: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item["payload"])
                except json.JSONDecodeError as exc:
                    raise ValueError(f"corrupt event payload for {run_id} event {item['id']}") from exc
                events.append(item)
            return events

    def latest_event(self, run_id: str, kind: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM events WHERE run_id=? AND kind=? ORDER BY id DESC LIMIT 1",
                (run_id, kind),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt event payload for {run_id} event {item['id']}") from exc
            return item

    def ensure_task_attempt(self, run_id: str, task_id: str, *, attempt: int, state: str) -> None:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        now = utc_now()
        with self._lock:
            self.db.execute(
                """INSERT OR IGNORE INTO task_attempts
                   (run_id, task_id, attempt, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, task_id, attempt, state, now, now),
            )
            self.db.commit()

    def update_task_attempt(
        self,
        run_id: str,
        task_id: str,
        *,
        attempt: int,
        expected_state: str,
        state: str,
        session_id: str | None = None,
        worktree: str | None = None,
        artifact_path: str | None = None,
        artifact_digest: str | None = None,
        verification_passed: bool | None = None,
        lease_owner: str | None = None,
        lease_expires_at: str | None = None,
    ) -> bool:
        """Compare-and-set one attempt so stale workers cannot overwrite state."""
        with self._lock:
            cursor = self.db.execute(
                """UPDATE task_attempts
                   SET state=?, session_id=COALESCE(?, session_id),
                       worktree=COALESCE(?, worktree), artifact_path=COALESCE(?, artifact_path),
                       artifact_digest=COALESCE(?, artifact_digest),
                       verification_passed=COALESCE(?, verification_passed),
                       lease_owner=COALESCE(?, lease_owner),
                       lease_expires_at=COALESCE(?, lease_expires_at), updated_at=?
                   WHERE run_id=? AND task_id=? AND attempt=? AND state=?""",
                (
                    state,
                    session_id,
                    worktree,
                    artifact_path,
                    artifact_digest,
                    None if verification_passed is None else int(verification_passed),
                    lease_owner,
                    lease_expires_at,
                    utc_now(),
                    run_id,
                    task_id,
                    attempt,
                    expected_state,
                ),
            )
            self.db.commit()
            return cursor.rowcount == 1

    def get_task_attempt(self, run_id: str, task_id: str, *, attempt: int | None = None) -> dict[str, Any] | None:
        with self._lock:
            if attempt is None:
                row = self.db.execute(
                    "SELECT * FROM task_attempts WHERE run_id=? AND task_id=? ORDER BY attempt DESC LIMIT 1",
                    (run_id, task_id),
                ).fetchone()
            else:
                row = self.db.execute(
                    "SELECT * FROM task_attempts WHERE run_id=? AND task_id=? AND attempt=?",
                    (run_id, task_id, attempt),
                ).fetchone()
            if row is None:
                return None
            result = dict(row)
            if result["verification_passed"] is not None:
                result["verification_passed"] = bool(result["verification_passed"])
            return result

    def list_task_attempts(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM task_attempts WHERE run_id=? ORDER BY task_id, attempt",
                (run_id,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                if item["verification_passed"] is not None:
                    item["verification_passed"] = bool(item["verification_passed"])
                result.append(item)
            return result
