# seed.py
# -----------------------------------------------------------------------------
# Fills an EMPTY database with realistic demo data so the map never starts
# blank in a presentation. Safe to run repeatedly - it refuses to touch a
# database that already has reports.
#
#   python seed.py                          -> seeds the local SQLite DB
#   DATABASE_URL=postgres... python seed.py -> seeds Postgres/RDS instead
#
# Demo account it creates:  demo@example.com / demo123456
# -----------------------------------------------------------------------------

from werkzeug.security import generate_password_hash

from app import app
from models import db, Report, User

# Eight incidents spread around Noida / East Delhi - mixed categories and
# severities so the map shows all three marker colours.
SEED_REPORTS = [
    ("Flooded underpass at Sector 62", "Knee-deep water, two-wheelers stalling.", "flood",    "high",   28.6270, 77.3640),
    ("Fire in Mamura market lane",     "Smoke from a shop; brigade called.",     "fire",     "high",   28.5980, 77.3860),
    ("Multi-car pileup on NH24",       "Three cars, left lane blocked.",         "accident", "medium",28.6180, 77.3050),
    ("Tree fallen near Sector 52",     "Blocking half the road after storm.",    "roadblock","medium", 28.5910, 77.3620),
    ("Waterlogging at City Centre",    "Ankle-deep, buses moving slowly.",       "flood",    "low",    28.5745, 77.3560),
    ("Medical camp needed in Khora",   "Several fever cases reported.",          "medical",  "medium",28.6220, 77.3330),
    ("Street light pole sparking",     "Sparks near the bus stop, keep clear.",  "other",    "low",    28.6060, 77.3560),
    ("Gas leak smell in Sector 34",    "Residents evacuating one block.",        "fire",     "high",   28.5860, 77.3440),
]


def seed():
    with app.app_context():
        if Report.query.count() > 0:
            print(f"Database already has {Report.query.count()} report(s) - nothing to do.")
            return

        # One demo citizen who "lives" in Sector 62 (so new incidents nearby
        # will list them as alerted). Reused if it already exists.
        demo = User.query.filter_by(email="demo@example.com").first()
        if demo is None:
            demo = User(
                name="Demo Citizen",
                email="demo@example.com",
                password_hash=generate_password_hash("demo123456"),
                home_lat=28.61, home_lng=77.36,
            )
            db.session.add(demo)
            db.session.flush()  # assigns demo.id without a full commit yet

        for title, desc, category, severity, lat, lng in SEED_REPORTS:
            db.session.add(Report(
                title=title, description=desc, category=category,
                severity=severity, lat=lat, lng=lng, user_id=demo.id,
            ))
        db.session.commit()
        print(f"Seeded {len(SEED_REPORTS)} reports + demo login demo@example.com / demo123456")


if __name__ == "__main__":
    seed()
