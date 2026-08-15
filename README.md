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


## What was the original requirement?

The original requirement was very simple: Take a long URL and give the user a shorter URL that should be working.
The Ask was:
The application should remember which long URL belongs to the short code and redirect the user to the original URL when the short code is opened.
User
  |
  | Long URL
  v                
 App
  |
  | Short URL
  v
User


User
  |
  | Long URL
  v
Application
  |
  | Create short code
  v
DynamoDB
  |
  | Save short code -> long URL
  v
Application
  |
  | Short URL
  v
User

## Functional requirements 

- Do we need to set up expiry, or will the shortened URLs remain in the system?
  We should have functionality to set an expiry for the shortened URL.
- Can a customer create a Tiny URL of his/her choice, or will it always be auto-generated?
  This should be flexible. The customer should be able to use either an auto-generated short code or a custom short code.
- If the user is allowed to create custom shortened links, what would be the maximum size of the custom URL?
  The maximum character limit should be 16 characters.
- Two users should not accidentally get the same short code for different URLs.
  Short codes should be unique. Duplicate short codes should be rejected with an error rather than overwriting an existing URL.(409 - Conflict)

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
- The system should protect the application from excessive or abnormal traffic through rate limiting.
- Frequently accessed URLs should be served efficiently to reduce load on the database.
- The system should provide analytics/visibility into URL usage and performance.



For generated short codes, we use an atomic DynamoDB counter and convert the number into a Base62 code. This gives us a simple way to generate unique codes across multiple application instances.

4. Challenges we anticipated while improving the prototype

Challenge 1 – Duplicate links / alias conflicts

A custom short name such as my-link could already exist.

Improvement:

Validate the custom alias.

Use a conditional DynamoDB write.

Return 409 Conflict when the alias already exists.

Challenge 2 – Application should be safer from bot attacks

Without any limit, someone could call the create API repeatedly and generate a very large number of URLs.

This can increase:

Application load

Database writes

Cost

Abuse risk

Improvement:

We created a separate app/ratelimit.py module for rate-limiting logic.

The limit is applied to the URL creation API.

Example:

Too many requests
        |
        v
     HTTP 429
        |
Retry-After header

When Redis is configured, the counter is shared between application instances. Without Redis, the prototype uses a local in-memory counter for development.

For a real production system, we would still put the first layer of rate limiting at the edge using something such as API Gateway, WAF, or another gateway service.

Challenge 3 – We had no analytics

The original application could shorten URLs, but we could not answer basic business questions such as:

How many people clicked the link?

Which link gets the most traffic?

What device are people using?

Which browser is being used?

When was the last click?

How are clicks changing over time?

This meant the application worked technically, but we could not easily understand its business performance.

Improvement:

We added an analytics flow.

User opens short URL
        |
        v
Application
        |
        +----> Redirect to original URL
        |
        +----> Record click information
                    |
                    v
                 Clicks table

The analytics data includes information such as:

Click time

Device

Browser

Operating system

Referrer

We intentionally keep analytics separate from the main URL mapping data.

5. Analytics now shows business performance

The dashboard can now show information such as:

Total Links
Total Clicks
Top Device
Top Browser
Last Click
Daily Click Trend
Recent Clicks

This helps us move from:

"Does the URL shortener work?"

to:

"How are people using the links we created?"

This is important for business conversion analysis because it gives us a way to understand which links are actually being used and how much traffic they generate.

For example:

Campaign A
100 links created
12,000 clicks

Campaign B
100 links created
3,000 clicks

The second level of the prototype can therefore help a business understand which links or campaigns are performing better.

Note: The current prototype measures clicks and usage. A full business-conversion system would additionally connect clicks to downstream business events such as sign-ups, purchases, or completed actions.

6. Challenge 4 – Maintaining availability during peak traffic

A URL shortener is usually a read-heavy application.

One URL might be opened hundreds or thousands of times after it is shared.

If every request goes directly to DynamoDB, the database receives a lot of repeated reads for the same data.

