# Personal Expense Tracker & Financial Analyzer

A personal finance app built to show pure-Python skills: classes, encapsulation, modular design,
SQL with parameterised queries, input validation, and hand-written analytics using only loops,
lists and dictionaries.

**Stack:** Python 3.11+, Streamlit (UI), SQLite3 (storage), Plotly (charts), `csv` (export).
Project code never imports Pandas or NumPy. (Streamlit installs them as its own dependencies;
nothing in this repository uses them.)

## Features

- **Dashboard:** total income and expenses, balance, monthly savings and savings %, category chart, income vs expense chart, recent transactions
- **Transactions:** add, edit, delete, search, filter by date / category / payment method / type, full validation
- **Budgets:** monthly category budgets, utilisation bars, warning at 80%, error when exceeded
- **Analytics:** monthly and category analysis, daily trend, average daily spend, top category, month-over-month comparison, generated insights
- **Reports:** CSV export (all or filtered), monthly summary (.txt), category breakdown (.csv)
- Indian digit grouping for money (₹12,34,567.00), clear success and error messages, empty-database handling

## Architecture

```
app.py                  Streamlit UI: sidebar navigation, pages, charts (no business logic)
database/db.py          Database class: connections, schema, execute / fetch helpers
modules/transactions.py Transaction dataclass + TransactionManager (CRUD, search, filters)
modules/budget.py       BudgetManager: upsert budgets, spending vs budget, alerts
modules/analytics.py    FinancialAnalyzer: aggregations and insights in plain Python
utils/validation.py     Validation rules, category and payment lists, ValidationError
utils/reports.py        format_inr, CSV and text report generation, file saving
utils/sample_data.py    Optional demo data loader
tests/test_core.py      Unit tests (temporary database, no UI needed)
data/                   SQLite file (expense_tracker.db) and exports/ are created here
```

Data flow: `app.py` -> manager classes -> `Database` -> SQLite. Inputs are validated in
`utils/validation.py` before any write. Every SQL value is bound as a `?` parameter.

## Install and run

```bash
cd expense_tracker
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. On first run the database is empty; use **Load demo data** in the
sidebar to see the dashboard filled in. Data is stored in `data/expense_tracker.db` and persists
across restarts.

## Run the tests

```bash
python -m unittest discover -s tests -v
```

## Notes on design choices

- Money is stored as `REAL` and rounded to 2 decimals on input. For a production ledger, store integer paise instead.
- Dates are stored as ISO text (`YYYY-MM-DD`) so SQL range filters and sorting work correctly.
- Budgets have a `UNIQUE (month, year, category)` constraint, so setting one again updates it.
- CSV cells that start with `=`, `+`, `-` or `@` are prefixed with `'` to prevent spreadsheet formula injection.
