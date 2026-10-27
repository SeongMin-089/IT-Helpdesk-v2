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


def odoo_search_read(model, fields, domain=None, limit=50):
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
