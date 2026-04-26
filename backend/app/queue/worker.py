from arq.connections import RedisSettings

from app.core.config import settings
from app.queue.tasks import run_eval_task


class WorkerSettings:
    functions = [run_eval_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 600  # 10 minutes max per eval run
