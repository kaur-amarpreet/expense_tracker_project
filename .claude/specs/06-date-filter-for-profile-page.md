# Spec: Date Filter For Profile Page

## Overview
Step 6 adds a date-range filter to the profile page so users can scope all
displayed data — summary stats, category breakdown, and recent transactions —
to a chosen period. Four preset buttons (This Month, Last Month, Last 3 Months,
All Time) cover the common cases; a custom date-range picker handles everything
else. The filter is applied server-side via query parameters on `GET /profile`,
keeping all logic in Python and the existing query helpers. No JavaScript state
management is needed — selecting a preset or submitting the custom form triggers
a full page reload.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column exists)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Backend route profile page (live query helpers in `database/queries.py` exist)

## Routes
No new routes. `GET /profile` is modified to accept optional query parameters:
- `period` — one of `this_month`, `last_month`, `last_3_months`, `all_time`
- `from` — ISO date string `YYYY-MM-DD` (custom range start, inclusive)
- `to` — ISO date string `YYYY-MM-DD` (custom range end, inclusive)

When `period` is present it takes precedence over `from`/`to`. When neither
is present the behaviour is identical to the current `all_time` default.

## Database changes
No database changes. The `expenses.date` column (`TEXT`, `YYYY-MM-DD` format)
already stores the data needed for range filtering.

## Templates
- **Modify**: `templates/profile.html`
  - Add a date filter bar between the identity card and the summary stats.
  - The bar contains four preset buttons (This Month, Last Month, Last 3 Months,
    All Time) and a collapsed custom range form with two `<input type="date">`
    fields and a single Apply button.
  - The active preset button is visually highlighted using a CSS class
    `filter-btn--active`.
  - Each preset button is a plain `<a>` tag linking to
    `url_for('profile', period=<slug>)` — no JavaScript needed.
  - The custom range form submits `GET /profile` with `from` and `to` params.
  - A small label below the filter bar shows the resolved human-readable range
    (e.g. "Showing: 1 May 2026 – 31 May 2026") passed as `filter_label` from
    the route.

## Files to change
- `app.py` — modify `profile()` to read `period`, `from`, `to` query params;
  resolve them to `date_from` / `date_to` strings; pass to all three query
  helpers; compute `active_period` and `filter_label` for the template
- `database/queries.py` — add optional `date_from=None, date_to=None` keyword
  args to `get_summary_stats`, `get_recent_transactions`, and
  `get_category_breakdown`; extend SQL `WHERE` clauses to filter by date range
  when those args are not `None`
- `templates/profile.html` — add filter bar (described above)
- `static/css/profile.css` — add styles for `.filter-bar`, `.filter-btn`,
  `.filter-btn--active`, `.filter-label`, `.custom-range-form`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string formatting in SQL;
  use `AND date >= ?` with bound parameters, not `f"AND date >= '{date_from}'"`
- Passwords hashed with werkzeug (unchanged)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `period` resolution must happen in `app.py`, not in query helpers — helpers
  only receive plain `date_from` / `date_to` strings or `None`
- `date_from` and `date_to` passed to helpers must always be `YYYY-MM-DD`
  strings or `None`
- Validate the `from` / `to` query params: if either is not a valid
  `YYYY-MM-DD` date, ignore both and fall back to `all_time` silently
- If `date_from` is after `date_to` after parsing, ignore both and fall back
  to `all_time` silently
- "This Month" = first day of the current calendar month to today's date
- "Last Month" = first day to last day of the previous calendar month
- "Last 3 Months" = same day 3 months ago to today (e.g. 2026-03-01 to
  2026-05-31 when today is 2026-05-31)
- "All Time" = no date restriction (`date_from=None, date_to=None`)
- The `filter_label` string must use the format `"DD Mon YYYY – DD Mon YYYY"`
  (e.g. `"01 May 2026 – 31 May 2026"`); for All Time use `"All time"`
- `active_period` passed to the template is one of the four preset slugs, or
  `"custom"` when a custom range is active, or `"all_time"` when no filter
  is applied

## Definition of done
- [ ] Visiting `/profile` with no query params shows all expenses (same as before)
- [ ] Clicking "This Month" reloads the page and all three data sections reflect only expenses in the current calendar month
- [ ] Clicking "Last Month" reloads the page and all three data sections reflect only last month's expenses
- [ ] Clicking "Last 3 Months" reloads the page and shows expenses from the past 3 months
- [ ] Clicking "All Time" reloads the page and shows all expenses (resets the filter)
- [ ] The active preset button is visually distinct from inactive buttons
- [ ] Submitting the custom range form with a valid `from` and `to` date reloads the page with filtered data
- [ ] Submitting an invalid date range (bad format or `from` after `to`) falls back to All Time without an error page
- [ ] The `filter_label` string below the filter bar correctly describes the active range
- [ ] A user with no expenses in the selected date range sees zeros in stats and empty lists — no errors
- [ ] All amounts still display the ₹ symbol
