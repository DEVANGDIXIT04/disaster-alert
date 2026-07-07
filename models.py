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
    # Crowd verification votes. cascade="all, delete-orphan" means: when a
    # report is deleted (e.g. voted "gone"), its votes are deleted too, so no
    # orphan rows are left pointing at a missing report.
    votes = db.relationship("Vote", backref="report",
                            cascade="all, delete-orphan")

    def to_dict(self):
        """Convert this row into a plain dict so Flask can return it as JSON."""
        # Tally the crowd-verification votes so the map popup can show them.
        still_here = sum(1 for v in self.votes if v.still_there)
        gone = sum(1 for v in self.votes if not v.still_there)
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
            "votes_still_here": still_here,
            "votes_gone": gone,
        }


class Vote(db.Model):
    """One user's verification vote on whether an incident is still happening.

    still_there = True  -> "I can confirm this is still here"
    still_there = False -> "this incident is over / not there anymore"

    The UniqueConstraint guarantees one vote per user per report: voting again
    updates the existing row instead of stuffing the ballot box.
    """

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    still_there = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("report_id", "user_id", name="uq_one_vote_per_user_per_report"),
    )
