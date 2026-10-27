import os
import re
from html import unescape
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069").rstrip("/")

ODOO_DB = os.getenv("ODOO_DB", "It_Helpdesk_v2")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")
ODOO_PROJECT_ID = int(os.getenv("ODOO_PROJECT_ID", "1"))

app = FastAPI(
    title="IT Helpdesk v2 API",
    version="0.2.0",
)


# ==========================================
# HTML -> 일반 텍스트 변환
# ==========================================


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip_depth += 1
        elif tag in ("br", "p", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def clean_description(value):
    if not value:
        return ""

    parser = TextExtractor()
    parser.feed(str(value))
    parser.close()

    text = unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


# ==========================================
# Odoo JSON-2 API
# ==========================================


def odoo_search_read(model, fields, domain=None, limit=50, context=None):
    if not ODOO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Odoo API key is not configured",
        )

    headers = {
        "Authorization": f"Bearer {ODOO_API_KEY}",
        "X-Odoo-Database": ODOO_DB,
        "Content-Type": "application/json",
    }

    payload = {
        "domain": domain if domain is not None else [],
        "fields": fields,
        "limit": limit,
    }
    if context is not None:
        payload["context"] = context

    try:
        response = requests.post(
            f"{ODOO_URL}/json/2/{model}/search_read",
            headers=headers,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Odoo request timed out",
        )

    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo API error: HTTP {response.status_code}",
        )

    except requests.exceptions.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Cannot connect to Odoo",
        )


# ==========================================
# Helpdesk 데이터 변환
# ==========================================


def relation_name(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]
    return None


def transform_ticket(task):
    ticket_id = task["id"]

    priority_map = {
        "0": "보통",
        "1": "높음",
    }

    priority = str(task.get("priority", "0"))

    return {
        "id": ticket_id,
        # 임시 화면 표시용 번호
        "reference": f"HD-{ticket_id:05d}",
        "title": task.get("name") or "",
        "description": clean_description(task.get("description")),
        "status": relation_name(task.get("stage_id")) or "미지정",
        "stage_id": (task["stage_id"][0] if task.get("stage_id") else None),
        "priority": priority_map.get(priority, "미분류"),
        "priority_code": priority,
        "assignee_ids": task.get("user_ids") or [],
        "tag_ids": task.get("tag_ids") or [],
        "project": relation_name(task.get("project_id")),
        "created_at": task.get("create_date"),
    }


# ==========================================
# FastAPI Routes
# ==========================================


@app.get("/")
def root():
    return {
        "application": "IT Helpdesk v2",
        "status": "running",
        "version": "0.2.0",
    }


@app.get("/api/tickets")
def get_tickets():
    tasks = odoo_search_read(
        model="project.task",
        domain=[["project_id", "=", ODOO_PROJECT_ID]],
        fields=[
            "id",
            "name",
            "description",
            "stage_id",
            "user_ids",
            "tag_ids",
            "priority",
            "project_id",
            "create_date",
        ],
    )

    tickets = [transform_ticket(task) for task in tasks]

    return {
        "success": True,
        "count": len(tickets),
        "tickets": tickets,
    }


# ==========================================
# Helpdesk 문의 상세 조회
# ==========================================


@app.get("/api/tickets/{ticket_id}")
def get_ticket_detail(ticket_id: int):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    tasks = odoo_search_read(
        model="project.task",
        domain=[
            ["id", "=", ticket_id],
            ["project_id", "=", ODOO_PROJECT_ID],
        ],
        fields=[
            "id",
            "name",
            "description",
            "stage_id",
            "user_ids",
            "tag_ids",
            "priority",
            "project_id",
            "create_date",
            "write_date",
        ],
        limit=1,
    )

    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="문의를 찾을 수 없습니다.",
        )

    ticket = transform_ticket(tasks[0])

    ticket["updated_at"] = tasks[0].get("write_date")

    return {
        "success": True,
        "ticket": ticket,
    }


# ==========================================
# OCA Helpdesk - Data Mapping
# ==========================================

OCA_TICKET_FIELDS = [
    "id",
    "number",
    "name",
    "description",
    "stage_id",
    "priority",
    "user_id",
    "category_id",
    "partner_id",
    "team_id",
    "closed",
    "active",
    "create_date",
    "write_date",
]

