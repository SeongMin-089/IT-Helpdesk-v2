from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.constants import OCA_PRIORITY_PATTERN, OCA_TICKET_FIELDS
from app.routers import auth
from app.services import odoo
from app.transformers import transform_oca_tickets


router = APIRouter(prefix="/api/oca/tickets")

TicketSort = Literal["priority", "newest", "oldest", "updated"]
TICKET_SORT_ORDERS = {
    "priority": "priority desc, create_date desc, id desc",
    "newest": "create_date desc, id desc",
    "oldest": "create_date asc, id asc",
    "updated": "write_date desc, id desc",
}


def build_ticket_list_domain(
    active,
    q=None,
    stage_id=None,
    priority=None,
    category_id=None,
    assignee_id=None,
    partner_id=None,
    team_id=None,
    tag_id=None,
    unassigned=None,
    closed=None,
):
    domain = [["active", "=", active]]
    if q is not None:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=422, detail="검색어는 비워둘 수 없습니다.")
        domain.extend(
            [
                "|",
                "|",
                ["number", "ilike", query],
                ["name", "ilike", query],
                ["description", "ilike", query],
            ]
        )
    filters = (
        ("stage_id", stage_id),
        ("priority", priority),
        ("category_id", category_id),
        ("user_id", assignee_id),
        ("partner_id", partner_id),
        ("team_id", team_id),
    )
    for field, value in filters:
        if value is not None:
            domain.append([field, "=", value])
    if tag_id is not None:
        domain.append(["tag_ids", "in", [tag_id]])
    if unassigned:
        domain.append(["user_id", "=", False])
    if closed is not None:
        domain.append(["closed", "=", closed])
    return domain


def get_oca_ticket_page(active, page=1, page_size=50, sort="priority", **filters):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="올바르지 않은 페이징 값입니다.")
    for field in (
        "stage_id",
        "category_id",
        "assignee_id",
        "partner_id",
        "team_id",
        "tag_id",
    ):
        value = filters.get(field)
        if value is not None and value <= 0:
            raise HTTPException(status_code=422, detail=f"{field}는 양수여야 합니다.")
    priority = filters.get("priority")
    if priority is not None and priority not in {"0", "1", "2", "3"}:
        raise HTTPException(status_code=422, detail="올바르지 않은 우선순위입니다.")
    if filters.get("unassigned") is True and filters.get("assignee_id") is not None:
        raise HTTPException(
            status_code=422,
            detail="미배정 문의와 담당자를 동시에 지정할 수 없습니다.",
        )
    order = TICKET_SORT_ORDERS.get(sort)
    if order is None:
        raise HTTPException(status_code=422, detail="올바르지 않은 정렬 기준입니다.")

    domain = build_ticket_list_domain(active=active, **filters)
    user = auth.get_current_user()
    if user["role"] != "agent":
        domain.append(["partner_id", "=", user["partner_id"]])
    context = {"active_test": False} if not active else None
    total = odoo.search_count("helpdesk.ticket", domain=domain, context=context)
    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=domain,
        limit=page_size,
        offset=(page - 1) * page_size,
        order=order,
        context=context,
    )
    tickets = transform_oca_tickets(records)
    total_pages = (total + page_size - 1) // page_size
    return {
        "success": True,
        "count": len(tickets),
        "tickets": tickets,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }


@router.get("/archived")
def get_archived_oca_tickets(
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
        active=False,
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


def get_oca_ticket_including_archived(ticket_id):
    records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
        context={"active_test": False},
    )
    if not records:
        return None
    auth.ensure_ticket_owner(records[0])
    return records[0]


def set_oca_ticket_active(ticket_id, active):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    existing = get_oca_ticket_including_archived(ticket_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    user = auth.get_current_user()
    if user["role"] != "agent":
        auth.require_ticket_owner(existing)
        from app.routers.tickets import get_ticket_workflow, get_workflow_position

        if get_workflow_position(existing, get_ticket_workflow(existing)) not in {0, 1}:
            raise HTTPException(
                status_code=409,
                detail="접수 또는 배정 단계의 본인 문의만 보관·복원할 수 있습니다.",
            )
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
