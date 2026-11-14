"""Spendly — Flask application entrypoint.

Run with ``python app.py`` (port 5001). Routes are organized by area: auth,
dashboard, expenses, categories. All persistent data lives in SQLite via
``database/db.py``.
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import date, datetime
from functools import wraps
from typing import Optional

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import DB_PATH, close_db, get_db, init_db

# Load environment variables from .env file
load_dotenv()

# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

DEFAULT_PORT = 5001
DEV_SECRET = "dev-secret-change-me"
DATABASE_MODE = os.environ.get("DATABASE_MODE", "sqlite").lower()

# Minimal RFC-5322-ish check; good enough to catch typos, not for
# validating every legal RFC address. Server-side only.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ #
# App factory                                                         #
# ------------------------------------------------------------------ #

def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", DEV_SECRET)
    app.config["DATABASE"] = DB_PATH
    app.config["DATABASE_MODE"] = DATABASE_MODE

    # Create tables on first run. Idempotent (SQLite only).
    if DATABASE_MODE == "sqlite" and not os.path.exists(DB_PATH):
        init_db(DB_PATH)

    # Make sure the connection is closed at the end of every request (SQLite only).
    if DATABASE_MODE == "sqlite":
        app.teardown_appcontext(close_db)

    # Inject ``current_user`` and a ``csrf_token`` callable into every
    # template so templates can branch on auth state and emit tokens
    # without reaching into ``session`` themselves.
    @app.context_processor
    def inject_user() -> dict:
        return {
            "current_user": _load_current_user(),
            "csrf_token": _issue_csrf_token,
        }

    register_filters(app)
    register_routes(app)
    register_error_handlers(app)
    return app


# ------------------------------------------------------------------ #
# Auth helpers                                                        #
# ------------------------------------------------------------------ #

def _load_current_user():
    """Load the current user from session.

    For SQLite: uses integer user_id from session.
    For Supabase: uses UUID user_id from session and fetches from Supabase auth.
    """
    user_id = session.get("user_id")
    if user_id is None:
        return None

    # Cache on ``g`` so multiple calls per request hit the DB once.
    if "current_user" not in g:
        if DATABASE_MODE == "supabase":
            # For Supabase, user info is already in session from auth
            g.current_user = {
                "id": session.get("user_id"),
                "email": session.get("user_email"),
                "display_name": session.get("display_name"),
            }
        else:
            # SQLite: fetch from database
            g.current_user = get_db().execute(
                "SELECT id, email, display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
    return g.current_user


def login_required(view):
    """Reject anonymous users with a redirect to /login?next=..."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _issue_csrf_token() -> str:
    """Return the per-session CSRF token, generating one if needed."""
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _check_csrf() -> bool:
    """Compare the submitted token against the session token."""
    submitted = request.form.get("_csrf", "")
    expected = session.get("_csrf", "")
    return bool(submitted) and bool(expected) and secrets.compare_digest(
        submitted, expected
    )


# ------------------------------------------------------------------ #
# Template filters                                                     #
# ------------------------------------------------------------------ #

def register_filters(app: Flask) -> None:
    @app.template_filter("money")
    def money(value) -> str:
        try:
            return f"₹{float(value):,.2f}"
        except (TypeError, ValueError):
            return "₹0.00"

    @app.template_filter("humandate")
    def humandate(value) -> str:
        if not value:
            return ""
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return str(value)


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

