import asyncio
import logging
from contextlib import suppress

from fastapi import FastAPI
from pydantic import BaseModel, Field
from redis import ConnectionPool, Redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

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
        QUEUE_WORKER_ENABLED,
        QUEUE_WORKER_INTERVAL_SECONDS,
    )
    from app.queueing import RedisRequestQueue
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
        QUEUE_WORKER_ENABLED,
        QUEUE_WORKER_INTERVAL_SECONDS,
    )
    from queueing import RedisRequestQueue  # type: ignore[no-redef]
    from rate_limiter import RateLimitConfig, RedisRateLimiter  # type: ignore[no-redef]


class RequestIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=256)
    payload: dict


class RequestOut(BaseModel):
    message: str
    user_id: str


class QueueResponse(BaseModel):
    message: str
    user_id: str
    queued: bool
    job_id: str | None = None


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
request_queue = RedisRequestQueue(redis_client=redis_client)
queue_worker_task: asyncio.Task | None = None


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "ok",
        "docs": "/docs",
        "developer": "Anjali Kumari",
    }


async def _queue_worker_loop() -> None:
    def _handler(user_id: str, payload: dict) -> bool:
        # Payload is available for business logic; rate limit gate controls processing.
        allowed, _ = rate_limiter.allow(user_id)
        return allowed

    while True:
        request_queue.process_one_ready(_handler)
        await asyncio.sleep(QUEUE_WORKER_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_queue_worker() -> None:
    global queue_worker_task
    if not QUEUE_WORKER_ENABLED:
        logger.info("queue_worker disabled")
        return
    if queue_worker_task is None or queue_worker_task.done():
        logger.info("queue_worker started interval_seconds=%s", QUEUE_WORKER_INTERVAL_SECONDS)
        queue_worker_task = asyncio.create_task(_queue_worker_loop())


@app.on_event("shutdown")
async def _stop_queue_worker() -> None:
    global queue_worker_task
    if queue_worker_task is None:
        return
    logger.info("queue_worker stopping")
    queue_worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await queue_worker_task
    logger.info("queue_worker stopped")
    queue_worker_task = None


@app.post("/request", response_model=QueueResponse)
def create_request(body: RequestIn) -> QueueResponse:
    allowed, retry_after_seconds = rate_limiter.allow(body.user_id)
    if not allowed:
        job_id = request_queue.enqueue(
            user_id=body.user_id,
            payload=body.payload,
            retry_after_seconds=retry_after_seconds,
        )
        return QueueResponse(
            message=(
                f"Max {RATE_LIMIT_MAX_REQUESTS} requests per user per {RATE_LIMIT_WINDOW_SECONDS} seconds "
                f"exceeded, retry after {retry_after_seconds} seconds. Request queued."
            ),
            user_id=body.user_id,
            queued=True,
            job_id=job_id,
        )

    return QueueResponse(
        message="Request accepted",
        user_id=body.user_id,
        queued=False,
        job_id=None,
    )


@app.get("/stats")
def get_stats() -> dict[str, dict[str, dict[str, int]]]:
    return {"users": rate_limiter.get_stats()}


@app.get("/queue/stats")
def get_queue_stats() -> dict[str, int]:
    return {"queued_requests": request_queue.size()}


@app.get("/queue/details")
def get_queue_details(limit: int = 50) -> dict[str, list[dict]]:
    return {"jobs": request_queue.details(limit=limit)}
