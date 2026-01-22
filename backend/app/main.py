from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import RateLimitMiddleware
from app.api.routes_health import router as health_router
from app.api.routes_evals import router as evals_router
from app.api.routes_testcases import router as testcases_router
from app.api.routes_runs import router as runs_router


configure_logging(settings.log_level)

app = FastAPI(title=settings.project_name, redirect_slashes=False)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute, burst=settings.rate_limit_burst)

app.include_router(health_router)
app.include_router(evals_router)
app.include_router(testcases_router)
app.include_router(runs_router)

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
