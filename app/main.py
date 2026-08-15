"""FastAPI web tier. Run many replicas behind a load balancer (ALB / round-robin).

Endpoints mirror the article:
  POST /api/create   -> create short URL (write path)
  GET  /{code}       -> 302 redirect to long URL (read path, cache-aside + analytics)
"""

import re
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl, field_validator

from .analytics import Analytics
from .cache import Cache
from .config import settings
from .ratelimit import RateLimiter
from .repository import AliasTakenError, LinkExpiredError, UrlRepository

app = FastAPI(title="URL Shortener")

# Instantiated once per process; each web server replica has its own.
repo = UrlRepository()
cache = Cache()
analytics = Analytics()
rate_limiter = RateLimiter()

_ALIAS_RE = re.compile(r"^[A-Za-z0-9$_.+!*'()-]+$")
_STATIC = Path(__file__).resolve().parent.parent / "static"
_INDEX_HTML = _STATIC / "index.html"
_DASHBOARD_HTML = _STATIC / "dashboard.html"

# Paths the redirect catch-all must NOT treat as short codes.
_RESERVED_CODES = {"favicon.ico", "robots.txt", "dashboard"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(_INDEX_HTML)


class CreateRequest(BaseModel):
    url: HttpUrl
    custom_url: str | None = None
    expiry_days: int | None = None   # blank/None = never expires

    @field_validator("custom_url")
    @classmethod
    def _check_alias(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) > settings.max_custom_alias_len:
            raise ValueError(f"custom_url exceeds {settings.max_custom_alias_len} chars")
        if not _ALIAS_RE.match(v):
            raise ValueError("custom_url has invalid characters")
        return v

    @field_validator("expiry_days")
    @classmethod
    def _check_expiry(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 1 or v > settings.max_expiry_days:
            raise ValueError(f"expiry_days must be between 1 and {settings.max_expiry_days}")
        return v


class CreateResponse(BaseModel):
    short_url: str
    code: str


def _short_url(request: Request, code: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/{code}"


@app.post("/api/create", response_model=CreateResponse, status_code=200)
def create(body: CreateRequest, request: Request, x_api_key: str = Header(...)):
    allowed, retry_after = rate_limiter.check(x_api_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    long_url = str(body.url)
    if body.custom_url:
        try:
            code = repo.create_custom(body.custom_url, long_url, x_api_key, body.expiry_days)
        except AliasTakenError:
            raise HTTPException(status_code=409, detail="custom_url already taken")
    else:
        code = repo.create_generated(long_url, x_api_key, body.expiry_days)
    expires_at = (
        int(time.time()) + body.expiry_days * 86400 if body.expiry_days else None
    )
    cache.set(code, long_url, expires_at)
    return CreateResponse(short_url=_short_url(request, code), code=code)


@app.get("/api/stats")
def stats_overview():
    """Dashboard payload: totals + one row per link (clicks, status, expiry, top country)."""
    links = repo.list_links()
    rows = []
    total_clicks = 0
    for link in links:
        summary = analytics.summary_for(link["code"])
        total_clicks += summary["clicks"]
        rows.append({
            "code": link["code"],
            "long_url": link.get("longUrl"),
            "created_at": link.get("createdAt"),
            "created_by": link.get("userId"),
            "expires_at": link.get("expiresAt"),
            "status": "expired" if link.get("expired") else link.get("status", "active"),
            "clicks": summary["clicks"],
            "top_browser": summary["top_browser"],
            "top_device": summary["top_device"],
            "last_click": summary["last_click"],
        })
    rows.sort(key=lambda r: r["clicks"], reverse=True)
    return {
        "total_links": len(rows),
        "total_clicks": total_clicks,
        "links": rows,
    }


@app.get("/api/stats/{code}")
def stats_for_code(code: str):
    """Per-link detail for the search view: metadata, totals, recent click log,
    and a daily click series for the chart."""
    meta = repo.get_meta(code)
    if meta is None:
        raise HTTPException(status_code=404, detail="short url not found")
    summary = analytics.summary_for(code)
    return {
        "code": code,
        "long_url": meta.get("longUrl"),
        "created_at": meta.get("createdAt"),
        "created_by": meta.get("userId"),
        "expires_at": meta.get("expiresAt"),
        "status": "expired" if meta.get("expired") else meta.get("status", "active"),
        "clicks": summary["clicks"],
        "top_browser": summary["top_browser"],
        "top_device": summary["top_device"],
        "last_click": summary["last_click"],
        "daily": summary["daily"],
        "recent": analytics.clicks_for(code, limit=50),
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(_DASHBOARD_HTML)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


# Declared LAST: this catch-all must not shadow /api/*, /dashboard, or /healthz.
@app.get("/{code}")
def redirect(code: str,
             user_agent: str | None = Header(None),
             referer: str | None = Header(None)):
    if code in _RESERVED_CODES:
        raise HTTPException(status_code=404, detail="not found")

    now_epoch = int(time.time())
    cached = cache.get(code)            # cache first
    if cached is not None:
        long_url, expires_at = cached
        # Enforce expiry even on a cache hit: a cached-but-expired link must NOT
        # redirect just because it's still within the cache TTL.
        if expires_at is not None and expires_at <= now_epoch:
            raise HTTPException(status_code=410, detail="this short url has expired")
    else:                               # miss -> DB, then backfill
        try:
            result = repo.get_long_url(code)
        except LinkExpiredError:
            raise HTTPException(status_code=410, detail="this short url has expired")
        if result is None:
            raise HTTPException(status_code=404, detail="short url not found")
        long_url, expires_at = result
        cache.set(code, long_url, expires_at)
    analytics.record_click(code, user_agent, referer)   # tap on every 302
    return RedirectResponse(url=long_url, status_code=302)
