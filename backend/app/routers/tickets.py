import base64
import binascii
from html import escape
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException, Query, Response

from app.constants import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_SIZE,
    OCA_PRIORITY_PATTERN,
    OCA_TICKET_FIELDS,
)
from app.routers import auth
from app.routers.archive import (
    TicketSort,
    get_oca_ticket_including_archived,
    get_oca_ticket_page,
)
from app.routers.categories import get_category_record
from app.routers.faqs import create_faq_draft, require_faq_writes
from app.schemas import (
    OcaTicketCreate,
    OcaTicketCommentCreate,
    OcaTicketReprocess,
    OcaTicketResolve,
    OcaTicketStageUpdate,
    OcaTicketUpdate,
)
from app.services import assignments, odoo
from app.transformers import clean_description, oca_relation, transform_oca_tickets


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
    auth.ensure_ticket_owner(records[0])
    if not records[0].get("active"):
        raise HTTPException(
            status_code=409,
            detail="보관된 문의의 단계는 변경할 수 없습니다.",
        )
    return records[0]


def ensure_ticket_accepts_content(ticket):
    if ticket.get("closed"):
        raise HTTPException(
            status_code=409,
            detail="종료된 문의에는 댓글이나 첨부 파일을 추가할 수 없습니다.",
        )


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
        author_id=auth.get_current_user()["partner_id"],
    )


def transform_ticket_message(message, note_subtype_id):
    return {
        "id": message["id"],
        "body": clean_description(message.get("body")),
        "author": oca_relation(message.get("author_id")),
        "created_at": message.get("date"),
        "kind": (
            "note"
            if relation_id(message.get("subtype_id")) == note_subtype_id
            else "comment"
        ),
        "message_type": message.get("message_type"),
        "subtype": oca_relation(message.get("subtype_id")),
    }


def get_ticket_comment_subtypes():
    records = odoo.search_read(
        model="ir.model.data",
        fields=["name", "res_id"],
        domain=[
            ["module", "=", "mail"],
            ["name", "in", ["mt_comment", "mt_note"]],
            ["model", "=", "mail.message.subtype"],
        ],
        limit=2,
    )
    subtype_ids = {record["name"]: record["res_id"] for record in records}
    if set(subtype_ids) != {"mt_comment", "mt_note"}:
        raise HTTPException(
            status_code=502,
            detail="Odoo 댓글 하위 유형을 확인할 수 없습니다.",
        )
    return subtype_ids


def get_ticket_for_content_read(ticket_id):
    if ticket_id <= 0:
        raise HTTPException(status_code=400, detail="올바르지 않은 문의 번호입니다.")
    ticket = get_oca_ticket_including_archived(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    return ticket


def transform_ticket_attachment(attachment):
    return {
        "id": attachment["id"],
        "name": attachment.get("name") or "",
        "content_type": attachment.get("mimetype") or "application/octet-stream",
        "size": attachment.get("file_size") or 0,
        "created_at": attachment.get("create_date"),
        "created_by": oca_relation(attachment.get("create_uid")),
    }


def tracking_relation_value(record, prefix):
    record_id = record.get(f"{prefix}_value_integer") or None
    name = record.get(f"{prefix}_value_char") or None
    if record_id is None and name is None:
        return None
    return {"id": record_id, "name": name}


def transform_ticket_tracking(tracking, message, field):
    return {
        "id": tracking["id"],
        "message_id": relation_id(tracking.get("mail_message_id")),
        "changed_at": message.get("date"),
        "changed_by": oca_relation(message.get("author_id")),
        "change_type": "status" if field["name"] == "stage_id" else "assignee",
        "field": {
            "id": field["id"],
            "name": field["name"],
            "label": field.get("field_description") or field["name"],
            "type": field.get("ttype"),
        },
        "old_value": tracking_relation_value(tracking, "old"),
        "new_value": tracking_relation_value(tracking, "new"),
    }


def validate_attachment(filename, content_type, file_data):
    if not file_data:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다.")
    if len(file_data) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=413,
            detail="첨부 파일은 10MB를 초과할 수 없습니다.",
        )
    if any(character in filename for character in ("/", "\\", "\r", "\n", "\0")):
        raise HTTPException(status_code=422, detail="올바르지 않은 파일명입니다.")

    expected_type = ALLOWED_ATTACHMENT_TYPES.get(PurePath(filename).suffix.lower())
    if expected_type is None or content_type != expected_type:
        raise HTTPException(
            status_code=422,
            detail="허용되지 않거나 파일 확장자와 일치하지 않는 형식입니다.",
        )


