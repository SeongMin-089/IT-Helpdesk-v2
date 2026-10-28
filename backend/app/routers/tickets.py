from html import escape

from fastapi import APIRouter, HTTPException

from app.constants import OCA_TICKET_FIELDS
from app.routers.categories import get_category_record
from app.schemas import OcaTicketCreate, OcaTicketStageUpdate, OcaTicketUpdate
from app.services import assignments, odoo
from app.transformers import transform_oca_tickets


router = APIRouter(prefix="/api/oca/tickets")


def odoo_create_ticket(values):
    return odoo.create("helpdesk.ticket", values)


def relation_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return value if isinstance(value, int) else None


def get_active_compatible_stage(stage_id, ticket):
    stages = odoo.search_read(
        model="helpdesk.ticket.stage",
        fields=["id", "active", "team_ids", "company_id"],
        domain=[["id", "=", stage_id]],
        limit=1,
        context={"active_test": False},
    )
    if not stages or not stages[0].get("active"):
        raise HTTPException(
            status_code=422,
            detail="존재하지 않거나 비활성인 문의 단계입니다.",
        )

    stage = stages[0]
    allowed_team_ids = stage.get("team_ids") or []
    if allowed_team_ids and relation_id(ticket.get("team_id")) not in allowed_team_ids:
        raise HTTPException(
            status_code=422,
            detail="문의 팀에서 사용할 수 없는 단계입니다.",
        )

    stage_company_id = relation_id(stage.get("company_id"))
    if stage_company_id and stage_company_id != relation_id(ticket.get("company_id")):
        raise HTTPException(
            status_code=422,
            detail="문의 회사에서 사용할 수 없는 단계입니다.",
        )
    return stage


@router.get("")
def get_oca_tickets():
    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["active", "=", True]],
        limit=50,
    )
    tickets = transform_oca_tickets(records)
    return {"success": True, "count": len(tickets), "tickets": tickets}


@router.get("/{ticket_id}")
def get_oca_ticket_detail(ticket_id: int):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )
    if not records:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    return {"success": True, "ticket": transform_oca_tickets(records)[0]}


@router.post("", status_code=201)
def create_oca_ticket(data: OcaTicketCreate):
    title = data.title.strip()
    description = data.description.strip()
    if not title or not description:
        raise HTTPException(
            status_code=422,
            detail="제목과 문의 내용은 필수입니다.",
        )

    values = {
        "name": title,
        "description": escape(description).replace("\n", "<br>"),
        "priority": data.priority,
    }
    auto_assignee = None

    if data.category_id is not None:
        category = get_category_record(data.category_id)
        if not category.get("active"):
            raise HTTPException(
                status_code=422,
                detail="비활성 문의 유형은 선택할 수 없습니다.",
            )
        values["category_id"] = data.category_id
        auto_assignee = assignments.get_category_default_assignees(
            {data.category_id}
        ).get(data.category_id)
        if auto_assignee:
            values["user_id"] = auto_assignee["id"]
        else:
            values["user_id"] = False

    result = odoo_create_ticket(values)
    if not isinstance(result, list) or len(result) != 1:
        raise HTTPException(
            status_code=502,
            detail="Unexpected Odoo create response",
        )

    return {
        "success": True,
        "message": "문의가 등록되었습니다.",
        "ticket_id": result[0],
        "auto_assigned": auto_assignee is not None,
        "assignee": auto_assignee,
    }


@router.patch("/{ticket_id}")
def update_oca_ticket(ticket_id: int, data: OcaTicketUpdate):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    existing = odoo.search_read(
        model="helpdesk.ticket",
        fields=["id"],
        domain=[["id", "=", ticket_id]],
        limit=1,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    values = {}
    if data.title is not None:
        values["name"] = data.title.strip()
    if data.description is not None:
        values["description"] = escape(data.description.strip()).replace(
            "\n", "<br>"
        )
    if data.priority is not None:
        values["priority"] = data.priority

    if "assignee_id" in data.model_fields_set:
        if data.assignee_id is not None:
            users = odoo.search_read(
                model="res.users",
                fields=["id"],
                domain=[
                    ["id", "=", data.assignee_id],
                    ["share", "=", False],
                    ["active", "=", True],
                ],
                limit=1,
            )
            if not users:
                raise HTTPException(
                    status_code=422,
                    detail="유효하지 않은 담당자입니다.",
                )
        values["user_id"] = data.assignee_id or False

    odoo.write("helpdesk.ticket", ticket_id, values)
    updated = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )
    return {
        "success": True,
        "message": "문의가 수정되었습니다.",
        "ticket": transform_oca_tickets(updated)[0],
    }


@router.patch("/{ticket_id}/stage")
def update_oca_ticket_stage(ticket_id: int, data: OcaTicketStageUpdate):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    existing = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
        context={"active_test": False},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    ticket = existing[0]
    if not ticket.get("active"):
        raise HTTPException(
            status_code=409,
            detail="보관된 문의의 단계는 변경할 수 없습니다.",
        )

    get_active_compatible_stage(data.stage_id, ticket)
    if relation_id(ticket.get("stage_id")) != data.stage_id:
        odoo.write("helpdesk.ticket", ticket_id, {"stage_id": data.stage_id})

    updated = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )
    if not updated or relation_id(updated[0].get("stage_id")) != data.stage_id:
        raise HTTPException(
            status_code=502,
            detail="Odoo에서 문의 단계 변경을 확인할 수 없습니다.",
        )

    return {
        "success": True,
        "message": "문의 단계가 변경되었습니다.",
        "ticket": transform_oca_tickets(updated)[0],
    }
