# Crowdsourced Disaster Alert & Response Platform

[![tests](https://github.com/DEVANGDIXIT04/disaster-alert/actions/workflows/ci.yml/badge.svg)](https://github.com/DEVANGDIXIT04/disaster-alert/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-black)
![AWS](https://img.shields.io/badge/AWS-Elastic%20Beanstalk%20%C2%B7%20RDS%20%C2%B7%20Lambda-ff9900)
![License](https://img.shields.io/badge/license-MIT-green)

A citizen-powered map for local emergencies. People report incidents (flood,
fire, accident…) by dropping a pin and filling a short form; everyone sees them
as live, severity-coloured markers. Logged-in users can ask **"what's near
me?"**, **crowd-verify** whether an incident is still happening, and every new
report triggers a **serverless function** that works out which nearby residents
would be alerted.

> **🔒 Live demo (HTTPS):** https://disaster-alert.65-1-37-139.sslip.io
> &nbsp;·&nbsp; also at http://disaster-alert-env.eba-twpixdbf.ap-south-1.elasticbeanstalk.com
> &nbsp;·&nbsp; demo login **`demo@example.com` / `demo123456`**

---

## Features

- 🗺️ **Live incident map** — click to report; markers coloured green/orange/red by severity; auto-refreshes every 30 s.
- 🔐 **Accounts & JWT auth** — register/login with hashed passwords; only signed-in users can report or vote.
- 📍 **Proximity search** — "incidents within X km of me" using the haversine formula.
- 🔔 **Serverless alerts** — an AWS Lambda computes who lives close enough to be notified.
- ✅ **Crowd verification** — users vote whether an incident is still there; a majority "gone" auto-removes it.
- ☁️ **Cloud-native** — one image runs locally, in Docker with Postgres, or on AWS; the database switches via a single env var.

## Architecture

```
                Browser — static/index.html (Leaflet map + vanilla JS)
                    │  JSON over HTTPS (fetch); JWT in the Authorization header
                    ▼
  ┌──────────────────────────────────────────────┐        DATABASE_URL selects:
  │  Flask REST API — app.py                       │       ┌────────────────────┐
  │   /api/register  /api/login        [auth.py]   │  ───▶ │ SQLite   (local)   │
  │   /api/reports   /api/reports/nearby           │       │ PostgreSQL (Docker │
  │   /api/reports/<id>/vote                       │       │   & Amazon RDS)    │
  │   serves index.html · gunicorn on AWS          │       └────────────────────┘
  └──────────────────────────────────────────────┘
                    │  same logic, two homes
                    ▼
   serverless/notify_lambda.py — find_nearby_users()
     • imported & called directly by app.py       (local path)
     • deployed as an AWS Lambda, invoked via boto3 (cloud path)
```

The map UI is a single static file served by Flask; the API is a separate JSON
interface under `/api`; the notification logic is an independently deployable
unit (the microservice / serverless split).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 · Flask · Flask-SQLAlchemy | Minimal, readable, explainable line by line |
| Auth | PyJWT · Werkzeug password hashing | Stateless tokens, salted one-way password hashes |
| Database | SQLite (dev) → PostgreSQL / Amazon RDS (cloud) | Zero-setup locally; managed & durable in the cloud — same code |
| Frontend | Leaflet.js + vanilla JS (CDN) | No build step, no framework |
| Serverless | AWS Lambda (stdlib-only handler) | Runs on demand, effectively free at this scale |
| Container | Docker + docker-compose | One image everywhere; compose adds real Postgres |
| Serving | gunicorn on Elastic Beanstalk | Production WSGI server behind managed nginx |
| CI | GitHub Actions | `pytest` on every push |

## Spiral iteration log

Built with the spiral model — a working slice first, then clearly separated
enhancements, one git commit each, so the evolution is visible.

| Version | Commit | What it added |
|---|---|---|
| v1 | `v1: report + map` | Flask + SQLite, Report model, GET/POST reports, Leaflet page (drop pin → submit → markers) |
| v2 | `v2: auth + categories` | User model, register/login, JWT + `@token_required`, category & severity, coloured markers, pytest suite |
| v3 | `v3: nearby + serverless + docker + aws` | Haversine + `/reports/nearby`, Lambda (also runs locally), Docker + compose (Postgres), `DATABASE_URL` switch, AWS deploy docs |
| v4 | `v4: cloud polish` | API invokes the **real** Lambda via boto3 (`notify_source` proof), seed data, 30 s auto-refresh, rate limiting + input caps, GitHub Actions CI |
| v5 | `v5: crowd verification` | Vote model + `/reports/<id>/vote`, majority-"gone" auto-removal, vote UI in popups, output-escaping (XSS hardening) |

## Quick start (local, 3 commands)

```bash
pip install -r requirements.txt
python app.py            # → http://localhost:5000
# optional: python seed.py   (8 demo incidents + demo@example.com / demo123456)
```

SQLite `local.db` is created automatically. Run the tests with `pytest`
(**24 tests**). Schema changed between versions? Delete `local.db` — it's recreated.

## Run with Docker + PostgreSQL

```bash
docker compose up --build     # → http://localhost:8000  (app + postgres:16)
```

## API reference

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/health` | — | Liveness check (used by the AWS health check) |
| `POST /api/register` | — | Create account → returns JWT |
| `POST /api/login` | — | Authenticate → returns JWT |
| `GET /api/reports` | — | List all incidents |
| `POST /api/reports` | JWT | Create an incident (+ returns who would be alerted) |
| `GET /api/reports/nearby?lat=&lng=&radius_km=` | — | Incidents within a radius |
| `POST /api/reports/<id>/vote` | JWT | Vote "still here" / "gone"; majority-gone auto-removes |

## Deploy to AWS

- App on Elastic Beanstalk → [deploy/aws-elastic-beanstalk.md](deploy/aws-elastic-beanstalk.md)
- PostgreSQL on RDS → [deploy/aws-rds-setup.md](deploy/aws-rds-setup.md)
- Lambda → [serverless/README.md](serverless/README.md)
- HTTPS / TLS (Let's Encrypt) → [deploy/https-setup.md](deploy/https-setup.md)

## Course concept coverage

| Concept | Where it lives |
|---|---|
| Cloud Deployment | `Procfile`, `.ebextensions/`, `deploy/aws-elastic-beanstalk.md` |
| RESTful API | `app.py` — resource routes under `/api`, correct verbs & status codes (200/201/400/401/404/429) |
| Database Integration | `models.py` (SQLAlchemy) + `DATABASE_URL` env switch (SQLite ↔ PostgreSQL/RDS) |
| Microservice split | `serverless/notify_lambda.py` — notification is a separate deployable unit |
| Serverless (AWS Lambda) | `serverless/notify_lambda.py`; the live API invokes it via boto3 — the `notify_source` field proves which path ran |
| Containerization | `Dockerfile`, `docker-compose.yml` (app + postgres:16) |
| Security / Auth | `auth.py` (JWT sign/verify, `@token_required`), password hashing, auth rate limiting, output escaping |

## Security notes

- Passwords stored only as **salted hashes** (`werkzeug.security`); plaintext is never persisted.
- JWTs signed HS256 with a secret from `JWT_SECRET`; **expire after 24 h**; kept in a JS variable, not `localStorage`.
- Login/register are **rate-limited** (10 attempts/min per IP) to blunt password guessing.
- All user-supplied text is **HTML-escaped** before rendering (stored-XSS defence), on top of server-side length caps.
- Identical login error for wrong email vs. wrong password, so accounts can't be enumerated.
- Served over **HTTPS** with a Let's Encrypt certificate (see [deploy/https-setup.md](deploy/https-setup.md)).

## Future scope

Real SMS/email via Amazon SNS · report photos in S3 · duplicate/moderation
detection · WebSocket push instead of polling · PostGIS for large-scale geo
queries · a shared rate-limit/vote store (Redis) for multi-instance scale.

## Team

| Name | Enrolment |
|---|---|
| Abhijeet Kumar Singh | 22803029 |
| Viyom Shukla | 22803030 |
| Devang Dixit | 22803031 |

**Course:** Cloud and Web Services Lab [17M15CS121] · JIIT, Sector 62

## License

Released under the [MIT License](LICENSE).
