"""SqliteStore: SQLite-backed persistence layer for snapshots, ledger, and metrics tables with WAL mode."""
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

STORE_PATH = os.getenv("STORE_PATH", os.path.join("data", "trading.db"))


class SqliteStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or STORE_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                date TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(kind, date)
            );

            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                date TEXT,
                broker TEXT,
                run_mode TEXT,
                status TEXT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_kind_date ON snapshots(kind, date);
            CREATE INDEX IF NOT EXISTS idx_ledger_date ON ledger(date);
            CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);
        """)
        conn.commit()

    # --- snapshots ---

    def save_snapshot(self, kind: str, date_str: str, payload: dict):
        now = datetime.utcnow().isoformat() + "Z"
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO snapshots (kind, date, payload, created_at)
               VALUES (?, ?, ?, ?)""",
            (kind, date_str, json.dumps(payload, ensure_ascii=False), now),
        )
        conn.commit()

    def load_snapshot(self, kind: str, date_str: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT payload FROM snapshots WHERE kind = ? AND date = ?",
            (kind, date_str),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    # --- ledger ---

    def save_ledger(self, date_str: str, payload: dict):
        now = datetime.utcnow().isoformat() + "Z"
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO ledger (date, payload, created_at)
               VALUES (?, ?, ?)""",
            (date_str, json.dumps(payload, ensure_ascii=False), now),
        )
        conn.commit()

    def load_ledger(self, date_str: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT payload FROM ledger WHERE date = ?", (date_str,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def list_ledger_dates(self) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT date FROM ledger ORDER BY date"
        ).fetchall()
        return [row["date"] for row in rows]

    # --- metrics ---

    def append_metrics(self, record: dict):
        now = datetime.utcnow().isoformat() + "Z"
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO metrics (ts, date, broker, run_mode, status, data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.get("ts", now),
                str(record.get("date") or ""),
                str(record.get("broker") or ""),
                str(record.get("run_mode") or ""),
                str(record.get("status") or ""),
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()
