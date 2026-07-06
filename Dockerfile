# Dockerfile
# -----------------------------------------------------------------------------
# Builds a container image of the whole app. The same image runs on a laptop,
# in docker-compose (with Postgres), or on any cloud that runs containers.
#
# Build:  docker build -t disaster-alert .
# Run:    docker run -p 8000:8000 disaster-alert
# -----------------------------------------------------------------------------

# "slim" = Debian with just enough to run Python; much smaller than the full image.
FROM python:3.12-slim

# Everything happens inside /app in the container.
WORKDIR /app

# Copy ONLY requirements first: Docker caches each step, so as long as
# requirements.txt is unchanged, rebuilding after a code edit skips the slow
# pip install step entirely.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the source code.
COPY . .

# Document the port the app listens on (docker run -p maps it to the host).
EXPOSE 8000

# gunicorn = production WSGI server (Flask's built-in server is dev-only).
# "app:app" means: in module app.py, use the object named "app".
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
