from fastapi import APIRouter

from app.services import odoo


router = APIRouter(prefix="/api/oca")


@router.get("/stages")
def get_oca_stages():
    stages = odoo.search_read(
        model="helpdesk.ticket.stage",
        fields=["id", "name", "sequence", "closed"],
        limit=100,
    )
    return {"success": True, "count": len(stages), "stages": stages}
