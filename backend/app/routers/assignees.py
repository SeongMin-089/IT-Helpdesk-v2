from fastapi import APIRouter

from app.services import assignments


router = APIRouter(prefix="/api/oca")


@router.get("/assignees")
def get_oca_assignees():
    users = assignments.get_valid_helpdesk_assignees()
    return {"success": True, "count": len(users), "assignees": users}