def register_routes(app: Flask) -> None:
    # ----- Public pages -----
    @app.route("/")
    def landing():
        return render_template("landing.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_register()
        return render_template("auth/register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_login()
        return render_template("auth/login.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")

        if DATABASE_MODE == "supabase":
            from database.supabase_client import get_supabase_client
            try:
                supabase = get_supabase_client()
                supabase.auth.sign_out()
            except Exception:
                pass  # Ignore sign_out errors

        session.clear()
        return redirect(url_for("landing"))

    # ----- Dashboard -----
    @app.route("/dashboard")
    @login_required
    def dashboard():
        return _handle_dashboard()

    # ----- Expenses -----
    @app.route("/expenses")
    @login_required
    def list_expenses():
        return _handle_list_expenses()

    @app.route("/expenses/new", methods=["GET", "POST"])
    @login_required
    def new_expense():
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_create_expense()
        return render_template(
            "expenses/new.html",
            form=_empty_expense_form(),
            categories=get_db().execute(
                "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name",
                (session["user_id"],),
            ).fetchall(),
        )

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_expense(expense_id: int):
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_update_expense(expense_id)
        return _handle_edit_expense_form(expense_id)

    @app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
    @login_required
    def delete_expense(expense_id: int):
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")
        return _handle_delete_expense(expense_id)

    # ----- Income -----
    @app.route("/income")
    @login_required
    def list_income():
        return _handle_list_income()

    @app.route("/income/new", methods=["GET", "POST"])
    @login_required
    def new_income():
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_create_income()
        return render_template(
            "income/new.html",
            form=_empty_income_form(),
            categories=get_db().execute(
                "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name",
                (session["user_id"],),
            ).fetchall(),
        )

    @app.route("/income/<int:income_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_income(income_id: int):
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_update_income(income_id)
        return _handle_edit_income_form(income_id)

    @app.route("/income/<int:income_id>/delete", methods=["POST"])
    @login_required
    def delete_income(income_id: int):
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")
        return _handle_delete_income(income_id)

    # ----- Categories -----
    @app.route("/categories")
    @login_required
    def list_categories():
        return _handle_list_categories()

    @app.route("/categories/new", methods=["GET", "POST"])
    @login_required
    def new_category():
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_create_category()
        return render_template(
            "categories/new.html", form={"name": ""}
        )

    @app.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_category(category_id: int):
        if request.method == "POST":
            if not _check_csrf():
                abort(400, "Invalid CSRF token.")
            return _handle_update_category(category_id)
        return _handle_edit_category_form(category_id)

    @app.route("/categories/<int:category_id>/delete", methods=["POST"])
    @login_required
    def delete_category(category_id: int):
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")
        return _handle_delete_category(category_id)

    # ----- Budgets -----
    @app.route("/budgets")
    @login_required
    def list_budgets():
        return _handle_budgets()

    @app.route("/budgets/new", methods=["POST"])
    @login_required
    def new_budget():
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")
        return _handle_create_budget()

    @app.route("/budgets/<int:budget_id>/delete", methods=["POST"])
    @login_required
    def delete_budget(budget_id: int):
        if not _check_csrf():
            abort(400, "Invalid CSRF token.")
        return _handle_delete_budget(budget_id)


# ------------------------------------------------------------------ #
# Handlers — auth                                                     #
# ------------------------------------------------------------------ #

def _handle_register():
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""

    form = {"email": email, "name": name}
    error = _validate_registration(email, name, password, confirm)
    if error:
        return render_template(
            "auth/register.html", error=error, form=form
        )

    if DATABASE_MODE == "supabase":
        return _handle_register_supabase(email, name, password)
    else:
        return _handle_register_sqlite(email, name, password)


def _handle_register_supabase(email: str, name: str, password: str):
    """Handle registration using Supabase Auth."""
    from database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    try:
        # Sign up user with Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "display_name": name
                }
            }
        })

        if auth_response.user:
            # Store user info in session
            session.clear()
            session["user_id"] = str(auth_response.user.id)
            session["user_email"] = email
            session["display_name"] = name
            session["supabase_access_token"] = auth_response.session.access_token
            session["_csrf"] = _issue_csrf_token()
            flash("Welcome to Spendly.", "success")
            return redirect(url_for("dashboard"))
        else:
            return render_template(
                "auth/register.html",
                error="Registration failed. Please try again.",
                form={"email": email, "name": name},
            )
    except Exception as e:
        return render_template(
            "auth/register.html",
            error=f"Registration error: {str(e)}",
            form={"email": email, "name": name},
        )


def _handle_register_sqlite(email: str, name: str, password: str):
    """Handle registration using SQLite."""
    from database import create_user  # local import to avoid cycle in tests

    user_id = create_user(email, name, generate_password_hash(password))
    session.clear()
    session["user_id"] = user_id
    session["display_name"] = name
    session["_csrf"] = _issue_csrf_token()
    flash("Welcome to Spendly.", "success")
    return redirect(url_for("dashboard"))


def _validate_registration(
    email: str, name: str, password: str, confirm: str
) -> Optional[str]:
    if not name:
        return "Please enter your name."
    if not EMAIL_RE.match(email):
        return "Please enter a valid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords do not match."

    # Check if email already exists
    if DATABASE_MODE == "supabase":
        from database.supabase_client import get_supabase_client
        supabase = get_supabase_client()
        # Check if user exists by trying to sign in (will fail if not exists)
        # Note: Supabase doesn't expose a direct "user exists" check for security
        # We'll let the sign_up fail with a duplicate error
    else:
        from database import get_user_by_email
        if get_user_by_email(email) is not None:
            return "An account with that email already exists."
    return None


