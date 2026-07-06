# Presentation & Viva Guide

## 5-minute demo script (click by click)

**Setup beforehand:** open the live AWS URL in one tab (and keep
`http://localhost:5000` running in another terminal as backup — see fallback
plan at the bottom). Have 2-3 reports already submitted so the map isn't empty.

1. **(30 s) The idea.** "Citizens crowdsource disaster reports on a shared
   live map; the platform works out who lives nearby and would be alerted.
   Built with the spiral model — three shippable versions, one per git commit."
   Show `git log --oneline`.

2. **(60 s) Live map + register.** Open the AWS URL — *"this is running on
   Elastic Beanstalk, publicly accessible"*. Point at coloured markers, click
   one to show the popup. Click the map to drop a pin **first** (it becomes
   your home location), then register a new account — point out you're now
   logged in and the app never stored your plaintext password.

3. **(60 s) Report an incident.** With the pin still dropped: fill title
   ("Fire near market"), pick category Fire, severity High, Submit. A red
   marker appears instantly, and the status line says *"N user(s) within 10 km
   would be alerted (computed by aws-lambda)"* — *"that 'aws-lambda' is not a
   label: the API just invoked our deployed Lambda function over boto3. Run
   locally, the same line says 'computed by local' — identical logic, two
   execution homes."* This is the strongest 10 seconds of the demo.

4. **(60 s) What's near me.** Set radius 5 km, click Search. The dashed circle
   is drawn, matching markers get a blue ring, the yellow banner lists each
   incident with its distance — *"distance is the haversine formula in plain
   Python; we deliberately avoided PostGIS to stay portable between SQLite
   and PostgreSQL."*

5. **(60 s) The cloud story.** Flip to slides/terminal:
   - `Procfile` + `eb status` → Elastic Beanstalk runs gunicorn for us.
   - `aws lambda invoke ... response.json` (from `serverless/README.md`) →
     show the returned `alerted_users` JSON.
   - `docker-compose.yml` → same image runs locally against real PostgreSQL;
     on AWS, `DATABASE_URL` points at RDS instead — zero code change.

6. **(30 s) Wrap.** Concept table from the README; future scope (SNS SMS, S3
   images, WebSockets).

## What to say per concept (one breath each)

- **REST:** "Resources are nouns under /api; verbs are HTTP methods; we return
  201 on create, 400 on bad input, 401 on missing/invalid token."
- **JWT:** "Login returns a signed token; the server stores no session — each
  request proves itself via the Authorization header. Signature = HMAC-SHA256
  with a server-side secret; expiry after 24 h."
- **Password security:** "Werkzeug's generate_password_hash — salted, one-way.
  The DB never sees a plaintext password."
- **Database:** "SQLAlchemy ORM. The connection string is an env var, so
  SQLite locally and RDS PostgreSQL in the cloud run identical code."
- **Serverless:** "notify_lambda.py has zero non-stdlib imports; zipped it IS
  the Lambda. AWS runs it on demand — no server to manage, billed per call."
- **Microservice:** "The notification logic is its own deployable unit with a
  clean contract (lat, lng, radius → users). The map app is a consumer."
- **Docker:** "One image, built once, runs anywhere; compose adds a real
  Postgres so the demo matches production shape."
- **Cloud:** "Elastic Beanstalk provisions EC2 + nginx + gunicorn from a
  Procfile; health checks hit /api/health; eb deploy ships the latest commit."

## Likely viva questions (with model answers)

**Q: Why Flask and not Django/Spring?**
A: Smallest possible surface for a REST API — we can explain every line. No
ORM magic, no admin panel we don't use.

**Q: How does the haversine formula work / why not just Pythagoras?**
A: Latitude/longitude are angles on a sphere, not x/y on a plane. Haversine
converts the angular difference into great-circle distance (≈0.5% error).
Pythagoras on degrees would be badly wrong at city scale for longitude.

**Q: What's inside a JWT?**
A: Three base64 parts: header (algorithm), payload (user_id, exp), signature =
HMAC of the first two with the server secret. Anyone can READ it; nobody can
FORGE it without the secret. That's why we never put secrets in the payload.

**Q: What happens if two users register the same email at once?**
A: The column has a UNIQUE constraint, so the database rejects the second
insert even if both pass the application check — defence in depth.

**Q: Why does the Lambda not query the real database?**
A: Deliberate scope cut: the handler accepts the user list in the event (or a
demo list) so it stays dependency-free and testable in the console. Production
version would query RDS from inside the VPC — listed as future scope.

**Q: SQLite vs PostgreSQL — what actually changes?**
A: Only DATABASE_URL. SQLAlchemy speaks both dialects. SQLite is a file (no
server, single writer); Postgres is a networked server with real concurrency —
that's why the cloud uses it.

**Q: Where is the state if you run two EB instances?**
A: JWTs are stateless so auth scales horizontally for free; the shared state
is only in the database — which is exactly why it must be RDS, not SQLite,
once there's more than one instance.

**Q: Is storing the JWT in a JS variable safe?**
A: Safer than localStorage (no persistence for XSS to steal later), at the
cost of logging in again per tab. For this scale, a reasonable trade.

## Fallback plan if the live AWS demo fails

1. Keep a terminal ready with `docker compose up` already running →
   demo everything at `http://localhost:8000` and say: "same container image
   AWS runs, pointing at a local Postgres instead of RDS".
2. Docker also down? `python app.py` → `http://localhost:5000` (SQLite path).
3. For the Lambda: run `pytest tests/ -k lambda -v` to show the handler being
   invoked with the documented sample event, or screenshot the AWS console
   test run beforehand.
