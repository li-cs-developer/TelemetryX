from rest_framework import serializers

from apps.fleet.models import Geofence


class TelemetryPingSerializer(serializers.Serializer):
    vin = serializers.CharField(max_length=17)
    timestamp = serializers.DateTimeField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    speed = serializers.FloatField()
    engine_temp = serializers.FloatField()
    fuel_pct = serializers.FloatField(required=False, allow_null=True)

    def validate_vin(self, value):
        return value.strip()


class GeofenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Geofence
        fields = [
            "id", "name", "center_lat", "center_lng", "radius_meters",
            "is_restricted", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]