def _handle_login():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    next_url = request.args.get("next") or url_for("dashboard")

    if DATABASE_MODE == "supabase":
        return _handle_login_supabase(email, password, next_url)
    else:
        return _handle_login_sqlite(email, password, next_url)


def _handle_login_supabase(email: str, password: str, next_url: str):
    """Handle login using Supabase Auth."""
    from database.supabase_client import get_supabase_client

    supabase = get_supabase_client()

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })

        if auth_response.user:
            # Get display name from user metadata
            display_name = auth_response.user.user_metadata.get("display_name", email.split("@")[0])

            session.clear()
            session["user_id"] = str(auth_response.user.id)
            session["user_email"] = email
            session["display_name"] = display_name
            session["supabase_access_token"] = auth_response.session.access_token
            session["_csrf"] = _issue_csrf_token()
            return redirect(next_url)
        else:
            return render_template(
                "auth/login.html",
                error="Invalid email or password.",
                form={"email": email},
            )
    except Exception as e:
        return render_template(
            "auth/login.html",
            error="Invalid email or password.",
            form={"email": email},
        )


def _handle_login_sqlite(email: str, password: str, next_url: str):
    """Handle login using SQLite."""
    from database import get_user_by_email
    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "auth/login.html",
            error="Invalid email or password.",
            form={"email": email},
        )

    session.clear()
    session["user_id"] = user["id"]
    session["display_name"] = user["display_name"]
    session["_csrf"] = _issue_csrf_token()
    return redirect(next_url)


# ------------------------------------------------------------------ #
# Handlers — dashboard                                                #
# ------------------------------------------------------------------ #

def _handle_dashboard():
    from database import (
        by_category_for_month,
        get_balance,
        recent_expenses,
        sum_for_month,
        sum_income_for_month,
    )

    user_id = session["user_id"]
    year, month = _parse_month(request.args.get("month"))
    prev_year, prev_month = _previous_month(year, month)

    return render_template(
        "dashboard.html",
        year=year,
        month=month,
        month_label=date(year, month, 1).strftime("%B %Y"),
        balance=get_balance(user_id),
        total_income_this_month=sum_income_for_month(user_id, year, month),
        total_expenses_this_month=sum_for_month(user_id, year, month),
        total_last_month=sum_for_month(user_id, prev_year, prev_month),
        by_category=by_category_for_month(user_id, year, month),
        recent=recent_expenses(user_id, limit=5),
    )


def _parse_month(raw: Optional[str]) -> tuple[int, int]:
    today = date.today()
    if not raw:
        return today.year, today.month
    try:
        parsed = datetime.strptime(raw, "%Y-%m")
        return parsed.year, parsed.month
    except ValueError:
        return today.year, today.month


def _previous_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


# ------------------------------------------------------------------ #
# Handlers — expenses                                                 #
# ------------------------------------------------------------------ #

def _empty_expense_form() -> dict:
    return {"amount": "", "category_id": "", "date": date.today().isoformat(), "note": ""}


def _parse_expense_form() -> tuple[Optional[dict], Optional[str]]:
    """Pull and validate the expense fields from ``request.form``."""
    try:
        amount_raw = (request.form.get("amount") or "").strip()
        amount = float(amount_raw)
    except ValueError:
        return None, "Amount must be a number."
    if amount <= 0:
        return None, "Amount must be greater than zero."

    category_raw = (request.form.get("category_id") or "").strip()
    if not category_raw.isdigit():
        return None, "Please choose a category."
    category_id = int(category_raw)

    date_raw = (request.form.get("date") or "").strip()
    try:
        datetime.strptime(date_raw, "%Y-%m-%d")
    except ValueError:
        return None, "Please enter a valid date (YYYY-MM-DD)."

    note = (request.form.get("note") or "").strip()
    if len(note) > 200:
        return None, "Note must be 200 characters or fewer."

    return (
        {
            "amount": amount,
            "category_id": category_id,
            "date": date_raw,
            "note": note or None,
        },
        None,
    )


def _categories_for_user(user_id: int):
    return get_db().execute(
        "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name",
        (user_id,),
    ).fetchall()


