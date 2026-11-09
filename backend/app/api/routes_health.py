from fastapi import APIRouter

from app.core.config import settings

# No auth: load balancers and uptime monitors can't send the admin key,
# and this returns nothing sensitive.
router = APIRouter()


@router.get("/health")
def health():
    # `deployment` lets the UI show the "demo only" banner and know whether the
    # eval form needs the admin key.
    return {
        "status": "ok",
        "deployment": settings.redline_env,
        "eval_auth_required": settings.require_eval_auth,
    }
