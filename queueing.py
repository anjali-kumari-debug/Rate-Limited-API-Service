from __future__ import annotations

import json
import logging
import time
import uuid

import redis

logger = logging.getLogger(__name__)


class RedisRequestQueue:
    def __init__(self, redis_client: redis.Redis, queue_key: str = "rl:request_queue") -> None:
        self._redis = redis_client
        self._queue_key = queue_key

    def enqueue(self, user_id: str, payload: dict, retry_after_seconds: int) -> str:
        job_id = uuid.uuid4().hex
        now = int(time.time())
        job = {
            "job_id": job_id,
            "user_id": user_id,
            "payload": payload,
            "enqueued_at": now,
            "scheduled_at": now + max(1, int(retry_after_seconds)),
            "status": "queued",
        }
        self._redis.rpush(self._queue_key, json.dumps(job))
        logger.info(
            "queue_enqueue job_id=%s user_id=%s scheduled_at=%s",
            job_id,
            user_id,
            job["scheduled_at"],
        )
        return job_id

    def size(self) -> int:
        return int(self._redis.llen(self._queue_key))

    def details(self, limit: int = 50) -> list[dict]:
        safe_limit = max(1, min(limit, 200))
        raw_jobs = self._redis.lrange(self._queue_key, 0, safe_limit - 1)
        details: list[dict] = []
        for raw in raw_jobs:
            job = json.loads(raw)
            details.append(
                {
                    "job_id": job.get("job_id"),
                    "user_id": job.get("user_id"),
                    "status": job.get("status"),
                    "enqueued_at": job.get("enqueued_at"),
                    "scheduled_at": job.get("scheduled_at"),
                }
            )
        return details

    def process_one_ready(self, handler: callable) -> dict:
        queue_len = self._redis.llen(self._queue_key)
        if queue_len <= 0:
            return {"status": "empty"}

        now = int(time.time())
        for _ in range(queue_len):
            raw = self._redis.lpop(self._queue_key)
            if raw is None:
                return {"status": "empty"}

            job = json.loads(raw)
            if int(job.get("scheduled_at", now)) > now:
                self._redis.rpush(self._queue_key, raw)
                continue

            processed = handler(job["user_id"], job.get("payload", {}))
            if processed:
                job["status"] = "processed"
                job["processed_at"] = now
                logger.info(
                    "queue_processed job_id=%s user_id=%s processed_at=%s",
                    job.get("job_id"),
                    job.get("user_id"),
                    job.get("processed_at"),
                )
                return {"status": "processed", "job": job}

            # Still limited, delay and requeue.
            job["scheduled_at"] = now + 1
            job["status"] = "requeued"
            self._redis.rpush(self._queue_key, json.dumps(job))
            logger.info(
                "queue_requeued job_id=%s user_id=%s scheduled_at=%s",
                job.get("job_id"),
                job.get("user_id"),
                job.get("scheduled_at"),
            )
            return {"status": "requeued", "job": job}

        return {"status": "no_ready_jobs"}
