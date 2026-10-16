"""
Quick smoke test: connects to whatever DynamoDB DYNAMODB_ENDPOINT points at,
lists tables, and prints useful diagnostics.

Usage:
    python scripts/check_dynamo.py
"""
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telemetryx.settings")
django.setup()

from apps.telemetry.dynamo import dynamo_client  # noqa: E402
from django.conf import settings                 # noqa: E402


def main():
    print(f"Region:   {settings.AWS_REGION}")
    print(f"Endpoint: {settings.DYNAMODB_ENDPOINT or '(real AWS)'}")
    print(f"Table:    {settings.DYNAMODB_TABLE}")
    print()

    client = dynamo_client()
    try:
        tables = client.list_tables().get("TableNames", [])
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"Tables visible: {tables or '(none)'}")

    if settings.DYNAMODB_TABLE in tables:
        desc = client.describe_table(TableName=settings.DYNAMODB_TABLE)["Table"]
        print(f"\n'{settings.DYNAMODB_TABLE}' status: {desc['TableStatus']}")
        print(f"  Key schema: {desc['KeySchema']}")
        ttl = client.describe_time_to_live(TableName=settings.DYNAMODB_TABLE)
        print(f"  TTL: {ttl['TimeToLiveDescription']}")
    else:
        print(f"\nTable '{settings.DYNAMODB_TABLE}' not found. "
              f"Run: python manage.py init_dynamo")


if __name__ == "__main__":
    main()