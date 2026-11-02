"""Supabase implementation of database functions for Spendly.

This module provides Supabase-compatible implementations of all database
operations that mirror the SQLite functions in db.py. Functions are called
from db.py when DATABASE_MODE is set to "supabase".
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from .supabase_client import get_authenticated_client, get_supabase_client


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
# Users                                                               #
# ------------------------------------------------------------------ #

def create_user(email: str, display_name: str, password_hash: str) -> str:
    """Create a user in Supabase.

    Note: For Supabase, user creation is handled by auth.sign_up in app.py.
    This function is kept for compatibility but should not be used in Supabase mode.
    """
    raise NotImplementedError("Use Supabase Auth sign_up instead")


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by ID from Supabase Auth."""
    supabase = get_supabase_client()
    try:
        response = supabase.auth.get_user(user_id)
        if response.user:
            return {
                "id": str(response.user.id),
                "email": response.user.email,
                "display_name": response.user.user_metadata.get("display_name", ""),
                "password_hash": "",  # Not stored in Supabase Auth
                "created_at": str(response.user.created_at),
            }
    except Exception:
        pass
    return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email from Supabase.

    Note: Supabase doesn't allow querying users by email for security reasons.
    This function returns None and relies on auth to handle user lookups.
    """
    return None


# ------------------------------------------------------------------ #
# Categories                                                          #
# ------------------------------------------------------------------ #

def get_categories(user_id: str) -> list[dict]:
    """Get all categories for a user."""
    supabase = get_authenticated_client()
    response = supabase.table("categories").select("id, name").eq("user_id", user_id).order("name").execute()
    return [{"id": row["id"], "name": row["name"]} for row in response.data]


def get_category(user_id: str, category_id: str) -> Optional[dict]:
    """Get a specific category for a user."""
    supabase = get_authenticated_client()
    response = supabase.table("categories").select("id, name").eq("id", category_id).eq("user_id", user_id).execute()
    if response.data:
        return {"id": response.data[0]["id"], "name": response.data[0]["name"]}
    return None


def create_category(user_id: str, name: str) -> str:
    """Create a new category and return its ID."""
    supabase = get_authenticated_client()
    response = supabase.table("categories").insert({"user_id": user_id, "name": name}).execute()
    return str(response.data[0]["id"])


def update_category(user_id: str, category_id: str, name: str) -> None:
    """Update a category name."""
    supabase = get_authenticated_client()
    supabase.table("categories").update({"name": name}).eq("id", category_id).eq("user_id", user_id).execute()


def delete_category(user_id: str, category_id: str) -> None:
    """Delete a category."""
    supabase = get_authenticated_client()
    supabase.table("categories").delete().eq("id", category_id).eq("user_id", user_id).execute()


def category_in_use(category_id: str) -> bool:
    """Check if a category is used by any expense."""
    supabase = get_authenticated_client()
    response = supabase.table("expenses").select("id").eq("category_id", category_id).limit(1).execute()
    return len(response.data) > 0


def seed_default_categories(user_id: str) -> None:
    """Populate the standard set of categories for a new user."""
    supabase = get_authenticated_client()
    for name in DEFAULT_CATEGORIES:
        try:
            supabase.table("categories").insert({"user_id": user_id, "name": name}).execute()
        except Exception:
            # Already exists — continue
            continue


# ------------------------------------------------------------------ #
# Expenses                                                            #
# ------------------------------------------------------------------ #

def create_expense(
    user_id: str,
    category_id: str,
    amount: float,
    date: str,
    note: Optional[str],
) -> str:
    """Create a new expense and return its ID."""
    supabase = get_authenticated_client()
    response = supabase.table("expenses").insert({
        "user_id": user_id,
        "category_id": category_id,
        "amount": amount,
        "date": date,
        "note": note,
    }).execute()
    return str(response.data[0]["id"])


def get_expense(user_id: str, expense_id: str) -> Optional[dict]:
    """Get a specific expense with category name."""
    supabase = get_authenticated_client()
    response = supabase.table("expenses").select(
        "id, user_id, category_id, amount, date, note, categories(name)"
    ).eq("id", expense_id).eq("user_id", user_id).execute()
    if response.data:
        row = response.data[0]
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "category_id": row["category_id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
    return None


def update_expense(
    user_id: str,
    expense_id: str,
    category_id: str,
    amount: float,
    date: str,
    note: Optional[str],
) -> None:
    """Update an expense."""
    supabase = get_authenticated_client()
    supabase.table("expenses").update({
        "category_id": category_id,
        "amount": amount,
        "date": date,
        "note": note,
    }).eq("id", expense_id).eq("user_id", user_id).execute()


def delete_expense(user_id: str, expense_id: str) -> None:
    """Delete an expense."""
    supabase = get_authenticated_client()
    supabase.table("expenses").delete().eq("id", expense_id).eq("user_id", user_id).execute()


def list_expenses(
    user_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
) -> list[dict]:
    """List expenses with filters."""
    supabase = get_authenticated_client()
    query = supabase.table("expenses").select(
        "id, amount, date, note, category_id, categories(name)"
    ).eq("user_id", user_id)

    if date_from:
        query = query.gte("date", date_from)
    if date_to:
        query = query.lte("date", date_to)
    if category_id:
        query = query.eq("category_id", category_id)

    response = query.order("date", desc=True).execute()

    return [
        {
            "id": row["id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_id": row["category_id"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
        for row in response.data
    ]


def sum_expenses(
    user_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
) -> float:
    """Sum expenses with filters."""
    supabase = get_authenticated_client()
    query = supabase.table("expenses").select("amount").eq("user_id", user_id)

    if date_from:
        query = query.gte("date", date_from)
    if date_to:
        query = query.lte("date", date_to)
    if category_id:
        query = query.eq("category_id", category_id)

    response = query.execute()
    return sum(float(row["amount"]) for row in response.data)


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (first_day, first_day_of_next_month) for a calendar month."""
    if month == 12:
        return (f"{year:04d}-12-01", f"{year + 1:04d}-01-01")
    return (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month + 1:02d}-01")


