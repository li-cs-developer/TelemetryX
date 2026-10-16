"""
Pure-Python geofence math. No external dependencies.
"""
from math import radians, sin, cos, asin, sqrt

EARTH_RADIUS_METERS = 6371000.0


def haversine_meters(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in meters between two lat/lng points."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(a))


def is_inside(lat, lng, geofence) -> bool:
    """True if (lat, lng) is within `geofence.radius_meters` of its center."""
    d = haversine_meters(lat, lng, geofence.center_lat, geofence.center_lng)
    return d <= geofence.radius_meters