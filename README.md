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



## 4. Scope Coverage

### Greenfield — New System Development

| **What I Built From Scratch** | **Business Purpose** |
|---|---|
| Short URL creation (auto-generated + custom codes) | Convert long URLs into short, easy-to-share links |
| DynamoDB-based URL storage | Provide scalable and highly available persistence |
| Unique short-code generation using Atomic Counter + Base62 | Ensure short codes are unique and compact |
| URL redirection | User clicks the short link and is redirected to the original URL |
| Optional URL expiry | Allow temporary links for campaigns or time-sensitive use cases |
| Input validation | Prevent invalid URLs and invalid custom short codes |
| Analytics and dashboard | Understand link usage, clicks, browser, device and recent activity |
| Health check endpoint | Provide a basic way to verify application availability |

**How:** Started with an empty project → defined functional and non-functional requirements → designed the DynamoDB data model → built the FastAPI API layer → added unique short-code generation → added validation, expiry and analytics.

---

### Brownfield — Enhancements to the Working Prototype

| **What I Added to the Working App** | **Business Purpose** |
|---|---|
| Custom short-code support | Allow customers to choose a meaningful short URL instead of always using an auto-generated code |
| Duplicate short-code protection | Prevent two users from using the same short code |
| URL expiry handling | Automatically stop links from being used after their configured expiry |
| Redis cache | Reduce DynamoDB reads and keep redirects fast during higher traffic |
| Application rate limiting | Protect the write path from excessive or bot traffic |
| Click analytics | Show how links are performing and provide better business visibility |
| Dashboard | Give users a simple view of link usage and performance |
| Cache expiry validation | Prevent an expired URL from redirecting even when it is still present in Redis |

**How:** The basic URL-shortener flow was working → identified real-world scalability, performance and reliability challenges → added Redis, rate limiting, expiry and analytics without changing the core URL-shortening flow.

---

### Ambiguous Requirement — "Make the URL Shortener More Reliable and Scalable"

| **Step** | **What I Did** |
|---|---|
| 1. Received the requirement | "The service should always be available and should not become slow during peak traffic." |
| 2. Identified the main risks | Database load, repeated reads, excessive traffic and lack of visibility |
| 3. Chose the database | Used DynamoDB for scalable and highly available storage |
| 4. Improved performance | Added Redis cache using the cache-aside pattern |
| 5. Added protection | Added application-level rate limiting on the write path |
| 6. Added reliability handling | Added expiry validation and a health-check endpoint |
| 7. Added visibility | Added click analytics and dashboard |
| 8. Defined SRE targets | Defined Golden Signals, SLOs, Error Budgets and priorities |

**Key Point:** Didn't over-engineer the first version. Started with the core requirement, identified likely production challenges, then added the improvements based on assumption **user impact, scalability and reliability needs**.


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
| Excessive URL creation requests | Returns `429 Too Many Requests` | ✅ Supported |
| Rate limit exceeded | `Retry-After` header is returned | ✅ Supported |
| Record link click | Click information is recorded for analytics | ✅ Supported |
| Browser / device / referer tracking | Analytics captures available request details | ✅ Supported |
| Dashboard overview | Shows total links, clicks and link-level statistics | ✅ Supported |
| Individual link analytics | Shows clicks, daily data and recent clicks | ✅ Supported |

## Automation Test Coverage Tradeoff

> The current prototype does **not yet contain a formal `pytest` test suite**. The above scenarios represent the functional behavior implemented and validated through the application flow.

