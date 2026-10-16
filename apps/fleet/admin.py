from django.contrib import admin
from .models import (
    Vehicle, Driver, MaintenanceLog,
    Geofence, ZoneEvent, VehicleApiKey,
)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("license_plate", "vin", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("vin", "license_plate")


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "assigned_vehicle", "safety_score")
    list_filter = ("organization",)


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "performed_at", "cost_usd")


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "center_lat", "center_lng",
                    "radius_meters", "is_restricted", "is_active")
    list_filter = ("organization", "is_restricted", "is_active")


@admin.register(ZoneEvent)
class ZoneEventAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "geofence", "kind", "occurred_at")
    list_filter = ("kind", "geofence")
    readonly_fields = ("vehicle", "geofence", "kind", "occurred_at", "lat", "lng")


@admin.register(VehicleApiKey)
class VehicleApiKeyAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "label", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    readonly_fields = ("key_hash", "created_at", "last_used_at")