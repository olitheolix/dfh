"""These endpoints must only be included during testing."""

from fastapi import APIRouter

import dfh.routers.uam as uam
from dfh.models import UAMGroup

router = APIRouter()


@router.delete("/demo/api/uam/v1/test-flushdb")
def flush_db():
    uam.UAM_DB.users.clear()
    uam.UAM_DB.groups.clear()
    uam.UAM_DB.root = UAMGroup(name="Org", owner="none", provider="none")
