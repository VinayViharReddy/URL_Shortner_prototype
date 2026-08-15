# URL Shortener

FastAPI + DynamoDB implementation of the scalable URL-shortener design
(base62 counter code generation, cache-aside read path, analytics tap).

## What was the original requirement?

The original requirement: Take a long URL and give the user a shorter URL that should be working.
The application should remember which long URL belongs to the short code and redirect the user to the original URL when the short code is opened.
User -> Long URL -> App (Database) -> Short URL -> User

## Assumed Decisions

- Do we need to set up expiry, or will the shortened URLs remain in the system?
  **We should have functionality to set an expiry for the shortened URL.** 
- Can a customer create a Tiny URL of his/her choice, or will it always be auto-generated?
  **This should be flexible. The customer should be able to use either an auto-generated short code or a custom short code.**
- If the user is allowed to create custom shortened links, what would be the maximum size of the custom URL?
  **The maximum character limit should be 16 characters.**
- How many requests can be received on Average
  **Average 1M requ/month**

## Functional Requirements
- Service should be able to create shortened URLs/links against a long URL.
- Clicking the short URL should redirect the user to the original long URL.
- Shortened links should be as small as possible, with a maximum character limit of 16.
- The service should support both auto-generated and customer-defined short URLs.
- The service should provide an option to set an expiry for shortened URLs.
- Short codes should be unique, and duplicate short codes should not be allowed.

## Non-Functional Requirements
- Service should be up and running all the time with high availability.
- URL redirection should be fast and should not degrade at any point of time, even during peak loads.
- Service should be able to handle increasing traffic and scale without impacting performance.

## Challenges anticipated while working on prototype
- The system should protect the application from excessive or abnormal traffic through rate limiting.
- Frequently accessed URLs should be served efficiently to reduce load on the database.
- The system should provide analytics/visibility into URL usage and performance.
– Duplicate links / alias conflicts
– Application should be safer from bot attacks - Without any limit, someone could call the create API repeatedly and generate a very large number of URLs.
- We had no analytics

## The original application could shorten URLs, but we could not answer basic business questions such as:
- How many people clicked the link?
- Which link gets the most traffic?
- What device are people using?
- Which browser is being used?
- When was the last click?
- How are clicks changing over time? This means the application worked technically, but we could not easily understand its business performance.
## Analytics Improvement
- Click time
- Device
- Browser
- Operating system
- Analytics should shows business performance
The dashboard should show information such as:
- Total Links
- Total Clicks
- Top Device
- Top Browser
- Last Click
- Daily Click Trend
- Recent Clicks

This helps us move from: "Does the URL shortener work?"  to: "How are people using the links we created?"
This is important for business conversion analysis because it gives us a way to understand which links are actually being used and how much traffic they generate.
**The final level of the prototype  help a business understand which links or campaigns are performing better**
Note: The current prototype measures clicks and usage. A full business-conversion system would additionally connect clicks to downstream business events such as sign-ups, purchases, or completed actions.


## Improvement - support for URL expiry.
The application checks the expiry time itself before redirecting. This is important because database cleanup may happen later than the actual expiry time.
We also store the expiry information in the Redis cache, so an expired link cannot continue working just because it is still cached.

## What improvemed

- DynamoDB – improved scalability and availability compared with simple local storage.
- Atomic counter + Base62 – creates short codes safely across multiple application instances.
- Duplicate protection – custom aliases cannot silently overwrite existing links.
- Rate limiting – helps protect the create API from abuse and excessive traffic.
- Redis cache – reduces repeated database reads during heavy traffic.
- Expiry support – expired links are blocked correctly, including cache hits.
- Analytics – allows us to understand link usage and business performance.
- Dashboard – gives a simple view of links, clicks, and trends.
- Safer dashboard rendering – reduces the risk of stored XSS.
- Correct click pagination – prevents undercounting when a link receives many clicks.


The Final improved prototype became:

                 +----------------+
                 |      User      |
                 +--------+-------+
                          |
                     Long URL
                          |
                          v
                 +----------------+
                 |      App       |
                 +---+--------+---+
                     |        |
                     |        +----------> Rate Limiter
                     |
             +-------+-------+
             |               |
             v               v
          DynamoDB         Redis
             |               |
             |               |
             +-------+-------+
                     |
                     v
                 Short URL
                     |
                     v
                   User
                     |
                     v
                Click event
                     |
                     v
                 Analytics
                     |
                     v
                Dashboard


## Layout — maps to the design diagram

| File | Diagram box |
|------|-------------|
| `app/main.py` | Webservers (behind a load balancer) |
| `app/repository.py` | Sharded Database (DynamoDB) + atomic counter |
| `app/cache.py` | Cache (Redis, cache-aside) |
| `app/analytics.py` | Analytics (DynamoDB `Clicks` table; logs when disabled) |
| `app/ratelimit.py` | Write-path rate limiting (Redis, in-memory fallback) |
| `app/base62.py` | counter <-> short code |

## Running the application locally

Install dependencies:

aws configure -> for setting up Dynamodb
python3 -m pip install -r requirements.txt

Start DynamoDB Local if required, create tables, and start the application:

python3 create_tables.py
python3 -m uvicorn app.main:app --reload --port 8080

Open:

http://127.0.0.1:8080

API documentation:

http://127.0.0.1:8080/docs

To enable Redis locally:

export REDIS_URL=redis://localhost:6379/0

Then restart the application.

## Final Goal:
- During the prototype, we looked at what could go wrong in a real application and improved it step by step.
We added:
- A scalable database using DynamoDB
- Safe short-code generation
- Duplicate alias protection
- Application rate limiting
- Redis caching
- URL expiry
- Click analytics
- Business-facing analytics dashboard -> Better click counting for large click volumes

## Rate limiting

Write path (`POST /api/create`) is limited per **API key** (the abuse/cost vector); redirects are not limited in-app — that belongs at the edge. The counter is **Redis-backed when `REDIS_URL` is set**, so the limit holds across all stateless replicas (atomic `INCR` + `EXPIRE`, fixed-window). Without Redis it falls back to a **per-process in-memory** counter — correct for a single replica, but N replicas would allow N× the limit. Exceeding the limit returns `429` with a `Retry-After` header.

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

- **Cache invalidation.** Cache now carries expiry so expired links can't redirect from cache, but there's no active invalidation on URL update/delete — TTL-based only.
