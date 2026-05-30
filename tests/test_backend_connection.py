# NOTE: Spec states total_spent=346.24 but seed data sums to
# 9450.00. Tests use 9450.00 as the authoritative value.

import pytest
import sqlite3
from werkzeug.security import generate_password_hash
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)
import app as flask_app


TEST_EXPENSES = [
    (1, 450.00,  "Food",          "2026-05-02", "Breakfast at cafe"),
    (1, 1200.00, "Transport",     "2026-05-05", "Monthly bus pass"),
    (1, 3500.00, "Bills",         "2026-05-08", "Electricity bill"),
    (1, 800.00,  "Health",        "2026-05-11", "Pharmacy"),
    (1, 500.00,  "Entertainment", "2026-05-14", "Movie ticket"),
    (1, 2200.00, "Shopping",      "2026-05-17", "Clothing"),
    (1, 150.00,  "Other",         "2026-05-20", "Notebook"),
    (1, 650.00,  "Food",          "2026-05-25", "Dinner with friend"),
]


@pytest.fixture
def db_conn():
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
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00")
    )
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        TEST_EXPENSES
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def monkeypatch_db(monkeypatch, db_conn):
    import database.queries as q
    monkeypatch.setattr(q, "get_db", lambda: db_conn)
    return db_conn


@pytest.fixture
def flask_client():
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    with flask_app.app.test_client() as client:
        yield client


# ---- SUBAGENT-2 TESTS (user / summary stats) ---- #

def test_get_user_by_id_valid(monkeypatch_db):
    result = get_user_by_id(1)
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert result["member_since"] == "January 2026"


def test_get_user_by_id_nonexistent(monkeypatch_db):
    result = get_user_by_id(9999)
    assert result is None


def test_get_summary_stats_with_expenses(monkeypatch_db):
    result = get_summary_stats(1)
    assert result["total_spent"] == 9450.0
    assert result["transaction_count"] == 8
    assert result["top_category"] == "Bills"


def test_get_summary_stats_latest_date(monkeypatch_db):
    result = get_summary_stats(1)
    assert result["latest_date"] == "25 May 2026"


def test_get_summary_stats_no_expenses(monkeypatch_db):
    monkeypatch_db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@example.com", "hash")
    )
    monkeypatch_db.commit()
    result = get_summary_stats(2)
    assert result["total_spent"] == 0.0
    assert result["transaction_count"] == 0
    assert result["top_category"] == "—"
    assert result["latest_date"] == "No expenses yet"


def test_get_user_by_id_member_since_format(monkeypatch_db):
    result = get_user_by_id(1)
    assert result["member_since"] == "January 2026"


# ---- SUBAGENT-1 TESTS (recent transactions) ---- #

def test_get_recent_transactions_returns_list(monkeypatch_db):
    result = get_recent_transactions(1)
    assert isinstance(result, list)
    assert len(result) == 8


def test_get_recent_transactions_newest_first(monkeypatch_db):
    result = get_recent_transactions(1)
    assert result[0]["date"] == "25 May 2026"


def test_get_recent_transactions_item_shape(monkeypatch_db):
    result = get_recent_transactions(1)
    for item in result:
        assert set(item.keys()) >= {"date", "description", "category", "amount"}
        assert isinstance(item["amount"], float)


def test_get_recent_transactions_description_fallback(monkeypatch_db):
    monkeypatch_db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (1, 10.0, "Misc", "2026-06-01", None)
    )
    monkeypatch_db.commit()
    result = get_recent_transactions(1)
    none_desc = next(r for r in result if r["date"] == "01 Jun 2026")
    assert none_desc["description"] == "Misc"


def test_get_recent_transactions_limit(monkeypatch_db):
    result = get_recent_transactions(1, limit=3)
    assert len(result) == 3


def test_get_recent_transactions_empty_user(monkeypatch_db):
    result = get_recent_transactions(999)
    assert result == []


# ---- SUBAGENT-3 TESTS (category breakdown) ---- #

def test_get_category_breakdown_returns_list(monkeypatch_db):
    result = get_category_breakdown(1)
    assert isinstance(result, list)
    assert len(result) == 7


def test_get_category_breakdown_ordered_by_amount(monkeypatch_db):
    result = get_category_breakdown(1)
    assert result[0]["name"] == "Bills"
    assert result[0]["amount"] == 3500.0


def test_get_category_breakdown_item_shape(monkeypatch_db):
    result = get_category_breakdown(1)
    for item in result:
        assert "name" in item
        assert "amount" in item
        assert "pct" in item
        assert isinstance(item["amount"], float)
        assert isinstance(item["pct"], int)


def test_get_category_breakdown_pct_sum_to_100(monkeypatch_db):
    result = get_category_breakdown(1)
    assert sum(item["pct"] for item in result) == 100


def test_get_category_breakdown_pct_are_integers(monkeypatch_db):
    result = get_category_breakdown(1)
    assert all(isinstance(item["pct"], int) for item in result)


def test_get_category_breakdown_empty_user(monkeypatch_db):
    result = get_category_breakdown(999)
    assert result == []


def test_get_category_breakdown_bills_amount(monkeypatch_db):
    result = get_category_breakdown(1)
    bills = next(item for item in result if item["name"] == "Bills")
    assert bills["amount"] == 3500.0


# ---- ROUTE TESTS ---- #

def test_profile_unauthenticated_redirects(flask_client):
    response = flask_client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated_returns_200(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    response = flask_client.get("/profile")
    assert response.status_code == 200


def test_profile_contains_user_name(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    response = flask_client.get("/profile")
    assert b"Demo User" in response.data


def test_profile_contains_email(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    response = flask_client.get("/profile")
    assert b"demo@spendly.com" in response.data


def test_profile_contains_rupee_symbol(flask_client):
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    response = flask_client.get("/profile")
    assert "₹".encode() in response.data


def test_profile_total_spent(flask_client):
    # Spec value 346.24 is incorrect; seed data sums to 9450.00
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
    response = flask_client.get("/profile")
    assert b"9,450.00" in response.data
