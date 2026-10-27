from fastapi import APIRouter, HTTPException

from app.constants import OCA_TICKET_FIELDS
from app.services import odoo
from app.transformers import transform_oca_tickets


router = APIRouter(prefix="/api/oca/tickets")


@router.get("/archived")
def get_archived_oca_tickets():
    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["active", "=", False]],
        limit=50,
        context={"active_test": False},
    )
    tickets = transform_oca_tickets(records)
    return {"success": True, "count": len(tickets), "tickets": tickets}


def get_oca_ticket_including_archived(ticket_id):
    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
        context={"active_test": False},
    )
    return records[0] if records else None


def set_oca_ticket_active(ticket_id, active):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    existing = get_oca_ticket_including_archived(ticket_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    if bool(existing.get("active")) == active:
        action = "복원" if active else "보관"
        raise HTTPException(
            status_code=409,
            detail=f"이미 {action}된 문의입니다.",
        )

    odoo.write("helpdesk.ticket", ticket_id, {"active": active})
    updated = get_oca_ticket_including_archived(ticket_id)
    if updated is None or bool(updated.get("active")) != active:
        raise HTTPException(
            status_code=502,
            detail="Odoo에서 문의 상태 변경을 확인할 수 없습니다.",
        )
    return updated


@router.patch("/{ticket_id}/archive")
def archive_oca_ticket(ticket_id: int):
    ticket = set_oca_ticket_active(ticket_id, False)
    return {
        "success": True,
        "message": "문의가 보관되었습니다.",
        "ticket": transform_oca_tickets([ticket])[0],
    }


@router.patch("/{ticket_id}/restore")
def restore_oca_ticket(ticket_id: int):
    ticket = set_oca_ticket_active(ticket_id, True)
    return {
        "success": True,
        "message": "문의가 복원되었습니다.",
        "ticket": transform_oca_tickets([ticket])[0],
    }
