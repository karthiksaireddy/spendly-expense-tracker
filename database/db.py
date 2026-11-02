"""Database module for Spendly.

Owns the database schema, connection lifecycle, and every helper that touches
the database. Routes in app.py should never call the database directly — go
through the helpers here so database logic stays in one place.

Supports both SQLite (for local development and tests) and Supabase (for production).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable, Optional

# Determine database mode from environment
DATABASE_MODE = os.environ.get("DATABASE_MODE", "sqlite").lower()

# Database file lives next to this module so the path is stable regardless
# of the working directory the app is launched from.
# Can be overridden via SPENDLY_TEST_DB environment variable for testing.
DB_PATH = os.environ.get(
    "SPENDLY_TEST_DB",
    os.path.join(os.path.dirname(__file__), "expense_tracker.db")
)

# Categories seeded for every new user (SPEC §4 "Defaults").
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Food",
    "Travel",
    "Shopping",
    "Education",
    "Bills",
    "Health",
    "Other",
)


# ------------------------------------------------------------------ #
# Connection lifecycle                                                #
# ------------------------------------------------------------------ #

def get_db() -> sqlite3.Connection:
    """Return a SQLite connection scoped to the current app context.

    The connection is created lazily and stored on ``flask.g`` so the same
    connection is reused for the duration of a request. ``Row`` factory
    makes rows indexable by column name, and foreign-key enforcement is
    turned on (off by default in SQLite).
    """
    from flask import current_app, g

    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc: Optional[BaseException] = None) -> None:
    """Close the request-scoped connection, if any."""
    from flask import g

    db: Optional[sqlite3.Connection] = g.pop("db", None)
    if db is not None:
        db.close()


# ------------------------------------------------------------------ #
# Schema                                                              #
# ------------------------------------------------------------------ #

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    display_name  TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    amount      REAL    NOT NULL CHECK (amount > 0),
    date        TEXT    NOT NULL,
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS income (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    amount      REAL    NOT NULL CHECK (amount > 0),
    date        TEXT    NOT NULL,
    note        TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS budgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    amount      REAL    NOT NULL CHECK (amount > 0),
    month       TEXT    NOT NULL,  -- Format: 'YYYY-MM'
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, category_id, month),
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_expenses_user_date
    ON expenses (user_id, date);

CREATE INDEX IF NOT EXISTS idx_income_user_date
    ON income (user_id, date);

CREATE INDEX IF NOT EXISTS idx_budgets_user_month
    ON budgets (user_id, month);
"""


def init_db(db_path: Optional[str] = None) -> None:
    """Create all tables and indexes if they don't already exist.

    ``db_path`` defaults to the module-level ``DB_PATH`` so this can be
    called either from inside an app context (which uses ``DATABASE``) or
    from the factory before the first request.
    """
    path = db_path
    if path is None:
        try:
            from flask import current_app

            path = current_app.config["DATABASE"]
        except RuntimeError:
            path = DB_PATH
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Users                                                               #
# ------------------------------------------------------------------ #

