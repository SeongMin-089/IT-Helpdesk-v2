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
