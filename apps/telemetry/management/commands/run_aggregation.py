from django.core.management.base import BaseCommand
from apps.telemetry.aggregation import rollup_yesterday


class Command(BaseCommand):
    help = "Manually run the nightly driver rollup job (bypasses Celery beat)."

    def handle(self, *args, **options):
        rollup_yesterday()
        self.stdout.write(self.style.SUCCESS("Rollup complete."))