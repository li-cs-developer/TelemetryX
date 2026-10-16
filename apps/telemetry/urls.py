from django.urls import path

from .views import (
    TelemetryIngestView, LivePositionsView,
    GeofenceListCreateView, GeofenceDetailView,
    HealthCheckView,
)

urlpatterns = [
    path("telemetry/", TelemetryIngestView.as_view(), name="telemetry-ingest"),
    path("live/", LivePositionsView.as_view(), name="live-positions"),
    path("geofences/", GeofenceListCreateView.as_view(), name="geofence-list"),
    path("geofences/<int:pk>/", GeofenceDetailView.as_view(), name="geofence-detail"),
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
]