"""
Evaluate geofence transitions and record ZoneEvents.

Called from ingestion after a ping is written. Compares the new ping against
the vehicle's last known geofence state (stored in DynamoDB as a "last_zone"
attribute) so we only write ZoneEvents on transitions, not every ping.
"""
from datetime import datetime, timezone

from apps.fleet.geofence import is_inside
from apps.fleet.models import Geofence, Vehicle, ZoneEvent


def evaluate_geofences(vehicle: Vehicle, lat: float, lng: float) -> list[ZoneEvent]:
    """
    For each active geofence in the vehicle's org, determine inside/outside.
    We don't persist per-ping zone state; instead we look at the most recent
    ZoneEvent per (vehicle, geofence) and decide if the new ping flips it.
    """
    events: list[ZoneEvent] = []
    now = datetime.now(timezone.utc)

    geofences = Geofence.objects.filter(
        organization=vehicle.organization, is_active=True,
    )

    for gf in geofences:
        now_inside = is_inside(lat, lng, gf)

        # Find the most recent known state for this pair
        last_event = (
            ZoneEvent.objects
            .filter(vehicle=vehicle, geofence=gf)
            .order_by("-occurred_at")
            .first()
        )

        if last_event is None:
            # First observation: record an entry only if inside
            if now_inside:
                events.append(ZoneEvent.objects.create(
                    vehicle=vehicle, geofence=gf,
                    kind="entered", occurred_at=now,
                    lat=lat, lng=lng,
                ))
            continue

        was_inside = (last_event.kind == "entered")

        if now_inside and not was_inside:
            events.append(ZoneEvent.objects.create(
                vehicle=vehicle, geofence=gf,
                kind="entered", occurred_at=now,
                lat=lat, lng=lng,
            ))
        elif not now_inside and was_inside:
            events.append(ZoneEvent.objects.create(
                vehicle=vehicle, geofence=gf,
                kind="exited", occurred_at=now,
                lat=lat, lng=lng,
            ))
        # else: no transition, no event

    return events