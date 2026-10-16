from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.fleet.models import Vehicle
from .models import SafetyEvent, AlertEmail

SPEED_LIMIT_MPH = 80


def _manager_email(org) -> str:
    """Return a manager email for the org, or a stub fallback."""
    from apps.accounts.models import User
    u = (
        User.objects
        .filter(organization=org, role__in=["owner", "manager"])
        .order_by("id")
        .first()
    )
    if u and u.email:
        return u.email
    return "ops@example.com"


def _stub_email(*, recipient, subject, body, related_kind="", related_id=None):
    """
    Record an AlertEmail row instead of actually sending anything.
    The Celery worker log will show the call. This is the stub.
    """
    row = AlertEmail.objects.create(
        recipient=recipient,
        subject=subject,
        body=body,
        status="stub",
        related_kind=related_kind,
        related_id=related_id,
        sent_at=timezone.now(),
    )
    print(f"[STUB EMAIL] to={recipient} subject={subject!r} "
          f"(row_id={row.id}, kind={related_kind})")
    return row


@shared_task
def check_speed_violation(vin: str, speed: float):
    if speed <= SPEED_LIMIT_MPH:
        return

    try:
        vehicle = Vehicle.objects.select_related("driver", "organization").get(vin=vin)
    except Vehicle.DoesNotExist:
        return

    driver = getattr(vehicle, "driver", None)
    if driver is None:
        return

    event = SafetyEvent.objects.create(
        driver=driver,
        vehicle=vehicle,
        kind="overspeed",
        value=float(speed),
        occurred_at=timezone.now(),
    )
    driver.safety_score = max(0, driver.safety_score - 2)
    driver.save(update_fields=["safety_score"])

    _stub_email(
        recipient=_manager_email(vehicle.organization),
        subject=f"Overspeed: {vehicle.license_plate} at {speed:.1f} mph",
        body=(
            f"Vehicle {vehicle.license_plate} ({vehicle.vin}) driven by "
            f"{driver.name} was recorded at {speed:.1f} mph "
            f"(limit {SPEED_LIMIT_MPH} mph)."
        ),
        related_kind="overspeed",
        related_id=event.id,
    )


@shared_task
def notify_zone_event(zone_event_id: int):
    """Called for each ZoneEvent created during ingestion."""
    from apps.fleet.models import ZoneEvent

    try:
        ev = ZoneEvent.objects.select_related(
            "vehicle__organization", "geofence",
        ).get(id=zone_event_id)
    except ZoneEvent.DoesNotExist:
        return

    gf = ev.geofence
    if ev.kind == "entered" and gf.is_restricted:
        subject = f"Entered restricted zone: {gf.name}"
    elif ev.kind == "exited" and not gf.is_restricted:
        subject = f"Left approved zone: {gf.name}"
    else:
        return  # no alert for the "safe" direction

    _stub_email(
        recipient=_manager_email(ev.vehicle.organization),
        subject=f"{subject} — {ev.vehicle.license_plate}",
        body=(
            f"Vehicle {ev.vehicle.license_plate} ({ev.vehicle.vin}) "
            f"{ev.kind} geofence '{gf.name}' at "
            f"{ev.lat:.5f}, {ev.lng:.5f} on {ev.occurred_at.isoformat()}."
        ),
        related_kind="geofence",
        related_id=ev.id,
    )