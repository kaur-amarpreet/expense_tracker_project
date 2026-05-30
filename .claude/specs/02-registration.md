# Spec: Registration

## Overview
This step implements the user registration flow — the `POST /register` route that processes the sign-up form, validates input, hashes the password, and inserts a new user record. The `GET /register` route already renders the form; this step wires it up so users can actually create accounts. Registration is the entry point for all authenticated features downstream (login, expense tracking, profile).

## Depends on
- Step 1 — Database Setup: `users` table, `get_db()`, and `init_db()` must exist in `database/db.py`

## Routes
- `POST /register` — validate form input, hash password, insert user, redirect to login — public

## Database changes
No database changes. The `users` table already exists with the required columns: `id`, `name`, `email` (unique), `password_hash`, `created_at`.

## Templates
- **Modify:** `templates/register.html`
  - Add `method="POST"` and `action="{{ url_for('register') }}"` to the `<form>` tag if not present
  - Render flashed error messages above the form
  - Render a success message or rely on redirect to login
  - Pre-fill `name` and `email` fields with submitted values on validation failure (avoid clearing the form)

## Files to change
- `app.py` — add `POST` method to the existing `register` route; implement validation, password hashing, DB insert, and redirect logic
- `templates/register.html` — wire form attributes and flash message display
- `database/db.py` — add `create_user(name, email, password_hash)` helper

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security` (`generate_password_hash`) ships with Flask.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders — no f-strings in SQL)
- Passwords hashed with `werkzeug.security.generate_password_hash` — never store plaintext
- Use CSS variables — never hardcode hex values in any new styles
- All templates extend `base.html`
- DB logic (`create_user`) belongs in `database/db.py`, not inline in the route
- On duplicate email, flash a user-friendly error and re-render the form — do not expose DB error messages
- Validate server-side: name non-empty, valid email format, password minimum 8 characters
- On success, `flash` a success message and `redirect` to `url_for('login')` — do not auto-login in this step
- Use `abort(400)` for truly malformed requests; use `flash` + re-render for validation errors

## Definition of done
- [ ] Submitting the form with valid name, email, and password creates a new row in the `users` table with a hashed (not plaintext) password
- [ ] After successful registration, the user is redirected to `/login` and a success flash message is visible
- [ ] Submitting with a duplicate email re-renders the form with an error message and does not create a duplicate row
- [ ] Submitting with an empty name, invalid email, or password shorter than 8 characters re-renders the form with a specific error message
- [ ] The name and email fields are pre-filled with the submitted values after a validation error
- [ ] The password field is always cleared after any submission (success or error)
- [ ] Visiting `/register` directly (GET) still renders the empty form with no errors