For example:

1 URL created
        |
        +--> User 1 reads it
        +--> User 2 reads it
        +--> User 3 reads it
        +--> ...
        +--> User 10,000 reads it

The same long URL is being requested again and again.

Improvement: add Redis caching.

7. Redis cache improvement

We added app/cache.py as a separate cache layer.

The idea is:

User
  |
  | Short URL
  v
Application
  |
  v
 Redis Cache
  |
  |-- Found? --> Return long URL
  |
  |-- Not found?
  v
DynamoDB
  |
  | Long URL
  v
Redis Cache
  |
  v
Application
  |
  v
User -> Redirect

In simple terms, Redis works like a quick-access cupboard.

DynamoDB is the main storage room. Redis keeps frequently used URLs close to the application so we do not have to go to the main storage every time.

Important point about the prototype

The Redis switch is already wired into the application code. It is optional and is enabled when REDIS_URL is configured.

Think of it like an electrical bulb:

Cache code exists
      |
      v
REDIS_URL configured?
      |
   +--+--+
   |     |
  Yes    No
   |      |
   v      v
Redis   Cache disabled / no-op

So the code is already prepared. We only need to provide the Redis connection when we deploy or run Redis.

Example:

export REDIS_URL=redis://localhost:6379/0

After that, the application can use Redis for:

URL caching

Shared rate limiting

8. Expiry handling was improved

We added support for URL expiry.

A URL can be created with an expiry period.

Example:

Create URL
   |
   | expiry_days = 7
   v
URL works for 7 days
   |
   v
After 7 days
   |
   v
HTTP 410 Gone

We do not depend only on DynamoDB automatic cleanup.

The application checks the expiry time itself before redirecting.

This is important because database cleanup may happen later than the actual expiry time.

We also store the expiry information in the Redis cache, so an expired link cannot continue working just because it is still cached.

9. Dashboard and search were added

The prototype now contains a dashboard.

The dashboard allows us to:

See total links

See total clicks

Search for a short code

View link details

View click history

View daily click trends

See recent clicks

See device and browser information

This makes the prototype easier to demonstrate and gives the business a simple view of link performance.

10. Security improvement in the dashboard

User-controlled values such as URLs and referrers should never be inserted into a web page as raw HTML.

The dashboard uses safe DOM updates such as textContent so those values are treated as text.

This reduces the risk of stored XSS attacks.

11. What each file does

app/main.py

This is the main application file.

It connects all the pieces together.

It contains the API endpoints for:

Creating a short URL

Redirecting a short URL

Viewing analytics

Viewing individual link statistics

Opening the dashboard

Health checking

It also connects:

Repository

Cache

Analytics

Rate limiter

This file is basically the traffic controller of the application.

app/repository.py

This file handles DynamoDB operations.

It is responsible for:

Creating generated short URLs

Creating custom aliases

Reading URLs

Checking expiry

Getting link metadata

Listing links for the dashboard

Generating the next number using an atomic DynamoDB counter

In simple terms:

This file talks to the database.

app/base62.py

This file converts numbers into short codes and back again.

For example:

Number
12345678
   |
   v
Base62
   |
   v
Short code
1L9zO9P

This helps us create short, URL-friendly identifiers.

app/cache.py

This is the Redis cache layer.

It handles:

Reading URLs from Redis

Writing URLs to Redis

Cache expiry

Cache keys such as url:<code>

If Redis is not configured, the cache safely behaves like a no-op.

app/ratelimit.py

This file contains all rate-limiting logic in one place.

It supports:

Redis-based shared rate limiting

Local in-memory rate limiting for simple local runs

Fixed time windows

Retry-After response information

Keeping this logic separate makes it easier to change the rate-limiting strategy later.

app/analytics.py

This file handles click analytics.

It records:

Short code

Time of click

Device

Browser

Operating system

Referrer

It also calculates:

Total clicks

Top browser

Top device

Last click

Daily click counts

It also handles DynamoDB query pagination so larger click histories are counted correctly.