@router.get("")
def get_oca_tickets(
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    stage_id: Annotated[int | None, Query(gt=0)] = None,
    priority: Annotated[str | None, Query(pattern=OCA_PRIORITY_PATTERN)] = None,
    category_id: Annotated[int | None, Query(gt=0)] = None,
    assignee_id: Annotated[int | None, Query(gt=0)] = None,
    partner_id: Annotated[int | None, Query(gt=0)] = None,
    team_id: Annotated[int | None, Query(gt=0)] = None,
    tag_id: Annotated[int | None, Query(gt=0)] = None,
    unassigned: bool | None = None,
    closed: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    sort: TicketSort = "priority",
):
    return get_oca_ticket_page(
        active=True,
        q=q,
        stage_id=stage_id,
        priority=priority,
        category_id=category_id,
        assignee_id=assignee_id,
        partner_id=partner_id,
        team_id=team_id,
        tag_id=tag_id,
        unassigned=unassigned,
        closed=closed,
        page=page,
        page_size=page_size,
        sort=sort,
    )


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
        context={"active_test": False},
    )
    if not records:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    auth.ensure_ticket_owner(records[0])
    return {"success": True, "ticket": transform_oca_tickets(records)[0]}


@router.post("", status_code=201)
def create_oca_ticket(data: OcaTicketCreate):
    user = auth.get_current_user()
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
        "partner_id": user["partner_id"],
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

    existing_records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
        context={"active_test": False},
    )
    if not existing_records:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    existing = existing_records[0]
    auth.ensure_ticket_owner(existing)
    if not existing.get("active") or existing.get("closed"):
        raise HTTPException(status_code=409, detail="종료·보관 문의는 수정할 수 없습니다.")

    user = auth.get_current_user()
    original_fields_requested = data.title is not None or data.description is not None
    management_fields_requested = (
        data.priority is not None or "assignee_id" in data.model_fields_set
    )
    if original_fields_requested:
        auth.require_ticket_owner(existing)
        workflow = get_ticket_workflow(existing)
        if get_workflow_position(existing, workflow) not in {NEW_STAGE, ASSIGNED_STAGE}:
            raise HTTPException(
                status_code=409,
                detail="접수 또는 배정 단계의 본인 문의만 원본 정보를 수정할 수 있습니다.",
            )
    if management_fields_requested and user["role"] != "agent":
        raise HTTPException(status_code=403, detail="IT 담당자 권한이 필요합니다.")

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
    auth.require_agent()
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
    auth.require_agent()
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
    auth.require_ticket_owner(ticket)
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
    auth.require_ticket_owner(ticket)
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


@router.get("/{ticket_id}/comments")
def get_oca_ticket_comments(ticket_id: int):
    get_ticket_for_content_read(ticket_id)
    subtype_ids = get_ticket_comment_subtypes()
    user = auth.get_current_user()
    visible_subtype_ids = (
        list(subtype_ids.values())
        if user["role"] == "agent"
        else [subtype_ids["mt_comment"]]
    )
    message_domain = [
        ["model", "=", "helpdesk.ticket"],
        ["res_id", "=", ticket_id],
        ["message_type", "=", "comment"],
        ["subtype_id", "in", visible_subtype_ids],
    ]
    if user["role"] != "agent":
        message_domain.append(["is_internal", "=", False])
    messages = odoo.search_read(
        model="mail.message",
        fields=[
            "id",
            "body",
            "author_id",
            "date",
            "message_type",
            "subtype_id",
        ],
        domain=message_domain,
        limit=100,
    )
    comments = [
        transform_ticket_message(message, subtype_ids["mt_note"])
        for message in messages
    ]
    return {"success": True, "count": len(comments), "comments": comments}


