from django.db import models
from apps.accounts.models import Organization
from apps.fleet.models import Driver


class DailyDriverSummary(models.Model):
    """
    Warm-store rollup. Written nightly from DynamoDB raw pings.
    Dashboards render long-term trends from here — no DynamoDB reads.
    """
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="daily_summaries",
    )
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="daily_summaries",
    )
    date = models.DateField()
    miles_driven = models.FloatField(default=0)
    avg_speed = models.FloatField(default=0)
    max_speed = models.FloatField(default=0)
    overspeed_count = models.PositiveIntegerField(default=0)
    pings_seen = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("driver", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.driver.name} {self.date}"