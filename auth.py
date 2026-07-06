# auth.py
# -----------------------------------------------------------------------------
# JWT (JSON Web Token) authentication helpers.
#
# How JWT auth works here:
#   1. On register/login we CREATE a token: a signed string containing the
#      user's id and an expiry time. Signing uses a secret only the server
#      knows, so nobody can forge or tamper with a token.
#   2. The browser sends the token back on every protected request in the
#      header:  Authorization: Bearer <token>
#   3. The @token_required decorator VERIFIES the signature and expiry, loads
#      the matching user from the DB, and hands it to the route function.
#
# The server stores no session state - the token itself proves who you are.
# That is why JWT is popular for REST APIs: any server instance can verify it.
# -----------------------------------------------------------------------------

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt  # the PyJWT library
from flask import jsonify, request

from models import db, User

# The signing secret comes from an environment variable in production.
# The fallback keeps local development zero-setup, but we warn loudly.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
if JWT_SECRET == "dev-secret-change-me":
    print("WARNING: using the default JWT secret. Set JWT_SECRET in production!")

TOKEN_LIFETIME = timedelta(hours=24)  # tokens expire after a day


def create_token(user_id):
    """Create a signed JWT containing the user's id and an expiry time."""
    payload = {
        "user_id": user_id,
        # "exp" is a standard JWT claim - PyJWT rejects the token automatically
        # once this moment has passed.
        "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME,
    }
    # HS256 = HMAC-SHA256, the simplest standard signing algorithm.
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def token_required(view_func):
    """Decorator for routes that need a logged-in user.

    Usage:
        @app.route("/api/reports", methods=["POST"])
        @token_required
        def create_report(current_user):   # <- the verified User is passed in
            ...

    Returns 401 (Unauthorized) with a JSON error if the token is missing,
    expired, or invalid.
    """
    @wraps(view_func)  # keeps the original function's name (Flask needs unique names)
    def wrapper(*args, **kwargs):
        # Expect a header like:  Authorization: Bearer eyJhbGciOi...
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing token. Log in first."}), 401
        token = auth_header.split(" ", 1)[1]

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired. Log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401

        user = db.session.get(User, payload["user_id"])
        if user is None:  # token is valid but the account no longer exists
            return jsonify({"error": "User not found."}), 401

        # Pass the authenticated user into the route as the first argument.
        return view_func(user, *args, **kwargs)

    return wrapper
