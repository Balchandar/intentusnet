from __future__ import annotations
import sqlite3
import json
from typing import Any, Dict, List


class SQLiteCalendarDB:
    """
    Simple SQLite-backed calendar for DLika demo.

    Schema:
        events(
            id INTEGER PK,
            title TEXT,
            start TEXT,  -- ISO8601 timestamp
            end TEXT,
            metadata TEXT,
            created_at TEXT
        )
    """

    def __init__(self, db_path: str = "dlika_calendar.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                start TEXT NOT NULL,
                end TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        conn.close()

    def create_event(self, title: str, start: str, end: str, metadata: Dict[str, Any]) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO events (title, start, end, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (title, start, end, json.dumps(metadata)),
        )
        conn.commit()
        event_id = cur.lastrowid
        conn.close()
        return event_id

    def delete_event(self, event_id: int) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()

    def get_events_in_range(self, start: str, end: str) -> List[Dict[str, Any]]:
        """
        Return events overlapping [start, end).
        """
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, start, end, metadata
            FROM events
            WHERE start < ? AND end > ?
            """,
            (end, start),
        )
        rows = cur.fetchall()
        conn.close()

        events: List[Dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "start": row[2],
                    "end": row[3],
                    "metadata": json.loads(row[4]) if row[4] else {},
                }
            )
        return events
