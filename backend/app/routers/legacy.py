from fastapi import APIRouter, HTTPException

from app import config
from app.services import odoo
from app.transformers import transform_project_ticket


router = APIRouter()
legacy_router = APIRouter()

PROJECT_TASK_FIELDS = [
    "id",
    "name",
    "description",
    "stage_id",
    "user_ids",
    "tag_ids",
    "priority",
    "project_id",
    "create_date",
]


@router.get("/")
def root():
    return {
        "application": "IT Helpdesk v2",
        "status": "running",
        "version": "0.2.0",
    }


@legacy_router.get("/api/tickets")
def get_tickets():
    tasks = odoo.search_read(
        model="project.task",
        domain=[["project_id", "=", config.ODOO_PROJECT_ID]],
        fields=PROJECT_TASK_FIELDS,
    )
    tickets = [transform_project_ticket(task) for task in tasks]
    return {"success": True, "count": len(tickets), "tickets": tickets}


@legacy_router.get("/api/tickets/{ticket_id}")
def get_ticket_detail(ticket_id: int):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    tasks = odoo.search_read(
        model="project.task",
        domain=[
            ["id", "=", ticket_id],
            ["project_id", "=", config.ODOO_PROJECT_ID],
        ],
        fields=[*PROJECT_TASK_FIELDS, "write_date"],
        limit=1,
    )
    if not tasks:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    ticket = transform_project_ticket(tasks[0])
    ticket["updated_at"] = tasks[0].get("write_date")
    return {"success": True, "ticket": ticket}
