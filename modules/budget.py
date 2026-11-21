"""Monthly category budgets, utilisation tracking and alerts."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime

from database.db import Database
from utils.reports import format_inr
from utils.validation import validate_budget

WARNING_THRESHOLD = 80.0   # percent
EXCEEDED_THRESHOLD = 100.0


@dataclass(frozen=True)
class BudgetStatus:
    id: int
    category: str
    budget_amount: float
    spent: float
    remaining: float       # negative when over budget
    utilization: float     # percent
    state: str             # 'ok' | 'warning' | 'exceeded'


def classify(utilization: float) -> str:
    if utilization >= EXCEEDED_THRESHOLD:
        return "exceeded"
    if utilization >= WARNING_THRESHOLD:
        return "warning"
    return "ok"


class BudgetManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set_budget(self, month: int, year: int, category: str, amount) -> None:
        """Create the budget, or update it if one already exists for that month/category."""
        data = validate_budget(month, year, category, amount)
        self._db.execute(
            """INSERT INTO budgets (month, year, category, budget_amount, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (month, year, category)
               DO UPDATE SET budget_amount = excluded.budget_amount""",
            (data["month"], data["year"], data["category"], data["budget_amount"],
             datetime.now().isoformat(timespec="seconds")),
        )

    def delete_budget(self, budget_id: int) -> bool:
        _, changed = self._db.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
        return changed > 0

    def _spending_by_category(self, month: int, year: int) -> dict[str, float]:
        start = date(year, month, 1).isoformat()
        end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
        rows = self._db.fetch_all(
            """SELECT category, SUM(amount) AS total FROM transactions
               WHERE transaction_type = 'Expense' AND transaction_date BETWEEN ? AND ?
               GROUP BY category""",
            (start, end),
        )
        return {row["category"]: row["total"] for row in rows}

    def status(self, month: int, year: int) -> list[BudgetStatus]:
        budgets = self._db.fetch_all(
            "SELECT id, category, budget_amount FROM budgets "
            "WHERE month = ? AND year = ? ORDER BY category",
            (month, year),
        )
        spending = self._spending_by_category(month, year)

        result = []
        for row in budgets:
            spent = spending.get(row["category"], 0.0)
            limit = row["budget_amount"]
            utilization = spent / limit * 100
            result.append(BudgetStatus(
                id=row["id"], category=row["category"], budget_amount=limit,
                spent=spent, remaining=limit - spent, utilization=utilization,
                state=classify(utilization),
            ))
        return result

    @staticmethod
    def alerts(statuses: list[BudgetStatus]) -> list[tuple[str, str]]:
        """Return (level, message) pairs; level is 'error' (exceeded) or 'warning' (80%+)."""
        messages = []
        for item in statuses:
            if item.state == "exceeded":
                over = -item.remaining
                messages.append((
                    "error",
                    f"{item.category}: budget exceeded by {format_inr(over)} "
                    f"({item.utilization:.0f}% used).",
                ))
            elif item.state == "warning":
                messages.append((
                    "warning",
                    f"{item.category}: {item.utilization:.0f}% of the budget is used, "
                    f"{format_inr(item.remaining)} left.",
                ))
        return messages