def _handle_create_expense():
    user_id = session["user_id"]
    parsed, error = _parse_expense_form()
    if error:
        return render_template(
            "expenses/new.html",
            error=error,
            form=_form_from_request(),
            categories=_categories_for_user(user_id),
        )

    # Reject categories not owned by the user.
    from database import get_category
    if get_category(user_id, parsed["category_id"]) is None:
        return render_template(
            "expenses/new.html",
            error="Please choose a category.",
            form=_form_from_request(),
            categories=_categories_for_user(user_id),
        )

    from database import create_expense
    create_expense(
        user_id=user_id,
        category_id=parsed["category_id"],
        amount=parsed["amount"],
        date=parsed["date"],
        note=parsed["note"],
    )
    flash("Expense added.", "success")
    return redirect(url_for("list_expenses"))


def _form_from_request() -> dict:
    return {
        "amount": request.form.get("amount", ""),
        "category_id": request.form.get("category_id", ""),
        "date": request.form.get("date", date.today().isoformat()),
        "note": request.form.get("note", ""),
    }


def _handle_edit_expense_form(expense_id: int):
    from database import get_expense
    user_id = session["user_id"]
    expense = get_expense(user_id, expense_id)
    if expense is None:
        abort(404)
    return render_template(
        "expenses/edit.html",
        expense=expense,
        categories=_categories_for_user(user_id),
    )


def _handle_update_expense(expense_id: int):
    from database import get_category, get_expense, update_expense
    user_id = session["user_id"]
    if get_expense(user_id, expense_id) is None:
        abort(404)

    parsed, error = _parse_expense_form()
    if error:
        # Re-render the edit form with the user's input preserved.
        return render_template(
            "expenses/edit.html",
            error=error,
            expense={
                "id": expense_id,
                "amount": request.form.get("amount", ""),
                "category_id": request.form.get("category_id", ""),
                "date": request.form.get("date", ""),
                "note": request.form.get("note", ""),
            },
            categories=_categories_for_user(user_id),
        )

    if get_category(user_id, parsed["category_id"]) is None:
        return render_template(
            "expenses/edit.html",
            error="That category doesn't exist.",
            expense={
                "id": expense_id,
                "amount": request.form.get("amount", ""),
                "category_id": request.form.get("category_id", ""),
                "date": request.form.get("date", ""),
                "note": request.form.get("note", ""),
            },
            categories=_categories_for_user(user_id),
        )

    update_expense(
        user_id=user_id,
        expense_id=expense_id,
        category_id=parsed["category_id"],
        amount=parsed["amount"],
        date=parsed["date"],
        note=parsed["note"],
    )
    flash("Expense updated.", "success")
    return redirect(url_for("list_expenses"))


def _handle_delete_expense(expense_id: int):
    from database import delete_expense, get_expense
    user_id = session["user_id"]
    if get_expense(user_id, expense_id) is None:
        abort(404)
    delete_expense(user_id, expense_id)
    flash("Expense deleted.", "success")
    return redirect(url_for("list_expenses"))


def _handle_list_expenses():
    from database import list_expenses, sum_expenses
    user_id = session["user_id"]
    date_from = _normalize_date(request.args.get("from"))
    date_to = _normalize_date(request.args.get("to"))
    category_raw = (request.args.get("category") or "").strip()
    category_id = int(category_raw) if category_raw.isdigit() else None
    search = (request.args.get("search") or "").strip()
    sort = (request.args.get("sort") or "date-desc").strip()

    expenses = list_expenses(user_id, date_from, date_to, category_id)

    # Apply search filter
    if search:
        expenses = [e for e in expenses if search.lower() in (e["note"] or "").lower()]

    # Apply sorting
    if sort == "date-asc":
        expenses = sorted(expenses, key=lambda x: (x["date"], x["id"]))
    elif sort == "amount-desc":
        expenses = sorted(expenses, key=lambda x: x["amount"], reverse=True)
    elif sort == "amount-asc":
        expenses = sorted(expenses, key=lambda x: x["amount"])
    else:  # date-desc (default)
        expenses = sorted(expenses, key=lambda x: (x["date"], x["id"]), reverse=True)

    return render_template(
        "expenses/list.html",
        expenses=expenses,
        total=sum_expenses(user_id, date_from, date_to, category_id),
        categories=_categories_for_user(user_id),
        filters={
            "from": date_from or "",
            "to": date_to or "",
            "category": category_raw,
            "search": search,
            "sort": sort,
        },
    )


def _normalize_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


# ------------------------------------------------------------------ #
# Handlers — categories                                               #
# ------------------------------------------------------------------ #

def _handle_list_categories():
    from database import category_in_use, get_categories
    user_id = session["user_id"]
    categories = get_categories(user_id)
    annotated = [
        {"id": c["id"], "name": c["name"], "in_use": category_in_use(c["id"])}
        for c in categories
    ]
    return render_template(
        "categories/list.html", categories=annotated
    )


