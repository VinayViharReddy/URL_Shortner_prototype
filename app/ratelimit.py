"""Rate limiting for the write path (POST /api/create).

Fixed-window counter, keyed by API key. Two backends, chosen at runtime:

  * Redis (when REDIS_URL is set): the counter lives in ONE shared store, so the
    limit holds no matter how many stateless replicas run behind the load
    balancer. `INCR` is atomic, so concurrent requests across replicas can't race
    the count; the window key is given a TTL so old windows self-expire.

  * In-memory (fallback): per-process dict. Correct only for a single replica —
    with N replicas the effective limit becomes N x the configured value because
    each process counts independently. Fine for local dev / single instance.

In real production the FIRST line of defense is edge throttling (API Gateway
usage plans, WAF rate-based rules, ALB) so abusive traffic never reaches compute
or incurs DynamoDB cost. This app-level limiter is defense-in-depth.
"""

import time

from .config import settings

try:
    import redis  # optional dependency
except ImportError:  # pragma: no cover
    redis = None


class RateLimiter:
    def __init__(self):
        self._client = None
        if settings.redis_url and redis is not None:
            self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self._local: dict[str, tuple[int, int]] = {}  # key -> (window_start, count)

    def check(self, identity: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds).

        retry_after is 0 when allowed; otherwise the seconds until the current
        window rolls over.
        """
        limit = settings.rate_limit_per_min
        if limit <= 0:  # 0/negative disables limiting
            return True, 0
        window = settings.rate_limit_window_seconds
        now = int(time.time())
        bucket = now // window
        retry_after = window - (now % window)

        if self._client:
            return self._check_redis(identity, bucket, limit, window, retry_after)
        return self._check_local(identity, bucket, limit, retry_after)

    def _check_redis(self, identity, bucket, limit, window, retry_after):
        key = f"rl:{identity}:{bucket}"
        count = self._client.incr(key)
        if count == 1:
            # First hit in this window: set TTL so the counter self-expires.
            self._client.expire(key, window)
        if count > limit:
            return False, retry_after
        return True, 0

    def _check_local(self, identity, bucket, limit, retry_after):
        start, count = self._local.get(identity, (bucket, 0))
        if start != bucket:  # new window
            start, count = bucket, 0
        count += 1
        self._local[identity] = (start, count)
        if count > limit:
            return False, retry_after
        return True, 0
