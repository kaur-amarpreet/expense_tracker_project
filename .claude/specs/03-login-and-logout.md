# Spec: Login and Logout

## Overview
This step wires up the login form so users can authenticate, starts a session on success, and implements the logout route to clear it. The `GET /login` route already renders the form and `GET /logout` is a stub — this step adds `POST /login` (credential validation + session creation) and converts the logout stub into a real session-clearing redirect. After this step, Spendly has a complete auth lifecycle: register → login → logout.

## Depends on
- Step 1 — Database Setup: `get_db()`, `users` table
- Step 2 — Registration: `users` rows exist with hashed passwords

## Routes
- `POST /login` — validate email/password against DB, set `session['user_id']`, redirect to `/expenses/add` placeholder — public
- `GET /logout` — clear `session`, flash confirmation, redirect to `GET /` — public

## Database changes
No database changes. The `users` table already has all required columns. One new read helper is needed in `database/db.py` (see Files to change).

## Templates
- **Modify:** `templates/login.html`
  - Add `method="POST"` and `action="{{ url_for('login') }}"` to the `<form>` tag if not already present
  - Render flashed error messages above the form
  - Pre-fill the email field with the submitted value on failure (never pre-fill the password field)
- **Modify:** `templates/base.html`
  - In the nav, show a **Log out** link (`url_for('logout')`) when `session.get('user_id')` is set
  - Show **Login** and **Register** links when no session exists

## Files to change
- `app.py` — add `POST` to the existing `login` route; implement credential check and session write; convert `logout` stub to a real route; import `check_password_hash` and `session` from their respective modules
- `database/db.py` — add `get_user_by_email(email)` helper that returns a `sqlite3.Row` or `None`
- `templates/login.html` — wire form attributes and flash message display; pre-fill email on error
- `templates/base.html` — conditional nav links based on session state

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` and `flask.session` ship with the existing install.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders — no f-strings in SQL)
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values in any new styles
- All templates extend `base.html`
- DB logic (`get_user_by_email`) belongs in `database/db.py`, not inline in the route
- On invalid credentials, flash a **single generic message** ("Invalid email or password.") — do not reveal which field was wrong
- On successful login, store only `session['user_id'] = user['id']` — do not store name, email, or password hash in the session
- `logout` must call `session.clear()`, then flash a brief confirmation, then redirect to `url_for('landing')`
- Do not auto-redirect logged-in users away from `/login` in this step — that guard belongs in a later step

## Definition of done
- [ ] Submitting the login form with the correct email and password sets `session['user_id']` and redirects the user
- [ ] Submitting with an incorrect password re-renders the form with the generic error "Invalid email or password." and does not set a session
- [ ] Submitting with an email that does not exist re-renders the form with the same generic error
- [ ] The email field is pre-filled with the submitted value after a failed login; the password field is always cleared
- [ ] Visiting `/logout` clears the session, flashes a confirmation message, and redirects to the landing page
- [ ] The nav in `base.html` shows **Log out** when logged in and **Login** / **Register** when not
- [ ] Visiting `/login` directly (GET) still renders the empty form with no errors
