from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from redis import ConnectionPool, Redis

try:
    # Works when running as package module: `uvicorn app.main:app`
    from app.constants import (
        APP_NAME,
        APP_VERSION,
        RATE_LIMIT_MAX_REQUESTS,
        RATE_LIMIT_WINDOW_SECONDS,
        REDIS_DB,
        REDIS_HOST,
        REDIS_MAX_CONNECTIONS,
        REDIS_PASSWORD,
        REDIS_PORT,
        REDIS_USERNAME,
    )
    from app.rate_limiter import RateLimitConfig, RedisRateLimiter
except ModuleNotFoundError:
    # Works when running from `app/` directory: `uvicorn main:app`
    from constants import (  # type: ignore[no-redef]
        APP_NAME,
        APP_VERSION,
        RATE_LIMIT_MAX_REQUESTS,
        RATE_LIMIT_WINDOW_SECONDS,
        REDIS_DB,
        REDIS_HOST,
        REDIS_MAX_CONNECTIONS,
        REDIS_PASSWORD,
        REDIS_PORT,
        REDIS_USERNAME,
    )
    from rate_limiter import RateLimitConfig, RedisRateLimiter  # type: ignore[no-redef]


class RequestIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=256)
    payload: dict


class RequestOut(BaseModel):
    message: str
    user_id: str


app = FastAPI(title=APP_NAME, version=APP_VERSION)
connection_pool = ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    username=REDIS_USERNAME or None,
    password=REDIS_PASSWORD or None,
    decode_responses=True,
    max_connections=REDIS_MAX_CONNECTIONS,
)
redis_client = Redis(connection_pool=connection_pool)
rate_limiter = RedisRateLimiter(
    redis_client=redis_client,
    config=RateLimitConfig(
        max_requests=RATE_LIMIT_MAX_REQUESTS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    ),
)


@app.post("/request", response_model=RequestOut)
def create_request(body: RequestIn) -> RequestOut:
    allowed, retry_after_seconds = rate_limiter.allow(body.user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Max {RATE_LIMIT_MAX_REQUESTS} requests per user per {RATE_LIMIT_WINDOW_SECONDS} seconds exceeded, retry after {retry_after_seconds} seconds",
                "user_id": body.user_id,
            },
        )

    return RequestOut(
        message="Request accepted",
        user_id=body.user_id,
    )


@app.get("/stats")
def get_stats() -> dict[str, dict[str, dict[str, int]]]:
    return {"users": rate_limiter.get_stats()}
