from django.db import models
from apps.accounts.models import Organization


class TenantManager(models.Manager):
    def for_org(self, org):
        return self.get_queryset().filter(organization=org)


class Vehicle(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="vehicles",
    )
    vin = models.CharField(max_length=17, unique=True)
    license_plate = models.CharField(max_length=20)
    model_year = models.IntegerField()
    make = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        ordering = ["license_plate"]

    def __str__(self):
        return f"{self.license_plate} ({self.vin[-6:]})"


class Driver(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="drivers",
    )
    name = models.CharField(max_length=100)
    license_number = models.CharField(max_length=50)
    assigned_vehicle = models.OneToOneField(
        Vehicle, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="driver",
    )
    safety_score = models.PositiveIntegerField(default=100)

    objects = TenantManager()

    def __str__(self):
        return self.name


class MaintenanceLog(models.Model):
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="maintenance_logs",
    )
    performed_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.vehicle.license_plate} @ {self.performed_at:%Y-%m-%d}"

class Geofence(models.Model):
    """
    A circular zone on the map. If `is_restricted`, entering triggers an alert.
    If not restricted, exiting triggers an alert.
    """
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="geofences",
    )
    name = models.CharField(max_length=100)
    center_lat = models.FloatField()
    center_lng = models.FloatField()
    radius_meters = models.FloatField()
    is_restricted = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.radius_meters:.0f}m)"


class ZoneEvent(models.Model):
    """
    Records a transition. Fires when a vehicle enters or exits a geofence.
    """
    KIND_CHOICES = [
        ("entered", "Entered"),
        ("exited", "Exited"),
    ]
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="zone_events",
    )
    geofence = models.ForeignKey(
        Geofence, on_delete=models.CASCADE, related_name="zone_events",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    occurred_at = models.DateTimeField()
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.vehicle.license_plate} {self.kind} {self.geofence.name}"


class VehicleApiKey(models.Model):
    """
    A device credential bound to one vehicle. Only this key can post pings
    for this VIN. The raw key is shown ONCE at creation; only the hash is stored.
    """
    vehicle = models.OneToOneField(
        Vehicle, on_delete=models.CASCADE, related_name="api_key",
    )
    key_hash = models.CharField(max_length=64, unique=True)  # sha256 hex
    label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.vehicle.license_plate} key ({self.label or 'unlabeled'})"