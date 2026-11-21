"""Run with:  python -m unittest discover -s tests -v   (from the project root)"""

import csv
import io
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import Database
from modules.analytics import FinancialAnalyzer
from modules.budget import BudgetManager
from modules.transactions import TransactionManager
from utils.reports import format_inr, monthly_summary_text, transactions_to_csv
from utils.validation import ValidationError, validate_transaction


class BaseCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        self.db = Database(self.db_path)
        self.tx = TransactionManager(self.db)
        self.budgets = BudgetManager(self.db)
        self.analyzer = FinancialAnalyzer(self.tx)
        self.today = date.today()
        self.first = self.today.replace(day=1)

    def tearDown(self):
        self._tmp.cleanup()


class TransactionTests(BaseCase):
    def test_crud(self):
        new_id = self.tx.add("Expense", 250.5, "Groceries", "Milk", self.first, "UPI")
        txn = self.tx.get(new_id)
        self.assertEqual((txn.amount, txn.category), (250.5, "Groceries"))

        self.assertTrue(self.tx.update(new_id, "Expense", 300, "Food & Dining", "Dinner", self.first, "Cash"))
        self.assertEqual(self.tx.get(new_id).payment_method, "Cash")

        self.assertTrue(self.tx.delete(new_id))
        self.assertIsNone(self.tx.get(new_id))
        self.assertFalse(self.tx.delete(new_id))

    def test_filters_and_search(self):
        self.tx.add("Expense", 100, "Groceries", "50% off sale", self.first, "UPI")
        self.tx.add("Expense", 200, "Transport", "Taxi", self.first, "Cash")
        self.tx.add("Income", 5000, "Salary", "", self.first, "Net Banking")
        self.assertEqual(len(self.tx.list(search="50%")), 1)           # literal %
        self.assertEqual(len(self.tx.list(search="'; DROP TABLE transactions;--")), 0)
        self.assertEqual(self.tx.count(), 3)                            # table still there
        self.assertEqual(len(self.tx.list(categories=["Transport", "Salary"])), 2)
        self.assertEqual(len(self.tx.list(payment_methods=["Cash"])), 1)
        self.assertEqual(len(self.tx.list(transaction_type="Income")), 1)
        yesterday = self.today - timedelta(days=400)
        self.assertEqual(self.tx.list(end_date=yesterday), [])

    def test_persistence_after_restart(self):
        self.tx.add("Income", 1000, "Salary", "", self.first, "UPI")
        reopened = TransactionManager(Database(self.db_path))
        self.assertEqual(reopened.count(), 1)

    def test_empty_database(self):
        self.assertEqual(self.tx.list(), [])
        summary = self.analyzer.overall_summary()
        self.assertEqual((summary["income"], summary["expense"], summary["savings_pct"]), (0, 0, 0))
        self.assertEqual(self.analyzer.highest_category(self.today.year, self.today.month), None)
        self.assertEqual(self.analyzer.average_daily_expense(self.today.year, self.today.month), 0)
        self.assertEqual(len(self.analyzer.generate_insights(self.today.year, self.today.month)), 1)


class ValidationTests(unittest.TestCase):
    def test_rejects_bad_input(self):
        bad = [
            dict(transaction_type="Loan", amount=10, category="Other", description="", transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount=-5, category="Other", description="", transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount="abc", category="Other", description="", transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount=float("nan"), category="Other", description="", transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount=10, category="Salary", description="", transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount=10, category="Other", description="x" * 201, transaction_date=date.today(), payment_method="UPI"),
            dict(transaction_type="Expense", amount=10, category="Other", description="", transaction_date=date.today() + timedelta(days=1), payment_method="UPI"),
            dict(transaction_type="Expense", amount=10, category="Other", description="", transaction_date="31-12-2024", payment_method="UPI"),
            dict(transaction_type="Expense", amount=10, category="Other", description="", transaction_date=date.today(), payment_method="Bitcoin"),
        ]
        for kwargs in bad:
            with self.assertRaises(ValidationError, msg=kwargs):
                validate_transaction(**kwargs)

    def test_accepts_and_cleans(self):
        cleaned = validate_transaction("Expense", "1,250.456", "Other", "  hi  ", "2025-01-05", "UPI")
        self.assertEqual((cleaned["amount"], cleaned["description"], cleaned["transaction_date"]),
                         (1250.46, "hi", "2025-01-05"))


