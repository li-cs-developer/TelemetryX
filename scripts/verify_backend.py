"""
End-to-end backend verification for TelemetryX.
Runs every check that matters and prints a PASS/FAIL report.

Usage:
    python scripts/verify_backend.py
"""
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telemetryx.settings")
django.setup()

from django.conf import settings                             # noqa: E402
from django.db import connection                             # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from botocore.exceptions import ClientError                  # noqa: E402

from apps.accounts.models import Organization, User          # noqa: E402
from apps.billing.models import Plan, Subscription           # noqa: E402
from apps.fleet.models import Driver, Vehicle                # noqa: E402
from apps.telemetry.dynamo import (                          # noqa: E402
    dynamo_client, telemetry_table,
)
from apps.telemetry.services import (                        # noqa: E402
    write_telemetry, get_latest_ping,
)


PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results = []


def record(status, name, detail=""):
    results.append((status, name, detail))
    icon = {"PASS": "[+]", "FAIL": "[X]", "WARN": "[!]"}[status]
    line = f"{icon} {name}"
    if detail:
        line += f"  —  {detail}"
    print(line)


# ---------------------------------------------------------------------------
# 1. MySQL connectivity
# ---------------------------------------------------------------------------
try:
    with connection.cursor() as c:
        c.execute("SELECT 1")
        c.fetchone()
    record(PASS, "MySQL connection",
           f"{connection.settings_dict['USER']}@{connection.settings_dict['HOST']}:"
           f"{connection.settings_dict['PORT']}/{connection.settings_dict['NAME']}")
