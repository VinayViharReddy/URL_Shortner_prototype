"""Cache-aside layer: the 'CACHE' box. Redis if configured, else no-op.

Read path: check cache -> on miss, caller hits DB and backfills.
This is what shields the DB from the 200:1 read/write skew (8000 reads/s).

Cached value is "<expiresAt>|<longUrl>" so the cache-hit path can enforce
expiry itself. Without this, an expired-but-still-cached link would keep
redirecting until its cache TTL lapsed (a correctness/security bug).
"""

from .config import settings

try:
    import redis  # optional dependency
except ImportError:  # pragma: no cover
    redis = None


class Cache:
    def __init__(self):
        self._client = None
        if settings.redis_url and redis is not None:
            self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    def get(self, code: str) -> tuple[str, int | None] | None:
        """Return (long_url, expires_at_epoch_or_None), or None on miss."""
        if not self._client:
            return None
        raw = self._client.get(self._key(code))
        if raw is None:
            return None
        exp_str, _, long_url = raw.partition("|")
        expires_at = int(exp_str) if exp_str else None
        return long_url, expires_at

    def set(self, code: str, long_url: str, expires_at: int | None = None) -> None:
        if not self._client:
            return
        value = f"{expires_at if expires_at is not None else ''}|{long_url}"
        self._client.set(self._key(code), value, ex=settings.cache_ttl_seconds)

    @staticmethod
    def _key(code: str) -> str:
        return f"url:{code}"
