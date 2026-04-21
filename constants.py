import os

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "Rate-Limited API Service"
APP_VERSION = "1.0"

RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "30"))

QUEUE_WORKER_ENABLED = os.getenv("QUEUE_WORKER_ENABLED", "true").lower() == "true"
QUEUE_WORKER_INTERVAL_SECONDS = float(os.getenv("QUEUE_WORKER_INTERVAL_SECONDS", "1.0"))
