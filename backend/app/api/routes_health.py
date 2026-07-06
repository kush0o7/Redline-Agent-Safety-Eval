from fastapi import APIRouter

# No auth: load balancers and uptime monitors can't send the admin key,
# and this returns nothing sensitive.
router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
