"""One-time table setup. Works against DynamoDB Local or real AWS.
    python create_tables.py
Uses the same env vars as the app (DYNAMODB_ENDPOINT, AWS_REGION, table names).
"""

import boto3
from botocore.exceptions import ClientError

from app.config import settings


def _client():
    kwargs = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
    return boto3.client("dynamodb", **kwargs)


def _create(ddb, name, hash_key, range_key=None):
    key_schema = [{"AttributeName": hash_key, "KeyType": "HASH"}]
    attr_defs = [{"AttributeName": hash_key, "AttributeType": "S"}]
    if range_key:
        key_schema.append({"AttributeName": range_key, "KeyType": "RANGE"})
        attr_defs.append({"AttributeName": range_key, "AttributeType": "S"})
    try:
        ddb.create_table(
            TableName=name,
            KeySchema=key_schema,
            AttributeDefinitions=attr_defs,
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"created {name}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"{name} already exists")
        else:
            raise


if __name__ == "__main__":
    ddb = _client()
    _create(ddb, settings.urls_table, "code")
    _create(ddb, settings.counter_table, "name")
    # Clicks: PK=code, SK=ts (analytics queries by code, newest-first on ts).
    _create(ddb, settings.clicks_table, "code", range_key="ts")
