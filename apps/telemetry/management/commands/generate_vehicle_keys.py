import secrets

from django.core.management.base import BaseCommand

from apps.fleet.models import Vehicle, VehicleApiKey
from apps.telemetry.auth import hash_api_key


class Command(BaseCommand):
    help = "Generate (or rotate) an API key for each vehicle. Prints the raw key once."

    def add_arguments(self, parser):
        parser.add_argument("--vin", help="Only generate for this VIN")
        parser.add_argument("--rotate", action="store_true",
                            help="Replace existing keys")

    def handle(self, *args, **options):
        qs = Vehicle.objects.filter(is_active=True)
        if options.get("vin"):
            qs = qs.filter(vin=options["vin"])

        if not qs.exists():
            self.stdout.write(self.style.ERROR("No matching vehicles."))
            return

        for v in qs:
            existing = VehicleApiKey.objects.filter(vehicle=v).first()
            if existing and not options["rotate"]:
                self.stdout.write(
                    f"{v.license_plate} ({v.vin}): key exists, "
                    f"skip (use --rotate to replace)"
                )
                continue

            if existing:
                existing.delete()

            raw = secrets.token_urlsafe(32)
            VehicleApiKey.objects.create(
                vehicle=v,
                key_hash=hash_api_key(raw),
                label="default",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(
                f"{v.license_plate} ({v.vin}): {raw}"
            ))

        self.stdout.write(self.style.WARNING(
            "Raw keys shown ONCE. Store them now; they cannot be recovered."
        ))