def sum_for_month(user_id: str, year: int, month: int) -> float:
    """Total spending in a single calendar month."""
    first, next_first = _month_bounds(year, month)
    supabase = get_authenticated_client()
    response = supabase.table("expenses").select("amount").eq("user_id", user_id).gte("date", first).lt("date", next_first).execute()
    return sum(float(row["amount"]) for row in response.data)


def by_category_for_month(
    user_id: str, year: int, month: int
) -> list[dict]:
    """Per-category totals for a month, ordered by amount descending."""
    first, next_first = _month_bounds(year, month)
    supabase = get_authenticated_client()

    # Get all categories first
    categories_response = supabase.table("categories").select("id, name").eq("user_id", user_id).execute()
    categories = {cat["id"]: cat["name"] for cat in categories_response.data}

    # Get expenses for the month
    expenses_response = supabase.table("expenses").select("category_id, amount").eq("user_id", user_id).gte("date", first).lt("date", next_first).execute()

    # Aggregate by category
    category_totals = {}
    for expense in expenses_response.data:
        cat_id = expense["category_id"]
        category_totals[cat_id] = category_totals.get(cat_id, 0) + float(expense["amount"])

    # Build result with only categories that have spending
    result = [
        {
            "category_id": cat_id,
            "category_name": categories.get(cat_id, ""),
            "total": total,
        }
        for cat_id, total in category_totals.items()
        if total > 0
    ]

    result.sort(key=lambda x: x["total"], reverse=True)
    return result