def create_user(email: str, display_name: str, password_hash: str) -> int:
    """Insert a new user and return the assigned id.

    Raises ``sqlite3.IntegrityError`` if the email is already taken.
    """
    if DATABASE_MODE == "supabase":
        from .supabase_impl import create_user as supabase_create_user
        return supabase_create_user(email, display_name, password_hash)
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO users (email, display_name, password_hash) VALUES (?, ?, ?)",
            (email, display_name, password_hash),
        )
        db.commit()
        user_id = cur.lastrowid
        seed_default_categories(user_id)
        return user_id


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_user_by_id as supabase_get_user_by_id
        return supabase_get_user_by_id(user_id)
    else:
        return get_db().execute(
            "SELECT id, email, display_name, password_hash, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_user_by_email as supabase_get_user_by_email
        return supabase_get_user_by_email(email)
    else:
        return get_db().execute(
            "SELECT id, email, display_name, password_hash, created_at "
            "FROM users WHERE email = ?",
            (email,),
        ).fetchone()


# ------------------------------------------------------------------ #
# Categories                                                          #
# ------------------------------------------------------------------ #

def get_categories(user_id: int) -> list[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_categories as supabase_get_categories
        return supabase_get_categories(user_id)
    else:
        return get_db().execute(
            "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()


def get_category(user_id: int, category_id: int) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_category as supabase_get_category
        return supabase_get_category(user_id, category_id)
    else:
        return get_db().execute(
            "SELECT id, name FROM categories WHERE id = ? AND user_id = ?",
            (category_id, user_id),
        ).fetchone()


def create_category(user_id: int, name: str) -> int:
    """Insert a new category and return the assigned id.

    Raises ``sqlite3.IntegrityError`` on duplicate (user_id, name).
    """
    if DATABASE_MODE == "supabase":
        from .supabase_impl import create_category as supabase_create_category
        return supabase_create_category(user_id, name)
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO categories (user_id, name) VALUES (?, ?)",
            (user_id, name),
        )
        db.commit()
        return cur.lastrowid


def update_category(user_id: int, category_id: int, name: str) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import update_category as supabase_update_category
        supabase_update_category(user_id, category_id, name)
    else:
        db = get_db()
        db.execute(
            "UPDATE categories SET name = ? WHERE id = ? AND user_id = ?",
            (name, category_id, user_id),
        )
        db.commit()


def delete_category(user_id: int, category_id: int) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import delete_category as supabase_delete_category
        supabase_delete_category(user_id, category_id)
    else:
        db = get_db()
        db.execute(
            "DELETE FROM categories WHERE id = ? AND user_id = ?",
            (category_id, user_id),
        )
        db.commit()


def category_in_use(category_id: int) -> bool:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import category_in_use as supabase_category_in_use
        return supabase_category_in_use(category_id)
    else:
        row = get_db().execute(
            "SELECT 1 FROM expenses WHERE category_id = ? LIMIT 1",
            (category_id,),
        ).fetchone()
        return row is not None


def seed_default_categories(user_id: int) -> None:
    """Populate the standard set of categories for a new user."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import seed_default_categories as supabase_seed_default_categories
        supabase_seed_default_categories(user_id)
    else:
        for name in DEFAULT_CATEGORIES:
            try:
                create_category(user_id, name)
            except sqlite3.IntegrityError:
                # Already exists — shouldn't happen for a new user, but stay
                # defensive in case seed is rerun.
                continue


# ------------------------------------------------------------------ #
# Expenses                                                            #
# ------------------------------------------------------------------ #

def create_expense(
    user_id: int,
    category_id: int,
    amount: float,
    date: str,
    note: Optional[str],
) -> int:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import create_expense as supabase_create_expense
        return supabase_create_expense(user_id, category_id, amount, date, note)
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO expenses (user_id, category_id, amount, date, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, category_id, amount, date, note),
        )
        db.commit()
        return cur.lastrowid


def get_expense(user_id: int, expense_id: int) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_expense as supabase_get_expense
        return supabase_get_expense(user_id, expense_id)
    else:
        return get_db().execute(
            "SELECT e.id, e.user_id, e.category_id, e.amount, e.date, e.note, "
            "       c.name AS category_name "
            "FROM expenses e "
            "JOIN categories c ON c.id = e.category_id "
            "WHERE e.id = ? AND e.user_id = ?",
            (expense_id, user_id),
        ).fetchone()


def update_expense(
    user_id: int,
    expense_id: int,
    category_id: int,
    amount: float,
    date: str,
    note: Optional[str],
) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import update_expense as supabase_update_expense
        supabase_update_expense(user_id, expense_id, category_id, amount, date, note)
    else:
        db = get_db()
        db.execute(
            "UPDATE expenses "
            "SET category_id = ?, amount = ?, date = ?, note = ? "
            "WHERE id = ? AND user_id = ?",
            (category_id, amount, date, note, expense_id, user_id),
        )
        db.commit()


def delete_expense(user_id: int, expense_id: int) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import delete_expense as supabase_delete_expense
        supabase_delete_expense(user_id, expense_id)
    else:
        db = get_db()
        db.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        db.commit()


def list_expenses(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    """Return the user's expenses, newest first, with filters applied.

    All filters are AND'd. A None or empty value means "no filter for that
    column". The caller is responsible for any input validation; this
    function trusts that ``date_from``/``date_to`` are ISO strings and
    ``category_id`` is a valid integer referencing a row owned by the user.
    """
    if DATABASE_MODE == "supabase":
        from .supabase_impl import list_expenses as supabase_list_expenses
        return supabase_list_expenses(user_id, date_from, date_to, category_id)
    else:
        sql = (
            "SELECT e.id, e.amount, e.date, e.note, "
            "       c.id AS category_id, c.name AS category_name "
            "FROM expenses e "
            "JOIN categories c ON c.id = e.category_id "
            "WHERE e.user_id = ? "
        )
        params: list[Any] = [user_id]
        if date_from:
            sql += "AND e.date >= ? "
            params.append(date_from)
        if date_to:
            sql += "AND e.date <= ? "
            params.append(date_to)
        if category_id:
            sql += "AND e.category_id = ? "
            params.append(category_id)
        sql += "ORDER BY e.date DESC, e.id DESC"
        return get_db().execute(sql, params).fetchall()


def sum_expenses(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> float:
    """Sum amounts over the same filter set as ``list_expenses``."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import sum_expenses as supabase_sum_expenses
        return supabase_sum_expenses(user_id, date_from, date_to, category_id)
    else:
        sql = "SELECT COALESCE(SUM(e.amount), 0) AS total FROM expenses e WHERE e.user_id = ? "
        params: list[Any] = [user_id]
        if date_from:
            sql += "AND e.date >= ? "
            params.append(date_from)
        if date_to:
            sql += "AND e.date <= ? "
            params.append(date_to)
        if category_id:
            sql += "AND e.category_id = ? "
            params.append(category_id)
        row = get_db().execute(sql, params).fetchone()
        return float(row["total"])


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (first_day, first_day_of_next_month) for a calendar month.

    The interval is half-open: ``[first, next_first)`` so callers can use
    ``date >= first AND date < next_first`` and never worry about the
    varying length of February or leap years.
    """
    if month == 12:
        return (f"{year:04d}-12-01", f"{year + 1:04d}-01-01")
    return (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month + 1:02d}-01")


# Export _month_bounds for use in supabase_impl
__all__ = ["_month_bounds"]


def sum_for_month(user_id: int, year: int, month: int) -> float:
    """Total spending in a single calendar month (1-indexed month)."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import sum_for_month as supabase_sum_for_month
        return supabase_sum_for_month(user_id, year, month)
    else:
        first, next_first = _month_bounds(year, month)
        db = get_db()
        row = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
            "WHERE user_id = ? AND date >= ? AND date < ?",
            (user_id, first, next_first),
        ).fetchone()
        return float(row["total"])


def by_category_for_month(
    user_id: int, year: int, month: int
) -> list[sqlite3.Row]:
    """Per-category totals for a month, ordered by amount descending.

    Categories with zero spending in the month are omitted (``HAVING
    total > 0``).
    """
    if DATABASE_MODE == "supabase":
        from .supabase_impl import by_category_for_month as supabase_by_category_for_month
        return supabase_by_category_for_month(user_id, year, month)
    else:
        first, next_first = _month_bounds(year, month)
        return get_db().execute(
            "SELECT c.id AS category_id, c.name AS category_name, "
            "       COALESCE(SUM(e.amount), 0) AS total "
            "FROM categories c "
            "LEFT JOIN expenses e "
            "  ON e.category_id = c.id "
            " AND e.date >= ? AND e.date < ? "
            "WHERE c.user_id = ? "
            "GROUP BY c.id, c.name "
            "HAVING total > 0 "
            "ORDER BY total DESC",
            (first, next_first, user_id),
        ).fetchall()


def recent_expenses(user_id: int, limit: int = 5) -> list[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import recent_expenses as supabase_recent_expenses
        return supabase_recent_expenses(user_id, limit)
    else:
        return get_db().execute(
            "SELECT e.id, e.amount, e.date, e.note, "
            "       c.name AS category_name "
            "FROM expenses e "
            "JOIN categories c ON c.id = e.category_id "
            "WHERE e.user_id = ? "
            "ORDER BY e.date DESC, e.id DESC "
            "LIMIT ?",
            (user_id, limit),
        ).fetchall()


# ------------------------------------------------------------------ #
# Income                                                              #
# ------------------------------------------------------------------ #

def create_income(
    user_id: int,
    category_id: int,
    amount: float,
    date: str,
    note: Optional[str],
) -> int:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import create_income as supabase_create_income
        return supabase_create_income(user_id, category_id, amount, date, note)
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO income (user_id, category_id, amount, date, note) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, category_id, amount, date, note),
        )
        db.commit()
        return cur.lastrowid


