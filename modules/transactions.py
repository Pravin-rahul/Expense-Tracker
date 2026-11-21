"""Transaction model and CRUD / search operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Iterable

from database.db import Database
from utils.validation import validate_transaction


@dataclass(frozen=True)
class Transaction:
    """Immutable row object. Using a class keeps the rest of the code readable."""

    id: int
    transaction_type: str
    amount: float
    category: str
    description: str
    transaction_date: str
    payment_method: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Transaction":
        return cls(**{key: row[key] for key in row.keys()})

    @property
    def is_income(self) -> bool:
        return self.transaction_type == "Income"

    @property
    def date(self) -> date:
        return date.fromisoformat(self.transaction_date)

    def to_dict(self) -> dict:
        return asdict(self)


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards so searching for '50%' matches literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TransactionManager:
    """All reads and writes for the transactions table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- Create / Update / Delete -------------------------------------------------
    def add(self, transaction_type, amount, category, description,
            transaction_date, payment_method) -> int:
        data = validate_transaction(transaction_type, amount, category, description,
                                    transaction_date, payment_method)
        new_id, _ = self._db.execute(
            """INSERT INTO transactions
               (transaction_type, amount, category, description,
                transaction_date, payment_method, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data["transaction_type"], data["amount"], data["category"],
             data["description"], data["transaction_date"], data["payment_method"],
             datetime.now().isoformat(timespec="seconds")),
        )
        return new_id

    def update(self, transaction_id: int, transaction_type, amount, category,
               description, transaction_date, payment_method) -> bool:
        data = validate_transaction(transaction_type, amount, category, description,
                                    transaction_date, payment_method)
        _, changed = self._db.execute(
            """UPDATE transactions
               SET transaction_type = ?, amount = ?, category = ?, description = ?,
                   transaction_date = ?, payment_method = ?
               WHERE id = ?""",
            (data["transaction_type"], data["amount"], data["category"],
             data["description"], data["transaction_date"], data["payment_method"],
             transaction_id),
        )
        return changed > 0

    def delete(self, transaction_id: int) -> bool:
        _, changed = self._db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        return changed > 0

    # ---- Read ---------------------------------------------------------------------
    def get(self, transaction_id: int) -> Transaction | None:
        row = self._db.fetch_one("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        return Transaction.from_row(row) if row else None

    def list(self, search: str = "", start_date=None, end_date=None,
             categories: Iterable[str] | None = None,
             payment_methods: Iterable[str] | None = None,
             transaction_type: str | None = None,
             limit: int | None = None) -> list[Transaction]:
        """Filtered, newest-first list. Every value is bound as a SQL parameter."""
        clauses: list[str] = []
        params: list = []

        search = (search or "").strip()
        if search:
            like = f"%{_escape_like(search)}%"
            clauses.append(
                "(description LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' "
                "OR payment_method LIKE ? ESCAPE '\\')"
            )
            params += [like, like, like]
        if start_date:
            clauses.append("transaction_date >= ?")
            params.append(_iso(start_date))
        if end_date:
            clauses.append("transaction_date <= ?")
            params.append(_iso(end_date))
        if categories:
            categories = list(categories)
            clauses.append(f"category IN ({','.join('?' * len(categories))})")
            params += categories
        if payment_methods:
            payment_methods = list(payment_methods)
            clauses.append(f"payment_method IN ({','.join('?' * len(payment_methods))})")
            params += payment_methods
        if transaction_type in ("Income", "Expense"):
            clauses.append("transaction_type = ?")
            params.append(transaction_type)

        sql = "SELECT * FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY transaction_date DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))

        return [Transaction.from_row(row) for row in self._db.fetch_all(sql, params)]

    def recent(self, count: int = 8) -> list[Transaction]:
        return self.list(limit=count)

    def count(self) -> int:
        return self._db.fetch_one("SELECT COUNT(*) AS n FROM transactions")["n"]

    def years(self) -> list[int]:
        rows = self._db.fetch_all(
            "SELECT DISTINCT CAST(strftime('%Y', transaction_date) AS INTEGER) AS y "
            "FROM transactions ORDER BY y"
        )
        return [row["y"] for row in rows]