Another important design choice is that an analytics failure should not stop the redirect from working.

In other words:

Analytics problem
      |
      X
      |
Redirect should still work

app/config.py

This file contains application configuration.

Examples include:

AWS region

DynamoDB table names

Redis URL

Cache TTL

Rate-limit settings

Expiry limits

Analytics settings

Keeping configuration in one place makes the application easier to run in different environments.

create_tables.py

This script creates the DynamoDB tables needed by the prototype.

It is useful when setting up the application for the first time.

The application currently uses tables for:

Short URL mappings

Atomic counter

Click analytics

static/index.html

This is the main web page where a user can create a short URL.

It provides the user interface for the URL-shortening flow.

static/dashboard.html

This is the analytics dashboard.

It displays:

Link totals

Click totals

Search results

Link details

Click trends

Recent clicks

requirements.txt

This file lists the Python packages required to run the project.

Examples include packages needed for:

FastAPI

Uvicorn

boto3 / DynamoDB

Redis

.gitignore

This tells Git which files should not be committed.

Typical examples include local environment files, cache files, and Python-generated files.

12. Final architecture

The prototype evolved from a simple application into the following design:

                         User
                          |
                          | Long URL
                          v
                  +----------------+
                  |   FastAPI App  |
                  +--------+-------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
         DynamoDB        Redis       Rate Limiter
             |             |             |
             |             |             |
             +-------------+-------------+
                           |
                           v
                     Short URL / 302
                           |
                           v
                         User

On redirect:

User -> Short URL -> App
                     |
             +-------+-------+
             |               |
             v               v
           Redis          DynamoDB
             |
             v
        Long URL
             |
             +---------> Redirect

At the same time:

Redirect -> Analytics -> Clicks table -> Dashboard

13. What we improved from the original prototype

The original requirement was only:

Long URL -> App -> Short URL

The improved prototype became:

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

Main improvements

DynamoDB – improved scalability and availability compared with simple local storage.

Atomic counter + Base62 – creates short codes safely across multiple application instances.

Duplicate protection – custom aliases cannot silently overwrite existing links.

Rate limiting – helps protect the create API from abuse and excessive traffic.

Redis cache – reduces repeated database reads during heavy traffic.

Expiry support – expired links are blocked correctly, including cache hits.

Analytics – allows us to understand link usage and business performance.

Dashboard – gives a simple view of links, clicks, and trends.

Safer dashboard rendering – reduces the risk of stored XSS.

Correct click pagination – prevents undercounting when a link receives many clicks.

14. What we would improve next for production

This prototype is designed to demonstrate the architecture and the main reliability improvements. A production version would go further.

Next improvement: stronger analytics architecture

Today, click analytics are written during the redirect request.

For very high traffic, a better design would be:

User
  |
  v
Short URL
  |
  v
Application
  |
  +----> Immediate 302 Redirect
  |
  +----> SQS / Kinesis
             |
             v
       Analytics Worker
             |
             v
       Aggregated analytics

This keeps analytics work away from the critical redirect path.

Other future improvements

Real API-key validation and key rotation

Edge rate limiting with API Gateway/WAF

Better dashboard scalability using indexes and pre-aggregated data

Production observability with metrics, logs, traces, dashboards, and alerts

Automated unit and integration tests

Explicit DynamoDB TTL configuration

Protection against any theoretical generated-code/custom-alias collision

15. Running the application locally

Install dependencies:

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

16. Final summary

The project started with one simple goal:

Convert a long URL into a short URL.

During the prototype, we looked at what could go wrong in a real application and improved it step by step.

We added:

A scalable database using DynamoDB

Safe short-code generation

Duplicate alias protection

Application rate limiting

Redis caching

URL expiry

Click analytics

A business-facing analytics dashboard

Better click counting for large click volumes

Safer dashboard rendering

The result is no longer just a basic URL-shortening demo. It is a prototype that demonstrates how the design can evolve toward a system that is more scalable, safer, observable, and useful for the business.

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
