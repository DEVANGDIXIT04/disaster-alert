# Crowdsourced Disaster Alert & Response Platform

Citizens report local incidents (flood, fire, accident...) by clicking a point
on a shared live map and filling a short form. Reports appear as markers
coloured by severity. A logged-in user can ask *"what's near me?"* and get all
incidents within a chosen radius, and every new report triggers a serverless
function that works out which registered users live close enough to be alerted.

**Team:** Abhijeet Kumar Singh (22803029) · Viyom Shukla (22803030) · Devang Dixit (22803031)
**Course:** Cloud and Web Services Lab [17M15CS121], JIIT Sector 62

---

## Architecture

```
                 Browser (static/index.html - Leaflet map + vanilla JS)
                     |  JSON over HTTP (fetch), JWT in Authorization header
                     v
   +------------------------------------------+
   |  Flask REST API (app.py)                 |      one env var switches DB:
   |   /api/register /api/login   [auth.py]   |      DATABASE_URL
   |   /api/reports  /api/reports/nearby      |     .------------------.
   |   serves index.html                      |---> | SQLite (local)   |
   |   gunicorn on AWS (Procfile/Dockerfile)  |     | PostgreSQL (RDS/ |
   +------------------------------------------+     |   docker "db")   |
                     |                               '------------------'
                     |  same function, two homes
                     v
   serverless/notify_lambda.py -- find_nearby_users()
     - imported + called directly by app.py (local path)
     - deployed as AWS Lambda, invoked with an event (cloud path)
```

The map UI is one static HTML file served by Flask; the API is a separate JSON
interface under `/api` — that's the microservice-style split: the notification
logic (`serverless/`) is an independently deployable unit.

## Spiral iteration log

| Version | git commit | What it added |
|---|---|---|
| v1 | `v1: report + map` | Flask + SQLite, Report model, GET/POST /api/reports, Leaflet page: drop a pin, submit, see markers |
| v2 | `v2: auth + categories` | User model, register/login, JWT (`auth.py`), protected report creation, category + severity, coloured markers, pytest suite |
| v3 | `v3: nearby + serverless + docker + aws` | Haversine + /api/reports/nearby, Lambda function (also runs locally), "near me" UI, Dockerfile + docker-compose (Postgres), DATABASE_URL switching, AWS deploy docs |

## Run locally in 3 commands

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

(SQLite file `local.db` is created automatically. Tests: `pytest`.
Schema changed between versions? Just delete `local.db` — it's recreated.)

## Run with Docker + PostgreSQL

```bash
docker compose up --build
# open http://localhost:8000
```

## Deploy to AWS

- App on Elastic Beanstalk: [deploy/aws-elastic-beanstalk.md](deploy/aws-elastic-beanstalk.md)
- PostgreSQL on RDS: [deploy/aws-rds-setup.md](deploy/aws-rds-setup.md)
- Lambda: [serverless/README.md](serverless/README.md)

## Where each course concept is implemented

| Concept | Where |
|---|---|
| Cloud Deployment | `deploy/aws-elastic-beanstalk.md`, `Procfile`, `.ebextensions/healthcheck.config` |
| RESTful API | `app.py` — resource routes under `/api`, proper verbs + status codes (200/201/400/401) |
| Database Integration | `models.py` (SQLAlchemy models), `app.py:~45` (`DATABASE_URL` env switch SQLite↔Postgres) |
| Microservice split | `serverless/notify_lambda.py` — notification logic is a separate deployable unit consumed by the API |
| Serverless (AWS Lambda) | `serverless/notify_lambda.py` (`lambda_handler`), deploy steps in `serverless/README.md` |
| Containerization | `Dockerfile`, `docker-compose.yml` (app + postgres:16) |
| Security / Auth (JWT) | `auth.py` (PyJWT sign/verify, `@token_required`), password hashing in `app.py` register/login |

## Future scope (deliberately not built)

Real SMS/email alerts via Amazon SNS · report images in S3 · moderation /
duplicate detection · WebSocket live updates · PostGIS for large-scale geo
queries · Kubernetes; SQS queues for burst traffic.

## Notes

- `JWT_SECRET` and `DATABASE_URL` are the only configuration (see `.env.example`).
- Passwords are stored only as salted hashes; JWTs expire after 24 h.
