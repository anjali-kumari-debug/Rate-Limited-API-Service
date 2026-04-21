from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import redis


@dataclass(frozen=True)
class RateLimitConfig:
    max_requests: int = 5
    window_seconds: int = 60


class RedisRateLimiter:
    """
    Redis-backed sliding-window limiter with atomic Lua operations.
    """

    def __init__(self, redis_client: redis.Redis, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._redis = redis_client
        self._allow_script = self._redis.register_script(
            """
            local user_key = KEYS[1]
            local stats_key = KEYS[2]
            local users_key = KEYS[3]

            local now = tonumber(ARGV[1])
            local cutoff = tonumber(ARGV[2])
            local max_requests = tonumber(ARGV[3])
            local ttl = tonumber(ARGV[4])
            local request_member = ARGV[5]
            local user_id = ARGV[6]

            redis.call("SADD", users_key, user_id)
            redis.call("ZREMRANGEBYSCORE", user_key, "-inf", cutoff)
            local current = redis.call("ZCARD", user_key)

            if current >= max_requests then
                redis.call("HINCRBY", stats_key, "rejected_total", 1)
                local oldest = redis.call("ZRANGE", user_key, 0, 0, "WITHSCORES")
                local retry_after = 1
                if oldest[2] ~= nil then
                    retry_after = math.ceil((tonumber(oldest[2]) + ttl) - now)
                    if retry_after < 1 then
                        retry_after = 1
                    end
                end
                return {0, 0, retry_after}
            end

            redis.call("ZADD", user_key, now, request_member)
            redis.call("EXPIRE", user_key, ttl)
            redis.call("HINCRBY", stats_key, "accepted_total", 1)
            current = current + 1
            return {1, max_requests - current, 0}
            """
        )

    def allow(self, user_id: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.config.window_seconds
        request_member = f"{now}:{uuid.uuid4().hex}"
        keys = [self._user_window_key(user_id), self._user_stats_key(user_id), self._users_set_key()]
        args = [now, cutoff, self.config.max_requests, self.config.window_seconds, request_member, user_id]
        allowed, remaining, retry_after_seconds = self._allow_script(keys=keys, args=args)
        return bool(int(allowed)), int(retry_after_seconds)

    def get_stats(self) -> dict[str, dict[str, int]]:
        now = time.time()
        cutoff = now - self.config.window_seconds
        user_ids = self._redis.smembers(self._users_set_key())
        result: dict[str, dict[str, int]] = {}

        for user_id in user_ids:
            window_key = self._user_window_key(user_id)
            stats_key = self._user_stats_key(user_id)

            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(window_key, "-inf", cutoff)
            pipe.zcard(window_key)
            pipe.hget(stats_key, "accepted_total")
            pipe.hget(stats_key, "rejected_total")
            _, current_window, accepted_total, rejected_total = pipe.execute()

            result[user_id] = {
                "accepted_total": int(accepted_total or 0),
                "rejected_total": int(rejected_total or 0),
                "requests_in_current_window": int(current_window),
                "limit_per_minute": self.config.max_requests,
            }

        return result

    @staticmethod
    def _users_set_key() -> str:
        return "rl:users"

    @staticmethod
    def _user_window_key(user_id: str) -> str:
        return f"rl:user:{user_id}:window"

    @staticmethod
    def _user_stats_key(user_id: str) -> str:
        return f"rl:user:{user_id}:stats"
