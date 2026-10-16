from django.urls import path
from .views import FleetOverview, VehicleDetail, GeofenceManagerView

urlpatterns = [
    path("", FleetOverview.as_view(), name="fleet-overview"),
    path("vehicles/<str:vin>/", VehicleDetail.as_view(), name="vehicle-detail"),
    path("geofences/", GeofenceManagerView.as_view(), name="geofence-manager"),
]