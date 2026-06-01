# Spec: Add Expense

## Overview
Step 7 replaces the stub `GET /expenses/add` route with a fully functional
add-expense form. Users who are logged in can submit a new expense by providing
an amount, category, date, and optional description. On success the expense is
saved to the `expenses` table and the user is redirected to their profile page.
This is the first route that writes user-generated data to the database.

## Depends on
- Step 01 — Database setup (`expenses` table must exist)
- Step 03 — Login/logout (session must be available)
- Step 05 — Profile page backend (redirect target after submission)

## Routes
- `GET  /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. The `expenses` table already exists:

```
expenses(id, user_id, amount, category, date, description, created_at)
```

A new DB helper `add_expense(user_id, amount, category, date, description)` must
be added to `database/db.py`.

## Templates
- **Create:** `templates/add_expense.html` — the add-expense form page
- **Modify:** none

## Files to change
- `app.py` — replace the stub `add_expense` route with GET+POST implementation
- `database/db.py` — add `add_expense()` helper

## Files to create
- `templates/add_expense.html` — form template extending `base.html`
- `static/css/add_expense.css` — page-specific styles (import in template only)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders — never f-strings in SQL)
- Passwords hashed with werkzeug (not applicable here, but keep existing hashing untouched)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Redirect unauthenticated users to `/login` (check `session.get("user_id")`)
- `amount` must be a positive number; reject zero or negative values
- `category` must be one of the fixed set: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- `date` must be a valid ISO date (YYYY-MM-DD); default the field to today's date
- `description` is optional (max 200 chars); strip whitespace, store `None` if blank
- On validation failure re-render the form with the user's input and a flash error
- On success flash a success message and redirect to `url_for("profile")`
- The `add_expense` DB helper lives in `database/db.py`, not inline in the route
- Import `add_expense` in `app.py` from `database.db`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders the form
- [ ] Submitting the form with valid data creates a new row in the `expenses` table
- [ ] After a successful submission the user lands on `/profile` with a success flash
- [ ] Submitting with a blank or zero amount shows a flash error and keeps other field values
- [ ] Submitting with an invalid category shows a flash error
- [ ] Submitting with a missing date shows a flash error
- [ ] The newly added expense appears in the recent expenses list on the profile page
- [ ] The form date field defaults to today's date on page load
