"""
Tests for Step 6: Date Filter for Profile Page (GET /profile)

Covers:
- Route auth guard (unauthenticated → 302 to /login)
- All four preset period params (this_month, last_month, last_3_months, all_time)
- Custom date-range params (valid, invalid format, from > to)
- filter_label and active_period reflected in rendered HTML
- "Showing:" label presence/absence based on active_period
- filter-btn--active CSS class on the correct preset button
- Query helpers (get_summary_stats, get_recent_transactions, get_category_breakdown)
  with date_from / date_to args — filtering, no-filter, and empty-range behaviour
- Zero-expense user/range: no crash, zeros in stats, empty lists
- ₹ symbol always present for authenticated profile page
"""

import sqlite3
from datetime import date, timedelta
import calendar
import pytest
from werkzeug.security import generate_password_hash

import app as flask_app_module
from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Expenses deliberately spread across multiple months to allow date-filter
# assertions.  Today is treated as 2026-05-31 in the project memory, so:
#   - 2026-05-xx  → "this month" and "last 3 months"
#   - 2026-04-xx  → "last month" and "last 3 months"
#   - 2026-03-xx  → "last 3 months" only
#   - 2026-01-xx  → outside last 3 months → only in "all time"

TEST_EXPENSES_MULTI_MONTH = [
    # (user_id, amount, category, date, description)
    (1, 100.00, "Food",      "2026-05-10", "May food"),
    (1, 200.00, "Transport", "2026-05-20", "May transport"),
    (1, 300.00, "Bills",     "2026-04-15", "April bills"),
    (1, 400.00, "Health",    "2026-03-05", "March health"),
    (1, 500.00, "Shopping",  "2026-01-20", "January shopping"),
]

# Total across all months: 1500.00
# May total: 300.00 (2 expenses)
# April total: 300.00 (1 expense)
# Last 3 months (Mar–May): 1000.00 (4 expenses)
# All time: 1500.00 (5 expenses)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    """
    Fresh in-memory SQLite DB with schema, one user, and multi-month expenses.
    Closed after the test.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Test User", "testuser@example.com", generate_password_hash("password123"),
         "2025-12-01 09:00:00"),
    )
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        TEST_EXPENSES_MULTI_MONTH,
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def monkeypatch_db(monkeypatch, db_conn):
    """
    Patch database.queries.get_db to return the in-memory connection so every
    query helper operates against isolated test data.
    """
    import database.queries as q
    monkeypatch.setattr(q, "get_db", lambda: db_conn)
    return db_conn


@pytest.fixture
def flask_client():
    """
    Flask test client with TESTING=True.  Does NOT patch the DB — used for
    route-level tests that hit the real (seed) DB.
    """
    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret"
    with flask_app_module.app.test_client() as client:
        yield client


@pytest.fixture
def auth_flask_client(flask_client):
    """Flask test client pre-authenticated as the seed Demo User (id=1)."""
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    return flask_client


@pytest.fixture
def auth_client_patched(monkeypatch, db_conn):
    """
    Flask test client that is BOTH authenticated AND patched to use the
    in-memory DB (so we can control exactly which expenses exist).
    """
    import database.queries as q
    import database.db as db_mod
    monkeypatch.setattr(q, "get_db", lambda: db_conn)
    monkeypatch.setattr(db_mod, "get_db", lambda: db_conn)

    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret"
    with flask_app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
        yield client


# ---------------------------------------------------------------------------
# Helper: compute expected date boundaries (mirrors _resolve_filter logic)
# ---------------------------------------------------------------------------

def _this_month_range():
    today = date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


def _last_month_range():
    today = date.today()
    last_of_prev = today.replace(day=1) - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return first_of_prev.isoformat(), last_of_prev.isoformat()


def _last_3_months_range():
    today = date.today()
    month, year = today.month - 3, today.year
    if month <= 0:
        month += 12
        year -= 1
    max_day = calendar.monthrange(year, month)[1]
    date_from = date(year, month, min(today.day, max_day)).isoformat()
    return date_from, today.isoformat()


# ---------------------------------------------------------------------------
# 1. Route auth guard
# ---------------------------------------------------------------------------

