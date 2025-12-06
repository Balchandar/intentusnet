from __future__ import annotations
import sqlite3
import json
from typing import Any, Dict, List, Optional


class SQLiteContactsDB:
    """
    Simple contacts DB for DLika.

    Schema:
        contacts(
            id INTEGER PK,
            name TEXT UNIQUE,
            phone TEXT,
            metadata TEXT,
            created_at TEXT
        )
    """

    def __init__(self, db_path: str = "dlika_contacts.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
        conn.close()

    def upsert_contact(self, name: str, phone: str, metadata: Dict[str, Any]) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO contacts (name, phone, metadata)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                phone = excluded.phone,
                metadata = excluded.metadata
            """,
            (name, phone, json.dumps(metadata)),
        )
        conn.commit()
        conn.close()

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, phone, metadata, created_at
            FROM contacts
            WHERE name = ?
            """,
            (name,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "phone": row[2],
            "metadata": json.loads(row[3]) if row[3] else {},
            "created_at": row[4],
        }

    def list_contacts(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, phone, metadata
            FROM contacts
            ORDER BY name ASC
            """
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "name": row[1],
                "phone": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
            }
            for row in rows
        ]
