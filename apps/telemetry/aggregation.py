"""
Nightly rollup: raw DynamoDB pings → MySQL DailyDriverSummary + UsageRecord.
Runs on Celery beat. Idempotent for a given date (update_or_create).
"""
from datetime import datetime, timedelta, timezone

from celery import shared_task
from django.db.models import Count

from apps.billing.models import UsageRecord
from apps.billing.services import get_or_create_subscription
from apps.fleet.models import Driver, Vehicle

from .services import get_route

# Rough conversion constant; fine for a learning project.
PING_INTERVAL_SECONDS = 3
METERS_PER_MILE = 1609.34


def _haversine_miles(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, asin, sqrt
    R = 6371000  # meters
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * asin(sqrt(a))


@shared_task
def rollup_yesterday():
    """
    Aggregate yesterday's telemetry for every active vehicle.
    Writes DailyDriverSummary per driver and a single UsageRecord per org.
    """
    now = datetime.now(timezone.utc)
    day_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    org_ping_totals = {}

    for vehicle in Vehicle.objects.select_related("organization").filter(is_active=True):
        items = get_route(vehicle.vin, day_start, day_end, limit=20000)
        if not items:
            continue

        # Sort chronologically (DynamoDB already returns in order thanks to sk)
        speeds = [float(i["speed_mph"]) for i in items]
        miles = 0.0
        for a, b in zip(items, items[1:]):
            miles += _haversine_miles(
                float(a["lat"]), float(a["lng"]),
                float(b["lat"]), float(b["lng"]),
            ) / METERS_PER_MILE

        overspeed = sum(1 for s in speeds if s > 80)

        driver = getattr(vehicle, "driver", None)
        if driver:
            from .models import DailyDriverSummary
            DailyDriverSummary.objects.update_or_create(
                driver=driver,
                date=day_start.date(),
                defaults={
                    "organization": vehicle.organization,
                    "miles_driven": round(miles, 2),
                    "avg_speed": round(sum(speeds) / len(speeds), 2),
                    "max_speed": round(max(speeds), 2),
                    "overspeed_count": overspeed,
                    "pings_seen": len(items),
                },
            )

        org_ping_totals.setdefault(vehicle.organization_id, 0)
        org_ping_totals[vehicle.organization_id] += len(items)

    # One UsageRecord per org
    for org_id, total in org_ping_totals.items():
        vehicle_count = Vehicle.objects.filter(
            organization_id=org_id, is_active=True
        ).count()
        UsageRecord.objects.update_or_create(
            organization_id=org_id,
            date=day_start.date(),
            defaults={"pings_ingested": total, "active_vehicles": vehicle_count},
        )