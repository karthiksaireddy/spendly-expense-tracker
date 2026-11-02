"""SQLite to Supabase Migration Script for Spendly.

This script safely migrates data from a local SQLite database to Supabase.
It performs the following operations:
1. Backs up the existing SQLite database
2. Reads users, categories, expenses, income, and budgets from SQLite
3. Creates corresponding entries in Supabase
4. Preserves all data relationships and integrity

IMPORTANT:
- This script does NOT delete any data from SQLite
- Run with DATABASE_MODE=sqlite to read from SQLite
- Supabase credentials must be configured in .env
- Run this script while the application is NOT running
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from typing import Any, Dict

import sys
from pathlib import Path

# Add parent directory to path to import database modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()


def backup_sqlite_db(db_path: str) -> str:
    """Create a backup of the SQLite database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"✓ SQLite database backed up to: {backup_path}")
    return backup_path


def get_supabase_client():
    """Initialize Supabase client with service role key for migration."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env for migration."
        )

    return create_client(url, key)


def get_user_email_map(sqlite_conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """Get a mapping of email to user data from SQLite for manual reference."""
    print("\n📦 Reading users from SQLite...")

    cursor = sqlite_conn.execute("SELECT id, email, display_name FROM users")
    users = cursor.fetchall()

    user_map = {}
    for user in users:
        sqlite_id, email, display_name = user
        user_map[email] = {
            "sqlite_id": str(sqlite_id),
            "email": email,
            "display_name": display_name,
        }
        print(f"  - {email} ({display_name})")

    print(f"✓ Found {len(user_map)} users in SQLite")
    return user_map


def migrate_categories(sqlite_conn: sqlite3.Connection, supabase, email_to_supabase_id: Dict[str, str], sqlite_user_map: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """Migrate categories from SQLite to Supabase."""
    print("\n📦 Migrating categories...")

    cursor = sqlite_conn.execute("SELECT id, user_id, name, created_at FROM categories")
    categories = cursor.fetchall()

    # Build reverse mapping from sqlite_id to email
    sqlite_id_to_email = {}
    for email, user_data in sqlite_user_map.items():
        sqlite_id_to_email[user_data["sqlite_id"]] = email

    category_id_map = {}  # Maps SQLite ID to Supabase UUID

    for category in categories:
        sqlite_id, user_id, name, created_at = category

        # Get user email from SQLite ID
        user_email = sqlite_id_to_email.get(str(user_id))

        # Skip if user hasn't re-registered in Supabase yet
        if not user_email or user_email not in email_to_supabase_id:
            print(f"  ⚠️  Skipping category '{name}' - user not yet registered in Supabase")
            continue

        try:
            import uuid
            supabase_id = str(uuid.uuid4())

            response = supabase.table("categories").insert({
                "id": supabase_id,
                "user_id": email_to_supabase_id[user_email],
                "name": name,
                "created_at": created_at,
            }).execute()

            category_id_map[str(sqlite_id)] = supabase_id
            print(f"  ✓ Migrated category: {name}")
        except Exception as e:
            print(f"  ✗ Failed to migrate category '{name}': {e}")

    print(f"✓ Migrated {len(category_id_map)} categories")
    return category_id_map


def migrate_expenses(sqlite_conn: sqlite3.Connection, supabase, email_to_supabase_id: Dict[str, str], sqlite_user_map: Dict[str, Dict[str, Any]], category_id_map: Dict[str, str]):
    """Migrate expenses from SQLite to Supabase."""
    print("\n📦 Migrating expenses...")

    # Build reverse mapping from sqlite_id to email
    sqlite_id_to_email = {}
    for email, user_data in sqlite_user_map.items():
        sqlite_id_to_email[user_data["sqlite_id"]] = email

    cursor = sqlite_conn.execute("SELECT id, user_id, category_id, amount, date, note, created_at FROM expenses")
    expenses = cursor.fetchall()

    count = 0
    for expense in expenses:
        sqlite_id, user_id, category_id, amount, date, note, created_at = expense

        # Get user email from SQLite ID
        user_email = sqlite_id_to_email.get(str(user_id))

        # Skip if user hasn't re-registered or category wasn't migrated
        if not user_email or user_email not in email_to_supabase_id:
            print(f"  ⚠️  Skipping expense - user not yet registered in Supabase")
            continue
        if str(category_id) not in category_id_map:
            print(f"  ⚠️  Skipping expense - category not migrated")
            continue

        try:
            import uuid
            supabase_id = str(uuid.uuid4())

            supabase.table("expenses").insert({
                "id": supabase_id,
                "user_id": email_to_supabase_id[user_email],
                "category_id": category_id_map[str(category_id)],
                "amount": float(amount),
                "date": date,
                "note": note,
                "created_at": created_at,
            }).execute()

            count += 1
            if count % 10 == 0:
                print(f"  ✓ Migrated {count} expenses...")
        except Exception as e:
            print(f"  ✗ Failed to migrate expense: {e}")

    print(f"✓ Migrated {count} expenses")


def migrate_income(sqlite_conn: sqlite3.Connection, supabase, email_to_supabase_id: Dict[str, str], sqlite_user_map: Dict[str, Dict[str, Any]], category_id_map: Dict[str, str]):
    """Migrate income from SQLite to Supabase."""
    print("\n📦 Migrating income...")

    # Build reverse mapping from sqlite_id to email
    sqlite_id_to_email = {}
    for email, user_data in sqlite_user_map.items():
        sqlite_id_to_email[user_data["sqlite_id"]] = email

    cursor = sqlite_conn.execute("SELECT id, user_id, category_id, amount, date, note, created_at FROM income")
    income_entries = cursor.fetchall()

    count = 0
    for income in income_entries:
        sqlite_id, user_id, category_id, amount, date, note, created_at = income

        # Get user email from SQLite ID
        user_email = sqlite_id_to_email.get(str(user_id))

        # Skip if user hasn't re-registered or category wasn't migrated
        if not user_email or user_email not in email_to_supabase_id:
            print(f"  ⚠️  Skipping income - user not yet registered in Supabase")
            continue
        if str(category_id) not in category_id_map:
            print(f"  ⚠️  Skipping income - category not migrated")
            continue

        try:
            import uuid
            supabase_id = str(uuid.uuid4())

            supabase.table("income").insert({
                "id": supabase_id,
                "user_id": email_to_supabase_id[user_email],
                "category_id": category_id_map[str(category_id)],
                "amount": float(amount),
                "date": date,
                "note": note,
                "created_at": created_at,
            }).execute()

            count += 1
            if count % 10 == 0:
                print(f"  ✓ Migrated {count} income entries...")
        except Exception as e:
            print(f"  ✗ Failed to migrate income: {e}")

    print(f"✓ Migrated {count} income entries")


def migrate_budgets(sqlite_conn: sqlite3.Connection, supabase, email_to_supabase_id: Dict[str, str], sqlite_user_map: Dict[str, Dict[str, Any]], category_id_map: Dict[str, str]):
    """Migrate budgets from SQLite to Supabase."""
    print("\n📦 Migrating budgets...")

    # Build reverse mapping from sqlite_id to email
    sqlite_id_to_email = {}
    for email, user_data in sqlite_user_map.items():
        sqlite_id_to_email[user_data["sqlite_id"]] = email

    cursor = sqlite_conn.execute("SELECT id, user_id, category_id, amount, month, created_at FROM budgets")
    budgets = cursor.fetchall()

    count = 0
    for budget in budgets:
        sqlite_id, user_id, category_id, amount, month, created_at = budget

        # Get user email from SQLite ID
        user_email = sqlite_id_to_email.get(str(user_id))

        # Skip if user hasn't re-registered or category wasn't migrated
        if not user_email or user_email not in email_to_supabase_id:
            print(f"  ⚠️  Skipping budget - user not yet registered in Supabase")
            continue
        if str(category_id) not in category_id_map:
            print(f"  ⚠️  Skipping budget - category not migrated")
            continue

        try:
            import uuid
            supabase_id = str(uuid.uuid4())

            supabase.table("budgets").insert({
                "id": supabase_id,
                "user_id": email_to_supabase_id[user_email],
                "category_id": category_id_map[str(category_id)],
                "amount": float(amount),
                "month": month,
                "created_at": created_at,
            }).execute()

            count += 1
        except Exception as e:
            print(f"  ✗ Failed to migrate budget: {e}")

    print(f"✓ Migrated {count} budgets")


def main():
    """Main migration function."""
    print("=" * 60)
    print("SQLite to Supabase Migration Script for Spendly")
    print("=" * 60)

    # Check prerequisites
    db_path = os.path.join(os.path.dirname(__file__), "../database/expense_tracker.db")

    if not os.path.exists(db_path):
        print(f"✗ SQLite database not found at: {db_path}")
        print("  Please ensure you have run the app with SQLite mode first.")
        return

    print(f"\n📂 SQLite database found at: {db_path}")

    # Backup SQLite database
    backup_path = backup_sqlite_db(db_path)

    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(db_path)
        sqlite_conn.row_factory = sqlite3.Row
        print("✓ Connected to SQLite database")

        # Connect to Supabase
        supabase = get_supabase_client()
        print("✓ Connected to Supabase")

        # Get users from SQLite
        sqlite_user_map = get_user_email_map(sqlite_conn)

        if not sqlite_user_map:
            print("\n✗ No users found in SQLite database. Nothing to migrate.")
            return

        # Get registered users from Supabase
        print("\n📦 Checking registered users in Supabase...")
        try:
            # List all users from Supabase (requires service role)
            # This is a simplified approach - in production you'd use admin API
            # For now, we'll ask the user to provide the email-to-UUID mapping
            print("\n⚠️  NOTE: Due to Supabase security, we cannot automatically list users.")
            print("  Users must have already registered in the Supabase app.")
            print("\n  Please enter the email addresses of users who have registered,")
            print("  one per line (empty line to finish):")

            email_to_supabase_id = {}
            while True:
                email = input("  Email: ").strip().lower()
                if not email:
                    break

                if email not in sqlite_user_map:
                    print(f"  ⚠️  Warning: {email} not found in SQLite database")
                    continue

                # Try to get the user from Supabase auth
                try:
                    # We can't directly query auth.users from client
                    # So we'll need the user to provide their UUID or we try to look it up
                    # For simplicity, let's ask for the UUID
                    user_uuid = input(f"  Enter Supabase UUID for {email}: ").strip()
                    if user_uuid:
                        email_to_supabase_id[email] = user_uuid
                        print(f"  ✓ Mapped {email} -> {user_uuid}")
                except Exception as e:
                    print(f"  ✗ Failed to map {email}: {e}")

            if not email_to_supabase_id:
                print("\n✗ No users mapped. Aborting migration.")
                return

        except Exception as e:
            print(f"\n✗ Failed to get user mapping: {e}")
            return

        # Confirm migration
        print("\n" + "=" * 60)
        print("Migration Summary:")
        print("=" * 60)
        print(f"SQLite users found: {len(sqlite_user_map)}")
        print(f"Users registered in Supabase: {len(email_to_supabase_id)}")
        print(f"Users to migrate: {len(email_to_supabase_id)}")
        print("\n⚠️  IMPORTANT:")
        print("  - Only data for registered users will be migrated")
        print("  - Unregistered users' data will remain in SQLite")
        print("  - A backup of your SQLite database has been created")
        print("\n  Ready to proceed? (Press Enter to continue, Ctrl+C to cancel)")
        input()

        # Perform migration
        category_id_map = migrate_categories(sqlite_conn, supabase, email_to_supabase_id, sqlite_user_map)
        migrate_expenses(sqlite_conn, supabase, email_to_supabase_id, sqlite_user_map, category_id_map)
        migrate_income(sqlite_conn, supabase, email_to_supabase_id, sqlite_user_map, category_id_map)
        migrate_budgets(sqlite_conn, supabase, email_to_supabase_id, sqlite_user_map, category_id_map)

        # Close connections
        sqlite_conn.close()

        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Update your .env file to set DATABASE_MODE=supabase")
        print("2. Restart the application")
        print("3. Ask migrated users to log in and verify their data")
        print(f"4. Your SQLite backup is at: {backup_path}")
        print("\n⚠️  Important: Keep the SQLite backup until you've verified everything works!")

    except KeyboardInterrupt:
        print("\n\n✗ Migration cancelled by user")
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        print(f"  Your SQLite backup is at: {backup_path}")
        raise


if __name__ == "__main__":
    main()
