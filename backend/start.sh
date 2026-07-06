#!/bin/sh
set -e

# Run DB migrations
alembic -c app/db/alembic.ini upgrade head

# Start ARQ worker in background, restarting it if it dies (e.g. OOM) —
# without this, a dead worker means every run queues forever with no error.
(
  while true; do
    python -m arq app.queue.worker.WorkerSettings || true
    echo "arq worker exited — restarting in 2s" >&2
    sleep 2
  done
) &

# Give worker time to grab its Redis connection before uvicorn tries
sleep 3

# Start uvicorn in foreground (PID 1 equivalent via exec).
# --proxy-headers: behind Fly's proxy the TCP peer is the edge, so trust
# X-Forwarded-* to recover real client IPs (only Fly can reach this port).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips '*'
