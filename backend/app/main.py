from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from urllib.parse import urlparse
from arq.connections import create_pool, RedisSettings

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import RateLimitMiddleware
from app.api.routes_health import router as health_router
from app.api.routes_evals import router as evals_router
from app.api.routes_testcases import router as testcases_router
from app.api.routes_runs import router as runs_router, stream_router
from app.api.routes_public import router as public_router


configure_logging(settings.log_level)


def _redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname,
        port=parsed.port or 6379,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(_redis_settings())
    yield
    await app.state.arq_pool.close()


app = FastAPI(title=settings.project_name, redirect_slashes=False, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute, burst=settings.rate_limit_burst)

app.include_router(health_router)
app.include_router(evals_router)
app.include_router(testcases_router)
app.include_router(stream_router)  # stream before runs so /stream isn't parsed as a run_id
app.include_router(runs_router)
app.include_router(public_router)

ui_path = os.getenv("UI_DIR", "/app/ui")
if os.path.isdir(ui_path):
    app.mount("/ui", StaticFiles(directory=ui_path, html=True), name="ui")


@app.get("/ui/")
def ui_index():
    index_path = os.path.join(ui_path, "index.html")
    if not os.path.isfile(index_path):
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(index_path)


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/ui/")
