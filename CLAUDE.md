# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (activate venv first)
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Run the app
python app.py                # serves on http://localhost:5001

# Run tests
pytest
pytest tests/test_foo.py::test_bar   # single test
```

## Architecture

**Spendly** is a Flask + SQLite personal expense tracker, structured as a guided student project. Features are implemented incrementally across numbered steps.

### Key files

- `app.py` — single Flask application file; all routes live here. Many routes are stubs labeled "coming in Step N" that students fill in.
- `database/db.py` — SQLite helper module (to be implemented in Step 1). Must provide:
  - `get_db()` — returns a `sqlite3.Connection` with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`
  - `init_db()` — creates tables with `CREATE TABLE IF NOT EXISTS`
  - `seed_db()` — inserts sample development data
- `templates/base.html` — Jinja2 base layout (navbar, footer, Google Fonts). All other templates `{% extends "base.html" %}`.
- `static/css/style.css` — all styling (DM Serif Display + DM Sans fonts).
- `static/js/main.js` — client-side JS stub; built out as features are added.

### Planned route progression

| Step | Route | Notes |
|------|-------|-------|
| 1 | — | `database/db.py` — SQLite setup |
| 3 | `/logout` | Session teardown |
| 4 | `/profile` | User profile page |
| 7 | `/expenses/add` | Create expense form |
| 8 | `/expenses/<id>/edit` | Edit expense |
| 9 | `/expenses/<id>/delete` | Delete expense |

### Database

SQLite file is `expense_tracker.db` (gitignored). Call `init_db()` once on first run or in an `app.before_request` / CLI command. Foreign keys must be enabled per connection via `PRAGMA foreign_keys = ON`.

### Auth pattern

Forms POST to `/login` and `/register`. Session management (Flask `session`) is added in Step 3. Passwords should be hashed with `werkzeug.security` (`generate_password_hash` / `check_password_hash`), which is already a dependency.
