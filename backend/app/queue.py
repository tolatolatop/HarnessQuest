from redis import Redis
from rq import Queue

from app.config import get_settings


def get_queue() -> Queue:
    settings = get_settings()
    return Queue("default", connection=Redis.from_url(settings.redis_url))

