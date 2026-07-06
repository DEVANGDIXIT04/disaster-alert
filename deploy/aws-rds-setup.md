# AWS RDS: the cloud PostgreSQL database

Locally we use SQLite (zero setup). In the cloud, the proper story is a
managed PostgreSQL on **Amazon RDS**: AWS handles backups, patching, and
storage. Because `app.py` reads `DATABASE_URL` from the environment, switching
is **one environment variable — zero code changes**. That's the point to make
in the viva.

> SQLite on the EB instance is fine for a first demo. Do this page when you
> want the full "managed cloud database" story.

## 1. Create the database (console, ~10 minutes)

RDS console → **Create database**:

- **Standard create** → Engine: **PostgreSQL**
- Template: **Free tier** (gives db.t3.micro / db.t4g.micro, 20 GB)
- DB instance identifier: `disaster-alert-db`
- Master username: `disaster` — Master password: choose one, note it down
- **Public access: Yes** (simplest for a student demo; a production setup
  would say No and share a VPC with the app)
- Initial database name (under *Additional configuration*): `disaster`
- Everything else: defaults → **Create database**

Wait for status **Available**, then copy the **Endpoint** from the
Connectivity tab, e.g. `disaster-alert-db.xxxx.ap-south-1.rds.amazonaws.com`.

## 2. Open the security group

By default nothing can connect. On the DB's page → Connectivity → click the
VPC security group → **Edit inbound rules** → add:

- Type: **PostgreSQL** (port 5432)
- Source: **Anywhere-IPv4** (`0.0.0.0/0`) for demo simplicity — or, tighter,
  the security group of the Elastic Beanstalk instance.

## 3. Build the connection string and give it to the app

```
DATABASE_URL = postgresql://disaster:<PASSWORD>@<ENDPOINT>:5432/disaster
```

```bash
eb setenv DATABASE_URL=postgresql://disaster:MyPass123@disaster-alert-db.xxxx.ap-south-1.rds.amazonaws.com:5432/disaster
```

The app restarts, `db.create_all()` creates the tables in Postgres on boot,
and from that moment every report is stored in RDS. Verify by submitting a
report, then `eb deploy`-ing again later — the data survives, unlike SQLite.

You can also test the same Postgres path **locally with Docker** (no AWS
needed): `docker compose up --build` — the compose file wires the same style
of `DATABASE_URL` to a postgres:16 container.

## Tear it down (avoid charges!)

RDS console → select `disaster-alert-db` → Actions → **Delete**
(untick "create final snapshot", tick the acknowledgement). Free tier covers
750 h/month for 12 months on old accounts — new accounts get a credit budget
instead, so deleting when not demoing is the safe habit either way.