class BudgetTests(BaseCase):
    def test_upsert_status_and_alerts(self):
        y, m = self.today.year, self.today.month
        self.budgets.set_budget(m, y, "Groceries", 1000)
        self.budgets.set_budget(m, y, "Groceries", 2000)               # update, not duplicate
        self.budgets.set_budget(m, y, "Transport", 500)
        self.budgets.set_budget(m, y, "Shopping", 1000)
        self.assertEqual(len(self.budgets.status(m, y)), 3)

        self.tx.add("Expense", 1700, "Groceries", "", self.first, "UPI")    # 85%
        self.tx.add("Expense", 600, "Transport", "", self.first, "Cash")    # 120%
        self.tx.add("Expense", 100, "Shopping", "", self.first, "Cash")     # 10%

        by_cat = {s.category: s for s in self.budgets.status(m, y)}
        self.assertEqual(by_cat["Groceries"].state, "warning")
        self.assertEqual(by_cat["Groceries"].remaining, 300)
        self.assertEqual(by_cat["Transport"].state, "exceeded")
        self.assertEqual(by_cat["Transport"].remaining, -100)
        self.assertEqual(by_cat["Shopping"].state, "ok")
        levels = sorted(level for level, _ in self.budgets.alerts(list(by_cat.values())))
        self.assertEqual(levels, ["error", "warning"])

    def test_exact_80_percent_triggers_warning(self):
        y, m = self.today.year, self.today.month
        self.budgets.set_budget(m, y, "Rent", 1000)
        self.tx.add("Expense", 800, "Rent", "", self.first, "UPI")
        self.assertEqual(self.budgets.status(m, y)[0].state, "warning")

    def test_budget_validation(self):
        with self.assertRaises(ValidationError):
            self.budgets.set_budget(13, 2025, "Groceries", 100)
        with self.assertRaises(ValidationError):
            self.budgets.set_budget(1, 2025, "Salary", 100)
        with self.assertRaises(ValidationError):
            self.budgets.set_budget(1, 2025, "Groceries", 0)


class AnalyticsTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.y, self.m = 2025, 3                                    # fixed past month
        self.prev = date(2025, 2, 10)
        d = lambda day: date(2025, 3, day)
        self.tx.add("Income", 50000, "Salary", "", d(1), "Net Banking")
        self.tx.add("Expense", 10000, "Rent", "", d(2), "Net Banking")
        self.tx.add("Expense", 2000, "Groceries", "", d(5), "UPI")
        self.tx.add("Expense", 1000, "Groceries", "", d(5), "UPI")
        self.tx.add("Expense", 500, "Transport", "", d(20), "Cash")
        self.tx.add("Expense", 6000, "Shopping", "", self.prev, "Credit Card")
        self.tx.add("Income", 40000, "Salary", "", self.prev, "Net Banking")

    def test_summary(self):
        s = self.analyzer.month_summary(self.y, self.m)
        self.assertEqual((s["income"], s["expense"], s["savings"]), (50000, 13500, 36500))
        self.assertAlmostEqual(s["savings_pct"], 73.0)
        overall = self.analyzer.overall_summary()
        self.assertEqual(overall["balance"], 90000 - 19500)

    def test_categories_and_highest(self):
        cats = self.analyzer.category_spending(self.y, self.m)
        self.assertEqual(list(cats), ["Rent", "Groceries", "Transport"])
        self.assertEqual(cats["Groceries"], 3000)
        self.assertEqual(self.analyzer.highest_category(self.y, self.m), ("Rent", 10000))

    def test_daily_and_average(self):
        daily = self.analyzer.daily_spending(self.y, self.m)
        self.assertEqual(len(daily), 31)
        self.assertEqual(daily["2025-03-05"], 3000)
        self.assertEqual(daily["2025-03-03"], 0)
        self.assertAlmostEqual(self.analyzer.average_daily_expense(self.y, self.m), 13500 / 31)

    def test_average_uses_elapsed_days_in_current_month(self):
        # "Today" is the 10th of the month, so the divisor is 10 days, not 31.
        avg = self.analyzer.average_daily_expense(2025, 3, today=date(2025, 3, 10))
        self.assertAlmostEqual(avg, 13500 / 10)

    def test_average_is_zero_for_future_month(self):
        self.assertEqual(self.analyzer.average_daily_expense(2025, 3, today=date(2025, 2, 1)), 0.0)

    def test_monthly_totals_and_comparison(self):
        rows = self.analyzer.monthly_totals(2025)
        self.assertEqual(len(rows), 12)
        self.assertEqual((rows[1]["income"], rows[1]["expense"], rows[1]["savings"]), (40000, 6000, 34000))
        self.assertEqual(rows[2]["savings"], 36500)
        cmp_ = self.analyzer.monthly_comparison(2025, 3)
        self.assertAlmostEqual(cmp_["expense_change_pct"], 125.0)
        self.assertEqual(cmp_["savings_change"], 2500)
        jan = self.analyzer.monthly_comparison(2025, 1)
        self.assertEqual(jan["previous_label"], "December 2024")

    def test_insights_and_reports(self):
        insights = self.analyzer.generate_insights(self.y, self.m)
        self.assertTrue(any("Rent" in line for line in insights))
        self.assertTrue(any("125%" in line for line in insights))
        text = monthly_summary_text(self.y, self.m, self.analyzer.month_summary(self.y, self.m),
                                    self.analyzer.category_spending(self.y, self.m), [], insights)
        self.assertIn("₹50,000.00", text)

    def test_csv_export(self):
        self.tx.add("Expense", 99, "Other", "=HYPERLINK(\"x\")", date(2025, 3, 9), "UPI")
        text = transactions_to_csv(self.tx.list())
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 8)
        self.assertTrue(any(r["description"].startswith("'=") for r in rows))   # formula neutralised


class FormatTests(unittest.TestCase):
    def test_inr(self):
        self.assertEqual(format_inr(0), "₹0.00")
        self.assertEqual(format_inr(999), "₹999.00")
        self.assertEqual(format_inr(1000), "₹1,000.00")
        self.assertEqual(format_inr(123456.5), "₹1,23,456.50")
        self.assertEqual(format_inr(12345678), "₹1,23,45,678.00")
        self.assertEqual(format_inr(-2500), "-₹2,500.00")


if __name__ == "__main__":
    unittest.main()
