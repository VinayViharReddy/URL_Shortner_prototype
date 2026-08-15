"""DynamoDB persistence: the 'Sharded Database' box in the diagram.

Two concerns handled here:
  1. Atomic counter (Counters table) -> unique base10 value per shorten request.
  2. Mapping store (ShortUrls table) with conditional put for custom aliases.

DynamoDB's UpdateItem ADD is atomic, giving us collision-free counter values
across concurrent web servers without a read-modify-write race. Partitioning by
`code` distributes reads/writes evenly (hashed partition key), which is how this
scales horizontally — the 'sharding' is native to DynamoDB.
"""

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from .base62 import encode
from .config import settings


class AliasTakenError(Exception):
    """Raised when a custom alias already maps to a different URL."""


class LinkExpiredError(Exception):
    """Raised when a code exists but its expiry has passed."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UrlRepository:
    def __init__(self):
        kwargs = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint
        self._ddb = boto3.resource("dynamodb", **kwargs)
        self._urls = self._ddb.Table(settings.urls_table)
        self._counters = self._ddb.Table(settings.counter_table)

    def next_counter(self) -> int:
        """Atomically increment and return the global counter."""
        resp = self._counters.update_item(
            Key={"name": "url_counter"},
            UpdateExpression="ADD seq :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        # First-ever call returns 1; add the seed so early codes are already 7 chars.
        return settings.counter_seed + int(resp["Attributes"]["seq"])

    def create_generated(self, long_url: str, user_id: str, expiry_days: int | None = None) -> str:
        """Counter-based code. Unique by construction, so no collision check."""
        code = encode(self.next_counter())
        self._put(code, long_url, user_id, expiry_days=expiry_days)
        return code

    def create_custom(self, alias: str, long_url: str, user_id: str,
                      expiry_days: int | None = None) -> str:
        """Custom alias. Conditional put rejects an already-taken alias."""
        try:
            self._put(code=alias, long_url=long_url, user_id=user_id,
                      require_absent=True, expiry_days=expiry_days)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise AliasTakenError(alias) from e
            raise
        return alias

    def get_long_url(self, code: str) -> tuple[str, int | None] | None:
        """Read path. Returns (long_url, expires_at_epoch_or_None).

        Raises LinkExpiredError if past expiry, returns None if not found.
        We check expiry in code rather than relying on TTL alone: DynamoDB TTL
        deletion can lag hours, so an expired-but-not-yet-reaped item must still
        return 410, not redirect.
        """
        resp = self._urls.get_item(
            Key={"code": code}, ProjectionExpression="longUrl, expiresAt"
        )
        item = resp.get("Item")
        if not item:
            return None
        expires_at = item.get("expiresAt")
        if expires_at is not None and int(expires_at) <= int(_now().timestamp()):
            raise LinkExpiredError(code)
        return item["longUrl"], (int(expires_at) if expires_at is not None else None)

    def _put(self, code: str, long_url: str, user_id: str,
             require_absent: bool = False, expiry_days: int | None = None):
        now = _now()
        item = {
            "code": code,
            "longUrl": long_url,
            "userId": user_id,
            "createdAt": now.isoformat(),
            "status": "active",
        }
        if expiry_days:
            expires = now + timedelta(days=expiry_days)
            item["expiresAt"] = int(expires.timestamp())   # epoch seconds for DynamoDB TTL
        put_kwargs = {"Item": item}
        if require_absent:
            put_kwargs["ConditionExpression"] = "attribute_not_exists(code)"
        self._urls.put_item(**put_kwargs)

    def get_meta(self, code: str) -> dict | None:
        """Full item for one code (for the search/detail view). None if not found."""
        resp = self._urls.get_item(
            Key={"code": code},
            ProjectionExpression="code, longUrl, createdAt, expiresAt, userId, #s",
            ExpressionAttributeNames={"#s": "status"},
        )
        item = resp.get("Item")
        if not item:
            return None
        exp = item.get("expiresAt")
        item["expired"] = bool(exp is not None and int(exp) <= int(_now().timestamp()))
        return item

    def list_links(self, user_id: str | None = None, limit: int = 200) -> list[dict]:
        """Scan the mapping table for the dashboard. Fine at learning-project scale;
        a production build would use a GSI on userId instead of a Scan."""
        scan_kwargs = {
            "ProjectionExpression": "code, longUrl, createdAt, expiresAt, userId, #s",
            "ExpressionAttributeNames": {"#s": "status"},
            "Limit": limit,
        }
        resp = self._urls.scan(**scan_kwargs)
        items = resp.get("Items", [])
        now_epoch = int(_now().timestamp())
        for it in items:
            exp = it.get("expiresAt")
            it["expired"] = bool(exp is not None and int(exp) <= now_epoch)
        return items
