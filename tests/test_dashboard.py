"""Dashboard tests."""
import re
from datetime import date


def _csrf(html: bytes) -> str:
    return re.search(rb'name="_csrf" value="([^"]+)"', html).group(1).decode()


def _add(client, category_id, amount, date_str, note=""):
    resp = client.get("/expenses/new")
    client.post(
        "/expenses/new",
        data={
            "amount": amount,
            "category_id": str(category_id),
            "date": date_str,
            "note": note,
            "_csrf": _csrf(resp.data),
        },
    )


def test_dashboard_renders_when_logged_in(logged_in):
    resp = logged_in.get("/dashboard")
    assert resp.status_code == 200
    today = date.today()
    assert today.strftime("%B %Y").encode() in resp.data


def test_dashboard_empty_state(logged_in):
    body = logged_in.get("/dashboard").data
    assert b"No expenses in" in body
    assert b"Add your first expense" in body


def test_dashboard_totals(logged_in, first_category_id):
    today = date.today()
    this_month = today.strftime("%Y-%m-15")
    last_month_date = today.replace(day=15)
    if last_month_date.month == 1:
        last_month_date = last_month_date.replace(year=last_month_date.year - 1, month=12)
    else:
        last_month_date = last_month_date.replace(month=last_month_date.month - 1)
    last_month = last_month_date.strftime("%Y-%m-15")

    _add(logged_in, first_category_id, "500", this_month, "this")
    _add(logged_in, first_category_id, "200", last_month, "last")

    body = logged_in.get("/dashboard").data
    # Both totals should be present (currency-formatted).
    assert b"500" in body
    assert b"200" in body


def test_dashboard_custom_month(logged_in, first_category_id):
    _add(logged_in, first_category_id, "999", "2026-03-15", "march")
    body = logged_in.get("/dashboard?month=2026-03").data
    assert b"999" in body
    assert b"March 2026" in body


def test_dashboard_chart_data_when_expenses_present(logged_in, first_category_id):
    _add(logged_in, first_category_id, "300", date.today().strftime("%Y-%m-15"), "now")
    body = logged_in.get("/dashboard").data
    # Chart.js script block with the labels/values JSON.
    assert b"category-chart" in body
    assert b"new Chart" in body
