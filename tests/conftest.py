"""Shared pytest fixtures.

Each test gets a fresh app backed by a temp SQLite file so tests never
touch the real ``database/expense_tracker.db``.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Create a temp directory and a per-process DB path BEFORE the app module
# is imported anywhere. The app's app.config["DATABASE"] reads DB_PATH at
# import time, so we have to set the env var first.
_test_db_dir = tempfile.mkdtemp(prefix="spendly-test-")
_test_db_path = os.path.join(_test_db_dir, "expense_tracker.db")
os.environ["SPENDLY_TEST_DB"] = _test_db_path

# Force SQLite mode for tests
os.environ["DATABASE_MODE"] = "sqlite"


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config.update(TESTING=True)
    yield application

    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_user(app):
    """Register a user and return a dict with their credentials and ids."""
    from werkzeug.security import generate_password_hash

    with app.app_context():
        from database import create_user

        user_id = create_user(
            "demo@example.com", "Demo User", generate_password_hash("password123")
        )
    return {
        "id": user_id,
        "email": "demo@example.com",
        "name": "Demo User",
        "password": "password123",
    }


@pytest.fixture
def logged_in(client, seed_user):
    """A client with the demo user already authenticated."""
    import re

    resp = client.get("/login")
    assert resp.status_code == 200
    token = re.search(rb'name="_csrf" value="([^"]+)"', resp.data).group(1).decode()
    resp = client.post(
        "/login",
        data={
            "email": seed_user["email"],
            "password": seed_user["password"],
            "_csrf": token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    return client


@pytest.fixture
def first_category_id(app, seed_user):
    with app.app_context():
        from database import get_categories

        cats = get_categories(seed_user["id"])
        return cats[0]["id"]
