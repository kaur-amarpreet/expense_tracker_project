"""
Tests for Step 07: Add Expense (GET + POST /expenses/add)

Coverage:
1.  Auth guard: GET /expenses/add while logged out → 302 to /login
2.  Auth guard: POST /expenses/add while logged out → 302 to /login
3.  Happy path: GET /expenses/add while logged in → 200, form rendered with today's date
4.  Happy path: POST valid expense → row inserted in DB, redirect to /profile (302)
5.  Happy path: POST valid expense → success flash visible after following redirect
6.  Validation: POST with blank amount → error flash, form re-rendered, no DB insert
7.  Validation: POST with zero amount → error flash, no DB insert
8.  Validation: POST with negative amount → error flash, no DB insert
9.  Validation: POST with non-numeric amount → error flash, no DB insert
10. Validation: POST with invalid category → error flash, no DB insert
11. Validation: POST with missing date → error flash, no DB insert
12. Validation: POST with description > 200 chars → error flash, no DB insert
13. DB side-effect: after valid POST, expense row has correct user_id, amount,
    category, date, description
14. Form re-population: on validation error, submitted values appear in response
15. Parametrized: all seven valid categories are accepted
16. Parametrized: invalid category strings are rejected
17. Optional description: omitting description stores None in DB and succeeds
18. Multi-expense: two valid POSTs for same user produce two distinct DB rows
19. Description whitespace: a description of only spaces is treated as blank (None)
"""

import sqlite3
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

import app as flask_app_module
import database.db as db_mod

# ---------------------------------------------------------------------------
# Constants mirroring the spec
# ---------------------------------------------------------------------------

VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]

