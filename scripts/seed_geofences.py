"""
Create two sample geofences for the Acme org:
 - HQ (restricted — entering is normal, exiting is a problem)
 - Depot (restricted — entering is a problem)
Run: python scripts/seed_geofences.py
"""
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telemetryx.settings")
django.setup()

from apps.accounts.models import Organization
from apps.fleet.models import Geofence


def main():
    org = Organization.objects.first()
    if not org:
        print("No org found. Run scripts/seed.py first.")
        sys.exit(1)

    Geofence.objects.get_or_create(
        organization=org, name="Depot (restricted)",
        defaults={
            "center_lat": 37.7749, "center_lng": -122.4194,
            "radius_meters": 1500, "is_restricted": True,
        },
    )
    Geofence.objects.get_or_create(
        organization=org, name="Downtown (approved)",
        defaults={
            "center_lat": 37.7790, "center_lng": -122.4140,
            "radius_meters": 3000, "is_restricted": False,
        },
    )
    print(f"Seeded geofences for {org.slug}:")
    for gf in Geofence.objects.filter(organization=org):
        print(f"  - {gf.name} ({gf.radius_meters:.0f}m)")


if __name__ == "__main__":
    main()