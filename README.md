# URL Shortener

FastAPI + DynamoDB implementation of the scalable URL-shortener design
(base62 counter code generation, cache-aside read path, analytics tap).

## Layout — maps to the design diagram

| File | Diagram box |
|------|-------------|
| `app/main.py` | Webservers (behind a load balancer) |
| `app/repository.py` | Sharded Database (DynamoDB) + atomic counter |
| `app/cache.py` | Cache (Redis, cache-aside) |
| `app/analytics.py` | Analytics (DynamoDB `Clicks` table; logs when disabled) |
| `app/ratelimit.py` | Write-path rate limiting (Redis, in-memory fallback) |
| `app/base62.py` | counter <-> short code |

## Run locally (DynamoDB Local)

```bash
# 1. deps
py -3 -m pip install -r requirements.txt

# 2. local DynamoDB (Docker)
docker run -d -p 8000:8000 amazon/dynamodb-local

# 3. env
export DYNAMODB_ENDPOINT=http://localhost:8000
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local

# 4. tables + server
py -3 create_tables.py
py -3 -m uvicorn app.main:app --reload --port 9000
```

Optional cache/analytics/limits:
```bash
export REDIS_URL=redis://localhost:6379/0   # enables cache-aside AND shared rate limiting
export ANALYTICS_SINK=dynamodb              # default; set to anything else to log-only
export RATE_LIMIT_PER_MIN=60                # write-path limit per API key (0 disables)
```

## Use

```bash
# create (generated code)
curl -X POST localhost:9000/api/create \
  -H 'x-api-key: demo' -H 'content-type: application/json' \
  -d '{"url":"https://medium.com/@sandeep4.verma"}'

# create (custom alias, max 16 chars)
curl -X POST localhost:9000/api/create \
  -H 'x-api-key: demo' -H 'content-type: application/json' \
  -d '{"url":"https://example.com","custom_url":"my-link"}'

# redirect (302)
curl -i localhost:9000/1L9zO9P
```

## Scaling notes
- **Web tier**: stateless — scale replicas behind an ALB/round-robin LB.
- **Counter**: DynamoDB `ADD` is atomic, so concurrent replicas never collide; no read-modify-write race.
- **DB partitioning**: `code` is the partition key (hashed) — even distribution, native sharding.
- **Reads**: cache-aside absorbs the 200:1 read skew; on miss, DB read backfills the cache.
- **Analytics**: 302 (not 301) guarantees every click hits the web tier, which taps the event stream.

## Rate limiting

Write path (`POST /api/create`) is limited per **API key** (the abuse/cost vector); redirects are not limited in-app — that belongs at the edge. The counter is **Redis-backed when `REDIS_URL` is set**, so the limit holds across all stateless replicas (atomic `INCR` + `EXPIRE`, fixed-window). Without Redis it falls back to a **per-process in-memory** counter — correct for a single replica, but N replicas would allow N× the limit. Exceeding the limit returns `429` with a `Retry-After` header.

## Known trade-offs / production next steps

Deliberately out of scope for this exercise; here's how I'd take it to production:

- **Rate limiting belongs at the edge.** In-app limiting here is defense-in-depth. The first gate should be API Gateway usage plans / WAF rate-based rules / ALB, so abusive traffic never reaches compute or DynamoDB.
- **Dashboard uses `Scan`.** Fine at this scale (already noted in `repository.py`); production would use a GSI on `userId` and paginate. Current `Scan(Limit=200)` also doesn't follow `LastEvaluatedKey`, so it can silently miss links beyond the first page.
- **Synchronous analytics.** `record_click` writes inline on the redirect path. At high QPS I'd fire-and-forget to SQS/Kinesis and aggregate downstream to keep redirect latency flat.
- **Hot partition on the `Clicks` table.** Partition key is `code`, so a single viral link concentrates all its click writes on one DynamoDB partition. I deliberately did *not* write-shard the key (`code#N`), because sharding forces fan-out reads — every stats query would have to hit all shards and merge, amplifying reads and worsening the N+1 below. The right fix isn't a key trick: buffer clicks through Kinesis/SQS and aggregate downstream, with an atomic per-link counter for totals. That removes the hot partition, the N+1, *and* the need to count rows — in one architectural move.
- **Dashboard N+1 query.** `GET /api/stats` lists all links, then queries the `Clicks` table once per link to build each summary. Fine at demo scale; at production scale the per-link click counts should come from a maintained aggregate (counter table / pre-computed rollups) instead of a live query per row. `clicks_for` now paginates via `LastEvaluatedKey`, so per-link totals are at least *correct* (no silent 1,000-click cap), just not cheap.
- **API-key auth is presence-only.** The header is required but not validated against a store of active keys. Production needs real key issuance/validation/revocation (or an API-gateway authorizer).
- **Cache invalidation.** Cache now carries expiry so expired links can't redirect from cache, but there's no active invalidation on URL update/delete — TTL-based only.
