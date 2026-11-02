"""Category CRUD tests."""
import re


def _csrf(html: bytes) -> str:
    return re.search(rb'name="_csrf" value="([^"]+)"', html).group(1).decode()


def test_defaults_seeded_on_register(client):
    resp = client.get("/register")
    client.post(
        "/register",
        data={
            "name": "Eve",
            "email": "eve@example.com",
            "password": "password123",
            "confirm": "password123",
            "_csrf": _csrf(resp.data),
        },
    )
    resp = client.get("/categories")
    assert b"Food" in resp.data
    assert b"Travel" in resp.data
    assert b"Bills" in resp.data
    assert b"Shopping" in resp.data
    assert b"Other" in resp.data


def test_create_category(logged_in):
    resp = logged_in.get("/categories/new")
    resp = logged_in.post(
        "/categories/new",
        data={"name": "Groceries", "_csrf": _csrf(resp.data)},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    resp = logged_in.get("/categories")
    assert b"Groceries" in resp.data


def test_duplicate_category_rejected(logged_in):
    for _ in range(2):
        resp = logged_in.get("/categories/new")
        logged_in.post(
            "/categories/new",
            data={"name": "Subscriptions", "_csrf": _csrf(resp.data)},
        )
    resp = logged_in.get("/categories/new")
    resp = logged_in.post(
        "/categories/new",
        data={"name": "Subscriptions", "_csrf": _csrf(resp.data)},
    )
    assert b"already have a category" in resp.data


def test_edit_category(logged_in):
    # Add one
    resp = logged_in.get("/categories/new")
    logged_in.post(
        "/categories/new",
        data={"name": "Original name", "_csrf": _csrf(resp.data)},
    )
    # Get its id by scraping from the list page - find the specific category we just added
    resp = logged_in.get("/categories")
    match = re.search(rb'Original name.*?/categories/(\d+)/edit', resp.data, re.DOTALL)
    cat_id = int(match.group(1).decode())

    resp = logged_in.get(f"/categories/{cat_id}/edit")
    token = _csrf(resp.data)
    resp = logged_in.post(
        f"/categories/{cat_id}/edit",
        data={"name": "Updated name", "_csrf": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # Verify the name was updated
    resp = logged_in.get("/categories")
    assert b"Updated name" in resp.data


def test_delete_unused_category_succeeds(logged_in):
    resp = logged_in.get("/categories/new")
    logged_in.post(
        "/categories/new",
        data={"name": "Throwaway", "_csrf": _csrf(resp.data)},
    )
    resp = logged_in.get("/categories")
    cat_id = int(re.search(rb'/categories/(\d+)/delete', resp.data).group(1).decode())
    token = _csrf(resp.data)
    resp = logged_in.post(
        f"/categories/{cat_id}/delete", data={"_csrf": token}, follow_redirects=False
    )
    assert resp.status_code == 302
    assert b"Category deleted" in logged_in.get("/categories").data


def test_delete_in_use_category_blocked(logged_in, first_category_id):
    # Add an expense that uses the first category
    resp = logged_in.get("/expenses/new")
    token = _csrf(resp.data)
    logged_in.post(
        "/expenses/new",
        data={
            "amount": "100",
            "category_id": str(first_category_id),
            "date": "2026-07-15",
            "note": "test",
            "_csrf": token,
        },
    )
    # Now try to delete that category
    resp = logged_in.get("/categories")
    token = _csrf(resp.data)
    resp = logged_in.post(
        f"/categories/{first_category_id}/delete",
        data={"_csrf": token},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    body = logged_in.get("/categories").data
    assert b"used by an expense" in body
