from __future__ import annotations

import ipaddress
import secrets
import socket
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings


def constant_time_key_match(candidate: str | None) -> bool:
    """Compare a presented key to the admin key without leaking length/content via timing."""
    if not candidate:
        return False
    try:
        return secrets.compare_digest(candidate, settings.admin_api_key)
    except TypeError:
        # compare_digest raises on non-ASCII input; treat as a failed match, not a 500
        return False


async def verify_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    if not constant_time_key_match(x_admin_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


# Private/internal IP ranges that must never be reachable via agent_endpoint_url
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS/GCP metadata
    ipaddress.ip_network("100.64.0.0/10"),    # Fly.io internal
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "169.254.169.254"}


def validate_agent_url(url: str) -> str:
    """Raise HTTPException if URL could reach internal services (SSRF)."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid agent endpoint URL")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Agent endpoint URL must use http or https")

    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        raise HTTPException(status_code=400, detail="Agent endpoint URL has no host")

    if host in _BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail="Agent endpoint URL points to a blocked host")

    # Collect every IP this host could point at. If it's a literal IP, that's the
    # only one; if it's a hostname, resolve it so a name that maps to an internal
    # address (cloud metadata, RFC1918, loopback) is rejected — not just raw IPs.
    candidate_ips: list[ipaddress._BaseAddress] = []
    try:
        candidate_ips.append(ipaddress.ip_address(host))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Agent endpoint URL host could not be resolved")
        for info in infos:
            try:
                candidate_ips.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue

    for addr in candidate_ips:
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            raise HTTPException(status_code=400, detail="Agent endpoint URL points to a private/internal address")
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise HTTPException(status_code=400, detail="Agent endpoint URL points to a private/internal address")

    return url


def client_ip(request: Request) -> str:
    """Best-effort real client IP.

    Behind Fly's proxy the TCP peer is the edge proxy, so prefer Fly-Client-IP
    (set by Fly, not spoofable through it), then the leftmost X-Forwarded-For hop
    (only populated correctly when uvicorn runs with --proxy-headers), then the
    raw socket peer.
    """
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip:
        return fly_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter.

    Two tiers:
    - /quick-eval POST: 5 requests per 5 minutes per IP (prevents LLM cost abuse)
    - everything else: per_minute + burst as configured
    """

    EVAL_LIMIT = 5
    EVAL_WINDOW = 300  # seconds

    def __init__(self, app, per_minute: int, burst: int) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self.burst = burst
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.eval_requests: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.time()

    def _cleanup(self, now: float) -> None:
        """Periodically evict stale IP entries to prevent memory growth."""
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        for bucket in (self.requests, self.eval_requests):
            stale = [ip for ip, dq in bucket.items() if not dq or now - dq[-1] > 600]
            for ip in stale:
                del bucket[ip]

    async def dispatch(self, request: Request, call_next):
        ip = client_ip(request)
        now = time.time()
        self._cleanup(now)

        # Tight limit for eval endpoint
        if request.method == "POST" and request.url.path == "/quick-eval":
            bucket = self.eval_requests[ip]
            while bucket and now - bucket[0] > self.EVAL_WINDOW:
                bucket.popleft()
            if len(bucket) >= self.EVAL_LIMIT:
                retry = int(self.EVAL_WINDOW - (now - bucket[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Too many eval requests. Try again in {retry}s."},
                    headers={"Retry-After": str(retry)},
                )
            bucket.append(now)

        # General rate limit for everything
        bucket = self.requests[ip]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= self.per_minute + self.burst:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        bucket.append(now)

        return await call_next(request)
