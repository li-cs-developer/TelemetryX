from datetime import datetime, timezone
from decimal import Decimal

from .dynamo import telemetry_table

TTL_DAYS = 90


def _pk(vin: str) -> str:
    return f"VEHICLE#{vin}"


def _sk(ts: datetime) -> str:
    return f"TS#{ts.astimezone(timezone.utc).isoformat()}"


def write_telemetry(*, vin, timestamp, lat, lng, speed, engine_temp, fuel_pct=None):
    ttl = int(timestamp.timestamp()) + TTL_DAYS * 86400
    item = {
        "pk": _pk(vin),
        "sk": _sk(timestamp),
        "lat": Decimal(str(lat)),
        "lng": Decimal(str(lng)),
        "speed_mph": Decimal(str(speed)),
        "engine_temp_c": Decimal(str(engine_temp)),
        "ttl_epoch": ttl,
    }
    if fuel_pct is not None:
        item["fuel_pct"] = Decimal(str(fuel_pct))
    telemetry_table().put_item(Item=item)


def get_latest_ping(vin):
    resp = telemetry_table().query(
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": _pk(vin)},
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_latest_for_all(vins):
    return {vin: item for vin in vins if (item := get_latest_ping(vin))}


def get_route(vin, start: datetime, end: datetime, limit=2000):
    resp = telemetry_table().query(
        KeyConditionExpression="pk = :pk AND sk BETWEEN :a AND :b",
        ExpressionAttributeValues={
            ":pk": _pk(vin),
            ":a": _sk(start),
            ":b": _sk(end),
        },
        ScanIndexForward=True,
        Limit=limit,
    )
    return resp.get("Items", [])