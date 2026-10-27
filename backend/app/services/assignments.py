from fastapi import HTTPException

from app.constants import CATEGORY_ASSIGNEE_PARAM_PREFIX, HELPDESK_GROUP_XML_IDS
from app.services import odoo


def get_helpdesk_group_ids():
    records = odoo.search_read(
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

    return odoo.search_read(
        model="res.users",
        fields=["id", "name"],
        domain=domain,
        limit=100,
    )


def get_category_default_assignees(category_ids):
    if not category_ids:
        return {}

    parameters = odoo.search_read(
        model="ir.config_parameter",
        fields=["key", "value"],
        domain=[["key", "=like", f"{CATEGORY_ASSIGNEE_PARAM_PREFIX}%"]],
        limit=1000,
    )

    configured = {}
    for parameter in parameters:
        try:
            category_id = int(
                parameter["key"].removeprefix(CATEGORY_ASSIGNEE_PARAM_PREFIX)
            )
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
    parameters = odoo.search_read(
        model="ir.config_parameter",
        fields=["id"],
        domain=[["key", "=", key]],
        limit=1,
    )

    value = str(user_id) if user_id is not None else ""
    if parameters:
        odoo.write("ir.config_parameter", parameters[0]["id"], {"value": value})
    else:
        odoo.create("ir.config_parameter", {"key": key, "value": value})


def validate_default_assignee(user_id):
    users = get_valid_helpdesk_assignees([user_id])
    if not users:
        raise HTTPException(
            status_code=422,
            detail="활성 상태이며 Helpdesk 권한이 있는 담당자만 지정할 수 있습니다.",
        )
    return users[0]
