"""
Vehicle API key authentication for the ingestion endpoint.
"""
import hashlib
from datetime import datetime

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.fleet.models import VehicleApiKey


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class VehicleApiKeyAuthentication(authentication.BaseAuthentication):
    """
    Looks for `X-Api-Key: <raw>` and resolves it to a VehicleApiKey.
    Attaches the row to request.auth and the vehicle to request.vehicle.
    """

    def authenticate(self, request):
        raw = request.headers.get("X-Api-Key")
        if not raw:
            raise exceptions.AuthenticationFailed("Missing X-Api-Key header")

        key_hash = hash_api_key(raw)
        try:
            api_key = VehicleApiKey.objects.select_related("vehicle").get(
                key_hash=key_hash, is_active=True,
            )
        except VehicleApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key")

        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        # Returning (user, auth) — user is None here because vehicles aren't users.
        # DRF allows this; the view checks request.auth for the bound vehicle.
        return (None, api_key)

    def authenticate_header(self, request):
        return "X-Api-Key"