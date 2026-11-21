"""Financial analytics. Rows come from SQLite; aggregation is plain Python loops and dicts."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from modules.transactions import Transaction, TransactionManager
from utils.reports import format_inr


class FinancialAnalyzer:
    def __init__(self, transactions: TransactionManager) -> None:
        self._tx = transactions

    # ---- helpers ------------------------------------------------------------------
    @staticmethod
    def month_bounds(year: int, month: int) -> tuple[date, date]:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])

    @staticmethod
    def previous_month(year: int, month: int) -> tuple[int, int]:
        return (year - 1, 12) if month == 1 else (year, month - 1)

    def month_transactions(self, year: int, month: int) -> list[Transaction]:
        start, end = self.month_bounds(year, month)
        return self._tx.list(start_date=start, end_date=end)

    # ---- core aggregations (pure functions of a list of transactions) ----------------
    @staticmethod
    def summarize(transactions: list[Transaction]) -> dict:
        income = expense = 0.0
        for txn in transactions:
            if txn.is_income:
                income += txn.amount
            else:
                expense += txn.amount
        savings = income - expense
        savings_pct = (savings / income * 100) if income > 0 else 0.0
        return {"income": income, "expense": expense, "balance": savings,
                "savings": savings, "savings_pct": savings_pct,
                "count": len(transactions)}

    @staticmethod
    def category_totals(transactions: list[Transaction]) -> dict[str, float]:
        """Expense totals per category, largest first."""
        totals: dict[str, float] = {}
        for txn in transactions:
            if not txn.is_income:
                totals[txn.category] = totals.get(txn.category, 0.0) + txn.amount
        return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))

    @staticmethod
    def payment_method_totals(transactions: list[Transaction]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for txn in transactions:
            if not txn.is_income:
                totals[txn.payment_method] = totals.get(txn.payment_method, 0.0) + txn.amount
        return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))

    # ---- public analytics ----------------------------------------------------------
    def overall_summary(self) -> dict:
        return self.summarize(self._tx.list())

    def month_summary(self, year: int, month: int) -> dict:
        return self.summarize(self.month_transactions(year, month))

    def category_spending(self, year: int, month: int) -> dict[str, float]:
        return self.category_totals(self.month_transactions(year, month))

    def highest_category(self, year: int, month: int) -> tuple[str, float] | None:
        totals = self.category_spending(year, month)
        return next(iter(totals.items())) if totals else None

    def monthly_totals(self, year: int) -> list[dict]:
        """Income, expense and savings for each of the 12 months of a year."""
        rows = [{"month": m, "label": calendar.month_abbr[m],
                 "income": 0.0, "expense": 0.0, "savings": 0.0} for m in range(1, 13)]
        for txn in self._tx.list(start_date=date(year, 1, 1), end_date=date(year, 12, 31)):
            row = rows[txn.date.month - 1]
            row["income" if txn.is_income else "expense"] += txn.amount
        for row in rows:
            row["savings"] = row["income"] - row["expense"]
        return rows

    def daily_spending(self, year: int, month: int) -> dict[str, float]:
        """Expense per calendar day, including days with no spending (0.0)."""
        start, end = self.month_bounds(year, month)
        days = {(start + timedelta(days=i)).isoformat(): 0.0
                for i in range((end - start).days + 1)}
        for txn in self.month_transactions(year, month):
            if not txn.is_income:
                days[txn.transaction_date] += txn.amount
        return days

    def average_daily_expense(self, year: int, month: int, today: date | None = None) -> float:
        """Average spend per day. For the current month only elapsed days are counted."""
        today = today or date.today()
        start, end = self.month_bounds(year, month)
        if start > today:
            return 0.0
        days = (min(end, today) - start).days + 1
        total = sum(self.daily_spending(year, month).values())
        return total / days

    def monthly_comparison(self, year: int, month: int) -> dict:
        prev_year, prev_month = self.previous_month(year, month)
        current = self.month_summary(year, month)
        previous = self.month_summary(prev_year, prev_month)

        def pct_change(new: float, old: float):
            return (new - old) / old * 100 if old else None

        return {
            "current": current, "previous": previous,
            "previous_label": f"{calendar.month_name[prev_month]} {prev_year}",
            "expense_change_pct": pct_change(current["expense"], previous["expense"]),
            "income_change_pct": pct_change(current["income"], previous["income"]),
            "savings_change": current["savings"] - previous["savings"],
        }

    def generate_insights(self, year: int, month: int) -> list[str]:
        """Plain-English observations built from the numbers above."""
        label = f"{calendar.month_name[month]} {year}"
        txns = self.month_transactions(year, month)
        if not txns:
            return [f"No transactions recorded for {label} yet."]

        insights: list[str] = []
        summary = self.summarize(txns)
        categories = self.category_totals(txns)

        if categories:
            name, amount = next(iter(categories.items()))
            share = amount / summary["expense"] * 100
            insights.append(f"{name} is your biggest expense: {format_inr(amount)}, "
                            f"{share:.0f}% of this month's spending.")

        if summary["income"] == 0 and summary["expense"] > 0:
            insights.append("No income is recorded this month, so everything spent came out of savings.")
        elif summary["income"] > 0:
            rate = summary["savings_pct"]
            if rate < 0:
                insights.append(f"You spent {format_inr(-summary['savings'])} more than you earned.")
            elif rate < 20:
                insights.append(f"You saved {rate:.0f}% of your income. A common target is 20% or more.")
            else:
                insights.append(f"You saved {rate:.0f}% of your income, which is above the 20% benchmark.")

        comparison = self.monthly_comparison(year, month)
        change = comparison["expense_change_pct"]
        if change is not None:
            direction = "up" if change > 0 else "down"
            insights.append(f"Spending is {direction} {abs(change):.0f}% compared with "
                            f"{comparison['previous_label']}.")

        daily = self.daily_spending(year, month)
        peak_day, peak_amount = max(daily.items(), key=lambda item: item[1])
        if peak_amount > 0:
            peak = date.fromisoformat(peak_day)
            insights.append(f"Your highest-spending day was {peak:%d %b} ({peak:%A}) "
                            f"at {format_inr(peak_amount)}.")

        methods = self.payment_method_totals(txns)
        if methods:
            method, amount = next(iter(methods.items()))
            insights.append(f"Most of your spending went through {method} ({format_inr(amount)}).")

        return insights