def _handle_create_category():
    from database import create_category
    name = (request.form.get("name") or "").strip()
    error = _validate_category_name(name)
    if error:
        return render_template(
            "categories/new.html",
            error=error,
            form={"name": name},
        )
    try:
        create_category(session["user_id"], name)
    except Exception:  # IntegrityError on duplicate
        return render_template(
            "categories/new.html",
            error="You already have a category with that name.",
            form={"name": name},
        )
    flash(f"Category “{name}” added.", "success")
    return redirect(url_for("list_categories"))


def _handle_edit_category_form(category_id: int):
    from database import get_category
    category = get_category(session["user_id"], category_id)
    if category is None:
        abort(404)
    return render_template(
        "categories/edit.html",
        category=category,
    )


def _handle_update_category(category_id: int):
    from database import get_category, update_category
    user_id = session["user_id"]
    if get_category(user_id, category_id) is None:
        abort(404)
    name = (request.form.get("name") or "").strip()
    error = _validate_category_name(name)
    if error:
        return render_template(
            "categories/edit.html",
            error=error,
            category={"id": category_id, "name": name},
        )
    try:
        update_category(user_id, category_id, name)
    except Exception:
        return render_template(
            "categories/edit.html",
            error="You already have a category with that name.",
            category={"id": category_id, "name": name},
        )
    flash("Category updated.", "success")
    return redirect(url_for("list_categories"))


def _handle_delete_category(category_id: int):
    from database import category_in_use, delete_category, get_category
    user_id = session["user_id"]
    category = get_category(user_id, category_id)
    if category is None:
        abort(404)
    if category_in_use(category_id):
        flash(
            f"Can't delete “{category['name']}” — it's used by an expense. "
            f"Reassign those expenses first.",
            "error",
        )
        return redirect(url_for("list_categories"))
    delete_category(user_id, category_id)
    flash("Category deleted.", "success")
    return redirect(url_for("list_categories"))


def _validate_category_name(name: str) -> Optional[str]:
    if not name:
        return "Please enter a category name."
    if len(name) > 40:
        return "Category name must be 40 characters or fewer."
    return None


# ------------------------------------------------------------------ #
# Handlers — income                                                   #
# ------------------------------------------------------------------ #

def _empty_income_form() -> dict:
    return {"amount": "", "category_id": "", "date": date.today().isoformat(), "note": ""}


def _parse_income_form() -> tuple[Optional[dict], Optional[str]]:
    """Pull and validate the income fields from ``request.form``."""
    try:
        amount_raw = (request.form.get("amount") or "").strip()
        amount = float(amount_raw)
    except ValueError:
        return None, "Amount must be a number."
    if amount <= 0:
        return None, "Amount must be greater than zero."

    category_raw = (request.form.get("category_id") or "").strip()
    if not category_raw.isdigit():
        return None, "Please choose a category."
    category_id = int(category_raw)

    date_raw = (request.form.get("date") or "").strip()
    try:
        datetime.strptime(date_raw, "%Y-%m-%d")
    except ValueError:
        return None, "Please enter a valid date (YYYY-MM-DD)."

    note = (request.form.get("note") or "").strip()
    if len(note) > 200:
        return None, "Note must be 200 characters or fewer."

    return (
        {
            "amount": amount,
            "category_id": category_id,
            "date": date_raw,
            "note": note or None,
        },
        None,
    )


def _handle_create_income():
    user_id = session["user_id"]
    parsed, error = _parse_income_form()
    if error:
        return render_template(
            "income/new.html",
            error=error,
            form=_form_from_request_income(),
            categories=_categories_for_user(user_id),
        )

    from database import get_category
    if get_category(user_id, parsed["category_id"]) is None:
        return render_template(
            "income/new.html",
            error="Please choose a category.",
            form=_form_from_request_income(),
            categories=_categories_for_user(user_id),
        )

    from database import create_income
    create_income(
        user_id=user_id,
        category_id=parsed["category_id"],
        amount=parsed["amount"],
        date=parsed["date"],
        note=parsed["note"],
    )
    flash("Income added.", "success")
    return redirect(url_for("list_income"))


def _form_from_request_income() -> dict:
    return {
        "amount": request.form.get("amount", ""),
        "category_id": request.form.get("category_id", ""),
        "date": request.form.get("date", date.today().isoformat()),
        "note": request.form.get("note", ""),
    }