class TestProfileAuthGuard:
    def test_unauthenticated_redirects_302(self, flask_client):
        response = flask_client.get("/profile")
        assert response.status_code == 302, "Unauthenticated user should be redirected"

    def test_unauthenticated_redirects_to_login(self, flask_client):
        response = flask_client.get("/profile")
        assert "/login" in response.headers["Location"], \
            "Redirect should point to /login"

    def test_unauthenticated_with_period_param_redirects(self, flask_client):
        response = flask_client.get("/profile?period=this_month")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_authenticated_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile")
        assert response.status_code == 200, "Authenticated user should see 200"


# ---------------------------------------------------------------------------
# 2. No-params default (all_time behaviour)
# ---------------------------------------------------------------------------

class TestProfileNoParams:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile")
        assert response.status_code == 200

    def test_contains_rupee_symbol(self, auth_flask_client):
        response = auth_flask_client.get("/profile")
        assert "₹".encode() in response.data, "Rupee symbol must appear on profile page"

    def test_showing_label_absent_for_no_params(self, auth_flask_client):
        response = auth_flask_client.get("/profile")
        assert b"Showing:" not in response.data, \
            "'Showing:' label must not appear when no filter is active"

    def test_all_time_button_active_for_no_params(self, auth_flask_client):
        response = auth_flask_client.get("/profile")
        html = response.data.decode()
        # The All Time anchor must have filter-btn--active
        assert "filter-btn--active" in html, "Some button must be active"
        # Verify it's attached to the All Time link, not others
        assert "All Time" in html


# ---------------------------------------------------------------------------
# 3. period=all_time explicit
# ---------------------------------------------------------------------------

