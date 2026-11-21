"""Optional demo data so the dashboard has something to show on first run."""

from __future__ import annotations

import calendar
import random
from datetime import date

from modules.budget import BudgetManager
from modules.transactions import TransactionManager

DAILY_SPEND = [  # (category, low, high, description, payment method)
    ("Food & Dining", 120, 650, "Lunch / snacks", "UPI"),
    ("Groceries", 300, 1800, "Vegetables and groceries", "UPI"),
    ("Transport", 60, 450, "Auto / bus / fuel", "Cash"),
    ("Shopping", 400, 3500, "Clothes and accessories", "Credit Card"),
    ("Entertainment", 150, 800, "Movie / OTT", "Debit Card"),
    ("Bills & Recharge", 199, 699, "Mobile / internet recharge", "UPI"),
]


def load_sample_data(transactions: TransactionManager, budgets: BudgetManager | None = None,
                     months: int = 3, seed: int = 7) -> int:
    rng = random.Random(seed)
    today = date.today()
    added = 0

    for back in range(months):
        year, month = today.year, today.month - back
        while month <= 0:
            month += 12
            year -= 1
        last_day = today.day if back == 0 else calendar.monthrange(year, month)[1]

        def on(day: int) -> date:
            return date(year, month, day)

        fixed = [
            (1, "Income", 65000, "Salary", "Monthly salary", "Net Banking"),
            (3, "Expense", 14000, "Rent", "House rent", "Net Banking"),
            (5, "Expense", 2200, "Utilities", "Electricity and water", "UPI"),
            (15, "Income", rng.randrange(6000, 14000, 500), "Freelance", "Freelance project", "UPI"),
        ]
        for day, kind, amount, category, description, method in fixed:
            if day <= last_day:
                transactions.add(kind, amount, category, description, on(day), method)
                added += 1

        for day in range(1, last_day + 1):
            if rng.random() < 0.75:
                category, low, high, description, method = rng.choice(DAILY_SPEND)
                amount = rng.randrange(low, high, 10)
                transactions.add("Expense", amount, category, description, on(day), method)
                added += 1

    if budgets is not None:
        for category, amount in [("Food & Dining", 5000), ("Groceries", 6000), ("Transport", 3000),
                                 ("Shopping", 5000), ("Entertainment", 2500)]:
            budgets.set_budget(today.month, today.year, category, amount)
    return added
