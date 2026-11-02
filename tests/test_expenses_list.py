"""Expense list + filter tests."""
import re


def _csrf(html: bytes) -> str:
    return re.search(rb'name="_csrf" value="([^"]+)"', html).group(1).decode()


def _add(client, category_id, amount, date, note=""):
    resp = client.get("/expenses/new")
    client.post(
        "/expenses/new",
        data={
            "amount": amount,
            "category_id": str(category_id),
            "date": date,
            "note": note,
            "_csrf": _csrf(resp.data),
        },
    )


def test_list_ordered_newest_first(logged_in, first_category_id):
    _add(logged_in, first_category_id, "100", "2026-07-10", "first")
    _add(logged_in, first_category_id, "200", "2026-07-15", "second")
    body = logged_in.get("/expenses").data
    # The newer expense should appear before the older one in the rendered HTML.
    assert body.index(b"second") < body.index(b"first")


def test_filter_by_date_range(logged_in, first_category_id):
    _add(logged_in, first_category_id, "100", "2026-07-05", "jul5")
    _add(logged_in, first_category_id, "200", "2026-07-15", "jul15")
    _add(logged_in, first_category_id, "300", "2026-07-25", "jul25")
    body = logged_in.get("/expenses?from=2026-07-10&to=2026-07-20").data
    assert b"jul15" in body
    assert b"jul5" not in body
    assert b"jul25" not in body


def test_filter_by_category(logged_in, app, seed_user):
    from database import create_category, get_categories

    with app.app_context():
        cat_a = get_categories(seed_user["id"])[0]["id"]
        cat_b = create_category(seed_user["id"], "Utilities")

    _add(logged_in, cat_a, "100", "2026-07-15", "in A")
    _add(logged_in, cat_b, "200", "2026-07-15", "in B")
    body = logged_in.get(f"/expenses?category={cat_b}").data
    assert b"in B" in body
    assert b"in A" not in body


def test_combined_filter(logged_in, first_category_id):
    _add(logged_in, first_category_id, "100", "2026-07-05", "out-of-range")
    _add(logged_in, first_category_id, "200", "2026-07-15", "in-range")
    body = logged_in.get(
        f"/expenses?from=2026-07-10&to=2026-07-20&category={first_category_id}"
    ).data
    assert b"in-range" in body
    assert b"out-of-range" not in body


def test_total_reflects_filter(logged_in, first_category_id):
    _add(logged_in, first_category_id, "100", "2026-07-05", "old")
    _add(logged_in, first_category_id, "250", "2026-07-15", "new")
    body = logged_in.get("/expenses?from=2026-07-10&to=2026-07-20").data
    assert b"250" in body


def test_invalid_filter_silently_ignored(logged_in, first_category_id):
    _add(logged_in, first_category_id, "100", "2026-07-15", "lone")
    # Bad date strings and a non-numeric category should not crash and
    # should fall back to the unfiltered list.
    body = logged_in.get(
        "/expenses?from=garbage&to=alsogarbage&category=banana"
    ).data
    assert b"lone" in body
