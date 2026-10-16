"""
DynamoDB access layer.

- When DYNAMODB_ENDPOINT is set (e.g. http://localhost:8000), boto3 talks to
  a local DynamoDB Local instance.
- When DYNAMODB_ENDPOINT is empty/None, boto3 uses the standard AWS resolution
  chain to hit real DynamoDB.
"""
import os
import boto3
from botocore.exceptions import ClientError
from django.conf import settings


def _aws_kwargs():
    kwargs = {"region_name": settings.AWS_REGION}

    if settings.DYNAMODB_ENDPOINT:
        kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT
        kwargs["aws_access_key_id"] = (
            getattr(settings, "AWS_ACCESS_KEY_ID", None)
            or os.getenv("AWS_ACCESS_KEY_ID")
            or "fakeMyKeyId"
        )
        kwargs["aws_secret_access_key"] = (
            getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
            or os.getenv("AWS_SECRET_ACCESS_KEY")
            or "fakeSecretAccessKey"
        )

    return kwargs


def dynamo_client():
    return boto3.client("dynamodb", **_aws_kwargs())


def dynamo_resource():
    return boto3.resource("dynamodb", **_aws_kwargs())


def telemetry_table():
    return dynamo_resource().Table(settings.DYNAMODB_TABLE)


def _table_exists(client) -> bool:
    try:
        client.describe_table(TableName=settings.DYNAMODB_TABLE)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def _ttl_enabled(client) -> bool:
    try:
        desc = client.describe_time_to_live(TableName=settings.DYNAMODB_TABLE)
        status = desc.get("TimeToLiveDescription", {}).get("TimeToLiveStatus")
        return status == "ENABLED"
    except ClientError:
        return False


def ensure_telemetry_table():
    """Idempotent: creates the table and enables TTL only when needed."""
    client = dynamo_client()

    if not _table_exists(client):
        client.create_table(
            TableName=settings.DYNAMODB_TABLE,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(
            TableName=settings.DYNAMODB_TABLE
        )

    if not _ttl_enabled(client):
        try:
            client.update_time_to_live(
                TableName=settings.DYNAMODB_TABLE,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": "ttl_epoch",
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ValidationException":
                raise