from urllib.parse import urlparse

from arq.connections import RedisSettings

from app.core.config import settings
from app.queue.tasks import run_eval_task


def _make_redis_settings(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname,
        port=parsed.port or 6379,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


class WorkerSettings:
    functions = [run_eval_task]
    redis_settings = _make_redis_settings(settings.redis_url)
    max_jobs = 10
    job_timeout = 600
