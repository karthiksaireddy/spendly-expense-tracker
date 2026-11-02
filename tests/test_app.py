"""Smoke test: app boots and the landing page renders."""
from app import create_app


def test_app_boots():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Spendly" in resp.data


def test_404_renders_error_page(client):
    resp = client.get("/this-does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data
