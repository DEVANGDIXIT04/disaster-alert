# app.py
# -----------------------------------------------------------------------------
# Crowdsourced Disaster Alert & Response Platform - Flask REST API.
#
# Spiral model progress:
#   Iteration 1: reports + map (GET/POST /api/reports, static page).
#   Iteration 2: users, JWT auth, category + severity.
#   Iteration 3 (this one): geo queries + serverless + cloud-ready.
#     - GET /api/reports/nearby  -> reports within a radius (haversine)
#     - POST /api/reports now also computes "who would be alerted", using
#       the SAME function that runs as an AWS Lambda in the cloud.
#     - DATABASE_URL switches SQLite -> PostgreSQL with zero code changes.
#
# Run locally:  pip install -r requirements.txt && python app.py
# Run tests:    pytest
# Run in Docker (with Postgres):  docker compose up --build
# -----------------------------------------------------------------------------

import json
import os
import time
from collections import defaultdict

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import create_token, token_required
from models import db, Report, User, CATEGORIES, SEVERITIES
# The notification logic lives in serverless/notify_lambda.py so the exact
# same file can be zipped and deployed as an AWS Lambda function. Importing
# it here is the "local path"; Lambda is the "cloud path".
from serverless.notify_lambda import find_nearby_users, haversine_km

# When a report is created, users whose home is within this many km of the
# incident are considered "alerted".
ALERT_RADIUS_KM = 10

# If set (on AWS), the API invokes the real deployed Lambda function by name
# instead of calling the imported Python function. Same logic either way -
# this just proves the serverless path is genuinely used in production.
NOTIFY_LAMBDA = os.environ.get("NOTIFY_LAMBDA")

# --- App and database setup -------------------------------------------------

# static_url_path="" means files in static/ are served from the site root,
# so the browser can just ask for "/" and get our map page.
app = Flask(__name__, static_folder="static", static_url_path="")

# Read the DB connection string from the environment. Locally there is no such
# variable, so we fall back to SQLite - a zero-setup file database. In the
# cloud we will set DATABASE_URL to a PostgreSQL address; the code is identical.
# The SQLite file gets an absolute path next to this file, so it ends up in
# the same place no matter which directory the app is started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "local.db")
)

db.init_app(app)

# Create the tables on startup if they don't exist yet (fine for a small app;
# big apps would use a migration tool instead).
with app.app_context():
    db.create_all()


# --- CORS -------------------------------------------------------------------
# Our HTML page is served by this same Flask app, but during the demo the API
# might also be called from another origin (e.g. the file opened directly, or
# a frontend hosted elsewhere). These headers tell browsers "any site may call
# this API". Permissive on purpose - this is a public, read-mostly demo API.

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# --- Rate limiting ------------------------------------------------------------
# A tiny in-memory limiter for the auth endpoints, so nobody can hammer
# register/login with a password-guessing script. Per-process memory is enough
# for a single instance; a multi-instance deployment would use a shared store
# (future scope). Disabled under pytest (TESTING=True) so tests can log in freely.

_attempts = defaultdict(list)   # ip address -> [timestamps of recent requests]

def rate_limited(ip, limit=10, window_seconds=60):
    """True if this ip already made `limit` auth requests in the last minute."""
    now = time.time()
    _attempts[ip] = [t for t in _attempts[ip] if now - t < window_seconds]
    if len(_attempts[ip]) >= limit:
        return True
    _attempts[ip].append(now)
    return False


def auth_rate_limit_response():
    """The shared 429 (Too Many Requests) response, or None if allowed."""
    if app.config.get("TESTING"):
        return None
    if rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many attempts. Try again in a minute."}), 429
    return None


# --- Notification dispatch ------------------------------------------------------

def run_notify_logic(lat, lng, candidates):
    """Work out who to alert. Returns (alerted_users, source).

    On AWS (NOTIFY_LAMBDA set): invoke the deployed Lambda function - a real
    cross-service call, and the response tells the UI it came from "aws-lambda".
    Anywhere else (or if the call fails): import-and-call the same code locally.
    """
    if NOTIFY_LAMBDA:
        try:
            import boto3  # only needed on the AWS path
            client = boto3.client("lambda",
                                  region_name=os.environ.get("AWS_REGION", "ap-south-1"))
            resp = client.invoke(
                FunctionName=NOTIFY_LAMBDA,
                Payload=json.dumps({"lat": lat, "lng": lng,
                                    "radius_km": ALERT_RADIUS_KM,
                                    "users": candidates}),
            )
            payload = json.loads(resp["Payload"].read())
            return payload["alerted_users"], "aws-lambda"
        except Exception as exc:  # noqa: BLE001 - alerting must never break reporting
            print(f"Lambda invoke failed ({exc}); falling back to local logic")
    return find_nearby_users(lat, lng, ALERT_RADIUS_KM, candidates), "local"


# --- Basic routes -----------------------------------------------------------

@app.route("/")
def home():
    """Serve the single-page map UI."""
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    """Used by humans and by the AWS health check to confirm the app is up."""
    return jsonify({"status": "ok"})


