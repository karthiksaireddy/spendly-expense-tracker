"""Auth tests: register, login, logout, validation, redirects."""
import re


def _csrf(html: bytes) -> str:
    return re.search(rb'name="_csrf" value="([^"]+)"', html).group(1).decode()


def test_register_creates_user_and_logs_in(client):
    resp = client.get("/register")
    token = _csrf(resp.data)

    resp = client.post(
        "/register",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "password123",
            "confirm": "password123",
            "_csrf": token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")

    # Subsequent request sees the new user in the nav.
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Alice" in resp.data


def test_register_duplicate_email_rejected(client):
    for _ in range(2):
        resp = client.get("/register")
        client.post(
            "/register",
            data={
                "name": "Bob",
                "email": "bob@example.com",
                "password": "password123",
                "confirm": "password123",
                "_csrf": _csrf(resp.data),
            },
        )
    resp = client.post(
        "/register",
        data={
            "name": "Bob 2",
            "email": "bob@example.com",
            "password": "password123",
            "confirm": "password123",
            "_csrf": _csrf(client.get("/register").data),
        },
    )
    assert b"already exists" in resp.data


def test_register_password_too_short(client):
    resp = client.get("/register")
    resp = client.post(
        "/register",
        data={
            "name": "Carol",
            "email": "carol@example.com",
            "password": "short",
            "confirm": "short",
            "_csrf": _csrf(resp.data),
        },
    )
    assert b"at least 8 characters" in resp.data


def test_register_mismatched_confirm(client):
    resp = client.get("/register")
    resp = client.post(
        "/register",
        data={
            "name": "Dan",
            "email": "dan@example.com",
            "password": "password123",
            "confirm": "different",
            "_csrf": _csrf(resp.data),
        },
    )
    assert b"do not match" in resp.data


def test_login_then_logout(logged_in):
    # logged_in already authenticated
    resp = logged_in.get("/dashboard")
    assert resp.status_code == 200

    # Fetch CSRF from any page, then POST to /logout
    resp = logged_in.get("/dashboard")
    token = _csrf(resp.data)
    resp = logged_in.post("/logout", data={"_csrf": token})
    assert resp.status_code == 302

    # After logout, dashboard redirects to login.
    resp = logged_in.get("/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_bad_password(client, seed_user):
    resp = client.get("/login")
    resp = client.post(
        "/login",
        data={
            "email": seed_user["email"],
            "password": "wrong",
            "_csrf": _csrf(resp.data),
        },
    )
    assert b"Invalid email or password" in resp.data


def test_protected_route_redirects_anonymous(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
