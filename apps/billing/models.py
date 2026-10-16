from django.db import models
from apps.accounts.models import Organization


class Plan(models.Model):
    """
    A plan defines the fleet size cap for an org. Stub-level: no payment provider.
    """
    code = models.SlugField(unique=True)          # e.g. "trial", "starter", "scale"
    name = models.CharField(max_length=80)
    max_vehicles = models.PositiveIntegerField(default=3)
    max_pings_per_second = models.PositiveIntegerField(default=5)
    monthly_price_cents = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["monthly_price_cents"]

    def __str__(self):
        return f"{self.name} (≤{self.max_vehicles} vans)"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ("trialing", "Trialing"),
        ("active", "Active"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
    ]
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="subscription",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="trialing")
    started_at = models.DateTimeField(auto_now_add=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.organization.slug} → {self.plan.code} ({self.status})"

    # -------- Enforcement helpers --------

    def is_writable(self) -> bool:
        return self.status in ("trialing", "active")

    def vehicle_count(self) -> int:
        return self.organization.vehicles.filter(is_active=True).count()

    def has_capacity_for_new_vehicle(self) -> bool:
        return self.vehicle_count() < self.plan.max_vehicles


class UsageRecord(models.Model):
    """
    Daily snapshot written by the aggregation job (see telemetry/aggregation.py).
    Purely for the dashboard to render usage vs. plan limits.
    """
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="usage_records",
    )
    date = models.DateField()
    pings_ingested = models.PositiveIntegerField(default=0)
    active_vehicles = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("organization", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.organization.slug} {self.date}"