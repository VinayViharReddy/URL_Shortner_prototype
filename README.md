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






