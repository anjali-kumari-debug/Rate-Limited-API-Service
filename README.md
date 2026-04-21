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
- Returns `429 Too Many Requests` if the user exceeds the limit

Example success response:

```json
{
  "message": "Request accepted",
  "user_id": "user-123"
}
```

### `GET /stats`
Returns per-user stats:
- accepted request total
- rejected request total
- current requests in active 60-second window
- configured per-minute limit

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

## Design Decisions

- **Framework:** FastAPI for clean API modeling, validation, and fast development
- **Rate limiting algorithm:** Redis sorted-set sliding window per user
- **Concurrency safety:** Atomic Lua script in Redis to evict/check/append/update stats in one operation
- **Storage:** Redis-backed state to support multi-instance deployments
- **Connection management:** Redis connection pool with max `30` connections

## Correctness Under Parallel Requests

- The limiter executes a single Lua script per request that:
  - removes expired entries
  - checks current window count
  - inserts a new timestamp only when allowed
  - updates accepted/rejected counters
- This is atomic in Redis, so limits stay accurate under parallel calls and across multiple app instances.

## Limitations (Important)

- If Redis is unavailable, rate limiting fails unless fallback logic is added
- Stats endpoint scans known users set; for very large user cardinality, pagination may be needed
- No authentication/authorization layer in this sample

## What I Would Improve With More Time

- Add robust Redis retry/circuit-breaker behavior
- Add request queue/retry behavior for soft throttling use cases
- Add tests:
  - unit tests for limiter edge cases
  - concurrency tests with parallel clients
  - API integration tests
- Add observability:
  - structured logs
  - metrics (429 count, accepted count, per-user hot keys)
- Add containerization and deployment config (e.g., Azure App Service / AKS)

## Bonus Direction (Optional)

- **Redis-backed limiter:** production-ready scaling and stronger global consistency
- **Queueing:** push over-limit requests into delayed processing queue
- **Cloud deployment:** package with Docker and deploy to Azure

## Submission Note

To submit, push this project to GitHub and share the repository URL in your email reply along with this README.