except Exception as e:
    record(FAIL, "MySQL connection", f"{type(e).__name__}: {e}")
    print("\nCannot continue without MySQL. Fix the DATABASE_URL in .env.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 2. Migrations applied
# ---------------------------------------------------------------------------
try:
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    if not plan:
        record(PASS, "Migrations", "all applied")
    else:
        record(FAIL, "Migrations",
               f"{len(plan)} unapplied: run `python manage.py migrate`")
except Exception as e:
    record(FAIL, "Migrations", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 3. Seed data present
# ---------------------------------------------------------------------------
org = Organization.objects.first()
if org:
    record(PASS, "Organization", f"{org.slug} ({org.name})")
else:
    record(FAIL, "Organization", "none found: run `python scripts/seed.py`")

vehicle = Vehicle.objects.first()
if vehicle:
    record(PASS, "Vehicle", f"{vehicle.license_plate} {vehicle.vin}")
else:
    record(FAIL, "Vehicle", "none found: run `python scripts/seed.py`")

driver = Driver.objects.first()
if driver:
    record(PASS, "Driver", f"{driver.name} -> {driver.assigned_vehicle}")
else:
    record(FAIL, "Driver", "none found: run `python scripts/seed.py`")

if Plan.objects.exists():
    codes = ", ".join(p.code for p in Plan.objects.all())
    record(PASS, "Plans", codes)
else:
    record(FAIL, "Plans", "none found: run `python manage.py init_plans`")

if Subscription.objects.exists():
    for s in Subscription.objects.all():
        record(PASS, "Subscription",
               f"{s.organization.slug} -> {s.plan.code} ({s.status})")
else:
    record(WARN, "Subscription", "none: first save of a Vehicle will create one")


# ---------------------------------------------------------------------------
# 4. Users: at least one can reach /dashboard and one can reach /admin
# ---------------------------------------------------------------------------
has_dashboard_user = User.objects.filter(
    organization__isnull=False, role__in=["owner", "manager", "viewer"]
).exists()
has_admin_user = User.objects.filter(is_superuser=True, is_staff=True).exists()

if has_dashboard_user:
    u = User.objects.filter(organization__isnull=False).first()
    record(PASS, "Dashboard-capable user", f"{u.username} ({u.role})")
else:
    record(FAIL, "Dashboard-capable user",
           "no user with an organization: run manage_admin.py unblock <user>")

if has_admin_user:
    u = User.objects.filter(is_superuser=True).first()
    record(PASS, "Admin-capable user", u.username)
else:
    record(FAIL, "Admin-capable user",
           "no superuser: run `python manage.py createsuperuser`")


# ---------------------------------------------------------------------------
# 5. DynamoDB connection
# ---------------------------------------------------------------------------
try:
    client = dynamo_client()
    tables = client.list_tables().get("TableNames", [])
    if settings.DYNAMODB_TABLE in tables:
        record(PASS, "DynamoDB table", settings.DYNAMODB_TABLE)
    else:
        record(FAIL, "DynamoDB table",
               f"'{settings.DYNAMODB_TABLE}' missing: run `python manage.py init_dynamo`")
except Exception as e:
    record(FAIL, "DynamoDB connection", f"{type(e).__name__}: {e}")
    print("\nIs DynamoDB Local running on port 8000?")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 6. DynamoDB TTL status
# ---------------------------------------------------------------------------
try:
    ttl = client.describe_time_to_live(TableName=settings.DYNAMODB_TABLE)
    status = ttl.get("TimeToLiveDescription", {}).get("TimeToLiveStatus")
    if status == "ENABLED":
        record(PASS, "DynamoDB TTL", "enabled on ttl_epoch")
    elif status in ("ENABLING", "DISABLING"):
        record(WARN, "DynamoDB TTL", f"status={status}")
    else:
        record(WARN, "DynamoDB TTL", f"status={status}")
except Exception as e:
    record(WARN, "DynamoDB TTL", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 7. Round-trip DynamoDB write/read for the seeded vehicle
# ---------------------------------------------------------------------------
if vehicle:
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        write_telemetry(
            vin=vehicle.vin,
            timestamp=now,
            lat=37.7749, lng=-122.4194,
            speed=42.0, engine_temp=90.0, fuel_pct=50.0,
        )
        latest = get_latest_ping(vehicle.vin)
        if latest and str(latest["pk"]) == f"VEHICLE#{vehicle.vin}":
            record(PASS, "DynamoDB write/read round-trip",
                   f"wrote+read 1 ping for {vehicle.vin}")
        else:
            record(FAIL, "DynamoDB write/read round-trip", "read returned nothing")
    except Exception as e:
        record(FAIL, "DynamoDB write/read round-trip",
               f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------------------
# 8. Geofence table + API key count
# ---------------------------------------------------------------------------
from apps.fleet.models import Geofence, VehicleApiKey  # noqa: E402

if Geofence.objects.exists():
    record(PASS, "Geofences", f"{Geofence.objects.count()} configured")
else:
    record(WARN, "Geofences", "none: run `python scripts/seed_geofences.py`")

if VehicleApiKey.objects.filter(is_active=True).exists():
    record(PASS, "Vehicle API keys",
           f"{VehicleApiKey.objects.filter(is_active=True).count()} active")
else:
    record(WARN, "Vehicle API keys",
           "none: run `python manage.py generate_vehicle_keys`")


# ---------------------------------------------------------------------------
# 9. Batch ingestion config
# ---------------------------------------------------------------------------
from django.conf import settings  # noqa: E402

record(
    PASS if settings.BATCH_INGESTION_ENABLED else WARN,
    "Batch ingestion",
    "ENABLED" if settings.BATCH_INGESTION_ENABLED else "disabled (sync path)",
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
fails = [r for r in results if r[0] == FAIL]
warns = [r for r in results if r[0] == WARN]

print()
print("=" * 60)
print(f"Summary: {len(results)} checks, "
      f"{len([r for r in results if r[0] == PASS])} pass, "
      f"{len(warns)} warn, {len(fails)} fail")
print("=" * 60)

if fails:
    print("\nFAILED CHECKS:")
    for status, name, detail in fails:
        print(f"  - {name}: {detail}")
    sys.exit(1)

print("\nAll required checks passed. Backend is ready.")