# PROJECT_EXPLAINED — the complete context

Read this once and you can explain every part of the project from memory.
(For the minute-by-minute demo script, see `PRESENTATION_GUIDE.md`.)

---

## 1. What this is, in one paragraph

A crowdsourced disaster map. Anyone can *see* incidents; registered users can
*report* them by clicking a point on the map and filling a short form. Every
report is stored with coordinates, so the platform can answer "what's within
X km of me?" and "who lives close enough to this new incident to be alerted?"
The alert computation runs as a real AWS Lambda in production and as a plain
imported function locally — same file, two execution homes.

## 2. The pieces and where they live

| File | Role |
|---|---|
| `static/index.html` | The entire frontend: Leaflet map + vanilla JS. No build step. Flask serves it at `/`. |
| `app.py` | The entire REST API: routes, validation, CORS, rate limiting, notification dispatch. |
| `models.py` | Two SQLAlchemy models: `User`, `Report`. Also the allowed category/severity sets. |
| `auth.py` | JWT creation (`create_token`) and verification (`@token_required` decorator). |
| `serverless/notify_lambda.py` | Haversine + `find_nearby_users()` + `lambda_handler()`. Stdlib-only so the Lambda zip is this one file. |
| `seed.py` | Fills an empty DB with 8 demo incidents + demo login (`demo@example.com` / `demo123456`). |
| `tests/test_api.py` | 24 pytest tests covering every endpoint, auth failure modes, geo maths, the Lambda handler, and the voting rules. |
| `Dockerfile` / `docker-compose.yml` | Container image; compose runs it against a real Postgres. |
| `Procfile` / `.ebextensions/` | Tell Elastic Beanstalk how to run us (gunicorn) and health-check us (`/api/health`). |
| `.github/workflows/ci.yml` | GitHub Actions: runs pytest on every push. |
| `deploy/*.md`, `serverless/README.md` | Copy-paste AWS runbooks (EB, RDS, Lambda). |

## 3. How each flow works, end to end

**Page load.** Browser GETs `/` → Flask returns `index.html` → JS calls
`GET /api/reports` → for each report a coloured `circleMarker` is drawn
(green/orange/red = low/medium/high). A `setInterval` repeats the fetch every
30 s and draws only markers it hasn't seen (`markersById`), so the map stays
live for everyone without WebSockets.

**Register / login.** `POST /api/register` validates input, checks the email
isn't taken, stores `generate_password_hash(password)` (salted, one-way —
plaintext never touches the DB), and returns a JWT. `POST /api/login` looks
the user up and `check_password_hash`-es; wrong email and wrong password give
the *same* 401 message so attackers can't probe which emails exist. Both
endpoints are rate-limited to 10 attempts/minute per IP (429 after that).
The JWT is `{user_id, exp}` signed HS256 with `JWT_SECRET`; it lives in a JS
variable (not localStorage) and expires in 24 h.

**Submitting a report.** The map click stores `pinLatLng` and shows a
draggable pin. Submit sends `POST /api/reports` with the JWT in
`Authorization: Bearer <token>`. On the server, `@token_required` verifies
the signature/expiry and loads the User; the route validates fields (length
caps, category/severity whitelists, lat/lng ranges), inserts the row, then
runs the notification step:

- **In production** (`NOTIFY_LAMBDA` env var set): boto3 *invokes the deployed
  Lambda function* with `{lat, lng, radius_km, users}`; the response's
  `notify_source` field says `"aws-lambda"` — you can literally see it in the
  UI status line.
- **Locally** (env var unset) or if the invoke fails: the same logic is called
  as an imported Python function; `notify_source` says `"local"`.

**"What's near me?".** `GET /api/reports/nearby?lat&lng&radius_km` computes
haversine distance from the query point to every report in Python and returns
the ones inside the radius, closest first. Haversine treats Earth as a sphere
(6371 km radius) — accurate to ~0.5%, and it's why we don't need PostGIS.
The UI draws a dashed circle, blue-rings the matching markers, and lists them
in a banner with distances.

