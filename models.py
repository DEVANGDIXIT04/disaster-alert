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


class Report(db.Model):
    """One citizen-submitted incident report (a pin on the map)."""

    id = db.Column(db.Integer, primary_key=True)          # auto-incrementing ID
    title = db.Column(db.String(120), nullable=False)     # short headline, e.g. "Waterlogging at Sector 62"
    description = db.Column(db.Text, nullable=False)      # longer free-text details
    lat = db.Column(db.Float, nullable=False)             # latitude of the incident
    lng = db.Column(db.Float, nullable=False)             # longitude of the incident
    # Stored in UTC so the timestamp means the same thing on every server.
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert this row into a plain dict so Flask can return it as JSON."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "lat": self.lat,
            "lng": self.lng,
            # isoformat() -> "2026-07-06T10:30:00" (a standard, JS-parseable string)
            "created_at": self.created_at.isoformat(),
        }
