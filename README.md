# Rate-Limited API Service

A production-considerate API service built with Python + FastAPI + Redis.

## API Endpoints

### `POST /request`
Accepts:

```json
{
  "user_id": "user-123",
  "payload": {
    "key": "value"
  }
}
```

Behavior:
- Allows at most **5 requests per user per minute** by default
- If user exceeds limit, request is queued for retry processing (bonus queueing)

Example success response:

```json
{
  "message": "Request accepted",
  "user_id": "user-123",
  "queued": false,
  "job_id": null
}
```

Example queued response:

```json
{
  "message": "Max 5 requests per user per 60 seconds exceeded, retry after 12 seconds. Request queued.",
  "user_id": "user-123",
  "queued": true,
  "job_id": "3b4f..."
}
```

### `GET /stats`
Returns per-user stats:
- accepted request total
- rejected request total
- current requests in active 60-second window
- configured per-minute limit

### `GET /queue/stats`
Returns current queued request count.
- Queue is processed automatically by a background worker loop.

## How to Run

1. Create and activate a virtual environment:

```bash
python3 -m venv appEnv
source appEnv/bin/activate
```

2. Configure environment:

```bash
cp .env
```

U may edit `.env` with your Redis host/port/credentials if needed.

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the server (choose one):

```bash
# If your current directory is app
uvicorn main:app --host 0.0.0.0 --port 8000
```
5. Test quickly:

```bash
curl -X POST http://localhost:8000/request \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","payload":{"msg":"hello"}}'
```

```bash
curl http://localhost:8000/stats
```

Interactive docs:
- Swagger UI: `http://localhost:8000/docs`

## Configuration

All runtime configuration is driven by `.env`.

- `RATE_LIMIT_MAX_REQUESTS` (default `5`)
- `RATE_LIMIT_WINDOW_SECONDS` (default `60`)
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_USERNAME`
- `REDIS_PASSWORD`
- `REDIS_MAX_CONNECTIONS` (default `30`)
- `QUEUE_WORKER_ENABLED` (default `true`)
- `QUEUE_WORKER_INTERVAL_SECONDS` (default `1.0`)

## Design Decisions

- **Framework:** FastAPI for clean API modeling, validation, and fast development
- **Rate limiting algorithm:** Redis sorted-set sliding window per user
- **Concurrency safety:** Atomic Lua script in Redis to evict/check/append/update stats in one operation
- **Storage:** Redis-backed state to support multi-instance deployments
- **Connection management:** Redis connection pool with max `30` connections
- **Queueing bonus:** Redis list-based queue for delayed retry processing with automatic background draining

## Correctness Under Parallel Requests

- The limiter executes a single Lua script per request that:
  - removes expired entries
  - checks current window count
  - inserts a new timestamp only when allowed
  - updates accepted/rejected counters
- This is atomic in Redis, so limits stay accurate under parallel calls and across multiple app instances.

## Limitations (Important)

- If Redis is unavailable, rate limiting fails unless fallback logic is added
- No authentication/authorization layer in this sample

## What I Would Improve With More Time

- Add robust Redis retry/circuit-breaker behavior
- Move queue worker into separate process/container for independent scaling
- Add tests:
  - unit tests for limiter edge cases
  - concurrency tests with parallel clients
  - API integration tests
- Add observability:
  - structured logs
  - metrics (429 count, accepted count, per-user hot keys)
- Add containerization and deployment config (e.g., Azure App Service / AKS)

## Bonus Direction (Optional)

- [x] **Use Redis or a database:** implemented with Redis-backed atomic rate limiting
- [x] **Add retry logic or queueing:** implemented with delayed Redis queue + auto worker drain
- [x] **Deploy on Azure or any cloud platform:** Deployed on render : https://rate-limited-api-service.onrender.com/


