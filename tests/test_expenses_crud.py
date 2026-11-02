"""Expense CRUD tests: add, edit, delete, ownership."""
import re


def _csrf(html: bytes) -> str:
    return re.search(rb'name="_csrf" value="([^"]+)"', html).group(1).decode()


def _add_expense(client, category_id, amount="250", date="2026-07-15", note="Lunch"):
    resp = client.get("/expenses/new")
    token = _csrf(resp.data)
    return client.post(
        "/expenses/new",
        data={
            "amount": amount,
            "category_id": str(category_id),
            "date": date,
            "note": note,
            "_csrf": token,
        },
        follow_redirects=False,
    )


def test_add_expense(logged_in, first_category_id):
    resp = _add_expense(logged_in, first_category_id)
    assert resp.status_code == 302
    body = logged_in.get("/expenses").data
    assert b"Lunch" in body
    assert b"250" in body


def test_add_expense_rejects_zero_amount(logged_in, first_category_id):
    resp = logged_in.get("/expenses/new")
    token = _csrf(resp.data)
    resp = logged_in.post(
        "/expenses/new",
        data={
            "amount": "0",
            "category_id": str(first_category_id),
            "date": "2026-07-15",
            "note": "",
            "_csrf": token,
        },
    )
    assert b"greater than zero" in resp.data


def test_add_expense_rejects_bad_date(logged_in, first_category_id):
    resp = logged_in.get("/expenses/new")
    token = _csrf(resp.data)
    resp = logged_in.post(
        "/expenses/new",
        data={
            "amount": "100",
            "category_id": str(first_category_id),
            "date": "not-a-date",
            "note": "",
            "_csrf": token,
        },
    )
    assert b"valid date" in resp.data


def test_add_expense_rejects_foreign_category(logged_in):
    # Pick a category id that does not belong to the demo user.
    resp = _add_expense(logged_in, 9999)
    assert b"Please choose a category" in resp.data


def test_edit_expense(logged_in, first_category_id):
    _add_expense(logged_in, first_category_id, amount="50", note="Coffee")
    # Find the expense id
    body = logged_in.get("/expenses").data
    m = re.search(rb'/expenses/(\d+)/edit', body)
    exp_id = int(m.group(1).decode())

    resp = logged_in.get(f"/expenses/{exp_id}/edit")
    token = _csrf(resp.data)
    resp = logged_in.post(
        f"/expenses/{exp_id}/edit",
        data={
            "amount": "75",
            "category_id": str(first_category_id),
            "date": "2026-07-15",
            "note": "Bigger coffee",
            "_csrf": token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    body = logged_in.get("/expenses").data
    assert b"Bigger coffee" in body
    assert b"75" in body


def test_delete_expense(logged_in, first_category_id):
    _add_expense(logged_in, first_category_id, note="Throwaway")
    body = logged_in.get("/expenses").data
    exp_id = int(re.search(rb'/expenses/(\d+)/delete', body).group(1).decode())

    token = _csrf(logged_in.get("/expenses").data)
    resp = logged_in.post(
        f"/expenses/{exp_id}/delete", data={"_csrf": token}, follow_redirects=False
    )
    assert resp.status_code == 302
    body = logged_in.get("/expenses").data
    assert b"Throwaway" not in body


def test_cross_user_access_returns_404(app, logged_in, first_category_id):
    # Create a second user and an expense under them.
    from werkzeug.security import generate_password_hash

    with app.app_context():
        from database import create_expense, create_user, get_categories

        other_id = create_user("other@example.com", "Other", generate_password_hash("password123"))
        other_cat = get_categories(other_id)[0]["id"]
        other_exp = create_expense(other_id, other_cat, 500, "2026-07-10", "Other user")

    # Logged-in user tries to access other user's expense.
    resp = logged_in.get(f"/expenses/{other_exp}/edit")
    assert resp.status_code == 404

    token = _csrf(logged_in.get("/dashboard").data)
    resp = logged_in.post(
        f"/expenses/{other_exp}/delete", data={"_csrf": token}
    )
    assert resp.status_code == 404


def test_csrf_required_on_post(client, seed_user, first_category_id):
    # Log in by setting the session directly, then submit a POST without a CSRF token.
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user["id"]
        sess["display_name"] = seed_user["name"]
    resp = client.post(
        "/expenses/new",
        data={
            "amount": "10",
            "category_id": str(first_category_id),
            "date": "2026-07-15",
            "note": "no csrf",
        },
    )
    assert resp.status_code == 400