def get_income(user_id: int, income_id: int) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_income as supabase_get_income
        return supabase_get_income(user_id, income_id)
    else:
        return get_db().execute(
            "SELECT i.id, i.user_id, i.category_id, i.amount, i.date, i.note, "
            "       c.name AS category_name "
            "FROM income i "
            "JOIN categories c ON c.id = i.category_id "
            "WHERE i.id = ? AND i.user_id = ?",
            (income_id, user_id),
        ).fetchone()


def update_income(
    user_id: int,
    income_id: int,
    category_id: int,
    amount: float,
    date: str,
    note: Optional[str],
) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import update_income as supabase_update_income
        supabase_update_income(user_id, income_id, category_id, amount, date, note)
    else:
        db = get_db()
        db.execute(
            "UPDATE income "
            "SET category_id = ?, amount = ?, date = ?, note = ? "
            "WHERE id = ? AND user_id = ?",
            (category_id, amount, date, note, income_id, user_id),
        )
        db.commit()


def delete_income(user_id: int, income_id: int) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import delete_income as supabase_delete_income
        supabase_delete_income(user_id, income_id)
    else:
        db = get_db()
        db.execute(
            "DELETE FROM income WHERE id = ? AND user_id = ?",
            (income_id, user_id),
        )
        db.commit()


