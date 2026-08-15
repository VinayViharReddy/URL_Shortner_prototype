"""Analytics tap: the 'Analytics' box. Every 302 redirect persists a click record.

We store no IP and no geo (GDPR: user chose to drop location tracking). Each click
records only time + device/browser/OS (parsed from the User-Agent) + referer.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

import boto3

from .config import settings

logger = logging.getLogger("analytics")


_BROWSERS = [
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Chrome/", "Chrome"),
    ("Firefox/", "Firefox"),
    ("Safari/", "Safari"),
]


def _parse_ua(ua: str | None) -> tuple[str, str, str]:
    """Return (device, browser, os) from a User-Agent string, best-effort."""
    if not ua:
        return ("Unknown", "Unknown", "Unknown")

    device = "Mobile" if re.search(r"Mobi|Android|iPhone|iPad", ua) else "Desktop"

    browser = "Unknown"
    for token, name in _BROWSERS:
        if token in ua:
            m = re.search(re.escape(token) + r"(\d+)", ua)
            browser = f"{name} {m.group(1)}" if m else name
            break

    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif re.search(r"iPhone|iPad|iOS", ua):
        os_name = "iOS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown"

    return (device, browser, os_name)


class Analytics:
    def __init__(self):
        self._enabled = settings.analytics_sink == "dynamodb"
        self._clicks = None
        if self._enabled:
            kwargs = {"region_name": settings.aws_region}
            if settings.dynamodb_endpoint:
                kwargs["endpoint_url"] = settings.dynamodb_endpoint
            self._clicks = boto3.resource("dynamodb", **kwargs).Table(settings.clicks_table)

    def record_click(self, code: str, user_agent: str | None, referer: str | None) -> None:
        device, browser, os_name = _parse_ua(user_agent)
        now = datetime.now(timezone.utc)
        item = {
            "code": code,
            "ts": now.isoformat(),
            "device": device,
            "browser": browser,
            "os": os_name,
            "referer": referer or "direct",
            "expiresAt": int((now + timedelta(days=settings.click_retention_days)).timestamp()),
        }
        if not self._clicks:
            logger.info("click (analytics off) %s", item)
            return
        try:
            self._clicks.put_item(Item=item)
        except Exception:  # never let analytics break the redirect
            logger.exception("failed to persist click for %s", code)

    def clicks_for(self, code: str, limit: int | None = None) -> list[dict]:
        """Click records for one code (PK query, newest first).

        Paginates through LastEvaluatedKey so totals are correct regardless of
        click volume — a single query page is not the full result set, and a
        fixed Limit would silently undercount popular links. Pass `limit` to cap
        the number returned (e.g. the recent-clicks view); leave None for all.
        """
        if not self._clicks:
            return []
        from boto3.dynamodb.conditions import Key

        items: list[dict] = []
        start_key = None
        while True:
            kwargs = {
                "KeyConditionExpression": Key("code").eq(code),
                "ScanIndexForward": False,
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self._clicks.query(**kwargs)
            items.extend(resp.get("Items", []))
            if limit is not None and len(items) >= limit:
                return items[:limit]
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return items

    def summary_for(self, code: str) -> dict:
        """Aggregate a code's clicks into totals + top browser/device + daily series."""
        items = self.clicks_for(code)
        return {
            "clicks": len(items),
            "top_browser": _top(items, "browser"),
            "top_device": _top(items, "device"),
            "last_click": items[0]["ts"] if items else None,
            "daily": _daily_series(items),
        }


def _top(items: list[dict], field: str) -> str | None:
    counts: dict[str, int] = {}
    for it in items:
        v = it.get(field)
        if v:
            counts[v] = counts.get(v, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _daily_series(items: list[dict]) -> list[dict]:
    """Clicks bucketed per calendar day (UTC), ascending — for the chart."""
    counts: dict[str, int] = {}
    for it in items:
        ts = it.get("ts")
        if not ts:
            continue
        day = ts[:10]  # YYYY-MM-DD
        counts[day] = counts.get(day, 0) + 1
    return [{"date": d, "clicks": counts[d]} for d in sorted(counts)]
