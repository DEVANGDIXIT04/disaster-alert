# models.py
# -----------------------------------------------------------------------------
# Database models for the Disaster Alert platform, defined with Flask-SQLAlchemy.
#
# Why SQLAlchemy? It is an ORM (Object Relational Mapper): we describe tables
# as Python classes, and it generates the SQL for us. The same code works with
# SQLite locally and PostgreSQL in the cloud - we only change the connection
# string (an environment variable), never this file.
# -----------------------------------------------------------------------------

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

# A single shared database object. app.py calls db.init_app(app) to connect it
# to the Flask application.
db = SQLAlchemy()

# Allowed values for report fields. Plain Python sets (not DB enums) keep the
# schema simple and portable between SQLite and PostgreSQL.
CATEGORIES = {"flood", "fire", "accident", "roadblock", "medical", "other"}
SEVERITIES = {"low", "medium", "high"}


class User(db.Model):
    """A registered citizen who can log in and submit reports."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)  # unique -> no duplicate accounts
    # We NEVER store the plaintext password - only a salted hash of it
    # (see auth logic in app.py using werkzeug.security).
    password_hash = db.Column(db.String(256), nullable=False)
    # Optional "home" location, used later to decide who gets alerted about
    # incidents near them. Nullable because a user may not share it.
    home_lat = db.Column(db.Float, nullable=True)
    home_lng = db.Column(db.Float, nullable=True)

    def to_dict(self):
        """Public view of a user - note: no password_hash in here, ever."""
        return {"id": self.id, "name": self.name, "email": self.email}


class Report(db.Model):
    """One citizen-submitted incident report (a pin on the map)."""

    id = db.Column(db.Integer, primary_key=True)          # auto-incrementing ID
    title = db.Column(db.String(120), nullable=False)     # short headline, e.g. "Waterlogging at Sector 62"
    description = db.Column(db.Text, nullable=False)      # longer free-text details
    category = db.Column(db.String(20), nullable=False, default="other")    # one of CATEGORIES
    severity = db.Column(db.String(10), nullable=False, default="medium")   # one of SEVERITIES
    lat = db.Column(db.Float, nullable=False)             # latitude of the incident
    lng = db.Column(db.Float, nullable=False)             # longitude of the incident
    # Stored in UTC so the timestamp means the same thing on every server.
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    # Who reported it. Nullable so old/anonymous rows don't break anything.
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user = db.relationship("User")  # lets us do report.user.name for the popup

    def to_dict(self):
        """Convert this row into a plain dict so Flask can return it as JSON."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "severity": self.severity,
            "lat": self.lat,
            "lng": self.lng,
            # isoformat() -> "2026-07-06T10:30:00" (a standard, JS-parseable string)
            "created_at": self.created_at.isoformat(),
            "reporter": self.user.name if self.user else "anonymous",
        }
