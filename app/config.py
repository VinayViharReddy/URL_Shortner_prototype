"""Runtime configuration, read from environment with sensible local defaultss."""

import os


class Settings:
    # DynamoDB
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    # Point to a local DynamoDB (e.g. amazon/dynamodb-local) for dev; leave blank for real AWS.
    dynamodb_endpoint: str | None = os.getenv("DYNAMODB_ENDPOINT") or None
    urls_table: str = os.getenv("URLS_TABLE", "ShortUrls")
    counter_table: str = os.getenv("COUNTER_TABLE", "Counters")
    clicks_table: str = os.getenv("CLICKS_TABLE", "Clicks")

    # Base62 counter start (article uses a large seed so codes are 7 chars).
    counter_seed: int = int(os.getenv("COUNTER_SEED", "100000000000"))

    # Cache-aside (Redis). If unset, cache layer becomes a no-op passthrough.
    redis_url: str | None = os.getenv("REDIS_URL") or None
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

    # Rate limiting on the write path, keyed by API key. Redis-backed when
    # REDIS_URL is set (correct across replicas), else in-memory. Set to 0 to disable.
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Analytics: click records persist to the Clicks table. Set to "off" to disable.
    analytics_sink: str = os.getenv("ANALYTICS_SINK", "dynamodb")

    # Clicks + expired short-urls keep this many days before DynamoDB TTL reaps them.
    click_retention_days: int = int(os.getenv("CLICK_RETENTION_DAYS", "90"))

    max_custom_alias_len: int = 16
    max_expiry_days: int = int(os.getenv("MAX_EXPIRY_DAYS", "3650"))


settings = Settings()
