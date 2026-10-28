from html import escape

from fastapi import APIRouter, HTTPException

from app.constants import OCA_TICKET_FIELDS
from app.routers.categories import get_category_record
from app.schemas import (
    OcaTicketCreate,
    OcaTicketReprocess,
    OcaTicketResolve,
    OcaTicketStageUpdate,
    OcaTicketUpdate,
)
from app.services import assignments, odoo
from app.transformers import transform_oca_tickets


router = APIRouter(prefix="/api/oca/tickets")

WORKFLOW_STAGE_COUNT = 5
NEW_STAGE = 0
ASSIGNED_STAGE = 1
IN_PROGRESS_STAGE = 2
RESOLVED_STAGE = 3
DONE_STAGE = 4


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


def get_ticket_for_stage_change(ticket_id):
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
        context={"active_test": False},
    )
    if not records:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    if not records[0].get("active"):
        raise HTTPException(
            status_code=409,
            detail="보관된 문의의 단계는 변경할 수 없습니다.",
        )
    return records[0]


def get_ticket_workflow(ticket):
    stages = odoo.search_read(
        model="helpdesk.ticket.stage",
        fields=[
            "id",
            "name",
            "sequence",
            "active",
            "team_ids",
            "company_id",
            "closed",
        ],
        domain=[["active", "=", True]],
        limit=100,
    )
    ticket_team_id = relation_id(ticket.get("team_id"))
    ticket_company_id = relation_id(ticket.get("company_id"))
    applicable = [
        stage
        for stage in stages
        if (
            not stage.get("team_ids")
            or ticket_team_id in stage.get("team_ids", [])
        )
        and (
            not relation_id(stage.get("company_id"))
            or relation_id(stage.get("company_id")) == ticket_company_id
        )
    ]
    applicable.sort(key=lambda stage: (stage.get("sequence") or 0, stage["id"]))

    if (
        len(applicable) != WORKFLOW_STAGE_COUNT
        or any(stage.get("closed") for stage in applicable[:-1])
        or not applicable[-1].get("closed")
    ):
        raise HTTPException(
            status_code=502,
            detail="Odoo의 활성 문의 단계가 5단계 업무 흐름과 일치하지 않습니다.",
        )
    return applicable


def get_workflow_position(ticket, workflow):
    current_stage_id = relation_id(ticket.get("stage_id"))
    for position, stage in enumerate(workflow):
        if stage["id"] == current_stage_id:
            return position
    raise HTTPException(
        status_code=409,
        detail="문의의 현재 단계가 5단계 업무 흐름에 포함되지 않습니다.",
    )


def apply_ticket_stage(ticket_id, stage_id, message):
    odoo.write("helpdesk.ticket", ticket_id, {"stage_id": stage_id})
    updated = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )
    if not updated or relation_id(updated[0].get("stage_id")) != stage_id:
        raise HTTPException(
            status_code=502,
            detail="Odoo에서 문의 단계 변경을 확인할 수 없습니다.",
        )
    return {
        "success": True,
        "message": message,
        "ticket": transform_oca_tickets(updated)[0],
    }


def post_workflow_note(ticket_id, label, content):
    safe_content = escape(content).replace("\n", "<br>")
    odoo.message_post(
        "helpdesk.ticket",
        ticket_id,
        f"<p><strong>{label}</strong><br>{safe_content}</p>",
    )


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
    ticket = get_ticket_for_stage_change(ticket_id)
    get_active_compatible_stage(data.stage_id, ticket)
    workflow = get_ticket_workflow(ticket)
    current_position = get_workflow_position(ticket, workflow)
    target_positions = {
        stage["id"]: position for position, stage in enumerate(workflow)
    }
    if data.stage_id not in target_positions:
        raise HTTPException(
            status_code=422,
            detail="문의 팀과 회사의 5단계 업무 흐름에 포함되지 않은 단계입니다.",
        )
    target_position = target_positions[data.stage_id]

    if current_position == target_position:
        return {
            "success": True,
            "message": "문의가 이미 요청한 단계입니다.",
            "ticket": transform_oca_tickets([ticket])[0],
        }
    if (current_position, target_position) not in {
        (NEW_STAGE, ASSIGNED_STAGE),
        (ASSIGNED_STAGE, IN_PROGRESS_STAGE),
    }:
        raise HTTPException(
            status_code=409,
            detail="허용되지 않은 단계 전환입니다. 업무 처리 전용 API를 사용하세요.",
        )
    return apply_ticket_stage(ticket_id, data.stage_id, "문의 단계가 변경되었습니다.")


@router.post("/{ticket_id}/resolve")
def resolve_oca_ticket(ticket_id: int, data: OcaTicketResolve):
    ticket = get_ticket_for_stage_change(ticket_id)
    workflow = get_ticket_workflow(ticket)
    if get_workflow_position(ticket, workflow) != IN_PROGRESS_STAGE:
        raise HTTPException(
            status_code=409,
            detail="처리 중인 문의만 해결할 수 있습니다.",
        )

    post_workflow_note(ticket_id, "해결 내용", data.resolution)
    return apply_ticket_stage(
        ticket_id,
        workflow[RESOLVED_STAGE]["id"],
        "문의가 해결되었습니다.",
    )


@router.post("/{ticket_id}/close")
def close_oca_ticket(ticket_id: int):
    ticket = get_ticket_for_stage_change(ticket_id)
    workflow = get_ticket_workflow(ticket)
    if get_workflow_position(ticket, workflow) != RESOLVED_STAGE:
        raise HTTPException(
            status_code=409,
            detail="해결된 문의만 종료할 수 있습니다.",
        )
    return apply_ticket_stage(
        ticket_id,
        workflow[DONE_STAGE]["id"],
        "문의가 종료되었습니다.",
    )


@router.post("/{ticket_id}/reprocess")
def reprocess_oca_ticket(ticket_id: int, data: OcaTicketReprocess):
    ticket = get_ticket_for_stage_change(ticket_id)
    workflow = get_ticket_workflow(ticket)
    if get_workflow_position(ticket, workflow) != RESOLVED_STAGE:
        raise HTTPException(
            status_code=409,
            detail="해결된 문의만 재처리할 수 있습니다.",
        )

    post_workflow_note(ticket_id, "재처리 사유", data.reason)
    return apply_ticket_stage(
        ticket_id,
        workflow[IN_PROGRESS_STAGE]["id"],
        "문의가 재처리 단계로 변경되었습니다.",
    )
