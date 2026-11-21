"""Formatting helpers and CSV / text report generation (built-in csv module only)."""

from __future__ import annotations

import calendar
import csv
import io
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = BASE_DIR / "data" / "exports"

CSV_COLUMNS = ["id", "transaction_date", "transaction_type", "category",
               "amount", "payment_method", "description", "created_at"]


def format_inr(amount: float) -> str:
    """Format using Indian digit grouping, e.g. 1234567.5 -> ₹12,34,567.50."""
    sign = "-" if amount < 0 else ""
    whole, fraction = f"{abs(float(amount)):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}₹{whole}.{fraction}"


def _safe_cell(value):
    """Stop spreadsheet apps from running text such as '=SUM(...)' as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def transactions_to_csv(transactions) -> str:
    """Serialise Transaction objects to CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for txn in transactions:
        row = txn.to_dict()
        writer.writerow({key: _safe_cell(row[key]) for key in CSV_COLUMNS})
    return buffer.getvalue()


def category_breakdown_to_csv(categories: dict[str, float]) -> str:
    total = sum(categories.values())
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["category", "amount", "share_percent"])
    for name, amount in categories.items():
        share = amount / total * 100 if total else 0
        writer.writerow([_safe_cell(name), f"{amount:.2f}", f"{share:.1f}"])
    return buffer.getvalue()


def save_to_exports(content: str, filename: str, folder: Path = EXPORT_DIR) -> Path:
    """Write text to data/exports/ and return the path (creates the folder if needed)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(filename).name   # .name strips any directory parts
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write(content)
    return path


def timestamped_name(prefix: str, extension: str = "csv") -> str:
    return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.{extension}"


def monthly_summary_text(year: int, month: int, summary: dict,
                         categories: dict[str, float], budget_statuses,
                         insights: list[str]) -> str:
    """Plain-text monthly financial summary."""
    title = f"Monthly Financial Summary - {calendar.month_name[month]} {year}"
    lines = [title, "=" * len(title), "",
             f"Total income    : {format_inr(summary['income'])}",
             f"Total expenses  : {format_inr(summary['expense'])}",
             f"Net savings     : {format_inr(summary['savings'])}",
             f"Savings rate    : {summary['savings_pct']:.1f}%",
             f"Transactions    : {summary['count']}", ""]

    lines.append("Spending by category")
    lines.append("--------------------")
    if categories:
        total = sum(categories.values())
        for name, amount in categories.items():
            lines.append(f"  {name:<18} {format_inr(amount):>16}  ({amount / total * 100:4.1f}%)")
    else:
        lines.append("  No expenses recorded.")
    lines.append("")

    lines.append("Budget status")
    lines.append("-------------")
    if budget_statuses:
        for item in budget_statuses:
            lines.append(
                f"  {item.category:<18} spent {format_inr(item.spent)} of "
                f"{format_inr(item.budget_amount)} ({item.utilization:.0f}%) [{item.state}]"
            )
    else:
        lines.append("  No budgets set for this month.")
    lines.append("")

    lines.append("Insights")
    lines.append("--------")
    lines += [f"  - {text}" for text in insights] or ["  None."]
    lines.append("")
    lines.append(f"Generated on {datetime.now():%d %b %Y, %I:%M %p}")
    return "\n".join(lines)
