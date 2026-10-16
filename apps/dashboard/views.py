from datetime import timedelta

from django.utils import timezone
from django.views.generic import DetailView, TemplateView

import json  # add this at the top of the file if not already there

from apps.accounts.mixins import OrgRequiredMixin
from apps.fleet.models import Geofence, Vehicle
from apps.telemetry.models import DailyDriverSummary
from apps.telemetry.services import get_latest_for_all, get_route


class FleetOverview(OrgRequiredMixin, TemplateView):
    template_name = "dashboard/fleet_overview.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        vehicles = Vehicle.objects.for_org(org).filter(is_active=True)
        latest = get_latest_for_all([v.vin for v in vehicles])

        ctx["vehicles_json"] = json.dumps([
            {
                "vin": v.vin,
                "plate": v.license_plate,
                "lat": float(latest[v.vin]["lat"]) if v.vin in latest else None,
                "lng": float(latest[v.vin]["lng"]) if v.vin in latest else None,
                "speed": float(latest[v.vin]["speed_mph"]) if v.vin in latest else 0,
            }
            for v in vehicles
        ])
        return ctx


class VehicleDetail(OrgRequiredMixin, DetailView):
    template_name = "dashboard/vehicle_detail.html"
    model = Vehicle
    slug_field = "vin"
    slug_url_kwarg = "vin"
    context_object_name = "vehicle"

    def get_queryset(self):
        return Vehicle.objects.for_org(self.request.user.organization)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        end = timezone.now()
        start = end - timedelta(hours=6)
        items = get_route(self.object.vin, start, end)

        ctx["route_json"] = json.dumps([
            {
                "lat": float(i["lat"]),
                "lng": float(i["lng"]),
                "speed": float(i["speed_mph"]),
                "t": i["sk"].replace("TS#", ""),
            }
            for i in items
        ])

        driver = getattr(self.object, "driver", None)
        if driver:
            summaries = (
                DailyDriverSummary.objects
                .filter(driver=driver)
                .order_by("-date")[:30]
            )
            ctx["trend_json"] = json.dumps([
                {"date": s.date.isoformat(),
                 "avg_speed": s.avg_speed,
                 "max_speed": s.max_speed,
                 "overspeed_count": s.overspeed_count,
                 "miles": s.miles_driven}
                for s in reversed(summaries)
            ])
        else:
            ctx["trend_json"] = json.dumps([])

        return ctx


class GeofenceManagerView(OrgRequiredMixin, TemplateView):
    template_name = "dashboard/geofences.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        qs = Geofence.objects.for_org(org)
        ctx["geofences_json"] = json.dumps([
            {
                "id": g.id,
                "name": g.name,
                "center_lat": g.center_lat,
                "center_lng": g.center_lng,
                "radius_meters": g.radius_meters,
                "is_restricted": g.is_restricted,
                "is_active": g.is_active,
            }
            for g in qs
        ])
        return ctx