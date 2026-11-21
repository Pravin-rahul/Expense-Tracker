"""Input validation. All user input passes through here before touching the database."""

from __future__ import annotations

import math
from datetime import date, datetime

TRANSACTION_TYPES = ("Income", "Expense")

EXPENSE_CATEGORIES = [
    "Food & Dining", "Groceries", "Rent", "Utilities", "Transport", "Shopping",
    "Health", "Education", "Entertainment", "Travel", "Bills & Recharge",
    "Insurance", "Investments", "Other",
]
INCOME_CATEGORIES = ["Salary", "Freelance", "Business", "Interest", "Gift", "Refund", "Other"]
ALL_CATEGORIES = sorted(set(EXPENSE_CATEGORIES) | set(INCOME_CATEGORIES))
PAYMENT_METHODS = ["UPI", "Cash", "Debit Card", "Credit Card", "Net Banking", "Wallet"]

MAX_AMOUNT = 100_000_000  # 10 crore
MAX_DESCRIPTION = 200


class ValidationError(ValueError):
    """Raised with a list of human-readable problems."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def categories_for(transaction_type: str) -> list[str]:
    return INCOME_CATEGORIES if transaction_type == "Income" else EXPENSE_CATEGORIES


def parse_amount(value) -> float:
    """Convert to a positive, finite float rounded to 2 decimals or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("Amount must be a number.")
    try:
        amount = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValueError("Amount must be a number.") from None
    if math.isnan(amount) or math.isinf(amount):
        raise ValueError("Amount must be a valid number.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if amount > MAX_AMOUNT:
        raise ValueError(f"Amount cannot exceed {MAX_AMOUNT:,}.")
    return round(amount, 2)


def parse_date(value) -> date:
    """Accept a date, datetime or 'YYYY-MM-DD' string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format.") from None


def validate_transaction(transaction_type, amount, category, description,
                         transaction_date, payment_method) -> dict:
    """Return a cleaned dict ready for the database or raise ValidationError."""
    errors: list[str] = []
    cleaned: dict = {}

    if transaction_type not in TRANSACTION_TYPES:
        errors.append("Transaction type must be Income or Expense.")
    cleaned["transaction_type"] = transaction_type

    try:
        cleaned["amount"] = parse_amount(amount)
    except ValueError as exc:
        errors.append(str(exc))

    if transaction_type in TRANSACTION_TYPES and category not in categories_for(transaction_type):
        errors.append(f"'{category}' is not a valid {str(transaction_type).lower()} category.")
    cleaned["category"] = category

    description = (description or "").strip()
    if len(description) > MAX_DESCRIPTION:
        errors.append(f"Description must be {MAX_DESCRIPTION} characters or fewer.")
    cleaned["description"] = description

    try:
        parsed = parse_date(transaction_date)
        if parsed > date.today():
            errors.append("Date cannot be in the future.")
        elif parsed.year < 2000:
            errors.append("Date must be in the year 2000 or later.")
        cleaned["transaction_date"] = parsed.isoformat()
    except ValueError as exc:
        errors.append(str(exc))

    if payment_method not in PAYMENT_METHODS:
        errors.append("Please choose a valid payment method.")
    cleaned["payment_method"] = payment_method

    if errors:
        raise ValidationError(errors)
    return cleaned


def validate_budget(month, year, category, amount) -> dict:
    errors: list[str] = []
    cleaned: dict = {}

    if not isinstance(month, int) or isinstance(month, bool) or not 1 <= month <= 12:
        errors.append("Month must be between 1 and 12.")
    cleaned["month"] = month

    if not isinstance(year, int) or isinstance(year, bool) or not 2000 <= year <= 2100:
        errors.append("Year must be between 2000 and 2100.")
    cleaned["year"] = year

    if category not in EXPENSE_CATEGORIES:
        errors.append("Please choose a valid expense category.")
    cleaned["category"] = category

    try:
        cleaned["budget_amount"] = parse_amount(amount)
    except ValueError as exc:
        errors.append(str(exc).replace("Amount", "Budget amount"))

    if errors:
        raise ValidationError(errors)
    return cleaned