OCA_PRIORITY_LABELS = {
    "0": "낮음",
    "1": "보통",
    "2": "높음",
    "3": "긴급",
}
OCA_PRIORITY_PATTERN = r"^[0-3]$"


def oca_relation(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return {
            "id": value[0],
            "name": value[1],
        }
    return None


def transform_oca_ticket(ticket):
    priority_code = str(ticket.get("priority") or "1")

    return {
        "id": ticket["id"],
        "reference": ticket.get("number") or "",
        "title": ticket.get("name") or "",
        "description": clean_description(ticket.get("description")),
        "status": oca_relation(ticket.get("stage_id")),
        "priority": OCA_PRIORITY_LABELS.get(priority_code, "미분류"),
        "priority_code": priority_code,
        "assignee": oca_relation(ticket.get("user_id")),
        "category": oca_relation(ticket.get("category_id")),
        "requester": oca_relation(ticket.get("partner_id")),
        "team": oca_relation(ticket.get("team_id")),
        "closed": bool(ticket.get("closed")),
        "active": bool(ticket.get("active")),
        "created_at": ticket.get("create_date"),
        "updated_at": ticket.get("write_date"),
    }


# ==========================================
# OCA Helpdesk - API Routes
# ==========================================


@app.get("/api/oca/tickets")
def get_oca_tickets():
    records = odoo_search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["active", "=", True]],
        limit=50,
    )

    tickets = [transform_oca_ticket(record) for record in records]

    return {
        "success": True,
        "count": len(tickets),
        "tickets": tickets,
    }


@app.get("/api/oca/tickets/archived")
def get_archived_oca_tickets():
    records = odoo_search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["active", "=", False]],
        limit=50,
        context={"active_test": False},
    )

    tickets = [transform_oca_ticket(record) for record in records]

    return {
        "success": True,
        "count": len(tickets),
        "tickets": tickets,
    }


@app.get("/api/oca/tickets/{ticket_id}")
def get_oca_ticket_detail(ticket_id: int):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    records = odoo_search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="문의를 찾을 수 없습니다.",
        )

    return {
        "success": True,
        "ticket": transform_oca_ticket(records[0]),
    }


@app.get("/api/oca/stages")
def get_oca_stages():
    stages = odoo_search_read(
        model="helpdesk.ticket.stage",
        fields=[
            "id",
            "name",
            "sequence",
            "closed",
        ],
        limit=100,
    )

    return {
        "success": True,
        "count": len(stages),
        "stages": stages,
    }


@app.get("/api/oca/categories")
def get_oca_categories():
    categories = odoo_search_read(
        model="helpdesk.ticket.category",
        fields=[
            "id",
            "name",
            "complete_name",
        ],
        limit=100,
    )

    return {
        "success": True,
        "count": len(categories),
        "categories": categories,
    }


# ==========================================
# OCA Helpdesk - Create Ticket
# ==========================================

from html import escape
from pydantic import BaseModel, Field


class OcaTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    priority: str = Field(default="1", pattern=OCA_PRIORITY_PATTERN)


def odoo_create_ticket(values):
    if not ODOO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Odoo API key is not configured",
        )

    try:
        response = requests.post(
            f"{ODOO_URL}/json/2/helpdesk.ticket/create",
            headers={
                "Authorization": f"Bearer {ODOO_API_KEY}",
                "X-Odoo-Database": ODOO_DB,
                "Content-Type": "application/json",
            },
            json={"vals_list": [values]},
            timeout=15,
        )

        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Odoo request timed out",
        )

    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo create failed: HTTP {response.status_code}",
        )

    except requests.exceptions.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Cannot connect to Odoo",
        )


@app.post("/api/oca/tickets", status_code=201)
def create_oca_ticket(data: OcaTicketCreate):
    title = data.title.strip()
    description = data.description.strip()

    if not title or not description:
        raise HTTPException(
            status_code=422,
            detail="제목과 문의 내용은 필수입니다.",
        )

    # HTML 특수문자를 안전하게 변환
    safe_description = escape(description).replace("\n", "<br>")

    values = {
        "name": title,
        "description": safe_description,
        "priority": data.priority,
    }

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
    }


# ==========================================
# OCA Helpdesk - Update Ticket
# ==========================================

from pydantic import model_validator


class OcaTicketUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: str | None = Field(default=None, pattern=OCA_PRIORITY_PATTERN)
    assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해야 합니다.")

        if self.title is not None and not self.title.strip():
            raise ValueError("제목은 비워둘 수 없습니다.")

        if self.description is not None and not self.description.strip():
            raise ValueError("내용은 비워둘 수 없습니다.")

        return self


def odoo_write(model, record_id, values):
    if not ODOO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Odoo API key is not configured",
        )

    try:
        response = requests.post(
            f"{ODOO_URL}/json/2/{model}/write",
            headers={
                "Authorization": f"Bearer {ODOO_API_KEY}",
                "X-Odoo-Database": ODOO_DB,
                "Content-Type": "application/json",
            },
            json={
                "ids": [record_id],
                "vals": values,
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()

        if result is not True:
            raise HTTPException(
                status_code=502,
                detail="Odoo update returned an unexpected result",
            )

        return result

    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="Odoo request timed out",
        )

    except requests.exceptions.HTTPError:
        raise HTTPException(
            status_code=502,
            detail=f"Odoo update failed: HTTP {response.status_code}",
        )

    except requests.exceptions.RequestException:
        raise HTTPException(
            status_code=502,
            detail="Cannot connect to Odoo",
        )


@app.patch("/api/oca/tickets/{ticket_id}")
def update_oca_ticket(
    ticket_id: int,
    data: OcaTicketUpdate,
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 번호입니다.",
        )

    existing = odoo_search_read(
        model="helpdesk.ticket",
        fields=["id"],
        domain=[["id", "=", ticket_id]],
        limit=1,
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="문의를 찾을 수 없습니다.",
        )

    values = {}

    if data.title is not None:
        values["name"] = data.title.strip()

    if data.description is not None:
        values["description"] = escape(data.description.strip()).replace("\n", "<br>")

    if data.priority is not None:
        values["priority"] = data.priority

    if "assignee_id" in data.model_fields_set:
        if data.assignee_id is not None:
            users = odoo_search_read(
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

        # null이면 담당자 배정 해제
        values["user_id"] = data.assignee_id or False

    odoo_write(
        model="helpdesk.ticket",
        record_id=ticket_id,
        values=values,
    )

    updated = odoo_search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=[["id", "=", ticket_id]],
        limit=1,
    )

    return {
        "success": True,
        "message": "문의가 수정되었습니다.",
        "ticket": transform_oca_ticket(updated[0]),
    }


# ==========================================
# OCA Helpdesk - Archive / Restore Ticket
# ==========================================


def get_oca_ticket_including_archived(ticket_id):
    records = odoo_search_read(
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
        raise HTTPException(
            status_code=404,
            detail="문의를 찾을 수 없습니다.",
        )

    if bool(existing.get("active")) == active:
        action = "복원" if active else "보관"
        raise HTTPException(
            status_code=409,
            detail=f"이미 {action}된 문의입니다.",
        )

    odoo_write(
        model="helpdesk.ticket",
        record_id=ticket_id,
        values={"active": active},
    )

    updated = get_oca_ticket_including_archived(ticket_id)
    if updated is None or bool(updated.get("active")) != active:
        raise HTTPException(
            status_code=502,
            detail="Odoo에서 문의 상태 변경을 확인할 수 없습니다.",
        )

    return updated


@app.patch("/api/oca/tickets/{ticket_id}/archive")
def archive_oca_ticket(ticket_id: int):
    ticket = set_oca_ticket_active(ticket_id, False)
    return {
        "success": True,
        "message": "문의가 보관되었습니다.",
        "ticket": transform_oca_ticket(ticket),
    }


@app.patch("/api/oca/tickets/{ticket_id}/restore")
def restore_oca_ticket(ticket_id: int):
    ticket = set_oca_ticket_active(ticket_id, True)
    return {
        "success": True,
        "message": "문의가 복원되었습니다.",
        "ticket": transform_oca_ticket(ticket),
    }


# ==========================================
# OCA Helpdesk - Assignees
# ==========================================


@app.get("/api/oca/assignees")
def get_oca_assignees():
    users = odoo_search_read(
        model="res.users",
        fields=["id", "name"],
        domain=[
            ["share", "=", False],
            ["active", "=", True],
        ],
        limit=100,
    )

    return {
        "success": True,
        "count": len(users),
        "assignees": users,
    }
