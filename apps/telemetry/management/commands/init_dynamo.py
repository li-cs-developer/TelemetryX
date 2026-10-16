from django.core.management.base import BaseCommand
from apps.telemetry.dynamo import ensure_telemetry_table


class Command(BaseCommand):
    help = "Create the DynamoDB telemetry table (idempotent) and enable TTL."

    def handle(self, *args, **options):
        ensure_telemetry_table()
        self.stdout.write(self.style.SUCCESS("FleetTelemetry table ready."))