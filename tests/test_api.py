# tests/test_api.py
# -----------------------------------------------------------------------------
# Smoke tests for the REST API, run with:  pytest
#
# Strategy: point DATABASE_URL at an in-memory SQLite database BEFORE importing
# the app, then use Flask's built-in test client - no real server, no real DB
# file, so tests are fast and leave nothing behind.
# -----------------------------------------------------------------------------

import os
import sys

# Make sure the project root is importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Must be set before "from app import app" - app.py reads it at import time.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest

from app import app, db


@pytest.fixture()
def client():
    """A fresh test client with empty tables for every single test."""
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()    # wipe anything a previous test created
        db.create_all()
    with app.test_client() as client:
        yield client


def register_and_get_token(client):
    """Helper: create a demo account and return its JWT."""
    res = client.post("/api/register", json={
        "name": "Test User",
        "email": "test@example.com",
        "password": "secret123",
    })
    assert res.status_code == 201
    return res.get_json()["token"]


# --- Health -------------------------------------------------------------------

def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


# --- Auth ---------------------------------------------------------------------

def test_register_returns_token(client):
    token = register_and_get_token(client)
    assert isinstance(token, str) and len(token) > 20  # looks like a JWT


def test_register_duplicate_email_rejected(client):
    register_and_get_token(client)
    res = client.post("/api/register", json={
        "name": "Copycat", "email": "test@example.com", "password": "secret123",
    })
    assert res.status_code == 400


def test_register_short_password_rejected(client):
    res = client.post("/api/register", json={
        "name": "X", "email": "x@example.com", "password": "123",
    })
    assert res.status_code == 400


def test_login_works_and_wrong_password_is_401(client):
    register_and_get_token(client)
    ok = client.post("/api/login", json={
        "email": "test@example.com", "password": "secret123",
    })
    assert ok.status_code == 200
    assert "token" in ok.get_json()

    bad = client.post("/api/login", json={
        "email": "test@example.com", "password": "wrong",
    })
    assert bad.status_code == 401


# --- Reports --------------------------------------------------------------------

GOOD_REPORT = {
    "title": "Flooded underpass",
    "description": "Water 2ft deep",
    "category": "flood",
    "severity": "high",
    "lat": 28.62,
    "lng": 77.36,
}


def test_create_report_requires_token(client):
    res = client.post("/api/reports", json=GOOD_REPORT)   # no Authorization header
    assert res.status_code == 401


def test_create_and_list_report(client):
    token = register_and_get_token(client)
    res = client.post("/api/reports", json=GOOD_REPORT,
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    created = res.get_json()
    assert created["category"] == "flood"
    assert created["reporter"] == "Test User"

    # It should now appear in the public list.
    listing = client.get("/api/reports")
    assert listing.status_code == 200
    assert len(listing.get_json()) == 1


def test_create_report_invalid_category_rejected(client):
    token = register_and_get_token(client)
    bad = dict(GOOD_REPORT, category="alien-invasion")
    res = client.post("/api/reports", json=bad,
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400


def test_create_report_bad_coordinates_rejected(client):
    token = register_and_get_token(client)
    bad = dict(GOOD_REPORT, lat="not-a-number")
    res = client.post("/api/reports", json=bad,
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
