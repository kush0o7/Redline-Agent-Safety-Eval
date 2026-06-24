#!/bin/sh
set -e

# Run DB migrations
alembic -c app/db/alembic.ini upgrade head

# Start ARQ worker in background
python -m arq app.queue.worker.WorkerSettings &

# Give worker 3s to grab its Redis connection before uvicorn tries
sleep 3

# Start uvicorn in foreground (PID 1 equivalent via exec)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