**Crowd verification (voting).** Each marker popup has "Still here" / "Gone"
buttons → `POST /api/reports/<id>/vote` with `{still_there: bool}` and the JWT.
One vote per user (a UniqueConstraint; voting again updates it). After each
vote the server recounts from the votes table; if there are at least
`VOTES_TO_RESOLVE` (3) votes **and** a strict majority say "gone", the report is
deleted (cascade also removes its votes). Other clients' maps drop the marker
on their next 30 s poll. The minimum-votes rule stops one person deleting a
genuine report.

**Database switching.** `app.py` reads `DATABASE_URL`; if unset it falls back
to a SQLite file next to `app.py`. Set it to a PostgreSQL URL (docker-compose
or RDS) and *nothing else changes* — SQLAlchemy speaks both dialects.

## 4. The deployed topology (as of the presentation)

```
you / graders / anyone
        |
        v  http://disaster-alert-env.eba-twpixdbf.ap-south-1.elasticbeanstalk.com
+--------------------------------------+
| Elastic Beanstalk: 1x t3.micro       |
|  nginx -> gunicorn -> app.py         |
|  env: JWT_SECRET, DATABASE_URL,      |
|       NOTIFY_LAMBDA                  |
+--------------------------------------+
     |                        |
     | SQL (5432)             | boto3 invoke
     v                        v
 RDS PostgreSQL          AWS Lambda
 disaster-alert-db       disaster-alert-notify
 (db.t4g.micro)          (python3.12, logs to CloudWatch)
```

GitHub: https://github.com/DEVANGDIXIT04/disaster-alert — 5 commits showing
the spiral (v1 map → v2 auth → v3 cloud → v4 polish → v5 crowd-verify),
Actions running pytest on every push.

## 5. How to present it (the narrative arc)

1. **Start with the problem** — during a flood, information is scattered;
   a shared map beats a hundred WhatsApp groups.
2. **Show it working live** (AWS URL) — browse markers, register, report,
   point at *"computed by aws-lambda"*, run the nearby search.
3. **Then reveal the engineering** — spiral commits on GitHub, the concept
   table in the README, one terminal command (`aws lambda invoke ...`) to
   show the Lambda answering directly.
4. **Close with judgment, not features** — the things you deliberately did
   NOT build (PostGIS, WebSockets, SMS) and why simplicity was the right
   engineering call at this scale. Graders reward knowing *why*.

**Killer lines to use:**
- "The same file is our Lambda in the cloud and a plain import locally —
  serverless isn't a separate codebase, it's a deployment choice."
- "Switching SQLite to RDS PostgreSQL was one environment variable. That's
  what an ORM buys you."
- "The server holds no session state — a JWT is the session, so this scales
  horizontally for free."

## 6. Command cheat sheet

```bash
# local
pip install -r requirements.txt && python app.py    # http://localhost:5000
python seed.py                                      # demo data (empty DB only)
pytest                                              # 24 tests

# docker (Postgres path)
docker compose up --build                           # http://localhost:8000

# aws
eb status / eb logs / eb deploy                     # env health / logs / ship last commit
aws lambda invoke --function-name disaster-alert-notify \
  --cli-binary-format raw-in-base64-out \
  --payload '{"lat":28.61,"lng":77.36,"radius_km":5}' out.json && cat out.json
eb terminate disaster-alert-env                     # teardown (also delete RDS!)
```

## 7. If someone asks "walk me through a request"

Say this, slowly: *"The browser sends `POST /api/reports` with a JSON body and
a JWT header. nginx forwards it to gunicorn, which runs our Flask app. The
`@token_required` decorator verifies the token's HMAC signature and expiry,
loads the user from PostgreSQL, and passes it into the route. The route
validates every field — lengths, whitelists, coordinate ranges — inserts the
report through SQLAlchemy, then invokes our Lambda with the incident location
and the list of users who shared home coordinates. The Lambda runs the
haversine formula, returns who's within 10 km, and that list goes back to the
browser in the 201 response — which is why the UI can instantly say how many
people would be alerted, and by which execution path."*

If you can say that paragraph, you can answer 80% of any viva on this project.