def list_income(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> list[sqlite3.Row]:
    """Return the user's income, newest first, with filters applied."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import list_income as supabase_list_income
        return supabase_list_income(user_id, date_from, date_to, category_id)
    else:
        sql = (
            "SELECT i.id, i.amount, i.date, i.note, "
            "       c.id AS category_id, c.name AS category_name "
            "FROM income i "
            "JOIN categories c ON c.id = i.category_id "
            "WHERE i.user_id = ? "
        )
        params: list[Any] = [user_id]
        if date_from:
            sql += "AND i.date >= ? "
            params.append(date_from)
        if date_to:
            sql += "AND i.date <= ? "
            params.append(date_to)
        if category_id:
            sql += "AND i.category_id = ? "
            params.append(category_id)
        sql += "ORDER BY i.date DESC, i.id DESC"
        return get_db().execute(sql, params).fetchall()


def sum_income(
    user_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
) -> float:
    """Sum amounts over the same filter set as ``list_income``."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import sum_income as supabase_sum_income
        return supabase_sum_income(user_id, date_from, date_to, category_id)
    else:
        sql = "SELECT COALESCE(SUM(i.amount), 0) AS total FROM income i WHERE i.user_id = ? "
        params: list[Any] = [user_id]
        if date_from:
            sql += "AND i.date >= ? "
            params.append(date_from)
        if date_to:
            sql += "AND i.date <= ? "
            params.append(date_to)
        if category_id:
            sql += "AND i.category_id = ? "
            params.append(category_id)
        row = get_db().execute(sql, params).fetchone()
        return float(row["total"])


def sum_income_for_month(user_id: int, year: int, month: int) -> float:
    """Total income in a single calendar month (1-indexed month)."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import sum_income_for_month as supabase_sum_income_for_month
        return supabase_sum_income_for_month(user_id, year, month)
    else:
        first, next_first = _month_bounds(year, month)
        db = get_db()
        row = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM income "
            "WHERE user_id = ? AND date >= ? AND date < ?",
            (user_id, first, next_first),
        ).fetchone()
        return float(row["total"])


def recent_income(user_id: int, limit: int = 5) -> list[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import recent_income as supabase_recent_income
        return supabase_recent_income(user_id, limit)
    else:
        return get_db().execute(
            "SELECT i.id, i.amount, i.date, i.note, "
            "       c.name AS category_name "
            "FROM income i "
            "JOIN categories c ON c.id = i.category_id "
            "WHERE i.user_id = ? "
            "ORDER BY i.date DESC, i.id DESC "
            "LIMIT ?",
            (user_id, limit),
        ).fetchall()


# ------------------------------------------------------------------ #
# Budgets                                                             #
# ------------------------------------------------------------------ #

def create_budget(user_id: int, category_id: int, amount: float, month: str) -> int:
    """Create or update a budget for a category in a specific month."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import create_budget as supabase_create_budget
        return supabase_create_budget(user_id, category_id, amount, month)
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO budgets (user_id, category_id, amount, month) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, category_id, month) "
            "DO UPDATE SET amount = excluded.amount",
            (user_id, category_id, amount, month),
        )
        db.commit()
        return cur.lastrowid


