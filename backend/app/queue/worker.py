from redis import Redis
from rq import Worker, Queue

from app.core.config import settings


def run_worker() -> None:
    redis_conn = Redis.from_url(settings.redis_url)
    queue = Queue("runs", connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    run_worker()
