# serverless/notify_lambda.py
# -----------------------------------------------------------------------------
# The "who should be alerted?" logic - written once, run in TWO places:
#
#   1. LOCALLY: app.py imports find_nearby_users() and calls it as a normal
#      Python function whenever a report is created.
#   2. IN THE CLOUD: this same file is zipped and deployed as an AWS Lambda
#      function; AWS calls lambda_handler() with an event.
#
# That is the whole "serverless" idea: the code has no server of its own -
# AWS runs it on demand and we pay (nothing, at this scale) per invocation.
#
# This file deliberately imports NOTHING outside the standard library, so the
# Lambda zip is just this one file - no dependency packaging needed.
# -----------------------------------------------------------------------------

import math


def haversine_km(lat1, lng1, lat2, lng2):
    """Distance in km between two points on Earth (haversine formula).

    Treats the Earth as a sphere of radius 6371 km, which is accurate to
    ~0.5% - plenty for "is this incident near me?". This avoids needing a
    GIS database extension like PostGIS.
    """
    r = 6371  # Earth's mean radius in km
    # The formula works in radians, so convert the degree inputs first.
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    # 'a' is the square of half the straight-line chord between the points.
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    # 2*atan2(...) converts that chord into the angle across Earth's surface.
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_users(lat, lng, radius_km, users):
    """Return the users whose home location is within radius_km of (lat, lng).

    'users' is a list of plain dicts: {id, name, email, home_lat, home_lng}.
    Plain dicts (not DB objects) so this works identically inside Lambda,
    where there is no SQLAlchemy. Each match gets a 'distance_km' added.
    """
    nearby = []
    for user in users:
        if user.get("home_lat") is None or user.get("home_lng") is None:
            continue  # user never shared a home location - can't alert them
        distance = haversine_km(lat, lng, user["home_lat"], user["home_lng"])
        if distance <= radius_km:
            nearby.append({**user, "distance_km": round(distance, 2)})
    # Closest people first - they are affected the most.
    nearby.sort(key=lambda u: u["distance_km"])
    return nearby


# A tiny built-in user list so the Lambda can be demoed in the AWS console
# with just {lat, lng, radius_km} - no database wiring required. In a real
# system the handler would query RDS here instead (see Future Scope).
DEMO_USERS = [
    {"id": 1, "name": "Abhijeet", "email": "abhijeet@example.com", "home_lat": 28.61, "home_lng": 77.36},
    {"id": 2, "name": "Viyom",    "email": "viyom@example.com",    "home_lat": 28.63, "home_lng": 77.37},
    {"id": 3, "name": "Devang",   "email": "devang@example.com",   "home_lat": 28.70, "home_lng": 77.10},
]


def lambda_handler(event, context):
    """AWS Lambda entry point.

    Expected event:
      {"lat": 28.61, "lng": 77.36, "radius_km": 5, "users": [...optional...]}

    Returns which users would be alerted. We only LOG the alert here - actually
    sending SMS/email (e.g. via Amazon SNS) is listed as Future Scope.
    """
    try:
        lat = float(event["lat"])
        lng = float(event["lng"])
        radius_km = float(event.get("radius_km", 5))
    except (KeyError, TypeError, ValueError):
        return {"error": "event must contain numeric lat, lng and optional radius_km"}

    users = event.get("users", DEMO_USERS)
    alerted = find_nearby_users(lat, lng, radius_km, users)

    # print() output lands in CloudWatch Logs - this IS our "notification".
    print(f"ALERT: incident at ({lat}, {lng}) -> notifying {len(alerted)} user(s): "
          + ", ".join(u["name"] for u in alerted))

    return {"alerted_users": alerted, "count": len(alerted)}
