## Prototype Architecture

<img width="1141" height="761" alt="image" src="https://github.com/user-attachments/assets/e74ae5fd-4ce2-4892-a58d-83245433768e" />

## Layout — maps to the design diagram

| File | Diagram box | explanation |
|------|-------------|------------------------------|
| `create_tables.py` | DynamoDB Setup | One-time DynamoDB table setup. The `if __name__ == "__main__"` block ensures the table creation runs only when this file is executed directly. |
| `app/main.py` | Web Servers | FastAPI web layer. Handles URL creation, redirects, validation, expiry, rate limiting, analytics APIs and health checks. |
| `app/repository.py` | DynamoDB + Atomic Counter | Handles DynamoDB operations. Stores and retrieves URLs, handles custom aliases and uses an atomic counter to generate unique IDs. |
| `app/cache.py` | Redis Cache | Handles Redis caching using the cache-aside pattern. Checks Redis first and falls back to DynamoDB on a cache miss. |
| `app/analytics.py` | Analytics | Records click information such as time, browser, device and referer, and provides data for the analytics dashboard. |
| `app/ratelimit.py` | Rate Limiting | Contains rate-limiting logic to protect the application from excessive or bot traffic on the write path. |
| `app/base62.py` | Counter ↔ Short Code | Converts the numeric counter value into a compact Base62 short code using letters and numbers. |
| `app/config.py` | Configuration | Loads environment-specific configuration such as AWS region, DynamoDB endpoint, table names, Redis URL and application limits. |
| `static/index.html` | URL Creation UI | Frontend page where users enter the long URL and create a short URL. |
| `static/dashboard.html` | Analytics Dashboard | Frontend dashboard used to view clicks and short-link performance. |
| `requirements.txt` | Dependencies | Lists the Python packages required to run the application. |


## Steps to Run Application Locally

Install dependencies:
- aws configure -> for setting up Dynamodb
- python3 -m pip install -r requirements.txt - **To Install Dependencies**
- python3 create_tables.py - **Start DynamoDB Local if required - We created tables in AWS, and start the application**
- python3 -m uvicorn app.main:app --reload --port 8080. - **To Run the App**
- To enable Redis locally   **export REDIS_URL=redis://localhost:6379/0 - Then restart the application.**

## Trade Offs

| Area | Trade-off |
|---|---|
| **Redis Cache** | Redis is wired into the application, but the switch is **off by default** in the prototype. It can be enabled when running Redis locally or when deploying to ECS with ElastiCache. |
| **DynamoDB** | Chosen for scalability and availability, with more design complexity than a simple relational database. |
| **Analytics** | Added for better link-performance visibility, but click recording is currently synchronous; at higher scale, it should move to an asynchronous queue by adding Queue mechanism (SQS) |
| **Rate Limiting** | Implemented at the application level for the prototype; in production, primary protection can move to WAF/API Gateway. |

## NORTH STAR (Production Grade)
<img width="1536" height="1024" alt=" Image Aug 17, 2026, 03_14_15 AM" src="https://github.com/user-attachments/assets/c086f362-68b3-4ada-aefc-65607efc2a63" />


## Test Cases / Functional Validation

| Test Case | Expected Result | Status |
|---|---|---|
| Create URL with valid long URL | Short URL is generated successfully | ✅ Supported |
| Create URL with custom short code | User-defined short code is created | ✅ Supported |
| Create URL without custom code | Short code is generated automatically using Base62 | ✅ Supported |
| Custom short code greater than 16 characters | Request is rejected | ✅ Validated |
| Custom short code with invalid characters | Request is rejected | ✅ Validated |
| Duplicate custom short code | Request returns `409 Conflict` | ✅ Handled |
| Expiry not provided | Short URL remains active | ✅ Supported |
| Expiry provided | Short URL expires after configured days | ✅ Supported |
| Access expired short URL | Returns `410 Gone` | ✅ Handled |
| Access non-existing short URL | Returns `404 Not Found` | ✅ Handled |
| Access valid short URL | Redirects to original URL using `302` | ✅ Supported |
| Redis cache hit | URL is served from Redis without DynamoDB lookup | ✅ Supported |
| Redis cache miss | Reads URL from DynamoDB and backfills Redis | ✅ Supported |
| Expired URL available in Redis | Expiry is checked and redirect is blocked | ✅ Handled |
| Excessive URL creation requests | Returns `429 Too Many Requests` | ✅ Supported |
| Rate limit exceeded | `Retry-After` header is returned | ✅ Supported |
| Record link click | Click information is recorded for analytics | ✅ Supported |
| Browser / device / referer tracking | Analytics captures available request details | ✅ Supported |
| Dashboard overview | Shows total links, clicks and link-level statistics | ✅ Supported |
| Individual link analytics | Shows clicks, daily data and recent clicks | ✅ Supported |
| Health check | `/healthz` returns application health status | ✅ Supported |
| Reserved application paths | Paths such as `/dashboard` are not treated as short codes | ✅ Handled |
| Invalid request URL | Request is rejected by Pydantic validation | ✅ Validated |

## Automation Test Coverage

> The current prototype does **not yet contain a formal `pytest` test suite**. The above scenarios represent the functional behavior implemented and validated through the application flow.

### Recommended Automated Tests

| Test Area | Test Scenario |
|---|---|
| Base62 | Encode/decode round-trip validation |
| URL Creation | Valid URL, invalid URL and missing fields |
| Custom Alias | 16-character limit, invalid characters and duplicate alias |
| Generated Code | Concurrent URL creation and uniqueness |
| Expiry | Active URL, expired URL and expiry boundary |
| Redirect | Valid URL, 404 and 410 responses |
| Redis | Cache hit, cache miss and Redis failure fallback |
| Rate Limiting | Requests within limit and requests exceeding limit |
| Analytics | Click recording and analytics failure handling |
| Dashboard | Correct click counts and link statistics |



