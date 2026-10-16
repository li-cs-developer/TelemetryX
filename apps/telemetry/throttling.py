"""
Per-VIN and per-IP throttling for the ingestion endpoint.

We pull the VIN from the raw request body because DRF's throttle() runs
before validated_data is available.
"""
import json
from rest_framework.throttling import SimpleRateThrottle


class PerVinThrottle(SimpleRateThrottle):
    scope = "per_vin"

    def get_cache_key(self, request, view):
        vin = ""
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            vin = body.get("vin", "")
        except (ValueError, UnicodeDecodeError):
            vin = ""
        if not vin:
            # If we can't identify the VIN, fall back to IP so the caller
            # is still limited rather than unmetered.
            vin = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": vin}


class PerIpThrottle(SimpleRateThrottle):
    scope = "per_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }