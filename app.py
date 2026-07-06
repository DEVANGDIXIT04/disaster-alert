# app.py
# -----------------------------------------------------------------------------
# Crowdsourced Disaster Alert & Response Platform - Flask REST API.
#
# Iteration 1 (spiral model): the smallest thing that works.
#   - GET  /api/health   -> liveness check
#   - GET  /api/reports  -> list all incident reports
#   - POST /api/reports  -> create a new incident report
#   - GET  /            -> serves the Leaflet map page (static/index.html)
#
# Run locally:  pip install -r requirements.txt && python app.py
# -----------------------------------------------------------------------------

import os

from flask import Flask, jsonify, request

from models import db, Report

# --- App and database setup -------------------------------------------------

# static_url_path="" means files in static/ are served from the site root,
# so the browser can just ask for "/" and get our map page.
app = Flask(__name__, static_folder="static", static_url_path="")

# Read the DB connection string from the environment. Locally there is no such
# variable, so we fall back to SQLite - a zero-setup file database. In the
# cloud we will set DATABASE_URL to a PostgreSQL address; the code is identical.
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///local.db"
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


# --- Routes -----------------------------------------------------------------

@app.route("/")
def home():
    """Serve the single-page map UI."""
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    """Used by humans and (later) by the AWS load balancer to check liveness."""
    return jsonify({"status": "ok"})


@app.route("/api/reports", methods=["GET"])
def list_reports():
    """Return every report, newest first, as a JSON array."""
    reports = Report.query.order_by(Report.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reports])


@app.route("/api/reports", methods=["POST"])
def create_report():
    """Create a report from a JSON body: {title, description, lat, lng}."""
    data = request.get_json(silent=True)  # silent=True -> None instead of a crash on bad JSON
    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required text fields.
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    if not title or not description:
        return jsonify({"error": "title and description are required"}), 400

    # Validate coordinates: must be numbers within the valid lat/lng ranges.
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat and lng must be numbers"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400

    report = Report(title=title, description=description, lat=lat, lng=lng)
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
