import os
import re
from html import escape, unescape
from html.parser import HTMLParser

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

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


def odoo_create(model, values):
    if not ODOO_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Odoo API key is not configured",
        )

    try:
        response = requests.post(
            f"{ODOO_URL}/json/2/{model}/create",
            headers={
                "Authorization": f"Bearer {ODOO_API_KEY}",
                "X-Odoo-Database": ODOO_DB,
                "Content-Type": "application/json",
            },
            json={"vals_list": [values]},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()

        if not isinstance(result, list) or len(result) != 1:
            raise HTTPException(
                status_code=502,
                detail="Odoo create returned an unexpected result",
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
            detail=f"Odoo create failed: HTTP {response.status_code}",
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
CATEGORY_FIELDS = [
    "id",
    "name",
    "complete_name",
    "sequence",
    "active",
    "parent_id",
    "show_in_portal",
]
CATEGORY_ASSIGNEE_PARAM_PREFIX = "it_helpdesk_v2.category_default_assignee."
HELPDESK_GROUP_XML_IDS = [
    "group_helpdesk_user_own",
    "group_helpdesk_user_team",
    "group_helpdesk_user",
    "group_helpdesk_manager",
]


def oca_relation(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return {
            "id": value[0],
            "name": value[1],
        }
    return None


def get_helpdesk_group_ids():
    records = odoo_search_read(
        model="ir.model.data",
        fields=["res_id"],
        domain=[
            ["module", "=", "helpdesk_mgmt"],
            ["name", "in", HELPDESK_GROUP_XML_IDS],
            ["model", "=", "res.groups"],
        ],
        limit=len(HELPDESK_GROUP_XML_IDS),
    )
    return [record["res_id"] for record in records]


def get_valid_helpdesk_assignees(user_ids=None):
    group_ids = get_helpdesk_group_ids()
    if not group_ids:
        return []

    domain = [
        ["share", "=", False],
        ["active", "=", True],
        ["group_ids", "in", group_ids],
    ]
    if user_ids is not None:
        if not user_ids:
            return []
        domain.append(["id", "in", list(user_ids)])

    return odoo_search_read(
        model="res.users",
        fields=["id", "name"],
        domain=domain,
        limit=100,
    )


def get_category_default_assignees(category_ids):
    if not category_ids:
        return {}

    parameters = odoo_search_read(
        model="ir.config_parameter",
        fields=["key", "value"],
        domain=[["key", "=like", f"{CATEGORY_ASSIGNEE_PARAM_PREFIX}%"]],
        limit=1000,
    )

    configured = {}
    for parameter in parameters:
        try:
            category_id = int(parameter["key"].removeprefix(CATEGORY_ASSIGNEE_PARAM_PREFIX))
            user_id = int(parameter.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if category_id in category_ids and user_id > 0:
            configured[category_id] = user_id

    if not configured:
        return {}

    valid_users = {
        user["id"]: user
        for user in get_valid_helpdesk_assignees(set(configured.values()))
    }
    return {
        category_id: valid_users[user_id]
        for category_id, user_id in configured.items()
        if user_id in valid_users
    }


def set_category_default_assignee(category_id, user_id):
    key = f"{CATEGORY_ASSIGNEE_PARAM_PREFIX}{category_id}"
    parameters = odoo_search_read(
        model="ir.config_parameter",
        fields=["id"],
        domain=[["key", "=", key]],
        limit=1,
    )

    value = str(user_id) if user_id is not None else ""
    if parameters:
        odoo_write("ir.config_parameter", parameters[0]["id"], {"value": value})
    else:
        odoo_create("ir.config_parameter", {"key": key, "value": value})


def validate_default_assignee(user_id):
    users = get_valid_helpdesk_assignees([user_id])
    if not users:
        raise HTTPException(
            status_code=422,
            detail="활성 상태이며 Helpdesk 권한이 있는 담당자만 지정할 수 있습니다.",
        )
    return users[0]


def transform_oca_ticket(ticket, category_default_assignees=None):
    priority_code = str(ticket.get("priority") or "1")
    category = oca_relation(ticket.get("category_id"))
    assignee = oca_relation(ticket.get("user_id"))
    category_default_assignees = category_default_assignees or {}
    default_assignee = category_default_assignees.get(category["id"]) if category else None

    return {
        "id": ticket["id"],
        "reference": ticket.get("number") or "",
        "title": ticket.get("name") or "",
        "description": clean_description(ticket.get("description")),
        "status": oca_relation(ticket.get("stage_id")),
        "priority": OCA_PRIORITY_LABELS.get(priority_code, "미분류"),
        "priority_code": priority_code,
        "assignee": assignee,
        "category": category,
        "auto_assigned": bool(
            default_assignee
            and assignee
            and default_assignee["id"] == assignee["id"]
        ),
        "requester": oca_relation(ticket.get("partner_id")),
        "team": oca_relation(ticket.get("team_id")),
        "closed": bool(ticket.get("closed")),
        "active": bool(ticket.get("active")),
        "created_at": ticket.get("create_date"),
        "updated_at": ticket.get("write_date"),
    }


def transform_oca_tickets(records):
    category_ids = {
        record["category_id"][0]
        for record in records
        if isinstance(record.get("category_id"), (list, tuple))
        and record["category_id"]
    }
    default_assignees = get_category_default_assignees(category_ids)
    return [
        transform_oca_ticket(record, default_assignees)
        for record in records
    ]


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

    tickets = transform_oca_tickets(records)

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

    tickets = transform_oca_tickets(records)

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
        "ticket": transform_oca_tickets(records)[0],
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


class OcaCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = Field(default=None, gt=0)
    show_in_portal: bool = True
    default_assignee_id: int | None = Field(default=None, gt=0)


class OcaCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    parent_id: int | None = Field(default=None, gt=0)
    show_in_portal: bool | None = None
    default_assignee_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해야 합니다.")
        if self.name is not None and not self.name.strip():
            raise ValueError("문의 유형명은 비워둘 수 없습니다.")
        return self


def get_category_record(category_id, active_only=False):
    if category_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="올바르지 않은 문의 유형 번호입니다.",
        )

    domain = [["id", "=", category_id]]
    if active_only:
        domain.append(["active", "=", True])

    records = odoo_search_read(
        model="helpdesk.ticket.category",
        fields=CATEGORY_FIELDS,
        domain=domain,
        limit=1,
        context={"active_test": False},
    )
    if not records:
        raise HTTPException(
            status_code=404,
            detail="문의 유형을 찾을 수 없습니다.",
        )
    return records[0]


def category_name_exists(name, parent_id, exclude_id=None):
    domain = [
        ["name", "=", name],
        ["parent_id", "=", parent_id or False],
    ]
    if exclude_id is not None:
        domain.append(["id", "!=", exclude_id])
    return bool(
        odoo_search_read(
            model="helpdesk.ticket.category",
            fields=["id"],
            domain=domain,
            limit=1,
            context={"active_test": False},
        )
    )


def is_etc_category(category):
    normalized = re.sub(r"\s+", "", category.get("name") or "").upper()
    return normalized in {"ETC", "기타", "기타(ETC)"}


def transform_categories(records):
    default_assignees = get_category_default_assignees(
        {record["id"] for record in records}
    )
    categories = [
        {
            "id": record["id"],
            "name": record.get("name") or "",
            "complete_name": record.get("complete_name") or "",
            "sequence": record.get("sequence") or 0,
            "active": bool(record.get("active")),
            "parent": oca_relation(record.get("parent_id")),
            "show_in_portal": bool(record.get("show_in_portal")),
            "default_assignee": default_assignees.get(record["id"]),
        }
        for record in records
    ]
    return sorted(
        categories,
        key=lambda category: (
            is_etc_category(category),
            category["sequence"],
            category["id"],
        ),
    )


def read_categories(include_inactive=False):
    domain = [] if include_inactive else [["active", "=", True]]
    context = {"active_test": False} if include_inactive else None
    records = odoo_search_read(
        model="helpdesk.ticket.category",
        fields=CATEGORY_FIELDS,
        domain=domain,
        limit=100,
        context=context,
    )
    return transform_categories(records)


@app.get("/api/oca/categories")
def get_oca_categories():
    categories = read_categories()
    return {
        "success": True,
        "count": len(categories),
        "categories": categories,
    }


@app.get("/api/oca/categories/all")
def get_all_oca_categories():
    categories = read_categories(include_inactive=True)
    return {
        "success": True,
        "count": len(categories),
        "categories": categories,
    }


@app.post("/api/oca/categories", status_code=201)
def create_oca_category(data: OcaCategoryCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="문의 유형명은 필수입니다.")

    if data.parent_id is not None:
        get_category_record(data.parent_id, active_only=True)
    if category_name_exists(name, data.parent_id):
        raise HTTPException(status_code=409, detail="동일한 문의 유형이 이미 존재합니다.")
    if data.default_assignee_id is not None:
        validate_default_assignee(data.default_assignee_id)

    category_id = odoo_create(
        "helpdesk.ticket.category",
        {
            "name": name,
            "parent_id": data.parent_id or False,
            "show_in_portal": data.show_in_portal,
        },
    )[0]
    if data.default_assignee_id is not None:
        set_category_default_assignee(category_id, data.default_assignee_id)

    category = transform_categories([get_category_record(category_id)])[0]
    return {
        "success": True,
        "message": "문의 유형이 등록되었습니다.",
        "category": category,
    }


@app.get("/api/oca/categories/{category_id}")
def get_oca_category_detail(category_id: int):
    category = transform_categories([get_category_record(category_id)])[0]
    return {
        "success": True,
        "category": category,
    }


@app.patch("/api/oca/categories/{category_id}")
def update_oca_category(category_id: int, data: OcaCategoryUpdate):
    existing = get_category_record(category_id)
    values = {}

    if data.name is not None:
        name = data.name.strip()
        parent_id = (
            data.parent_id
            if "parent_id" in data.model_fields_set
            else (existing["parent_id"][0] if existing.get("parent_id") else None)
        )
        if category_name_exists(name, parent_id, exclude_id=category_id):
            raise HTTPException(status_code=409, detail="동일한 문의 유형이 이미 존재합니다.")
        values["name"] = name

    if "parent_id" in data.model_fields_set:
        if data.parent_id == category_id:
            raise HTTPException(status_code=422, detail="자기 자신을 상위 유형으로 지정할 수 없습니다.")
        if data.parent_id is not None:
            get_category_record(data.parent_id, active_only=True)
        target_name = data.name.strip() if data.name is not None else existing["name"]
        if category_name_exists(target_name, data.parent_id, exclude_id=category_id):
            raise HTTPException(status_code=409, detail="동일한 문의 유형이 이미 존재합니다.")
        values["parent_id"] = data.parent_id or False

    if data.show_in_portal is not None:
        values["show_in_portal"] = data.show_in_portal

    if "default_assignee_id" in data.model_fields_set:
        if data.default_assignee_id is not None:
            validate_default_assignee(data.default_assignee_id)
        set_category_default_assignee(category_id, data.default_assignee_id)

    if values:
        odoo_write("helpdesk.ticket.category", category_id, values)

    category = transform_categories([get_category_record(category_id)])[0]
    return {
        "success": True,
        "message": "문의 유형이 수정되었습니다.",
        "category": category,
    }


def set_category_active(category_id, active):
    category = get_category_record(category_id)
    if bool(category.get("active")) == active:
        action = "복원" if active else "비활성화"
        raise HTTPException(status_code=409, detail=f"이미 {action}된 문의 유형입니다.")

    odoo_write("helpdesk.ticket.category", category_id, {"active": active})
    updated = get_category_record(category_id)
    if bool(updated.get("active")) != active:
        raise HTTPException(status_code=502, detail="문의 유형 상태 변경을 확인할 수 없습니다.")
    return transform_categories([updated])[0]


@app.patch("/api/oca/categories/{category_id}/archive")
def archive_oca_category(category_id: int):
    return {
        "success": True,
        "message": "문의 유형이 비활성화되었습니다.",
        "category": set_category_active(category_id, False),
    }


@app.patch("/api/oca/categories/{category_id}/restore")
def restore_oca_category(category_id: int):
    return {
        "success": True,
        "message": "문의 유형이 활성화되었습니다.",
        "category": set_category_active(category_id, True),
    }


# ==========================================
# OCA Helpdesk - Create Ticket
# ==========================================


class OcaTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    priority: str = Field(default="1", pattern=OCA_PRIORITY_PATTERN)
    category_id: int | None = Field(default=None, gt=0)


def odoo_create_ticket(values):
    return odoo_create("helpdesk.ticket", values)


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
    auto_assignee = None

    if data.category_id is not None:
        category = get_category_record(data.category_id)
        if not category.get("active"):
            raise HTTPException(
                status_code=422,
                detail="비활성 문의 유형은 선택할 수 없습니다.",
            )
        values["category_id"] = data.category_id
        auto_assignee = get_category_default_assignees({data.category_id}).get(
            data.category_id
        )
        if auto_assignee:
            values["user_id"] = auto_assignee["id"]
        else:
            # OCA의 회사 단위 자동배정 기본값보다 유형별 정책을 우선한다.
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


# ==========================================
# OCA Helpdesk - Update Ticket
# ==========================================


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
        "ticket": transform_oca_tickets(updated)[0],
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
        "ticket": transform_oca_tickets([ticket])[0],
    }


@app.patch("/api/oca/tickets/{ticket_id}/restore")
def restore_oca_ticket(ticket_id: int):
    ticket = set_oca_ticket_active(ticket_id, True)
    return {
        "success": True,
        "message": "문의가 복원되었습니다.",
        "ticket": transform_oca_tickets([ticket])[0],
    }


# ==========================================
# OCA Helpdesk - Assignees
# ==========================================


@app.get("/api/oca/assignees")
def get_oca_assignees():
    users = get_valid_helpdesk_assignees()

    return {
        "success": True,
        "count": len(users),
        "assignees": users,
    }
