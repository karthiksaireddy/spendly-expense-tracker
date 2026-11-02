"""Re-exports so callers can do ``from database import get_db, init_db, ...``."""
from .db import (
    DEFAULT_CATEGORIES,
    DB_PATH,
    by_category_for_month,
    category_in_use,
    close_db,
    create_budget,
    create_category,
    create_expense,
    create_income,
    create_user,
    delete_budget,
    delete_category,
    delete_expense,
    delete_income,
    get_balance,
    get_budget,
    get_budgets_for_month,
    get_categories,
    get_category,
    get_db,
    get_expense,
    get_income,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_expenses,
    list_income,
    recent_expenses,
    recent_income,
    seed_default_categories,
    sum_expenses,
    sum_for_month,
    sum_income,
    sum_income_for_month,
    update_category,
    update_expense,
    update_income,
)

# Supabase-specific exports (only import if supabase package is available)
try:
    from .supabase_client import (
        get_authenticated_client,
        get_supabase_client,
        reset_client,
    )
except ImportError:
    # Provide stubs for when supabase package is not installed
    def get_supabase_client():
        raise NotImplementedError("Supabase client not available. Install supabase package or use SQLite mode.")

    def get_authenticated_client():
        raise NotImplementedError("Supabase client not available. Install supabase package or use SQLite mode.")

    def reset_client():
        raise NotImplementedError("Supabase client not available. Install supabase package or use SQLite mode.")

__all__ = [
    "DEFAULT_CATEGORIES",
    "DB_PATH",
    "by_category_for_month",
    "category_in_use",
    "close_db",
    "create_budget",
    "create_category",
    "create_expense",
    "create_income",
    "create_user",
    "delete_budget",
    "delete_category",
    "delete_expense",
    "delete_income",
    "get_balance",
    "get_budget",
    "get_budgets_for_month",
    "get_categories",
    "get_category",
    "get_db",
    "get_expense",
    "get_income",
    "get_user_by_email",
    "get_user_by_id",
    "init_db",
    "list_expenses",
    "list_income",
    "recent_expenses",
    "recent_income",
    "seed_default_categories",
    "sum_expenses",
    "sum_for_month",
    "sum_income",
    "sum_income_for_month",
    "update_category",
    "update_expense",
    "update_income",
    "get_authenticated_client",
    "get_supabase_client",
    "reset_client",
]
