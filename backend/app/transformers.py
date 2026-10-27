import re
from html import unescape
from html.parser import HTMLParser

from app.constants import OCA_PRIORITY_LABELS
from app.services.assignments import get_category_default_assignees


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


def relation_name(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]
    return None


def oca_relation(value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return {"id": value[0], "name": value[1]}
    return None


def transform_project_ticket(task):
    ticket_id = task["id"]
    priority_map = {"0": "보통", "1": "높음"}
    priority = str(task.get("priority", "0"))
    return {
        "id": ticket_id,
        "reference": f"HD-{ticket_id:05d}",
        "title": task.get("name") or "",
        "description": clean_description(task.get("description")),
        "status": relation_name(task.get("stage_id")) or "미지정",
        "stage_id": task["stage_id"][0] if task.get("stage_id") else None,
        "priority": priority_map.get(priority, "미분류"),
        "priority_code": priority,
        "assignee_ids": task.get("user_ids") or [],
        "tag_ids": task.get("tag_ids") or [],
        "project": relation_name(task.get("project_id")),
        "created_at": task.get("create_date"),
    }


def transform_oca_ticket(ticket):
    priority_code = str(ticket.get("priority") or "1")
    category = oca_relation(ticket.get("category_id"))
    assignee = oca_relation(ticket.get("user_id"))
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
        # Odoo does not preserve enough provenance to distinguish an automatic
        # assignment from a manual assignment after the ticket is created.
        "auto_assigned": None,
        "requester": oca_relation(ticket.get("partner_id")),
        "team": oca_relation(ticket.get("team_id")),
        "closed": bool(ticket.get("closed")),
        "active": bool(ticket.get("active")),
        "created_at": ticket.get("create_date"),
        "updated_at": ticket.get("write_date"),
    }


def transform_oca_tickets(records):
    return [transform_oca_ticket(record) for record in records]


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
