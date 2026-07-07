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


# --- Geo features (iteration 3) --------------------------------------------------

def test_haversine_known_distance():
    """Sanity-check the formula: Noida Sector 62 to Connaught Place is ~16 km."""
    from serverless.notify_lambda import haversine_km
    d = haversine_km(28.6272, 77.3649, 28.6315, 77.2167)
    assert 14 < d < 17


def test_nearby_requires_lat_lng(client):
    res = client.get("/api/reports/nearby")           # no query params at all
    assert res.status_code == 400


def test_nearby_filters_by_radius(client):
    token = register_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    # One report right here, one ~30 km away.
    client.post("/api/reports", json=GOOD_REPORT, headers=headers)
    far = dict(GOOD_REPORT, title="Far away fire", lat=28.90, lng=77.60)
    client.post("/api/reports", json=far, headers=headers)

    res = client.get("/api/reports/nearby?lat=28.62&lng=77.36&radius_km=5")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 1                          # only the close one
    assert data["reports"][0]["title"] == "Flooded underpass"
    assert data["reports"][0]["distance_km"] <= 5


def test_create_report_returns_alerted_users(client):
    # This user's home is AT the incident location -> must be alerted.
    res = client.post("/api/register", json={
        "name": "Near Resident", "email": "near@example.com",
        "password": "secret123", "home_lat": 28.62, "home_lng": 77.36,
    })
    token = res.get_json()["token"]

    # A second user far away (Mumbai) -> must NOT be alerted.
    client.post("/api/register", json={
        "name": "Far Resident", "email": "far@example.com",
        "password": "secret123", "home_lat": 19.07, "home_lng": 72.87,
    })

    res = client.post("/api/reports", json=GOOD_REPORT,
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 201
    alerted = res.get_json()["alerted_users"]
    assert [u["name"] for u in alerted] == ["Near Resident"]
    assert alerted[0]["distance_km"] < 1


def test_lambda_handler_with_sample_event():
    """The exact event we document in serverless/README.md must work."""
    from serverless.notify_lambda import lambda_handler
    result = lambda_handler({"lat": 28.61, "lng": 77.36, "radius_km": 5}, None)
    assert result["count"] >= 1                        # demo users live nearby
    assert result["count"] == len(result["alerted_users"])


# --- Hardening (v4) ---------------------------------------------------------------

def test_create_report_overlong_title_rejected(client):
    token = register_and_get_token(client)
    bad = dict(GOOD_REPORT, title="x" * 121)           # cap is 120
    res = client.post("/api/reports", json=bad,
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400


def test_create_report_reports_notify_source(client):
    token = register_and_get_token(client)
    res = client.post("/api/reports", json=GOOD_REPORT,
                      headers={"Authorization": f"Bearer {token}"})
    # Locally NOTIFY_LAMBDA is unset, so the imported function must be used.
    assert res.get_json()["notify_source"] == "local"


def test_auth_rate_limit_kicks_in():
    """11th login attempt inside a minute -> 429. Uses TESTING=False because
    the limiter is deliberately switched off for the rest of the suite."""
    from app import app, _attempts
    _attempts.clear()
    app.config["TESTING"] = False
    try:
        with app.test_client() as client:
            for _ in range(10):
                client.post("/api/login", json={"email": "x@example.com",
                                                "password": "wrong"})
            res = client.post("/api/login", json={"email": "x@example.com",
                                                  "password": "wrong"})
            assert res.status_code == 429
    finally:
        app.config["TESTING"] = True
        _attempts.clear()


# --- Crowd-verification voting (v5) ---------------------------------------------

def make_user_token(client, email, home_lat=28.62, home_lng=77.36):
    """Register a distinct user (each vote must come from a different account)."""
    res = client.post("/api/register", json={
        "name": email.split("@")[0], "email": email, "password": "secret123",
        "home_lat": home_lat, "home_lng": home_lng,
    })
    assert res.status_code == 201
    return res.get_json()["token"]


def create_a_report(client):
    """Create one report and return its id."""
    token = register_and_get_token(client)
    res = client.post("/api/reports", json=GOOD_REPORT,
                      headers={"Authorization": f"Bearer {token}"})
    return res.get_json()["id"]


def test_vote_requires_token(client):
    rid = create_a_report(client)
    res = client.post(f"/api/reports/{rid}/vote", json={"still_there": False})
    assert res.status_code == 401


def test_vote_on_missing_report_is_404(client):
    token = register_and_get_token(client)
    res = client.post("/api/reports/999/vote", json={"still_there": True},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_vote_bad_body_is_400(client):
    rid = create_a_report(client)
    token = make_user_token(client, "voter@example.com")
    res = client.post(f"/api/reports/{rid}/vote", json={"still_there": "maybe"},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400


def test_single_gone_vote_does_not_remove(client):
    """One vote is below the minimum, so the report survives."""
    rid = create_a_report(client)
    token = make_user_token(client, "v1@example.com")
    res = client.post(f"/api/reports/{rid}/vote", json={"still_there": False},
                      headers={"Authorization": f"Bearer {token}"})
    body = res.get_json()
    assert body["removed"] is False
    assert body["votes_gone"] == 1
    assert len(client.get("/api/reports").get_json()) == 1   # still listed


def test_majority_gone_removes_report(client):
    """Enough votes with a 'gone' majority -> the report is auto-removed."""
    from app import VOTES_TO_RESOLVE
    rid = create_a_report(client)
    last = None
    for i in range(VOTES_TO_RESOLVE):
        token = make_user_token(client, f"gone{i}@example.com")
        last = client.post(f"/api/reports/{rid}/vote", json={"still_there": False},
                           headers={"Authorization": f"Bearer {token}"}).get_json()
    assert last["removed"] is True
    assert client.get("/api/reports").get_json() == []        # gone from the map


def test_still_here_majority_keeps_report(client):
    """Meets the vote minimum but the majority say it's still here -> kept."""
    from app import VOTES_TO_RESOLVE
    rid = create_a_report(client)
    # One "gone" vote, then enough "still here" votes to outnumber it.
    client.post(f"/api/reports/{rid}/vote", json={"still_there": False},
                headers={"Authorization": f"Bearer {make_user_token(client, 'g@example.com')}"})
    for i in range(VOTES_TO_RESOLVE):
        client.post(f"/api/reports/{rid}/vote", json={"still_there": True},
                    headers={"Authorization": f"Bearer {make_user_token(client, f'stay{i}@example.com')}"})
    assert len(client.get("/api/reports").get_json()) == 1


def test_revote_updates_not_duplicates(client):
    """Voting twice as the same user changes the vote instead of adding one."""
    rid = create_a_report(client)
    token = make_user_token(client, "changer@example.com")
    hdr = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/reports/{rid}/vote", json={"still_there": False}, headers=hdr)
    res = client.post(f"/api/reports/{rid}/vote", json={"still_there": True}, headers=hdr)
    body = res.get_json()
    assert body["total_votes"] == 1        # not 2
    assert body["votes_gone"] == 0
    assert body["votes_still_here"] == 1
