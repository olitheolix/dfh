import logging

from fastapi import APIRouter, status
from fastapi.responses import FileResponse

# Convenience.
logit = logging.getLogger("app")
router = APIRouter()


# ----------------------------------------------------------------------
# Basic Routes.
# ----------------------------------------------------------------------


@router.get("/healthz")
@router.get("/demo/api/healthz")
def get_healthz() -> int:
    """Health check endpoint. Always returns 200."""
    return status.HTTP_200_OK


# Serve static web app on all paths that have not been defined explicitly.
@router.get("/{path:path}", include_in_schema=False)
async def catch_all():
    return FileResponse("static/index.html")
