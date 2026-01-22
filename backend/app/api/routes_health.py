from fastapi import APIRouter, Depends

from app.core.security import verify_admin_key

router = APIRouter(dependencies=[Depends(verify_admin_key)])


@router.get("/health")
def health():
    return {"status": "ok"}
