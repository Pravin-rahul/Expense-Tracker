"""Personal Expense Tracker & Financial Analyzer - Streamlit UI.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date

import plotly.graph_objects as go
import streamlit as st

from database.db import Database
from modules.analytics import FinancialAnalyzer
from modules.budget import BudgetManager
from modules.transactions import TransactionManager
from utils.reports import (category_breakdown_to_csv, format_inr, monthly_summary_text,
                           save_to_exports, timestamped_name, transactions_to_csv)
from utils.sample_data import load_sample_data
from utils.validation import (ALL_CATEGORIES, EXPENSE_CATEGORIES, MAX_DESCRIPTION,
                              PAYMENT_METHODS, TRANSACTION_TYPES, ValidationError,
                              categories_for)

st.set_page_config(page_title="Expense Tracker", page_icon="₹", layout="wide")

INCOME_COLOR = "#0f766e"
EXPENSE_COLOR = "#be123c"
SAVINGS_COLOR = "#1d4ed8"
PALETTE = ["#0f766e", "#1d4ed8", "#be123c", "#b45309", "#7c3aed", "#0891b2",
           "#65a30d", "#db2777", "#475569", "#ea580c", "#4f46e5", "#059669"]

CSS = """
<style>
  .stApp { background: #ffffff; }
  [data-testid="stSidebar"] { background: #f8fafc; border-right: 1px solid #e2e8f0; }
  .block-container { padding-top: 2rem; max-width: 1200px; }
  .kpi { border: 1px solid #e2e8f0; border-left: 4px solid var(--accent); border-radius: 8px;
         padding: 14px 18px; background: #ffffff; margin-bottom: 12px; }
  .kpi .label { color: #64748b; font-size: 0.85rem; }
  .kpi .value { color: #0f172a; font-size: 1.55rem; font-weight: 650; line-height: 1.3;
                overflow-wrap: anywhere; }
  .kpi .note { color: #64748b; font-size: 0.78rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- services
@st.cache_resource
def get_services():
    db = Database()
    transactions = TransactionManager(db)
    return db, transactions, BudgetManager(db), FinancialAnalyzer(transactions)


DB, TX, BUDGETS, ANALYZER = get_services()


# --------------------------------------------------------------------------- UI helpers
def flash(kind: str, message: str) -> None:
    """Queue a message that survives st.rerun()."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def render_flash() -> None:
    show = {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}
    for kind, message in st.session_state.pop("_flash", []):
        show[kind](message)


def kpi(label: str, value: str, accent: str, note: str = "") -> None:
    note_html = f'<div class="note">{note}</div>' if note else ""
    st.markdown(
        f'<div class="kpi" style="--accent:{accent}"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{note_html}</div>',
        unsafe_allow_html=True,
    )


def show_chart(fig: go.Figure) -> None:
    fig.update_layout(template="plotly_white", margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=-0.15), font=dict(size=13))
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:                       # older Streamlit versions
        st.plotly_chart(fig, use_container_width=True)


def show_table(rows: list[dict]) -> None:
    try:
        st.dataframe(rows, hide_index=True, width="stretch")
    except TypeError:
        st.dataframe(rows, hide_index=True, use_container_width=True)


def transaction_rows(transactions) -> list[dict]:
    return [{
        "ID": t.id,
        "Date": t.date.strftime("%d %b %Y"),
        "Type": t.transaction_type,
        "Category": t.category,
        "Amount": ("+ " if t.is_income else "- ") + format_inr(t.amount),
        "Payment": t.payment_method,
        "Description": t.description,
    } for t in transactions]


def month_picker(key: str) -> tuple[int, int]:
    today = date.today()
    years = sorted(set(TX.years()) | {today.year}, reverse=True)
    col_year, col_month, _ = st.columns([1, 1, 2])
    year = col_year.selectbox("Year", years, key=f"{key}_year")
    month = col_month.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                                format_func=lambda m: calendar.month_name[m], key=f"{key}_month")
    return year, month


def filter_controls(key: str) -> dict:
    """Shared search/filter widgets. Returns keyword arguments for TransactionManager.list()."""
    col_a, col_b = st.columns([2, 1])
    search = col_a.text_input("Search", placeholder="Description, category or payment method",
                              key=f"{key}_search")
    kind = col_b.selectbox("Type", ["All", *TRANSACTION_TYPES], key=f"{key}_type")
    col_c, col_d = st.columns(2)
    categories = col_c.multiselect("Category", ALL_CATEGORIES, key=f"{key}_cats")
    methods = col_d.multiselect("Payment method", PAYMENT_METHODS, key=f"{key}_methods")

    start = end = None
    if st.checkbox("Filter by date range", key=f"{key}_use_dates"):
        today = date.today()
        picked = st.date_input("Date range", value=(today.replace(day=1), today),
                               max_value=today, key=f"{key}_dates")
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            start, end = picked
        else:
            st.info("Pick an end date to apply the range.")

    return dict(search=search, start_date=start, end_date=end, categories=categories,
                payment_methods=methods, transaction_type=None if kind == "All" else kind)


def show_validation_errors(error: ValidationError) -> None:
    for message in error.errors:
        st.error(message)


# --------------------------------------------------------------------------- pages
def page_dashboard() -> None:
    st.title("Dashboard")
    render_flash()
    overall = ANALYZER.overall_summary()
    if overall["count"] == 0:
        st.info("No transactions yet. Add one under Transactions, or load demo data from the sidebar.")

    year, month = month_picker("dash")
    monthly = ANALYZER.month_summary(year, month)
    label = f"{calendar.month_name[month]} {year}"

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi("Total income", format_inr(overall["income"]), INCOME_COLOR, "All time")
    with c2:
        kpi("Total expenses", format_inr(overall["expense"]), EXPENSE_COLOR, "All time")
    with c3:
        kpi("Current balance", format_inr(overall["balance"]),
            INCOME_COLOR if overall["balance"] >= 0 else EXPENSE_COLOR, "Income minus expenses")

    c4, c5, c6 = st.columns(3)
    with c4:
        kpi("Monthly savings", format_inr(monthly["savings"]),
            SAVINGS_COLOR if monthly["savings"] >= 0 else EXPENSE_COLOR, label)
    with c5:
        kpi("Savings percentage", f"{monthly['savings_pct']:.1f}%", SAVINGS_COLOR,
            "Of income" if monthly["income"] else "No income recorded this month")
    with c6:
        kpi("Spent this month", format_inr(monthly["expense"]), EXPENSE_COLOR, label)

    left, right = st.columns(2)
    with left:
        categories = ANALYZER.category_spending(year, month)
        if categories:
            fig = go.Figure(go.Pie(labels=list(categories), values=list(categories.values()),
                                   hole=0.55, marker=dict(colors=PALETTE),
                                   hovertemplate="%{label}: ₹%{value:,.0f} (%{percent})<extra></extra>"))
            fig.update_layout(title=f"Spending by category, {label}")
            show_chart(fig)
        else:
            st.subheader("Spending by category")
            st.caption(f"No expenses recorded for {label}.")
    with right:
        rows = ANALYZER.monthly_totals(year)
        if any(r["income"] or r["expense"] for r in rows):
            fig = go.Figure([
                go.Bar(name="Income", x=[r["label"] for r in rows], y=[r["income"] for r in rows],
                       marker_color=INCOME_COLOR),
                go.Bar(name="Expenses", x=[r["label"] for r in rows], y=[r["expense"] for r in rows],
                       marker_color=EXPENSE_COLOR),
            ])
            fig.update_layout(barmode="group", title=f"Income vs expenses, {year}",
                              yaxis_tickprefix="₹")
            show_chart(fig)
        else:
            st.subheader("Income vs expenses")
            st.caption(f"No transactions recorded for {year}.")

    st.subheader("Recent transactions")
    recent = TX.recent(8)
    if recent:
        show_table(transaction_rows(recent))
    else:
        st.caption("Nothing here yet.")


def tab_add_transaction() -> None:
    kind = st.radio("Type", TRANSACTION_TYPES, horizontal=True, key="add_type")
    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        amount = col1.number_input("Amount (₹)", min_value=0.0, step=100.0, format="%.2f")
        txn_date = col2.date_input("Date", value=date.today(), max_value=date.today())
        category = col1.selectbox("Category", categories_for(kind))
        method = col2.selectbox("Payment method", PAYMENT_METHODS)
        description = st.text_input("Description (optional)", max_chars=MAX_DESCRIPTION)
        submitted = st.form_submit_button(f"Add {kind.lower()}", type="primary")

    if not submitted:
        return
    try:
        new_id = TX.add(kind, amount, category, description, txn_date, method)
    except ValidationError as error:
        show_validation_errors(error)
    except sqlite3.Error as error:
        st.error(f"Could not save the transaction: {error}")
    else:
        st.success(f"{kind} of {format_inr(amount)} saved (ID {new_id}).")
        if kind == "Expense":
            for item in BUDGETS.status(txn_date.month, txn_date.year):
                if item.category == category and item.state != "ok":
                    level = st.error if item.state == "exceeded" else st.warning
                    level(BUDGETS.alerts([item])[0][1])


def tab_history() -> None:
    filters = filter_controls("hist")
    results = TX.list(**filters)
    totals = ANALYZER.summarize(results)
    st.caption(f"{len(results)} transaction(s) | income {format_inr(totals['income'])} | "
               f"expenses {format_inr(totals['expense'])}")
    if not results:
        st.info("No transactions match these filters.")
        return
    show_table(transaction_rows(results))
    st.download_button("Download these results (CSV)", transactions_to_csv(results),
                       file_name=timestamped_name("transactions_filtered"), mime="text/csv")


def tab_edit_delete() -> None:
    query = st.text_input("Find a transaction", placeholder="Search by description, category or payment method",
                          key="edit_search")
    candidates = TX.list(search=query, limit=100)
    if not candidates:
        st.info("No transactions found. Add one first or change the search.")
        return

    labels = {t.id: f"#{t.id} | {t.date:%d %b %Y} | {t.transaction_type} | "
                    f"{format_inr(t.amount)} | {t.category}"
                    + (f" | {t.description}" if t.description else "") for t in candidates}
    selected_id = st.selectbox("Transaction", list(labels), format_func=labels.get, key="edit_select")
    txn = TX.get(selected_id)
    if txn is None:
        st.error("That transaction no longer exists.")
        return

    kid = txn.id
    kind = st.radio("Type", TRANSACTION_TYPES, index=TRANSACTION_TYPES.index(txn.transaction_type),
                    horizontal=True, key=f"edit_type_{kid}")
    options = categories_for(kind)
    with st.form(f"edit_form_{kid}"):
        col1, col2 = st.columns(2)
        amount = col1.number_input("Amount (₹)", min_value=0.0, value=float(txn.amount), step=100.0,
                                   format="%.2f", key=f"edit_amount_{kid}")
        txn_date = col2.date_input("Date", value=txn.date, max_value=date.today(), key=f"edit_date_{kid}")
        category = col1.selectbox("Category", options,
                                  index=options.index(txn.category) if txn.category in options else 0,
                                  key=f"edit_cat_{kid}")
        method = col2.selectbox("Payment method", PAYMENT_METHODS,
                                index=PAYMENT_METHODS.index(txn.payment_method)
                                if txn.payment_method in PAYMENT_METHODS else 0,
                                key=f"edit_method_{kid}")
        description = st.text_input("Description", value=txn.description, max_chars=MAX_DESCRIPTION,
                                    key=f"edit_desc_{kid}")
        save = st.form_submit_button("Save changes", type="primary")

    if save:
        try:
            TX.update(kid, kind, amount, category, description, txn_date, method)
        except ValidationError as error:
            show_validation_errors(error)
        except sqlite3.Error as error:
            st.error(f"Could not update the transaction: {error}")
        else:
            flash("success", f"Transaction #{kid} updated.")
            st.rerun()

    with st.expander("Delete this transaction"):
        confirmed = st.checkbox(f"Yes, permanently delete #{kid}", key=f"confirm_delete_{kid}")
        if st.button("Delete transaction", disabled=not confirmed, key=f"delete_{kid}"):
            try:
                TX.delete(kid)
            except sqlite3.Error as error:
                st.error(f"Could not delete the transaction: {error}")
            else:
                flash("success", f"Transaction #{kid} deleted.")
                st.rerun()


def page_transactions() -> None:
    st.title("Transactions")
    render_flash()
    add_tab, history_tab, edit_tab = st.tabs(["Add", "History and search", "Edit or delete"])
    with add_tab:
        tab_add_transaction()
    with history_tab:
        tab_history()
    with edit_tab:
        tab_edit_delete()


def page_budgets() -> None:
    st.title("Budgets")
    render_flash()
    year, month = month_picker("budget")

    with st.form("budget_form"):
        col1, col2 = st.columns(2)
        category = col1.selectbox("Category", EXPENSE_CATEGORIES)
        amount = col2.number_input("Monthly budget (₹)", min_value=0.0, step=500.0, format="%.2f")
        saved = st.form_submit_button(f"Set budget for {calendar.month_name[month]} {year}", type="primary")
    if saved:
        try:
            BUDGETS.set_budget(month, year, category, amount)
        except ValidationError as error:
            show_validation_errors(error)
        except sqlite3.Error as error:
            st.error(f"Could not save the budget: {error}")
        else:
            flash("success", f"Budget for {category} set to {format_inr(amount)}.")
            st.rerun()

    statuses = BUDGETS.status(month, year)
    if not statuses:
        st.info("No budgets for this month yet. Use the form above to set one.")
        return

    for level, message in BudgetManager.alerts(statuses):
        (st.error if level == "error" else st.warning)(message)

    total_budget = sum(s.budget_amount for s in statuses)
    total_spent = sum(s.spent for s in statuses)
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi("Total budgeted", format_inr(total_budget), SAVINGS_COLOR)
    with c2:
        kpi("Spent in budgeted categories", format_inr(total_spent), EXPENSE_COLOR)
    with c3:
        kpi("Remaining", format_inr(total_budget - total_spent),
            INCOME_COLOR if total_budget >= total_spent else EXPENSE_COLOR)

    for item in statuses:
        row_a, row_b = st.columns([3, 1])
        row_a.markdown(f"**{item.category}** - {format_inr(item.spent)} of "
                       f"{format_inr(item.budget_amount)} ({item.utilization:.0f}% used)")
        row_a.progress(min(item.utilization / 100, 1.0))
        remaining = (f"{format_inr(item.remaining)} left" if item.remaining >= 0
                     else f"{format_inr(-item.remaining)} over")
        row_b.caption(f"Remaining: {remaining}")
        if row_b.button("Remove", key=f"rm_budget_{item.id}"):
            BUDGETS.delete_budget(item.id)
            flash("success", f"Budget for {item.category} removed.")
            st.rerun()

    fig = go.Figure([
        go.Bar(name="Budget", x=[s.category for s in statuses],
               y=[s.budget_amount for s in statuses], marker_color="#cbd5e1"),
        go.Bar(name="Spent", x=[s.category for s in statuses], y=[s.spent for s in statuses],
               marker_color=[{"ok": INCOME_COLOR, "warning": "#b45309", "exceeded": EXPENSE_COLOR}[s.state]
                             for s in statuses]),
    ])
    fig.update_layout(barmode="group", title="Budget vs spending", yaxis_tickprefix="₹")
    show_chart(fig)


def page_analytics() -> None:
    st.title("Analytics")
    year, month = month_picker("analytics")
    label = f"{calendar.month_name[month]} {year}"

    txns = ANALYZER.month_transactions(year, month)
    if not txns:
        st.info(f"No transactions for {label}. Pick another month or add some data.")
        return

    summary = ANALYZER.summarize(txns)
    highest = ANALYZER.highest_category(year, month)
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi("Total spending", format_inr(summary["expense"]), EXPENSE_COLOR, label)
    with c2:
        kpi("Average daily spending", format_inr(ANALYZER.average_daily_expense(year, month)),
            SAVINGS_COLOR, "Elapsed days only for the current month")
    with c3:
        kpi("Highest category", highest[0] if highest else "None", "#b45309",
            format_inr(highest[1]) if highest else "No expenses")

    st.subheader("Insights")
    for line in ANALYZER.generate_insights(year, month):
        st.markdown(f"- {line}")

    left, right = st.columns(2)
    with left:
        categories = ANALYZER.category_spending(year, month)
        if categories:
            names = list(categories)[::-1]
            fig = go.Figure(go.Bar(x=[categories[n] for n in names], y=names, orientation="h",
                                   marker_color=INCOME_COLOR,
                                   hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            fig.update_layout(title="Expenses by category", xaxis_tickprefix="₹")
            show_chart(fig)
    with right:
        daily = ANALYZER.daily_spending(year, month)
        fig = go.Figure(go.Scatter(x=list(daily), y=list(daily.values()), mode="lines+markers",
                                   line=dict(color=EXPENSE_COLOR), fill="tozeroy",
                                   fillcolor="rgba(190,18,60,0.08)",
                                   hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>"))
        fig.update_layout(title="Daily spending trend", yaxis_tickprefix="₹")
        show_chart(fig)

    st.subheader("Compared with the previous month")
    comparison = ANALYZER.monthly_comparison(year, month)
    cur, prev = comparison["current"], comparison["previous"]

    def change(value):
        return "n/a" if value is None else f"{value:+.1f}%"

    show_table([
        {"Measure": "Income", label: format_inr(cur["income"]),
         comparison["previous_label"]: format_inr(prev["income"]),
         "Change": change(comparison["income_change_pct"])},
        {"Measure": "Expenses", label: format_inr(cur["expense"]),
         comparison["previous_label"]: format_inr(prev["expense"]),
         "Change": change(comparison["expense_change_pct"])},
        {"Measure": "Savings", label: format_inr(cur["savings"]),
         comparison["previous_label"]: format_inr(prev["savings"]),
         "Change": format_inr(comparison["savings_change"])},
    ])

    rows = ANALYZER.monthly_totals(year)
    fig = go.Figure(go.Bar(x=[r["label"] for r in rows], y=[r["savings"] for r in rows],
                           marker_color=[SAVINGS_COLOR if r["savings"] >= 0 else EXPENSE_COLOR for r in rows],
                           hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>"))
    fig.update_layout(title=f"Monthly savings, {year}", yaxis_tickprefix="₹")
    show_chart(fig)


def page_reports() -> None:
    st.title("Reports")
    render_flash()

    st.subheader("Export transactions")
    filters = filter_controls("report")
    results = TX.list(**filters)
    st.caption(f"{len(results)} transaction(s) selected")
    if results:
        csv_text = transactions_to_csv(results)
        col1, col2 = st.columns(2)
        col1.download_button("Download CSV", csv_text, file_name=timestamped_name("transactions"),
                             mime="text/csv", type="primary")
        if col2.button("Save a copy in data/exports"):
            try:
                path = save_to_exports(csv_text, timestamped_name("transactions"))
            except OSError as error:
                st.error(f"Could not write the file: {error}")
            else:
                st.success(f"Saved to {path}")
    else:
        st.info("Nothing to export with these filters.")

    st.divider()
    st.subheader("Monthly financial summary")
    year, month = month_picker("report_month")
    txns = ANALYZER.month_transactions(year, month)
    if not txns:
        st.info(f"No transactions for {calendar.month_name[month]} {year}.")
        return

    summary = ANALYZER.summarize(txns)
    categories = ANALYZER.category_totals(txns)
    text = monthly_summary_text(year, month, summary, categories, BUDGETS.status(month, year),
                                ANALYZER.generate_insights(year, month))
    st.code(text, language="text")
    stem = f"summary_{year}_{month:02d}"
    col1, col2 = st.columns(2)
    col1.download_button("Download summary (.txt)", text, file_name=f"{stem}.txt", mime="text/plain")
    col2.download_button("Download category breakdown (.csv)", category_breakdown_to_csv(categories),
                         file_name=f"{stem}_categories.csv", mime="text/csv")


# --------------------------------------------------------------------------- navigation
PAGES = {
    "Dashboard": page_dashboard,
    "Transactions": page_transactions,
    "Budgets": page_budgets,
    "Analytics": page_analytics,
    "Reports": page_reports,
}


def main() -> None:
    with st.sidebar:
        st.markdown("### Expense Tracker")
        st.caption("Personal finance, tracked locally")
        choice = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
        st.divider()
        if TX.count() == 0:
            st.caption("The database is empty.")
            if st.button("Load demo data"):
                added = load_sample_data(TX, BUDGETS)
                flash("success", f"Loaded {added} demo transactions and sample budgets.")
                st.rerun()
        else:
            st.caption(f"{TX.count()} transactions stored in {DB.path.name}")
    PAGES[choice]()


main()