@router.get("/{ticket_id}/history")
def get_oca_ticket_history(
    ticket_id: int,
    limit: int = Query(default=50, ge=1, le=100),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )
    if get_oca_ticket_including_archived(ticket_id) is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    fields = odoo.search_read(
        model="ir.model.fields",
        fields=["id", "name", "field_description", "ttype"],
        domain=[
            ["model", "=", "helpdesk.ticket"],
            ["name", "in", ["stage_id", "user_id"]],
        ],
        limit=2,
    )
    field_by_id = {field["id"]: field for field in fields}
    if {field["name"] for field in fields} != {"stage_id", "user_id"}:
        raise HTTPException(
            status_code=502,
            detail="Odoo에서 상태·담당자 필드 메타데이터를 확인할 수 없습니다.",
        )

    messages = odoo.search_read(
        model="mail.message",
        fields=["id", "date", "author_id"],
        domain=[
            ["model", "=", "helpdesk.ticket"],
            ["res_id", "=", ticket_id],
        ],
        limit=100,
        order="date desc, id desc",
    )
    if not messages:
        return {"success": True, "count": 0, "history": []}

    message_by_id = {message["id"]: message for message in messages}
    tracking_values = odoo.search_read(
        model="mail.tracking.value",
        fields=[
            "id",
            "field_id",
            "mail_message_id",
            "old_value_integer",
            "old_value_char",
            "new_value_integer",
            "new_value_char",
        ],
        domain=[
            ["mail_message_id", "in", list(message_by_id)],
            ["field_id", "in", list(field_by_id)],
        ],
        limit=200,
        order="id desc",
    )

    history = []
    for tracking in tracking_values:
        field = field_by_id.get(relation_id(tracking.get("field_id")))
        message = message_by_id.get(
            relation_id(tracking.get("mail_message_id"))
        )
        if field is not None and message is not None:
            history.append(transform_ticket_tracking(tracking, message, field))
    history.sort(
        key=lambda item: (item.get("changed_at") or "", item["id"]),
        reverse=True,
    )
    history = history[:limit]
    return {"success": True, "count": len(history), "history": history}


@router.post("/{ticket_id}/comments", status_code=201)
def create_oca_ticket_comment(ticket_id: int, data: OcaTicketCommentCreate):
    ticket = get_ticket_for_stage_change(ticket_id)
    ensure_ticket_accepts_content(ticket)
    user = auth.get_current_user()
    if data.kind == "note" and user["role"] != "agent":
        raise HTTPException(status_code=403, detail="내부 메모는 IT 담당자만 작성할 수 있습니다.")
    safe_body = escape(data.body).replace("\n", "<br>")
    subtype_xmlid = "mail.mt_note" if data.kind == "note" else "mail.mt_comment"
    message_id = odoo.message_post(
        "helpdesk.ticket",
        ticket_id,
        f"<p>{safe_body}</p>",
        subtype_xmlid=subtype_xmlid,
        author_id=user["partner_id"],
    )
    return {
        "success": True,
        "message": "댓글이 등록되었습니다.",
        "comment_id": message_id,
        "kind": data.kind,
    }


@router.get("/{ticket_id}/attachments")
def get_oca_ticket_attachments(ticket_id: int):
    get_ticket_for_content_read(ticket_id)
    records = odoo.search_read(
        model="ir.attachment",
        fields=[
            "id",
            "name",
            "mimetype",
            "file_size",
            "create_date",
            "create_uid",
        ],
        domain=[
            ["res_model", "=", "helpdesk.ticket"],
            ["res_id", "=", ticket_id],
            ["type", "=", "binary"],
        ],
        limit=100,
    )
    attachments = [transform_ticket_attachment(record) for record in records]
    return {
        "success": True,
        "count": len(attachments),
        "attachments": attachments,
    }