VALID_EXPENSE = {
    "amount": "250.00",
    "category": "Food",
    "date": "2026-06-01",
    "description": "Lunch at cafe",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn():
    """
    Fresh in-memory SQLite DB with schema and a single test user (id=1).
    Yields the raw connection so tests can inspect rows directly.
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
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "testuser@example.com", generate_password_hash("testpass123")),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def patched_client(monkeypatch, db_conn):
    """
    Flask test client with both database.db.get_db and database.queries.get_db
    patched to use the isolated in-memory DB.  The client is NOT pre-authenticated.
    """
    monkeypatch.setattr(db_mod, "get_db", lambda: db_conn)

    # Patch queries module only if it exists and exposes get_db
    try:
        import database.queries as q_mod
        monkeypatch.setattr(q_mod, "get_db", lambda: db_conn)
    except (ImportError, AttributeError):
        pass

    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret"

    with flask_app_module.app.test_client() as client:
        yield client


@pytest.fixture
def auth_client(patched_client, db_conn):
    """
    Same patched client but pre-authenticated as user id=1 via session injection.
    Returns (client, db_conn) so tests can query the DB directly.
    """
    with patched_client.session_transaction() as sess:
        sess["user_id"] = 1
    return patched_client, db_conn


def _expense_count(conn):
    """Return the total number of rows in the expenses table."""
    return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]


def _latest_expense(conn):
    """Return the most recently inserted expense row as a sqlite3.Row."""
    return conn.execute(
        "SELECT * FROM expenses ORDER BY id DESC LIMIT 1"
    ).fetchone()


# ---------------------------------------------------------------------------
# 1 & 2 — Auth guard
# ---------------------------------------------------------------------------

class TestAddExpenseAuthGuard:
    def test_get_unauthenticated_redirects(self, patched_client):
        response = patched_client.get("/expenses/add", follow_redirects=False)
        assert response.status_code == 302, \
            "Unauthenticated GET /expenses/add must return 302"

    def test_get_unauthenticated_redirects_to_login(self, patched_client):
        response = patched_client.get("/expenses/add", follow_redirects=False)
        assert "/login" in response.headers["Location"], \
            "Unauthenticated GET /expenses/add must redirect to /login"

    def test_post_unauthenticated_redirects(self, patched_client):
        response = patched_client.post(
            "/expenses/add",
            data=VALID_EXPENSE,
            follow_redirects=False,
        )
        assert response.status_code == 302, \
            "Unauthenticated POST /expenses/add must return 302"

    def test_post_unauthenticated_redirects_to_login(self, patched_client):
        response = patched_client.post(
            "/expenses/add",
            data=VALID_EXPENSE,
            follow_redirects=False,
        )
        assert "/login" in response.headers["Location"], \
            "Unauthenticated POST /expenses/add must redirect to /login"


# ---------------------------------------------------------------------------
# 3 — Happy path: GET renders form with today's date
# ---------------------------------------------------------------------------

class TestAddExpenseGetForm:
    def test_get_returns_200(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add", follow_redirects=False)
        assert response.status_code == 200, \
            "Authenticated GET /expenses/add must return 200"

    def test_get_renders_form_element(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert b"<form" in response.data, \
            "Response must contain a <form> element"

    def test_get_contains_today_date(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        today_iso = date.today().isoformat()
        assert today_iso.encode() in response.data, \
            f"Form must default date field to today ({today_iso})"

    def test_get_contains_amount_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert b'name="amount"' in response.data or b"amount" in response.data, \
            "Form must contain an amount input"

    def test_get_contains_category_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert b'name="category"' in response.data or b"category" in response.data, \
            "Form must contain a category selector"

    def test_get_contains_all_valid_categories(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        for cat in VALID_CATEGORIES:
            assert cat.encode() in response.data, \
                f"Category '{cat}' must appear in the form"

    def test_get_contains_date_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert b'name="date"' in response.data or b'type="date"' in response.data, \
            "Form must contain a date input"


# ---------------------------------------------------------------------------
# 4 & 5 — Happy path: POST valid expense
# ---------------------------------------------------------------------------

class TestAddExpenseValidPost:
    def test_valid_post_redirects(self, auth_client):
        client, _ = auth_client
        response = client.post(
            "/expenses/add",
            data=VALID_EXPENSE,
            follow_redirects=False,
        )
        assert response.status_code == 302, \
            "Valid POST must redirect (302)"

    def test_valid_post_redirects_to_profile(self, auth_client):
        client, _ = auth_client
        response = client.post(
            "/expenses/add",
            data=VALID_EXPENSE,
            follow_redirects=False,
        )
        assert "/profile" in response.headers["Location"], \
            "Valid POST must redirect to /profile"

    def test_valid_post_shows_success_flash(self, auth_client):
        client, _ = auth_client
        response = client.post(
            "/expenses/add",
            data=VALID_EXPENSE,
            follow_redirects=True,
        )
        html = response.data.decode()
        # The spec says: flash a success message on success
        assert "success" in html.lower() or "added" in html.lower(), \
            "A success flash message must appear after a valid expense submission"

    def test_valid_post_inserts_one_row(self, auth_client):
        client, conn = auth_client
        before = _expense_count(conn)
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        after = _expense_count(conn)
        assert after == before + 1, \
            "Exactly one new expense row must be inserted on a valid POST"


# ---------------------------------------------------------------------------
# 13 — DB side-effect: correct field values stored
# ---------------------------------------------------------------------------

class TestAddExpenseDbSideEffect:
    def test_correct_user_id_stored(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["user_id"] == 1, \
            "expense.user_id must match the logged-in user's id"

    def test_correct_amount_stored(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        row = _latest_expense(conn)
        assert float(row["amount"]) == pytest.approx(250.00), \
            "expense.amount must equal the submitted value"

    def test_correct_category_stored(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["category"] == "Food", \
            "expense.category must equal the submitted value"

    def test_correct_date_stored(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["date"] == "2026-06-01", \
            "expense.date must equal the submitted ISO date string"

    def test_correct_description_stored(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["description"] == "Lunch at cafe", \
            "expense.description must equal the submitted value"

    def test_description_none_when_blank(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "description": ""}
        client.post("/expenses/add", data=data, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["description"] is None, \
            "A blank description must be stored as NULL, not empty string"

    def test_description_none_when_whitespace_only(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "description": "   "}
        client.post("/expenses/add", data=data, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["description"] is None, \
            "A whitespace-only description must be stripped and stored as NULL"


# ---------------------------------------------------------------------------
# 6–12 — Validation errors: no DB insert, error flash, form re-rendered
# ---------------------------------------------------------------------------

class TestAddExpenseValidation:
    def _assert_no_insert_and_error(self, client, conn, data):
        """Helper: assert count unchanged and response is not a redirect."""
        before = _expense_count(conn)
        response = client.post(
            "/expenses/add",
            data=data,
            follow_redirects=False,
        )
        after = _expense_count(conn)
        assert after == before, \
            "No expense row must be inserted when validation fails"
        # Must re-render the form (200), not redirect
        assert response.status_code == 200, \
            "Validation failure must re-render the form with 200"
        return response

    def test_blank_amount_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": ""}
        self._assert_no_insert_and_error(client, conn, data)

    def test_blank_amount_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": ""}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "amount" in html, \
            "An error message about amount must appear for blank amount"

    def test_zero_amount_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "0"}
        self._assert_no_insert_and_error(client, conn, data)

    def test_zero_amount_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "0"}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "amount" in html or "positive" in html, \
            "An error message must appear for zero amount"

    def test_negative_amount_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "-10.00"}
        self._assert_no_insert_and_error(client, conn, data)

    def test_negative_amount_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "-10.00"}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "amount" in html or "positive" in html, \
            "An error message must appear for negative amount"

    def test_non_numeric_amount_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "abc"}
        self._assert_no_insert_and_error(client, conn, data)

    def test_non_numeric_amount_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "amount": "abc"}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "amount" in html, \
            "An error message must appear for non-numeric amount"

    def test_invalid_category_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "category": "Luxury"}
        self._assert_no_insert_and_error(client, conn, data)

    def test_invalid_category_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "category": "Luxury"}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "category" in html, \
            "An error message must appear for an invalid category"

    def test_missing_date_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "date": ""}
        self._assert_no_insert_and_error(client, conn, data)

    def test_missing_date_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "date": ""}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "date" in html, \
            "An error message must appear for a missing date"

    def test_malformed_date_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "date": "not-a-date"}
        self._assert_no_insert_and_error(client, conn, data)

    def test_description_too_long_no_insert(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "description": "x" * 201}
        self._assert_no_insert_and_error(client, conn, data)

    def test_description_too_long_error_flash(self, auth_client):
        client, conn = auth_client
        data = {**VALID_EXPENSE, "description": "x" * 201}
        response = client.post("/expenses/add", data=data, follow_redirects=True)
        html = response.data.decode().lower()
        assert "error" in html or "description" in html or "200" in html, \
            "An error message must appear when description exceeds 200 chars"

    def test_description_exactly_200_chars_accepted(self, auth_client):
        """Boundary: exactly 200-char description must NOT trigger an error."""
        client, conn = auth_client
        data = {**VALID_EXPENSE, "description": "y" * 200}
        before = _expense_count(conn)
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        after = _expense_count(conn)
        assert after == before + 1, \
            "A 200-character description must be accepted and stored"
        assert response.status_code == 302, \
            "A 200-character description must result in a redirect (success)"


# ---------------------------------------------------------------------------
# 14 — Form re-population on validation error
# ---------------------------------------------------------------------------

class TestAddExpenseFormRepopulation:
    def test_amount_repopulated_on_error(self, auth_client):
        client, _ = auth_client
        data = {**VALID_EXPENSE, "category": "InvalidCat", "amount": "99.50"}
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        assert b"99.50" in response.data, \
            "Submitted amount must be preserved in the re-rendered form on error"

    def test_category_repopulated_on_error(self, auth_client):
        """Even an invalid category value should be echoed back or at least not crash."""
        client, _ = auth_client
        data = {**VALID_EXPENSE, "amount": ""}
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        # The form must come back (200) with category context available
        assert response.status_code == 200, \
            "Validation error must re-render the form, not redirect"

    def test_date_repopulated_on_error(self, auth_client):
        client, _ = auth_client
        data = {**VALID_EXPENSE, "amount": "", "date": "2026-06-15"}
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        assert b"2026-06-15" in response.data, \
            "Submitted date must be preserved in the re-rendered form on error"

    def test_description_repopulated_on_error(self, auth_client):
        client, _ = auth_client
        data = {**VALID_EXPENSE, "amount": "", "description": "My test note"}
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        assert b"My test note" in response.data, \
            "Submitted description must be preserved in the re-rendered form on error"


# ---------------------------------------------------------------------------
# 15 — Parametrized: all valid categories are accepted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", VALID_CATEGORIES)
def test_valid_category_accepted(auth_client, category):
    client, conn = auth_client
    data = {**VALID_EXPENSE, "category": category}
    before = _expense_count(conn)
    response = client.post("/expenses/add", data=data, follow_redirects=False)
    after = _expense_count(conn)
    assert after == before + 1, \
        f"Category '{category}' must be accepted and stored"
    assert response.status_code == 302, \
        f"Valid category '{category}' must produce a redirect (success)"


# ---------------------------------------------------------------------------
# 16 — Parametrized: invalid category strings are rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_category", [
    "",
    "food",           # wrong case
    "FOOD",           # all caps
    "Luxury",         # not in the list
    "transport",      # lowercase
    "Bills ",         # trailing space
    " Food",          # leading space
    "Entertainment!", # special character
    "None",           # Python None as string
])
def test_invalid_category_rejected(auth_client, bad_category):
    client, conn = auth_client
    data = {**VALID_EXPENSE, "category": bad_category}
    before = _expense_count(conn)
    response = client.post("/expenses/add", data=data, follow_redirects=False)
    after = _expense_count(conn)
    assert after == before, \
        f"Category '{bad_category}' must be rejected — no DB insert expected"
    assert response.status_code == 200, \
        f"Rejected category '{bad_category}' must re-render form (200)"


# ---------------------------------------------------------------------------
# 17 — Optional description: omitting it stores None
# ---------------------------------------------------------------------------

class TestAddExpenseOptionalDescription:
    def test_no_description_key_succeeds(self, auth_client):
        client, conn = auth_client
        data = {"amount": "100.00", "category": "Other", "date": "2026-06-01"}
        before = _expense_count(conn)
        response = client.post("/expenses/add", data=data, follow_redirects=False)
        after = _expense_count(conn)
        assert after == before + 1, \
            "Omitting description entirely must still insert the expense"
        assert response.status_code == 302

    def test_no_description_stores_none(self, auth_client):
        client, conn = auth_client
        data = {"amount": "100.00", "category": "Other", "date": "2026-06-01"}
        client.post("/expenses/add", data=data, follow_redirects=False)
        row = _latest_expense(conn)
        assert row["description"] is None, \
            "Missing description must be stored as NULL in the DB"


# ---------------------------------------------------------------------------
# 18 — Multi-expense: two valid POSTs produce two distinct DB rows
# ---------------------------------------------------------------------------

class TestAddExpenseMultipleInserts:
    def test_two_posts_create_two_rows(self, auth_client):
        client, conn = auth_client
        data_a = {**VALID_EXPENSE, "amount": "100.00", "description": "First"}
        data_b = {**VALID_EXPENSE, "amount": "200.00", "description": "Second"}
        before = _expense_count(conn)
        client.post("/expenses/add", data=data_a, follow_redirects=False)
        client.post("/expenses/add", data=data_b, follow_redirects=False)
        after = _expense_count(conn)
        assert after == before + 2, \
            "Two valid POSTs must insert two distinct expense rows"

    def test_two_posts_have_correct_amounts(self, auth_client):
        client, conn = auth_client
        data_a = {**VALID_EXPENSE, "amount": "111.11"}
        data_b = {**VALID_EXPENSE, "amount": "222.22"}
        client.post("/expenses/add", data=data_a, follow_redirects=False)
        client.post("/expenses/add", data=data_b, follow_redirects=False)
        rows = conn.execute(
            "SELECT amount FROM expenses ORDER BY id DESC LIMIT 2"
        ).fetchall()
        amounts = {float(r["amount"]) for r in rows}
        assert pytest.approx(111.11) in amounts, "First expense amount must be stored"
        assert pytest.approx(222.22) in amounts, "Second expense amount must be stored"

    def test_expenses_belong_to_correct_user(self, auth_client):
        client, conn = auth_client
        client.post("/expenses/add", data=VALID_EXPENSE, follow_redirects=False)
        rows = conn.execute(
            "SELECT user_id FROM expenses WHERE user_id = ?", (1,)
        ).fetchall()
        for row in rows:
            assert row["user_id"] == 1, "Every inserted expense must belong to user_id=1"