def _handle_edit_income_form(income_id: int):
    from database import get_income
    user_id = session["user_id"]
    income = get_income(user_id, income_id)
    if income is None:
        abort(404)
    return render_template(
        "income/edit.html",
        income=income,
        categories=_categories_for_user(user_id),
    )


def _handle_update_income(income_id: int):
    from database import get_category, get_income, update_income
    user_id = session["user_id"]
    if get_income(user_id, income_id) is None:
        abort(404)

    parsed, error = _parse_income_form()
    if error:
        return render_template(
            "income/edit.html",
            error=error,
            income={
                "id": income_id,
                "amount": request.form.get("amount", ""),
                "category_id": request.form.get("category_id", ""),
                "date": request.form.get("date", ""),
                "note": request.form.get("note", ""),
            },
            categories=_categories_for_user(user_id),
        )

    if get_category(user_id, parsed["category_id"]) is None:
        return render_template(
            "income/edit.html",
            error="That category doesn't exist.",
            income={
                "id": income_id,
                "amount": request.form.get("amount", ""),
                "category_id": request.form.get("category_id", ""),
                "date": request.form.get("date", ""),
                "note": request.form.get("note", ""),
            },
            categories=_categories_for_user(user_id),
        )

    update_income(
        user_id=user_id,
        income_id=income_id,
        category_id=parsed["category_id"],
        amount=parsed["amount"],
        date=parsed["date"],
        note=parsed["note"],
    )
    flash("Income updated.", "success")
    return redirect(url_for("list_income"))


def _handle_delete_income(income_id: int):
    from database import delete_income, get_income
    user_id = session["user_id"]
    if get_income(user_id, income_id) is None:
        abort(404)
    delete_income(user_id, income_id)
    flash("Income deleted.", "success")
    return redirect(url_for("list_income"))


def _handle_list_income():
    from database import list_income, sum_income
    user_id = session["user_id"]
    date_from = _normalize_date(request.args.get("from"))
    date_to = _normalize_date(request.args.get("to"))
    category_raw = (request.args.get("category") or "").strip()
    category_id = int(category_raw) if category_raw.isdigit() else None

    return render_template(
        "income/list.html",
        income=list_income(user_id, date_from, date_to, category_id),
        total=sum_income(user_id, date_from, date_to, category_id),
        categories=_categories_for_user(user_id),
        filters={
            "from": date_from or "",
            "to": date_to or "",
            "category": category_raw,
        },
    )


# ------------------------------------------------------------------ #
# Handlers — budgets                                                  #
# ------------------------------------------------------------------ #

def _handle_budgets():
    from database import get_budgets_for_month
    user_id = session["user_id"]
    year, month = _parse_month(request.args.get("month"))
    month_str = f"{year:04d}-{month:02d}"

    return render_template(
        "budgets/list.html",
        year=year,
        month=month,
        month_label=date(year, month, 1).strftime("%B %Y"),
        month_str=month_str,
        budgets=get_budgets_for_month(user_id, month_str),
        categories=_categories_for_user(user_id),
    )


def _handle_create_budget():
    from database import create_budget
    user_id = session["user_id"]
    category_raw = (request.form.get("category_id") or "").strip()
    amount_raw = (request.form.get("amount") or "").strip()
    month = (request.form.get("month") or "").strip()

    if not category_raw.isdigit():
        flash("Please choose a category.", "error")
        return redirect(url_for("list_budgets"))
    category_id = int(category_raw)

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash("Amount must be a positive number.", "error")
        return redirect(url_for("list_budgets"))

    if not month or len(month) != 7 or month[4] != '-':
        flash("Invalid month format.", "error")
        return redirect(url_for("list_budgets"))

    try:
        create_budget(user_id, category_id, amount, month)
        flash("Budget set.", "success")
    except Exception:
        flash("Failed to set budget.", "error")

    return redirect(url_for("list_budgets", month=month))


def _handle_delete_budget(budget_id: int):
    from database import delete_budget, get_budgets_for_month
    user_id = session["user_id"]
    delete_budget(user_id, budget_id)
    flash("Budget deleted.", "success")

    # Get month from request args to redirect back to the same month
    month = request.args.get("month", "")
    return redirect(url_for("list_budgets", month=month))


# ------------------------------------------------------------------ #
# Error handlers                                                      #
# ------------------------------------------------------------------ #

def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", code=400, message=str(e.description)), 400

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500, message="Something went wrong."), 500


# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=DEFAULT_PORT, debug=True)