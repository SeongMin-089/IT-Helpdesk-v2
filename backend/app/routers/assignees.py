from fastapi import APIRouter

from app.routers import auth
from app.services import assignments


router = APIRouter(prefix="/api/oca")


@router.get("/assignees")
def get_oca_assignees():
    auth.require_agent()
    users = assignments.get_valid_helpdesk_assignees()
    return {"success": True, "count": len(users), "assignees": users}
