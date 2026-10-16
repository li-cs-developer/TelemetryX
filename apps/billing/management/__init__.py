from django.core.management.base import BaseCommand
from apps.billing.models import Plan

DEFAULTS = [
    # code,      name,        max_vehicles, max_pings_per_sec, price_cents, default
    ("trial",   "Trial",      3,            2,                 0,           True),
    ("starter", "Starter",    25,           10,                9900,        False),
    ("scale",   "Scale",      250,          60,                49900,       False),
]


class Command(BaseCommand):
    help = "Seed default plans (idempotent)."

    def handle(self, *args, **options):
        for code, name, mv, mpps, price, default in DEFAULTS:
            Plan.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "max_vehicles": mv,
                    "max_pings_per_second": mpps,
                    "monthly_price_cents": price,
                    "is_default": default,
                },
            )
        self.stdout.write(self.style.SUCCESS("Plans seeded."))