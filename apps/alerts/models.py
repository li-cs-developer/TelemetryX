from django.db import models
from apps.fleet.models import Driver, Vehicle


class SafetyEvent(models.Model):
    KIND_CHOICES = [
        ("overspeed", "Overspeed"),
        ("harsh_brake", "Harsh Brake"),
        ("idle", "Excessive Idle"),
    ]
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="safety_events",
    )
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="safety_events",
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    value = models.FloatField()
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.driver.name} - {self.kind} ({self.value})"

class AlertEmail(models.Model):
    """
    Outbound email queue. In dev, emails are recorded here but NOT sent.
    A `send_alert_email` Celery task writes the row; a real provider would
    plug in here later.
    """
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("stub", "Stub (not sent)"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    related_kind = models.CharField(max_length=30, blank=True)  # "overspeed" | "geofence"
    related_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.recipient} — {self.subject}"