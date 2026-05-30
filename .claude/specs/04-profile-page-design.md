# Spec: Profile Page Design

## Overview
This step replaces the `/profile` stub with a real, fully styled page that shows
a logged-in user's account details and a lightweight spending summary drawn from
existing expense data. It is the first authenticated-only page in Spendly and
establishes the pattern — session check → DB fetch → render template — that all
subsequent logged-in pages will follow.

## Depends on
- Step 01 — Database Setup (users and expenses tables exist, `get_db()` ready)
- Step 02 — Registration (users can be created)
- Step 03 — Login and Logout (session contains `user_id` after login)

## Routes
- `GET /profile` — renders the profile page — **logged-in only**
  (redirect to `/login` if `session["user_id"]` is absent)

## Database changes
No new tables or columns.

Two new helper functions in `database/db.py`:
- `get_user_by_id(user_id)` — `SELECT * FROM users WHERE id = ?`
- `get_expense_summary(user_id)` — returns a single row with:
  - `total_count` — number of expenses for this user
  - `total_amount` — sum of all expense amounts (₹)
  - `latest_date` — most recent expense date (nullable if no expenses)

## Templates
- **Create:** `templates/profile.html` — extends `base.html`
  - Page title block: `Profile — Spendly`
  - Profile card containing:
    - User's name (large, serif heading)
    - Email address
    - Member since date (formatted as `DD Mon YYYY`, e.g. `02 Jan 2025`)
    - Divider
    - Spending summary section with three stat tiles:
      - Total expenses logged (count)
      - Total amount spent (formatted as ₹X,XXX.XX)
      - Most recent expense date (or "No expenses yet" if null)
- **Modify:** `templates/base.html`
  - Inside the `{% if session.get('user_id') %}` nav block, add a "Profile" link
    before the "Log out" link:
    `<a href="{{ url_for('profile') }}">Profile</a>`

## Files to change
- `app.py` — replace the `/profile` stub with a real route function
- `database/db.py` — add `get_user_by_id()` and `get_expense_summary()`
- `templates/base.html` — add Profile nav link for authenticated users
- `static/css/style.css` — add profile page styles (card, stat tiles)

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never f-strings in SQL
- Use `get_db()` from `database/db.py` for every connection; never open sqlite3 directly in routes
- Passwords are never displayed or exposed on the profile page
- All templates extend `base.html`
- Use CSS variables — never hardcode hex values in any stylesheet
- Date formatting (`02 Jan 2025`) must be done in the route (Python `strftime`), not in the template
- If the user is not logged in (`session.get("user_id")` is falsy), redirect to `/login` with `redirect(url_for("login"))` — do not use `abort()`
- Import `get_user_by_id` and `get_expense_summary` in `app.py` alongside existing imports
- Currency formatting: use `₹` prefix with two decimal places and comma thousands separator (e.g. `₹1,200.00`)
- Amount formatting must be done in the route (Python `f"{amount:,.2f}"`), passed to the template as a pre-formatted string

## Definition of done
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Visiting `/profile` while logged in renders `profile.html` (no raw string returned)
- [ ] The profile page displays the logged-in user's name and email correctly
- [ ] The "Member since" date is displayed in `DD Mon YYYY` format
- [ ] Total expense count and total amount (₹) are shown and match the seeded data (8 expenses, ₹9,450.00 for demo user)
- [ ] The "Profile" nav link appears in the navbar when logged in and is absent when logged out
- [ ] The "Profile" nav link navigates correctly to `/profile`
- [ ] All amounts display with the ₹ prefix and two decimal places
- [ ] No hardcoded URLs in `profile.html` — all links use `url_for()`
- [ ] No hardcoded hex colours in new CSS — all values use CSS variables
