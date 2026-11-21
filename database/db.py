"""SQLite access layer: connection handling, schema creation and query helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "expense_tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_type  TEXT NOT NULL CHECK (transaction_type IN ('Income', 'Expense')),
    amount            REAL NOT NULL CHECK (amount > 0),
    category          TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    transaction_date  TEXT NOT NULL,            -- ISO format: YYYY-MM-DD
    payment_method    TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    month          INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year           INTEGER NOT NULL,
    category       TEXT NOT NULL,
    budget_amount  REAL NOT NULL CHECK (budget_amount > 0),
    created_at     TEXT NOT NULL,
    UNIQUE (month, year, category)
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category);
"""


class Database:
    """Thin wrapper around sqlite3.

    Every call opens a short-lived connection, commits on success and rolls
    back on any error, so callers never have to manage connections themselves.
    The path is kept private (encapsulation) and exposed read-only.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def path(self) -> Path:
        return self._db_path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Sequence = ()) -> tuple[int, int]:
        """Run INSERT/UPDATE/DELETE. Returns (last_row_id, affected_rows)."""
        with self.connection() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid, cur.rowcount

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def fetch_one(self, sql: str, params: Sequence = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()