def recent_expenses(user_id: str, limit: int = 5) -> list[dict]:
    """Get recent expenses."""
    supabase = get_authenticated_client()
    response = supabase.table("expenses").select(
        "id, amount, date, note, categories(name)"
    ).eq("user_id", user_id).order("date", desc=True).limit(limit).execute()

    return [
        {
            "id": row["id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
        for row in response.data
    ]


# ------------------------------------------------------------------ #
# Income                                                              #
# ------------------------------------------------------------------ #

def create_income(
    user_id: str,
    category_id: str,
    amount: float,
    date: str,
    note: Optional[str],
) -> str:
    """Create a new income entry and return its ID."""
    supabase = get_authenticated_client()
    response = supabase.table("income").insert({
        "user_id": user_id,
        "category_id": category_id,
        "amount": amount,
        "date": date,
        "note": note,
    }).execute()
    return str(response.data[0]["id"])


def get_income(user_id: str, income_id: str) -> Optional[dict]:
    """Get a specific income entry with category name."""
    supabase = get_authenticated_client()
    response = supabase.table("income").select(
        "id, user_id, category_id, amount, date, note, categories(name)"
    ).eq("id", income_id).eq("user_id", user_id).execute()
    if response.data:
        row = response.data[0]
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "category_id": row["category_id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
    return None


def update_income(
    user_id: str,
    income_id: str,
    category_id: str,
    amount: float,
    date: str,
    note: Optional[str],
) -> None:
    """Update an income entry."""
    supabase = get_authenticated_client()
    supabase.table("income").update({
        "category_id": category_id,
        "amount": amount,
        "date": date,
        "note": note,
    }).eq("id", income_id).eq("user_id", user_id).execute()


def delete_income(user_id: str, income_id: str) -> None:
    """Delete an income entry."""
    supabase = get_authenticated_client()
    supabase.table("income").delete().eq("id", income_id).eq("user_id", user_id).execute()


def list_income(
    user_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
) -> list[dict]:
    """List income entries with filters."""
    supabase = get_authenticated_client()
    query = supabase.table("income").select(
        "id, amount, date, note, category_id, categories(name)"
    ).eq("user_id", user_id)

    if date_from:
        query = query.gte("date", date_from)
    if date_to:
        query = query.lte("date", date_to)
    if category_id:
        query = query.eq("category_id", category_id)

    response = query.order("date", desc=True).execute()

    return [
        {
            "id": row["id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_id": row["category_id"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
        for row in response.data
    ]


def sum_income(
    user_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[str] = None,
) -> float:
    """Sum income with filters."""
    supabase = get_authenticated_client()
    query = supabase.table("income").select("amount").eq("user_id", user_id)

    if date_from:
        query = query.gte("date", date_from)
    if date_to:
        query = query.lte("date", date_to)
    if category_id:
        query = query.eq("category_id", category_id)

    response = query.execute()
    return sum(float(row["amount"]) for row in response.data)


def sum_income_for_month(user_id: str, year: int, month: int) -> float:
    """Total income in a single calendar month."""
    first, next_first = _month_bounds(year, month)
    supabase = get_authenticated_client()
    response = supabase.table("income").select("amount").eq("user_id", user_id).gte("date", first).lt("date", next_first).execute()
    return sum(float(row["amount"]) for row in response.data)


def recent_income(user_id: str, limit: int = 5) -> list[dict]:
    """Get recent income entries."""
    supabase = get_authenticated_client()
    response = supabase.table("income").select(
        "id, amount, date, note, categories(name)"
    ).eq("user_id", user_id).order("date", desc=True).limit(limit).execute()

    return [
        {
            "id": row["id"],
            "amount": row["amount"],
            "date": row["date"],
            "note": row["note"],
            "category_name": row["categories"]["name"] if row.get("categories") else "",
        }
        for row in response.data
    ]


# ------------------------------------------------------------------ #
# Budgets                                                             #
# ------------------------------------------------------------------ #

def create_budget(user_id: str, category_id: str, amount: float, month: str) -> str:
    """Create or update a budget for a category in a specific month."""
    supabase = get_authenticated_client()

    # Check if budget exists
    existing = supabase.table("budgets").select("id").eq("user_id", user_id).eq("category_id", category_id).eq("month", month).execute()

    if existing.data:
        # Update existing
        response = supabase.table("budgets").update({"amount": amount}).eq("id", existing.data[0]["id"]).execute()
        return str(response.data[0]["id"])
    else:
        # Create new
        response = supabase.table("budgets").insert({
            "user_id": user_id,
            "category_id": category_id,
            "amount": amount,
            "month": month,
        }).execute()
        return str(response.data[0]["id"])


def get_budget(user_id: str, category_id: str, month: str) -> Optional[dict]:
    """Get a specific budget."""
    supabase = get_authenticated_client()
    response = supabase.table("budgets").select("id, user_id, category_id, amount, month").eq("user_id", user_id).eq("category_id", category_id).eq("month", month).execute()
    if response.data:
        return response.data[0]
    return None


def get_budgets_for_month(user_id: str, month: str) -> list[dict]:
    """Get all budgets for a user in a specific month, with category names and spending."""
    supabase = get_authenticated_client()
    year = int(month[:4])
    month_num = int(month[5:7])
    first, next_first = _month_bounds(year, month_num)

    # Get budgets with category info
    budgets_response = supabase.table("budgets").select(
        "id, category_id, amount, month, categories(name)"
    ).eq("user_id", user_id).eq("month", month).execute()

    result = []
    for budget in budgets_response.data:
        # Calculate spent amount for this category in the month
        expenses_response = supabase.table("expenses").select("amount").eq("user_id", user_id).eq("category_id", budget["category_id"]).gte("date", first).lt("date", next_first).execute()
        spent = sum(float(exp["amount"]) for exp in expenses_response.data)

        result.append({
            "id": budget["id"],
            "category_id": budget["category_id"],
            "amount": budget["amount"],
            "month": budget["month"],
            "category_name": budget["categories"]["name"] if budget.get("categories") else "",
            "spent": spent,
        })

    result.sort(key=lambda x: x["category_name"])
    return result


def delete_budget(user_id: str, budget_id: str) -> None:
    """Delete a budget."""
    supabase = get_authenticated_client()
    supabase.table("budgets").delete().eq("id", budget_id).eq("user_id", user_id).execute()


def get_balance(user_id: str) -> float:
    """Calculate total balance (total income - total expenses)."""
    supabase = get_authenticated_client()

    income_response = supabase.table("income").select("amount").eq("user_id", user_id).execute()
    total_income = sum(float(row["amount"]) for row in income_response.data)

    expenses_response = supabase.table("expenses").select("amount").eq("user_id", user_id).execute()
    total_expenses = sum(float(row["amount"]) for row in expenses_response.data)

    return total_income - total_expenses
