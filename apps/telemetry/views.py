from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.tasks import check_speed_violation, notify_zone_event
from apps.accounts.permissions import IsManager
from apps.fleet.models import Geofence, Vehicle

from .auth import VehicleApiKeyAuthentication
from .batcher import enqueue_ping
from .serializers import GeofenceSerializer, TelemetryPingSerializer
from .services import get_latest_for_all, write_telemetry
from .throttling import PerIpThrottle, PerVinThrottle
from .zone_service import evaluate_geofences


class TelemetryIngestView(APIView):
    authentication_classes = [VehicleApiKeyAuthentication]
    permission_classes = []
    throttle_classes = [PerVinThrottle, PerIpThrottle]

    def post(self, request):
        ser = TelemetryPingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Auth: request.auth is a VehicleApiKey instance
        bound_vehicle = request.auth.vehicle
        if bound_vehicle.vin != data["vin"]:
            return Response(
                {"detail": "API key does not match VIN"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not bound_vehicle.is_active:
            return Response(
                {"detail": "Vehicle is inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ---- Batch path ----
        if settings.BATCH_INGESTION_ENABLED:
            enqueue_ping({
                "vin": data["vin"],
                "timestamp": data["timestamp"].isoformat(),
                "lat": data["lat"],
                "lng": data["lng"],
                "speed": data["speed"],
                "engine_temp": data["engine_temp"],
                **({"fuel_pct": data["fuel_pct"]} if data.get("fuel_pct") is not None else {}),
            })
            return Response({"ok": True, "queued": True},
                            status=status.HTTP_202_ACCEPTED)

        # ---- Sync path (default) ----
        write_telemetry(
            vin=data["vin"],
            timestamp=data["timestamp"],
            lat=data["lat"],
            lng=data["lng"],
            speed=data["speed"],
            engine_temp=data["engine_temp"],
            fuel_pct=data.get("fuel_pct"),
        )

        check_speed_violation.delay(data["vin"], data["speed"])

        # Geofence transitions
        for ev in evaluate_geofences(bound_vehicle, data["lat"], data["lng"]):
            notify_zone_event.delay(ev.id)

        # Push WS
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"org_{bound_vehicle.organization_id}",
            {
                "type": "telemetry.update",
                "payload": {
                    "vin": data["vin"],
                    "plate": bound_vehicle.license_plate,
                    "lat": float(data["lat"]),
                    "lng": float(data["lng"]),
                    "speed": float(data["speed"]),
                },
            },
        )

        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


class LivePositionsView(LoginRequiredMixin, APIView):
    """Initial snapshot for the dashboard. WebSocket carries the live stream."""

    def get(self, request):
        org = request.user.organization
        vehicles = Vehicle.objects.for_org(org).filter(is_active=True)
        latest = get_latest_for_all([v.vin for v in vehicles])
        out = []
        for v in vehicles:
            item = latest.get(v.vin)
            out.append({
                "vin": v.vin,
                "plate": v.license_plate,
                "lat": float(item["lat"]) if item else None,
                "lng": float(item["lng"]) if item else None,
                "speed": float(item["speed_mph"]) if item else 0,
            })
        return Response({"vehicles": out})


class GeofenceListCreateView(LoginRequiredMixin, APIView):
    """
    GET  — list geofences in the user's org.
    POST — create a new geofence (managers only).
    """
    permission_classes = [IsManager]

    def get(self, request):
        qs = Geofence.objects.for_org(request.user.organization)
        return Response(GeofenceSerializer(qs, many=True).data)

    def post(self, request):
        ser = GeofenceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        gf = ser.save(organization=request.user.organization)
        return Response(GeofenceSerializer(gf).data, status=status.HTTP_201_CREATED)


class GeofenceDetailView(LoginRequiredMixin, APIView):
    permission_classes = [IsManager]

    def _get(self, request, pk):
        try:
            return Geofence.objects.for_org(request.user.organization).get(pk=pk)
        except Geofence.DoesNotExist:
            return None

    def get(self, request, pk):
        gf = self._get(request, pk)
        if not gf:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(GeofenceSerializer(gf).data)

    def patch(self, request, pk):
        gf = self._get(request, pk)
        if not gf:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = GeofenceSerializer(gf, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        gf = self._get(request, pk)
        if not gf:
            return Response(status=status.HTTP_404_NOT_FOUND)
        gf.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.db import connection
        from .dynamo import dynamo_client
        checks = {}

        try:
            with connection.cursor() as c:
                c.execute("SELECT 1")
                c.fetchone()
            checks["mysql"] = "ok"
        except Exception as e:
            checks["mysql"] = f"error: {type(e).__name__}"

        try:
            dynamo_client().list_tables()
            checks["dynamodb"] = "ok"
        except Exception as e:
            checks["dynamodb"] = f"error: {type(e).__name__}"

        ok = all(v == "ok" for v in checks.values())
        return Response(
            {"status": "ok" if ok else "degraded", "checks": checks},
            status=200 if ok else 503,
        )