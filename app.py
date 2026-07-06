# app.py
# -----------------------------------------------------------------------------
# Crowdsourced Disaster Alert & Response Platform - Flask REST API.
#
# Spiral model progress:
#   Iteration 1: reports + map (GET/POST /api/reports, static page).
#   Iteration 2 (this one): users, JWT auth, category + severity.
#     - POST /api/register  -> create account, get a token
#     - POST /api/login     -> get a token
#     - POST /api/reports   -> now requires a valid token
#
# Run locally:  pip install -r requirements.txt && python app.py
# Run tests:    pytest
# -----------------------------------------------------------------------------

import os

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import create_token, token_required
from models import db, Report, User, CATEGORIES, SEVERITIES

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


# --- Basic routes -----------------------------------------------------------

@app.route("/")
def home():
    """Serve the single-page map UI."""
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    """Used by humans and (later) by the AWS load balancer to check liveness."""
    return jsonify({"status": "ok"})


# --- Auth routes ------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def register():
    """Create an account: {name, email, password, home_lat?, home_lng?}.

    Returns 201 with a JWT so the user is logged in immediately.
    """
    data = request.get_json(silent=True)  # silent=True -> None instead of a crash on bad JSON
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()  # emails are case-insensitive
    password = str(data.get("password") or "")

    if not name or not email or "@" not in email:
        return jsonify({"error": "A name and a valid email are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "This email is already registered"}), 400

    user = User(
        name=name,
        email=email,
        # generate_password_hash salts + hashes; the plaintext is never stored.
        password_hash=generate_password_hash(password),
        # Optional home location (used later for "who should be alerted?").
        home_lat=data.get("home_lat"),
        home_lng=data.get("home_lng"),
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"token": create_token(user.id), "user": user.to_dict()}), 201


@app.route("/api/login", methods=["POST"])
def login():
    """Log in with {email, password}; returns a fresh JWT."""
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
    {title, description, category, severity, lat, lng}."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required text fields.
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if not title or not description:
        return jsonify({"error": "title and description are required"}), 400

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

    # 201 Created is the correct status code for a successful POST that
    # created a new resource.
    return jsonify(report.to_dict()), 201


# --- Entry point ------------------------------------------------------------

if __name__ == "__main__":
    # Development server only. In the cloud, gunicorn runs the app instead
    # (see Procfile in a later iteration).
    app.run(debug=True, port=5000)
