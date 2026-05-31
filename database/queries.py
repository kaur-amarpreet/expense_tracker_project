from database.db import get_db
from datetime import datetime


def _date_filter(date_from, date_to):
    clause, params = "", []
    if date_from is not None:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to is not None:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, params


# ---- SUBAGENT-2: USER / SUMMARY STATS ---- #

def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": datetime.strptime(
                row["created_at"], "%Y-%m-%d %H:%M:%S"
            ).strftime("%B %Y"),
        }
    finally:
        conn.close()


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)

        row = conn.execute(
            "SELECT"
            "    COUNT(*)                   AS transaction_count,"
            "    COALESCE(SUM(amount), 0.0) AS total_spent,"
            "    MAX(date)                  AS latest_date"
            " FROM expenses WHERE user_id = ?"
            + date_clause,
            [user_id] + date_params
        ).fetchone()
        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?"
            + date_clause
            + " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            [user_id] + date_params
        ).fetchone()
        latest_date = (
            datetime.strptime(row["latest_date"], "%Y-%m-%d").strftime("%d %b %Y")
            if row["latest_date"] else "No expenses yet"
        )
        return {
            "total_spent": float(row["total_spent"]),
            "transaction_count": int(row["transaction_count"]),
            "top_category": top_row["category"] if top_row else "—",
            "latest_date": latest_date,
        }
    finally:
        conn.close()


# ---- SUBAGENT-1: RECENT TRANSACTIONS ---- #

def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)

        rows = conn.execute(
            "SELECT amount, category, date, description"
            " FROM expenses WHERE user_id = ?"
            + date_clause
            + " ORDER BY date DESC, id DESC LIMIT ?",
            [user_id] + date_params + [limit]
        ).fetchall()
        return [
            {
                "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
                "description": row["description"] or row["category"],
                "category": row["category"],
                "amount": float(row["amount"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


# ---- SUBAGENT-3: CATEGORY BREAKDOWN ---- #

def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)

        rows = conn.execute(
            "SELECT category, SUM(amount) AS total"
            " FROM expenses WHERE user_id = ?"
            + date_clause
            + " GROUP BY category ORDER BY total DESC",
            [user_id] + date_params
        ).fetchall()
        if not rows:
            return []

        grand_total = sum(row["total"] for row in rows)
        exact = [row["total"] / grand_total * 100 for row in rows]
        floored = [int(p) for p in exact]
        remainders = [exact[i] - floored[i] for i in range(len(rows))]
        deficit = 100 - sum(floored)
        indices_by_remainder = sorted(range(len(rows)), key=lambda i: remainders[i], reverse=True)
        for i in range(deficit):
            floored[indices_by_remainder[i]] += 1

        return [
            {
                "name": rows[i]["category"],
                "amount": float(rows[i]["total"]),
                "pct": floored[i],
            }
            for i in range(len(rows))
        ]
    finally:
        conn.close()
