# Deploy to AWS — Option A: Elastic Beanstalk (recommended)

Elastic Beanstalk (EB) is AWS's "just run my code" service: you upload the
project, it provisions an EC2 instance, installs Python, reads the `Procfile`,
starts gunicorn behind nginx, and gives you a public URL. You manage nothing.

**Prerequisites:** AWS CLI configured (`aws configure`), Python installed.

## 1. Install the EB CLI (one-time)

```bash
pip install awsebcli
```

## 2. Initialise the EB app (one-time, run inside the project folder)

```bash
cd disaster-alert
eb init -p python-3.12 disaster-alert --region ap-south-1
```

- `-p python-3.12` = the "Python 3.12 on Amazon Linux 2023" platform.
- `ap-south-1` = Mumbai; use the region you configured in `aws configure`.
- This only writes local config (`.elasticbeanstalk/`, gitignored); nothing
  is created in AWS yet. If it asks about CodeCommit or SSH, answer **n**.

**How the pieces connect:** EB zips the git-tracked files and uploads them.
On the instance it runs `pip install -r requirements.txt`, then starts the
command from our `Procfile` (`web: gunicorn app:app`) behind nginx on port 80.
The `.ebextensions/healthcheck.config` file points the environment's health
check at our `GET /api/health` endpoint.

## 3. Create the environment (the actual deployment, ~5 minutes)

```bash
eb create disaster-alert-env --single
```

`--single` = one t3.micro instance, **no load balancer** — the cheapest
possible setup and all a demo needs. (Omit `--single` later to get a load-
balanced, auto-scaling environment; that's the scalability story for the viva.)

## 4. Set the environment variables

```bash
# Generate a random secret first:  python -c "import secrets; print(secrets.token_hex(32))"
eb setenv JWT_SECRET=<paste-the-random-string>
```

Without `DATABASE_URL` the app uses SQLite **on the instance's own disk** —
perfectly fine for the demo, but data is lost if the instance is replaced.
For the full "cloud database" story, create an RDS PostgreSQL instance
(see `aws-rds-setup.md`) and then:

```bash
eb setenv DATABASE_URL=postgresql://USER:PASSWORD@ENDPOINT:5432/DBNAME
```

(Each `eb setenv` restarts the app automatically.)

## 5. Open it

```bash
eb open          # opens http://disaster-alert-env.<hash>.ap-south-1.elasticbeanstalk.com
eb status        # environment health + the URL (CNAME field)
eb logs          # server logs, if something is wrong
```

The URL is public — anyone on the internet can use the app now.

## 6. Deploy updates later

```bash
git commit -am "some change"     # EB deploys the last COMMIT, not the working dir
eb deploy
```

## Tear it down (avoid charges!)

```bash
eb terminate disaster-alert-env    # deletes the EC2 instance, nginx, URL - everything
```

Also delete the RDS instance if you created one (see `aws-rds-setup.md`),
and the S3 bucket EB created (named `elasticbeanstalk-ap-south-1-<account>`)
can be emptied/deleted from the S3 console.

---

# Option B: plain EC2 (fallback, brief)

If EB is unavailable, the manual version of what EB automates:

1. **Launch instance:** EC2 console → Launch → Amazon Linux 2023, t3.micro
   (free tier), create a key pair, security group allowing ports **22** (SSH,
   your IP only) and **80** (HTTP, anywhere).
2. **Install and run the app:**
   ```bash
   ssh -i key.pem ec2-user@<public-ip>
   sudo dnf install -y python3.12 python3.12-pip git nginx
   git clone <your-repo-url> && cd disaster-alert
   pip3.12 install -r requirements.txt
   JWT_SECRET=<random> nohup python3.12 -m gunicorn app:app -b 127.0.0.1:8000 &
   ```
3. **Put nginx in front** (so the app is on port 80): add to
   `/etc/nginx/conf.d/app.conf`:
   ```
   server { listen 80; location / { proxy_pass http://127.0.0.1:8000; } }
   ```
   then `sudo systemctl enable --now nginx`.
4. Visit `http://<public-ip>`. Terminate the instance from the console when done.
