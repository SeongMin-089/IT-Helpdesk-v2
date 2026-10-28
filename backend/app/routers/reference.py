from fastapi import APIRouter

from app.constants import OCA_PRIORITY_LABELS, OCA_TICKET_FIELDS
from app.services import odoo
from app.transformers import transform_oca_tickets


router = APIRouter(prefix="/api/oca")


@router.get("/stages")
def get_oca_stages():
    stages = odoo.search_read(
        model="helpdesk.ticket.stage",
        fields=["id", "name", "sequence", "closed"],
        limit=100,
    )
    return {"success": True, "count": len(stages), "stages": stages}


@router.get("/dashboard")
def get_oca_dashboard():
    active_domain = [["active", "=", True]]
    summary = {
        "total": odoo.search_count("helpdesk.ticket", domain=active_domain),
        "open": odoo.search_count(
            "helpdesk.ticket",
            domain=active_domain + [["closed", "=", False]],
        ),
        "closed": odoo.search_count(
            "helpdesk.ticket",
            domain=active_domain + [["closed", "=", True]],
        ),
        "unassigned": odoo.search_count(
            "helpdesk.ticket",
            domain=active_domain
            + [["closed", "=", False], ["user_id", "=", False]],
        ),
    }

    stages = odoo.search_read(
        model="helpdesk.ticket.stage",
        fields=["id", "name", "sequence", "closed"],
        domain=[["active", "=", True]],
        limit=100,
    )
    stage_groups = odoo.formatted_read_group(
        "helpdesk.ticket",
        groupby=["stage_id"],
        aggregates=["__count"],
        domain=active_domain,
    )
    stage_counts = {
        group["stage_id"][0]: group["__count"]
        for group in stage_groups
        if group.get("stage_id")
    }
    stages.sort(key=lambda stage: (stage.get("sequence") or 0, stage["id"]))
    by_stage = [
        {
            "id": stage["id"],
            "name": stage.get("name") or "",
            "closed": bool(stage.get("closed")),
            "count": stage_counts.get(stage["id"], 0),
        }
        for stage in stages
    ]

    priority_groups = odoo.formatted_read_group(
        "helpdesk.ticket",
        groupby=["priority"],
        aggregates=["__count"],
        domain=active_domain,
    )
    priority_counts = {
        str(group["priority"]): group["__count"]
        for group in priority_groups
        if group.get("priority") is not False
    }
    by_priority = [
        {
            "priority": priority,
            "label": OCA_PRIORITY_LABELS[priority],
            "count": priority_counts.get(priority, 0),
        }
        for priority in ("0", "1", "2", "3")
    ]

    recent_records = odoo.search_read(
        model="helpdesk.ticket",
        fields=OCA_TICKET_FIELDS,
        domain=active_domain,
        limit=5,
        order="create_date desc, id desc",
    )
    return {
        "success": True,
        "summary": summary,
        "by_stage": by_stage,
        "by_priority": by_priority,
        "recent_tickets": transform_oca_tickets(recent_records),
    }
