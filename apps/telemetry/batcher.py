"""
Redis-backed ingestion buffer.

Pings land in a Redis list. A scheduled Celery task drains the list in
batches of BATCH_SIZE and writes to DynamoDB via batch_writer(). One
WebSocket group_send per batch instead of one per ping.

If BATCH_INGESTION_ENABLED is False, the ingestion view writes synchronously
via services.write_telemetry() — the original path.
"""
import json
import logging
from datetime import datetime, timezone

import redis
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings

from apps.fleet.models import Vehicle
from apps.alerts.tasks import check_speed_violation, notify_zone_event
from .dynamo import telemetry_table
from .services import TTL_DAYS
from .zone_service import evaluate_geofences

log = logging.getLogger(__name__)

_redis_client = None


def _redis():
    global _redis_client
    if _redis_client is None:
        # Reuse the Redis the broker already uses
        _redis_client = redis.from_url(settings.CELERY_BROKER_URL)
    return _redis_client


def enqueue_ping(payload: dict) -> int:
    """
    Push a validated ping onto the buffer. Returns the new queue length.
    payload must be JSON-serializable (datetime converted to ISO string).
    """
    key = settings.BATCH_QUEUE_KEY
    q = _redis()
    length = q.rpush(key, json.dumps(payload, default=str))
    if length > settings.BATCH_MAX_QUEUE:
        # trim from the front (oldest) to keep the queue bounded
        q.ltrim(key, -settings.BATCH_MAX_QUEUE, -1)
        log.warning("Ping queue exceeded %d, trimmed", settings.BATCH_MAX_QUEUE)
    return length


@shared_task
def flush_ping_buffer():
    """
    Scheduled task. Pops up to BATCH_SIZE items, writes them in one DynamoDB
    batch, evaluates geofences + overspeed, publishes one WS message.
    """
    q = _redis()
    key = settings.BATCH_QUEUE_KEY

    batch = []
    for _ in range(settings.BATCH_SIZE):
        item = q.lpop(key)
        if item is None:
            break
        try:
            batch.append(json.loads(item))
        except json.JSONDecodeError:
            log.warning("Bad JSON in queue: %r", item)

    if not batch:
        return

    # ---- 1. DynamoDB batch write ----
    table = telemetry_table()
    with table.batch_writer() as writer:
        for p in batch:
            ts = datetime.fromisoformat(p["timestamp"])
            ttl = int(ts.timestamp()) + TTL_DAYS * 86400
            writer.put_item(Item={
                "pk": f"VEHICLE#{p['vin']}",
                "sk": f"TS#{ts.astimezone(timezone.utc).isoformat()}",
                "lat": str(p["lat"]),
                "lng": str(p["lng"]),
                "speed_mph": str(p["speed"]),
                "engine_temp_c": str(p["engine_temp"]),
                "ttl_epoch": ttl,
                **({"fuel_pct": str(p["fuel_pct"])} if "fuel_pct" in p else {}),
            })

    # ---- 2. Group by vehicle for side-effects ----
    by_vin: dict[str, list[dict]] = {}
    for p in batch:
        by_vin.setdefault(p["vin"], []).append(p)

    vehicles = {
        v.vin: v
        for v in Vehicle.objects.filter(vin__in=by_vin.keys()).select_related("organization")
    }

    ws_updates = []
    for vin, pings in by_vin.items():
        vehicle = vehicles.get(vin)
        if not vehicle:
            continue
        # Use the last ping for WS + geofence (current position)
        last = pings[-1]

        # Geofence evaluation
        try:
            for ev in evaluate_geofences(vehicle, last["lat"], last["lng"]):
                notify_zone_event.delay(ev.id)
        except Exception:
            log.exception("Geofence evaluation failed for %s", vin)

        # Overspeed check on the last speed
        check_speed_violation.delay(vin, last["speed"])

        ws_updates.append({
            "vin": vin,
            "plate": vehicle.license_plate,
            "lat": float(last["lat"]),
            "lng": float(last["lng"]),
            "speed": float(last["speed"]),
        })

    # ---- 3. One WS message per vehicle (not per ping) ----
    channel_layer = get_channel_layer()
    for update in ws_updates:
        async_to_sync(channel_layer.group_send)(
            f"org_{vehicles[update['vin']].organization_id}",
            {"type": "telemetry.update", "payload": update},
        )