@router.post("/{ticket_id}/attachments", status_code=201)
def upload_oca_ticket_attachment(
    ticket_id: int,
    filename: str = Query(min_length=1, max_length=255),
    content_type: str = Query(min_length=1, max_length=200),
    file_data: bytes = Body(media_type="application/octet-stream"),
):
    ticket = get_ticket_for_stage_change(ticket_id)
    ensure_ticket_accepts_content(ticket)
    validate_attachment(filename, content_type, file_data)
    result = odoo.create(
        "ir.attachment",
        {
            "name": filename,
            "datas": base64.b64encode(file_data).decode("ascii"),
            "mimetype": content_type,
            "res_model": "helpdesk.ticket",
            "res_id": ticket_id,
            "type": "binary",
        },
    )
    return {
        "success": True,
        "message": "첨부 파일이 등록되었습니다.",
        "attachment": {
            "id": result[0],
            "name": filename,
            "content_type": content_type,
            "size": len(file_data),
        },
    }


@router.get("/{ticket_id}/attachments/{attachment_id}/download")
def download_oca_ticket_attachment(ticket_id: int, attachment_id: int):
    get_ticket_for_content_read(ticket_id)
    if attachment_id <= 0:
        raise HTTPException(status_code=400, detail="올바르지 않은 첨부 번호입니다.")

    records = odoo.search_read(
        model="ir.attachment",
        fields=["id", "name", "mimetype", "datas"],
        domain=[
            ["id", "=", attachment_id],
            ["res_model", "=", "helpdesk.ticket"],
            ["res_id", "=", ticket_id],
            ["type", "=", "binary"],
        ],
        limit=1,
    )
    if not records:
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다.")

    attachment = records[0]
    try:
        content = base64.b64decode(attachment.get("datas") or "", validate=True)
    except (binascii.Error, TypeError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="Odoo 첨부 파일 데이터를 읽을 수 없습니다.",
        )

    filename = attachment.get("name") or f"attachment-{attachment_id}"
    return Response(
        content=content,
        media_type=attachment.get("mimetype") or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
            )
        },
    )


@router.post("/{ticket_id}/faq-drafts", status_code=201)
def create_faq_draft_from_ticket(ticket_id: int):
    auth.require_agent()
    require_faq_writes()
    ticket = get_ticket_for_stage_change(ticket_id)
    workflow = get_ticket_workflow(ticket)
    if get_workflow_position(ticket, workflow) not in {
        RESOLVED_STAGE,
        DONE_STAGE,
    }:
        raise HTTPException(
            status_code=409,
            detail="해결 또는 종료된 문의만 FAQ 초안으로 만들 수 있습니다.",
        )

    subtype_records = odoo.search_read(
        model="ir.model.data",
        fields=["res_id"],
        domain=[
            ["module", "=", "mail"],
            ["name", "=", "mt_note"],
            ["model", "=", "mail.message.subtype"],
        ],
        limit=1,
    )
    if not subtype_records:
        raise HTTPException(
            status_code=502,
            detail="Odoo 내부 메모 유형을 확인할 수 없습니다.",
        )

    messages = odoo.search_read(
        model="mail.message",
        fields=["id", "body", "subtype_id", "date"],
        domain=[
            ["model", "=", "helpdesk.ticket"],
            ["res_id", "=", ticket_id],
            ["message_type", "=", "comment"],
            ["subtype_id", "=", subtype_records[0]["res_id"]],
            ["body", "ilike", "해결 내용"],
        ],
        limit=20,
        order="date desc, id desc",
    )
    resolution = None
    for message in messages:
        lines = clean_description(message.get("body")).splitlines()
        if lines and lines[0].strip() == "해결 내용":
            content = "\n".join(lines[1:]).strip()
            if content:
                resolution = content
                break
    if resolution is None:
        raise HTTPException(
            status_code=422,
            detail="FAQ 초안에 사용할 해결 내용 내부 메모를 찾을 수 없습니다.",
        )

    faq = create_faq_draft(ticket.get("name") or "", resolution)
    return {
        "success": True,
        "message": "문의 해결 내용을 비공개 FAQ 초안으로 생성했습니다.",
        "review_required": True,
        "faq": faq,
    }
