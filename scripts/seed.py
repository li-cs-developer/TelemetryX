"""
Seed an Organization, User, Vehicle, Driver, and Subscription.
Run with: python scripts/seed.py
"""
import os
import sys
from pathlib import Path

import django

# Ensure the project root (parent of scripts/) is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telemetryx.settings")
django.setup()

from apps.accounts.models import Organization, User
from apps.billing.services import get_or_create_subscription
from apps.fleet.models import Driver, Vehicle

org, _ = Organization.objects.get_or_create(
    slug="acme-logistics",
    defaults={"name": "Acme Logistics"},
)

user, created = User.objects.get_or_create(
    username="ops",
    defaults={"organization": org, "role": "owner", "is_staff": True},
)
if created:
    user.set_password("ops12345")
    user.save()
    print("Created user 'ops' / password 'ops12345'")

vehicle, _ = Vehicle.objects.get_or_create(
    vin="1HGCR2F83HA000000",
    defaults={
        "organization": org,
        "license_plate": "TX-4821",
        "model_year": 2024,
        "make": "Ford",
        "model": "Transit",
    },
)

driver, _ = Driver.objects.get_or_create(
    license_number="DL-99887",
    defaults={
        "organization": org,
        "name": "Sam Rivera",
        "assigned_vehicle": vehicle,
    },
)

sub = get_or_create_subscription(org)

print(f"Org={org.name}")
print(f"User={user.username} (role={user.role})")
print(f"Vehicle={vehicle}")
print(f"Driver={driver}")
print(f"Subscription={sub}")