# --- Auth routes ------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def register():
    """Create an account: {name, email, password, home_lat?, home_lng?}.

    Returns 201 with a JWT so the user is logged in immediately.
    """
    limited = auth_rate_limit_response()
    if limited:
        return limited

    data = request.get_json(silent=True)  # silent=True -> None instead of a crash on bad JSON
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()  # emails are case-insensitive
    password = str(data.get("password") or "")

    if not name or not email or "@" not in email:
        return jsonify({"error": "A name and a valid email are required"}), 400
    if len(name) > 80 or len(email) > 120:
        return jsonify({"error": "name/email too long"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "This email is already registered"}), 400

    user = User(
        name=name,
        email=email,
        # generate_password_hash salts + hashes; the plaintext is never stored.
        password_hash=generate_password_hash(password),
        # Optional home location, used to decide who gets alerted about
        # incidents near them.
        home_lat=data.get("home_lat"),
        home_lng=data.get("home_lng"),
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"token": create_token(user.id), "user": user.to_dict()}), 201


@app.route("/api/login", methods=["POST"])
def login():
    """Log in with {email, password}; returns a fresh JWT."""
    limited = auth_rate_limit_response()
    if limited:
        return limited

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    user = User.query.filter_by(email=email).first()
    # One combined check + one generic message, so an attacker can't probe
    # which emails have accounts.
    if user is None or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    return jsonify({"token": create_token(user.id), "user": user.to_dict()})


# --- Report routes ----------------------------------------------------------

@app.route("/api/reports", methods=["GET"])
def list_reports():
    """Return every report, newest first, as a JSON array. Public - anyone
    should be able to SEE incidents; only reporting needs an account."""
    reports = Report.query.order_by(Report.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@app.route("/api/reports", methods=["POST"])
@token_required  # rejects the request with 401 unless a valid JWT is presented
def create_report(current_user):
    """Create a report from a JSON body:
    {title, description, category, severity, lat, lng}.

    After saving, runs the notification logic and returns the list of users
    who would be alerted (same code that runs as the AWS Lambda)."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required text fields.
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if not title or not description:
        return jsonify({"error": "title and description are required"}), 400
    # Length caps: the DB column allows 120 for title, and a 2000-char cap on
    # description stops someone dumping megabytes into the popup HTML.
    if len(title) > 120 or len(description) > 2000:
        return jsonify({"error": "title max 120 chars, description max 2000"}), 400

    # Category and severity must be one of the allowed values (see models.py).
    category = str(data.get("category") or "other").lower()
    severity = str(data.get("severity") or "medium").lower()
    if category not in CATEGORIES:
        return jsonify({"error": f"category must be one of: {sorted(CATEGORIES)}"}), 400
    if severity not in SEVERITIES:
        return jsonify({"error": f"severity must be one of: {sorted(SEVERITIES)}"}), 400

    # Validate coordinates: must be numbers within the valid lat/lng ranges.
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lng must be numbers"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400

    report = Report(
        title=title,
        description=description,
        category=category,
        severity=severity,
        lat=lat,
        lng=lng,
        user_id=current_user.id,  # we know who this is thanks to the JWT
    )
    db.session.add(report)
    db.session.commit()

    # --- Notification step (the "serverless" logic) ---------------------------
    # Collect every user who shared a home location, as plain dicts, and ask
    # who lives close enough to care - via the real Lambda on AWS, or the
    # imported function locally (see run_notify_logic).
    candidates = [
        {"id": u.id, "name": u.name, "email": u.email,
         "home_lat": u.home_lat, "home_lng": u.home_lng}
        for u in User.query.filter(User.home_lat.isnot(None),
                                   User.home_lng.isnot(None)).all()
    ]
    alerted, notify_source = run_notify_logic(lat, lng, candidates)

    response = report.to_dict()
    response["alerted_users"] = alerted
    response["alert_radius_km"] = ALERT_RADIUS_KM
    response["notify_source"] = notify_source  # "aws-lambda" in the cloud, "local" otherwise
    # 201 Created is the correct status code for a successful POST that
    # created a new resource.
    return jsonify(response), 201


@app.route("/api/reports/nearby")
def nearby_reports():
    """Reports within a radius: /api/reports/nearby?lat=..&lng=..&radius_km=..

    We fetch all reports and filter with the haversine formula in Python.
    For a city-scale student project that is fast enough and avoids needing
    a spatial database extension (PostGIS) - a deliberate simplicity choice.
    """
    try:
        lat = float(request.args["lat"])
        lng = float(request.args["lng"])
        radius_km = float(request.args.get("radius_km", 5))
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lng query params are required numbers"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or radius_km <= 0:
        return jsonify({"error": "lat/lng out of range or radius not positive"}), 400

    nearby = []
    for report in Report.query.all():
        distance = haversine_km(lat, lng, report.lat, report.lng)
        if distance <= radius_km:
            item = report.to_dict()
            item["distance_km"] = round(distance, 2)
            nearby.append(item)
    nearby.sort(key=lambda r: r["distance_km"])  # closest first

    return jsonify({"count": len(nearby), "radius_km": radius_km, "reports": nearby})


# --- Entry point ------------------------------------------------------------

if __name__ == "__main__":
    # Development server only. In the cloud, gunicorn runs the app instead
    # (see Procfile / Dockerfile).
    app.run(debug=True, port=5000)