def get_budget(user_id: int, category_id: int, month: str) -> Optional[sqlite3.Row]:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_budget as supabase_get_budget
        return supabase_get_budget(user_id, category_id, month)
    else:
        return get_db().execute(
            "SELECT id, user_id, category_id, amount, month "
            "FROM budgets "
            "WHERE user_id = ? AND category_id = ? AND month = ?",
            (user_id, category_id, month),
        ).fetchone()


def get_budgets_for_month(user_id: int, month: str) -> list[sqlite3.Row]:
    """Get all budgets for a user in a specific month, with category names and spending."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_budgets_for_month as supabase_get_budgets_for_month
        return supabase_get_budgets_for_month(user_id, month)
    else:
        return get_db().execute(
            "SELECT b.id, b.category_id, b.amount, b.month, "
            "       c.name AS category_name, "
            "       COALESCE(SUM(e.amount), 0) AS spent "
            "FROM budgets b "
            "JOIN categories c ON c.id = b.category_id "
            "LEFT JOIN expenses e ON e.category_id = b.category_id "
            "  AND e.user_id = b.user_id "
            "  AND e.date >= ? AND e.date < ? "
            "WHERE b.user_id = ? AND b.month = ? "
            "GROUP BY b.id, b.category_id, b.amount, b.month, c.name "
            "ORDER BY c.name",
            (*_month_bounds(int(month[:4]), int(month[5:7])), user_id, month),
        ).fetchall()


def delete_budget(user_id: int, budget_id: int) -> None:
    if DATABASE_MODE == "supabase":
        from .supabase_impl import delete_budget as supabase_delete_budget
        supabase_delete_budget(user_id, budget_id)
    else:
        db = get_db()
        db.execute(
            "DELETE FROM budgets WHERE id = ? AND user_id = ?",
            (budget_id, user_id),
        )
        db.commit()


def get_balance(user_id: int) -> float:
    """Calculate total balance (total income - total expenses)."""
    if DATABASE_MODE == "supabase":
        from .supabase_impl import get_balance as supabase_get_balance
        return supabase_get_balance(user_id)
    else:
        income = get_db().execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM income WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
        expenses = get_db().execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
        return float(income) - float(expenses)