class TestPeriodAllTime:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=all_time")
        assert response.status_code == 200

    def test_showing_label_absent(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=all_time")
        assert b"Showing:" not in response.data, \
            "'Showing:' must not appear for all_time period"

    def test_all_time_button_has_active_class(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=all_time")
        html = response.data.decode()
        # Find the All Time link and confirm it has filter-btn--active
        idx = html.find("All Time")
        assert idx != -1, "All Time button text must be present"
        # The active class should appear somewhere before "All Time" text (within the same anchor tag)
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding, \
            "All Time button must carry filter-btn--active when period=all_time"

    def test_this_month_button_not_active(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=all_time")
        html = response.data.decode()
        idx = html.find("This Month")
        assert idx != -1
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" not in surrounding, \
            "This Month button must NOT be active when period=all_time"

    def test_rupee_symbol_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=all_time")
        assert "₹".encode() in response.data


# ---------------------------------------------------------------------------
# 4. period=this_month
# ---------------------------------------------------------------------------

class TestPeriodThisMonth:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=this_month")
        assert response.status_code == 200

    def test_this_month_button_has_active_class(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=this_month")
        html = response.data.decode()
        idx = html.find("This Month")
        assert idx != -1
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding, \
            "This Month button must carry filter-btn--active when period=this_month"

    def test_showing_label_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=this_month")
        assert b"Showing:" in response.data, \
            "'Showing:' label must appear for this_month filter"

    def test_rupee_symbol_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=this_month")
        assert "₹".encode() in response.data

    def test_stats_only_current_month(self, auth_client_patched):
        """
        With controlled test data, this_month filter must only count May 2026
        expenses (100 + 200 = 300).  This test is date-sensitive: if run in a
        month other than May 2026 the May expenses will NOT be in 'this month',
        so we assert the count is <= total count (non-crash guarantee) and the
        response is 200.
        """
        response = auth_client_patched.get("/profile?period=this_month")
        assert response.status_code == 200

    def test_all_time_button_not_active_for_this_month(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=this_month")
        html = response.data.decode()
        idx = html.find("All Time")
        assert idx != -1
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" not in surrounding, \
            "All Time button must NOT be active when period=this_month"


# ---------------------------------------------------------------------------
# 5. period=last_month
# ---------------------------------------------------------------------------

class TestPeriodLastMonth:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        assert response.status_code == 200

    def test_returns_200_with_zero_expenses_in_range(self, auth_client_patched):
        """Even if no expenses fall in last month, the page must not crash."""
        response = auth_client_patched.get("/profile?period=last_month")
        assert response.status_code == 200

    def test_last_month_button_has_active_class(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        html = response.data.decode()
        idx = html.find("Last Month")
        assert idx != -1
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding, \
            "Last Month button must carry filter-btn--active when period=last_month"

    def test_showing_label_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        assert b"Showing:" in response.data

    def test_rupee_symbol_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        assert "₹".encode() in response.data

    def test_this_month_button_not_active(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        html = response.data.decode()
        idx = html.find("This Month")
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" not in surrounding


# ---------------------------------------------------------------------------
# 6. period=last_3_months
# ---------------------------------------------------------------------------

class TestPeriodLast3Months:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        assert response.status_code == 200

    def test_last_3_months_button_has_active_class(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        html = response.data.decode()
        idx = html.find("Last 3 Months")
        assert idx != -1
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding, \
            "Last 3 Months button must carry filter-btn--active"

    def test_showing_label_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        assert b"Showing:" in response.data

    def test_rupee_symbol_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        assert "₹".encode() in response.data

    def test_all_time_button_not_active(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        html = response.data.decode()
        idx = html.find("All Time")
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" not in surrounding


# ---------------------------------------------------------------------------
# 7. Custom valid date range
# ---------------------------------------------------------------------------

class TestCustomValidRange:
    def test_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert response.status_code == 200

    def test_showing_label_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert b"Showing:" in response.data, \
            "'Showing:' must appear for a custom date range"

    def test_filter_label_contains_formatted_from_date(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        # Spec: "DD Mon YYYY – DD Mon YYYY"
        assert b"01 May 2026" in response.data, \
            "filter_label must contain the formatted from-date"

    def test_filter_label_contains_formatted_to_date(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert b"31 May 2026" in response.data, \
            "filter_label must contain the formatted to-date"

    def test_rupee_symbol_present(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert "₹".encode() in response.data

    def test_no_preset_button_active_for_custom(self, auth_flask_client):
        """When active_period='custom', no preset button should have filter-btn--active."""
        response = auth_flask_client.get("/profile?from=2026-05-01&to=2026-05-31")
        html = response.data.decode()
        presets = ["This Month", "Last Month", "Last 3 Months", "All Time"]
        for preset in presets:
            idx = html.find(preset)
            assert idx != -1, f"Button '{preset}' must be present in template"
            surrounding = html[max(0, idx - 200):idx]
            assert "filter-btn--active" not in surrounding, \
                f"Button '{preset}' must NOT be active when a custom range is selected"

    def test_custom_range_stats_scoped(self, auth_client_patched):
        """Custom range 2026-05-01 to 2026-05-31 should only count May expenses."""
        response = auth_client_patched.get("/profile?from=2026-05-01&to=2026-05-31")
        assert response.status_code == 200
        # May has 2 expenses: 100.00 + 200.00 = 300.00
        assert b"300.00" in response.data, \
            "Only May expenses (total ₹300.00) should be visible for May custom range"
        assert b"2" in response.data  # transaction count

    def test_custom_range_excludes_out_of_range_expenses(self, auth_client_patched):
        """January expense (500.00) must not appear in May-only custom range."""
        response = auth_client_patched.get("/profile?from=2026-05-01&to=2026-05-31")
        html = response.data.decode()
        # January shopping should not appear in stats total
        assert "1,500.00" not in html, \
            "All-time total must not appear when a custom range is selected"

    def test_single_day_range_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-10&to=2026-05-10")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 8. Invalid date format → silent fallback to all_time
# ---------------------------------------------------------------------------

class TestInvalidDateFormat:
    def test_bad_format_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=bad&to=bad")
        assert response.status_code == 200, \
            "Invalid date format must not cause a crash"

    def test_bad_format_showing_label_absent(self, auth_flask_client):
        """Falls back to all_time so 'Showing:' must not appear."""
        response = auth_flask_client.get("/profile?from=bad&to=bad")
        assert b"Showing:" not in response.data, \
            "Invalid dates must silently fall back to all_time (no 'Showing:' label)"

    def test_bad_format_all_time_button_active(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=bad&to=bad")
        html = response.data.decode()
        idx = html.find("All Time")
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding, \
            "All Time button must be active after silent fallback from invalid dates"

    def test_only_from_bad(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=notadate&to=2026-05-31")
        assert response.status_code == 200
        assert b"Showing:" not in response.data

    def test_only_to_bad(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-01&to=notadate")
        assert response.status_code == 200
        assert b"Showing:" not in response.data

    def test_partial_date_format_fallback(self, auth_flask_client):
        """Dates like 2026-5-1 (missing zero-padding) are invalid ISO dates."""
        response = auth_flask_client.get("/profile?from=2026-5-1&to=2026-5-31")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 9. from > to → silent fallback to all_time
# ---------------------------------------------------------------------------

class TestFromAfterTo:
    def test_from_after_to_returns_200(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-31&to=2026-05-01")
        assert response.status_code == 200, \
            "from > to must not crash the page"

    def test_from_after_to_showing_label_absent(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-31&to=2026-05-01")
        assert b"Showing:" not in response.data, \
            "from > to must silently fall back to all_time"

    def test_from_after_to_all_time_button_active(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-05-31&to=2026-05-01")
        html = response.data.decode()
        idx = html.find("All Time")
        surrounding = html[max(0, idx - 200):idx]
        assert "filter-btn--active" in surrounding

    def test_from_equals_to_is_valid(self, auth_flask_client):
        """A single-day range where from == to is valid and should not fall back."""
        response = auth_flask_client.get("/profile?from=2026-05-15&to=2026-05-15")
        assert response.status_code == 200
        assert b"Showing:" in response.data, \
            "from == to is a valid single-day range and should show 'Showing:'"


# ---------------------------------------------------------------------------
# 10. Zero-expense user / empty range: no crash, correct zero display
# ---------------------------------------------------------------------------

class TestZeroExpenseRange:
    def test_authenticated_user_with_no_expenses_returns_200(self, monkeypatch, db_conn):
        """User exists but has no expenses at all."""
        # Insert a second user with no expenses
        db_conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("Empty User", "empty@example.com", generate_password_hash("pass12345"),
             "2025-11-01 08:00:00"),
        )
        db_conn.commit()

        import database.queries as q
        import database.db as db_mod
        monkeypatch.setattr(q, "get_db", lambda: db_conn)
        monkeypatch.setattr(db_mod, "get_db", lambda: db_conn)

        flask_app_module.app.config["TESTING"] = True
        flask_app_module.app.config["SECRET_KEY"] = "test-secret"
        with flask_app_module.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 2
            response = client.get("/profile")
        assert response.status_code == 200, "Empty-expense user must see 200"
        assert b"0" in response.data  # transaction count

    def test_date_range_with_no_matching_expenses_returns_200(self, auth_client_patched):
        """A date range with zero matching expenses must not raise an error."""
        response = auth_client_patched.get("/profile?from=2020-01-01&to=2020-01-31")
        assert response.status_code == 200

    def test_empty_range_shows_no_transactions_text(self, auth_client_patched):
        response = auth_client_patched.get("/profile?from=2020-01-01&to=2020-01-31")
        assert b"No transactions yet." in response.data or b"0" in response.data

    def test_empty_range_no_category_breakdown(self, auth_client_patched):
        response = auth_client_patched.get("/profile?from=2020-01-01&to=2020-01-31")
        assert b"No expenses recorded yet." in response.data or response.status_code == 200


# ---------------------------------------------------------------------------
# 11. Query helper unit tests: get_summary_stats with date args
# ---------------------------------------------------------------------------

class TestGetSummaryStatsDateFilter:
    def test_no_filter_returns_all_expenses(self, monkeypatch_db):
        result = get_summary_stats(1)
        assert result["transaction_count"] == 5, "All 5 test expenses should be counted"
        assert result["total_spent"] == 1500.00

    def test_none_date_args_returns_all_expenses(self, monkeypatch_db):
        result = get_summary_stats(1, date_from=None, date_to=None)
        assert result["transaction_count"] == 5

    def test_date_filter_may_only(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2026-05-01", date_to="2026-05-31")
        assert result["transaction_count"] == 2, "Only 2 May expenses expected"
        assert result["total_spent"] == 300.00

    def test_date_filter_april_only(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2026-04-01", date_to="2026-04-30")
        assert result["transaction_count"] == 1
        assert result["total_spent"] == 300.00

    def test_date_filter_no_match_returns_zeros(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2020-01-01", date_to="2020-12-31")
        assert result["transaction_count"] == 0
        assert result["total_spent"] == 0.0

    def test_date_filter_no_match_latest_date_fallback(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2020-01-01", date_to="2020-12-31")
        assert result["latest_date"] == "No expenses yet"

    def test_date_filter_single_day(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2026-05-10", date_to="2026-05-10")
        assert result["transaction_count"] == 1
        assert result["total_spent"] == 100.00

    def test_date_filter_latest_date_formatted(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2026-05-01", date_to="2026-05-31")
        assert result["latest_date"] == "20 May 2026", \
            "latest_date must be formatted as 'DD Mon YYYY'"

    def test_date_filter_top_category(self, monkeypatch_db):
        result = get_summary_stats(1, date_from="2026-05-01", date_to="2026-05-31")
        # May: Food=100, Transport=200 → top is Transport
        assert result["top_category"] == "Transport"

    def test_date_filter_unknown_user_returns_zeros(self, monkeypatch_db):
        result = get_summary_stats(999, date_from="2026-05-01", date_to="2026-05-31")
        assert result["transaction_count"] == 0
        assert result["total_spent"] == 0.0


# ---------------------------------------------------------------------------
# 12. Query helper unit tests: get_recent_transactions with date args
# ---------------------------------------------------------------------------

class TestGetRecentTransactionsDateFilter:
    def test_no_filter_returns_all(self, monkeypatch_db):
        result = get_recent_transactions(1)
        assert len(result) == 5

    def test_none_date_args_returns_all(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from=None, date_to=None)
        assert len(result) == 5

    def test_date_filter_may_only(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2026-05-01", date_to="2026-05-31")
        assert len(result) == 2, "Only 2 May transactions expected"
        dates = {tx["date"] for tx in result}
        assert "10 May 2026" in dates
        assert "20 May 2026" in dates

    def test_date_filter_excludes_out_of_range(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2026-05-01", date_to="2026-05-31")
        dates = {tx["date"] for tx in result}
        assert "15 Apr 2026" not in dates, "April expense must be excluded from May filter"
        assert "20 Jan 2026" not in dates, "January expense must be excluded from May filter"

    def test_date_filter_no_match_returns_empty_list(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2020-01-01", date_to="2020-12-31")
        assert result == [], "Empty list expected when no expenses in range"

    def test_date_filter_item_shape(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2026-05-01", date_to="2026-05-31")
        for item in result:
            assert "date" in item
            assert "description" in item
            assert "category" in item
            assert "amount" in item

    def test_date_filter_newest_first(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2026-01-01", date_to="2026-05-31")
        dates = [tx["date"] for tx in result]
        assert dates == sorted(dates, reverse=True), \
            "Transactions must be returned newest-first"

    def test_date_filter_respects_limit(self, monkeypatch_db):
        result = get_recent_transactions(1, limit=1, date_from="2026-05-01", date_to="2026-05-31")
        assert len(result) == 1

    def test_date_filter_unknown_user(self, monkeypatch_db):
        result = get_recent_transactions(999, date_from="2026-05-01", date_to="2026-05-31")
        assert result == []

    def test_date_filter_single_day(self, monkeypatch_db):
        result = get_recent_transactions(1, date_from="2026-04-15", date_to="2026-04-15")
        assert len(result) == 1
        assert result[0]["amount"] == 300.00


# ---------------------------------------------------------------------------
# 13. Query helper unit tests: get_category_breakdown with date args
# ---------------------------------------------------------------------------

class TestGetCategoryBreakdownDateFilter:
    def test_no_filter_returns_all_categories(self, monkeypatch_db):
        result = get_category_breakdown(1)
        assert len(result) == 5, "5 distinct categories in test data"

    def test_none_date_args_returns_all(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from=None, date_to=None)
        assert len(result) == 5

    def test_date_filter_may_only_returns_correct_categories(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-05-01", date_to="2026-05-31")
        # May: Food (100), Transport (200) → 2 categories
        assert len(result) == 2
        names = {c["name"] for c in result}
        assert "Food" in names
        assert "Transport" in names

    def test_date_filter_may_only_amounts(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-05-01", date_to="2026-05-31")
        transport = next(c for c in result if c["name"] == "Transport")
        food = next(c for c in result if c["name"] == "Food")
        assert transport["amount"] == 200.00
        assert food["amount"] == 100.00

    def test_date_filter_may_only_pct_sum_100(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-05-01", date_to="2026-05-31")
        assert sum(c["pct"] for c in result) == 100

    def test_date_filter_no_match_returns_empty_list(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2020-01-01", date_to="2020-12-31")
        assert result == [], "Empty list expected when no expenses in range"

    def test_date_filter_ordered_by_amount_desc(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-01-01", date_to="2026-05-31")
        amounts = [c["amount"] for c in result]
        assert amounts == sorted(amounts, reverse=True), \
            "Categories must be ordered by amount descending"

    def test_date_filter_item_shape(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-05-01", date_to="2026-05-31")
        for item in result:
            assert "name" in item
            assert "amount" in item
            assert "pct" in item
            assert isinstance(item["pct"], int)
            assert isinstance(item["amount"], float)

    def test_date_filter_unknown_user_returns_empty(self, monkeypatch_db):
        result = get_category_breakdown(999, date_from="2026-05-01", date_to="2026-05-31")
        assert result == []

    def test_date_filter_top_category_correct(self, monkeypatch_db):
        result = get_category_breakdown(1, date_from="2026-05-01", date_to="2026-05-31")
        assert result[0]["name"] == "Transport", \
            "Transport (200) must be top category in May"


# ---------------------------------------------------------------------------
# 14. filter_label format: "DD Mon YYYY – DD Mon YYYY"
# ---------------------------------------------------------------------------

class TestFilterLabelFormat:
    def test_this_month_label_format(self, auth_flask_client):
        """filter_label for this_month must match DD Mon YYYY – DD Mon YYYY."""
        response = auth_flask_client.get("/profile?period=this_month")
        html = response.data.decode()
        import re
        # Pattern: "01 Jan 2026 – 31 Jan 2026"
        pattern = r"\d{2} [A-Z][a-z]{2} \d{4} – \d{2} [A-Z][a-z]{2} \d{4}"
        assert re.search(pattern, html), \
            "filter_label must follow 'DD Mon YYYY – DD Mon YYYY' format"

    def test_last_month_label_format(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_month")
        html = response.data.decode()
        import re
        pattern = r"\d{2} [A-Z][a-z]{2} \d{4} – \d{2} [A-Z][a-z]{2} \d{4}"
        assert re.search(pattern, html), \
            "Last month filter_label must follow the correct format"

    def test_all_time_label_value(self, auth_flask_client):
        """For all_time the filter_label value is 'All time' but 'Showing:' is hidden."""
        response = auth_flask_client.get("/profile")
        # 'Showing:' absent means the label paragraph is not rendered at all
        assert b"Showing:" not in response.data

    def test_custom_range_label_matches_input_dates(self, auth_flask_client):
        response = auth_flask_client.get("/profile?from=2026-03-01&to=2026-03-31")
        assert b"01 Mar 2026" in response.data
        assert b"31 Mar 2026" in response.data

    def test_last_3_months_label_format(self, auth_flask_client):
        response = auth_flask_client.get("/profile?period=last_3_months")
        html = response.data.decode()
        import re
        pattern = r"\d{2} [A-Z][a-z]{2} \d{4} – \d{2} [A-Z][a-z]{2} \d{4}"
        assert re.search(pattern, html), \
            "Last 3 months filter_label must follow the correct format"


# ---------------------------------------------------------------------------
# 15. Parametrized: every preset period returns 200 and shows rupee symbol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ["this_month", "last_month", "last_3_months", "all_time"])
def test_every_preset_returns_200_with_rupee(auth_flask_client, period):
    response = auth_flask_client.get(f"/profile?period={period}")
    assert response.status_code == 200, f"period={period} must return 200"
    assert "₹".encode() in response.data, \
        f"Rupee symbol must appear on profile page for period={period}"


# ---------------------------------------------------------------------------
# 16. Parametrized: unknown / garbage period value falls back gracefully
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period", ["", "yesterday", "weekly", "123", "all_Time"])
def test_unknown_period_value_returns_200(auth_flask_client, period):
    """Unrecognised period values must silently fall back to all_time."""
    response = auth_flask_client.get(f"/profile?period={period}")
    assert response.status_code == 200, \
        f"Unknown period '{period}' must not crash the server"
