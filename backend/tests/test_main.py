import base64
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from app import config  # noqa: E402
from app.routers import archive, categories, faqs, legacy, tickets  # noqa: E402
from app.schemas import (  # noqa: E402
    OcaCategoryCreate,
    OcaCategoryUpdate,
    OcaFaqCreate,
    OcaFaqUpdate,
    OcaTicketCommentCreate,
    OcaTicketCreate,
    OcaTicketReprocess,
    OcaTicketResolve,
    OcaTicketStageUpdate,
    OcaTicketUpdate,
)
from app.services import odoo  # noqa: E402


class MemoryOdoo:
    def __init__(self):
        self.tickets = {
            1: {
                "id": 1,
                "number": "T-001",
                "name": "Printer failure",
                "description": "Keep <b>all</b> fields",
                "stage_id": [2, "Assigned"],
                "priority": "3",
                "user_id": [7, "Agent Kim"],
                "category_id": [4, "Hardware"],
                "partner_id": [9, "Requester Lee"],
                "team_id": [3, "IT"],
                "company_id": [1, "Main Company"],
                "closed": False,
                "active": True,
                "create_date": "2026-10-27 01:00:00",
                "write_date": "2026-10-27 01:00:00",
            }
        }
        self.stages = {
            1: {
                "id": 1,
                "name": "New",
                "sequence": 1,
                "active": True,
                "team_ids": [],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            2: {
                "id": 2,
                "name": "Assigned",
                "sequence": 2,
                "active": True,
                "team_ids": [3],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            3: {
                "id": 3,
                "name": "In progress",
                "sequence": 3,
                "active": True,
                "team_ids": [3],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            4: {
                "id": 4,
                "name": "Resolved",
                "sequence": 4,
                "active": True,
                "team_ids": [3],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            5: {
                "id": 5,
                "name": "Done",
                "sequence": 5,
                "active": True,
                "team_ids": [3],
                "company_id": [1, "Main Company"],
                "closed": True,
            },
            6: {
                "id": 6,
                "name": "Inactive",
                "sequence": 6,
                "active": False,
                "team_ids": [],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            7: {
                "id": 7,
                "name": "Other team",
                "sequence": 7,
                "active": True,
                "team_ids": [99],
                "company_id": [1, "Main Company"],
                "closed": False,
            },
            8: {
                "id": 8,
                "name": "Other company",
                "sequence": 8,
                "active": True,
                "team_ids": [],
                "company_id": [2, "Other Company"],
                "closed": False,
            },
        }
        self.categories = {
            10: {
                "id": 10,
                "name": "General",
                "complete_name": "General",
                "sequence": 10,
                "active": True,
                "parent_id": False,
                "show_in_portal": True,
            },
            11: {
                "id": 11,
                "name": "기타(ETC)",
                "complete_name": "기타(ETC)",
                "sequence": 1,
                "active": True,
                "parent_id": False,
                "show_in_portal": True,
            },
        }
        self.document_pages = {
            100: {
                "id": 100,
                "name": "Public FAQ",
                "content": False,
                "tag_ids": [],
                "active": True,
                "parent_id": False,
                "type": "category",
                "create_date": "2026-10-27 01:00:00",
                "write_date": "2026-10-27 01:00:00",
            },
            101: {
                "id": 101,
                "name": "Draft FAQ",
                "content": False,
                "tag_ids": [],
                "active": True,
                "parent_id": False,
                "type": "category",
                "create_date": "2026-10-27 01:00:00",
                "write_date": "2026-10-27 01:00:00",
            },
            110: {
                "id": 110,
                "name": "Network reset",
                "content": "<p>Restart the router safely.</p>",
                "tag_ids": [201],
                "active": True,
                "parent_id": [100, "Public FAQ"],
                "type": "content",
                "create_date": "2026-10-27 02:00:00",
                "write_date": "2026-10-27 02:00:00",
            },
            111: {
                "id": 111,
                "name": "Private draft",
                "content": "<p>Draft content</p>",
                "tag_ids": [202],
                "active": True,
                "parent_id": [101, "Draft FAQ"],
                "type": "content",
                "create_date": "2026-10-27 02:00:00",
                "write_date": "2026-10-27 02:00:00",
            },
            112: {
                "id": 112,
                "name": "Archived public FAQ",
                "content": "<p>Old content</p>",
                "tag_ids": [],
                "active": False,
                "parent_id": [100, "Public FAQ"],
                "type": "content",
                "create_date": "2026-10-27 02:00:00",
                "write_date": "2026-10-27 02:00:00",
            },
        }
        self.document_tags = {
            201: {"id": 201, "name": "network", "active": True},
            202: {"id": 202, "name": "hardware", "active": True},
        }
        self.document_histories = []
        self.parameters = {}
        self.users = {
            7: {
                "id": 7,
                "name": "Agent Kim",
                "active": True,
                "share": False,
                "group_ids": [31],
            },
            8: {
                "id": 8,
                "name": "No Helpdesk Access",
                "active": True,
                "share": False,
                "group_ids": [1],
            },
            9: {
                "id": 9,
                "name": "Inactive Agent",
                "active": False,
                "share": False,
                "group_ids": [31],
            },
        }
        self.created_ticket_values = None
        self.messages = []
        self.mail_messages = {}
        self.model_fields = {
            1001: {
                "id": 1001,
                "name": "stage_id",
                "field_description": "Stage",
                "ttype": "many2one",
                "model": "helpdesk.ticket",
            },
            1002: {
                "id": 1002,
                "name": "user_id",
                "field_description": "Assigned user",
                "ttype": "many2one",
                "model": "helpdesk.ticket",
            },
        }
        self.tracking_values = {}
        self.deny_tracking_access = False
        self.attachments = {
            50: {
                "id": 50,
                "name": "error.txt",
                "mimetype": "text/plain",
                "file_size": 5,
                "create_date": "2026-10-27 03:00:00",
                "create_uid": [7, "Agent Kim"],
                "res_model": "helpdesk.ticket",
                "res_id": 1,
                "type": "binary",
                "datas": "ZXJyb3I=",
            }
        }
        self.created_attachment_values = None
        self.events = []

    @staticmethod
    def _matches(record, domain):
        for field, operator, value in domain or []:
            current = record.get(field)
            relation_value = (
                current[0]
                if isinstance(current, list)
                and len(current) == 2
                and isinstance(current[1], str)
                else current
            )
            if operator == "=" and relation_value != value:
                return False
            if operator == "!=" and relation_value == value:
                return False
            if operator == "in":
                if relation_value is not current:
                    if relation_value not in value:
                        return False
                elif isinstance(current, list):
                    if not any(item in value for item in current):
                        return False
                elif current not in value:
                    return False
            if operator == "ilike":
                if str(value).casefold() not in str(current or "").casefold():
                    return False
            if operator == "=like":
                prefix = value[:-1] if value.endswith("%") else value
                if not str(current or "").startswith(prefix):
                    return False
        return True

    @staticmethod
    def _select_fields(records, fields, limit):
        return [
            {field: copy.deepcopy(record.get(field)) for field in fields}
            for record in records[:limit]
        ]

    def search_read(
        self,
        model,
        fields,
        domain=None,
        limit=50,
        context=None,
        order=None,
    ):
        if model == "res.users":
            records = list(self.users.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "ir.model.data":
            records = [
                {
                    "module": "helpdesk_mgmt",
                    "name": "group_helpdesk_user",
                    "model": "res.groups",
                    "res_id": 31,
                },
                {
                    "module": "mail",
                    "name": "mt_note",
                    "model": "mail.message.subtype",
                    "res_id": 2,
                },
            ]
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "ir.config_parameter":
            records = list(self.parameters.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "helpdesk.ticket.category":
            records = list(self.categories.values())
            if not (context or {}).get("active_test") is False:
                records = [record for record in records if record["active"]]
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "helpdesk.ticket.stage":
            records = list(self.stages.values())
            if not (context or {}).get("active_test") is False:
                records = [record for record in records if record["active"]]
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "mail.message":
            records = list(self.mail_messages.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "mail.tracking.value":
            if self.deny_tracking_access:
                raise HTTPException(
                    status_code=403,
                    detail="Odoo access denied for mail.tracking.value",
                )
            records = list(self.tracking_values.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "ir.model.fields":
            records = list(self.model_fields.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "document.page":
            records = list(self.document_pages.values())
            if not (context or {}).get("active_test") is False:
                records = [record for record in records if record["active"]]
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "document.page.tag":
            records = list(self.document_tags.values())
            if not (context or {}).get("active_test") is False:
                records = [record for record in records if record["active"]]
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "ir.attachment":
            records = list(self.attachments.values())
            records = [record for record in records if self._matches(record, domain)]
            return self._select_fields(records, fields, limit)
        if model == "project.task":
            return []
        if model != "helpdesk.ticket":
            return []

        records = list(self.tickets.values())
        if not (context or {}).get("active_test") is False:
            records = [record for record in records if record["active"]]

        records = [record for record in records if self._matches(record, domain)]
        return self._select_fields(records, fields, limit)

    def create(self, model, values):
        if model == "helpdesk.ticket.category":
            record_id = max(self.categories) + 1
            parent_id = values.get("parent_id") or False
            parent_name = self.categories[parent_id]["complete_name"] if parent_id else ""
            name = values["name"]
            self.categories[record_id] = {
                "id": record_id,
                "name": name,
                "complete_name": f"{parent_name} / {name}" if parent_name else name,
                "sequence": 10,
                "active": True,
                "parent_id": (
                    [parent_id, self.categories[parent_id]["complete_name"]]
                    if parent_id
                    else False
                ),
                "show_in_portal": values.get("show_in_portal", True),
            }
            return [record_id]
        if model == "document.page":
            record_id = max(self.document_pages) + 1
            parent_id = values["parent_id"]
            tag_ids = values.get("tag_ids", [[6, 0, []]])[0][2]
            self.document_pages[record_id] = {
                "id": record_id,
                "name": values["name"],
                "content": values["content"],
                "tag_ids": copy.deepcopy(tag_ids),
                "active": values.get("active", True),
                "parent_id": [parent_id, self.document_pages[parent_id]["name"]],
                "type": values.get("type", "content"),
                "create_date": "2026-10-27 05:00:00",
                "write_date": "2026-10-27 05:00:00",
            }
            self.document_histories.append(
                {"page_id": record_id, "content": values["content"]}
            )
            return [record_id]
        if model == "ir.config_parameter":
            record_id = 100 + len(self.parameters)
            self.parameters[record_id] = {"id": record_id, **copy.deepcopy(values)}
            return [record_id]
        if model == "helpdesk.ticket":
            self.created_ticket_values = copy.deepcopy(values)
            record_id = max(self.tickets) + 1
            category_id = values.get("category_id")
            user_id = values.get("user_id")
            self.tickets[record_id] = {
                "id": record_id,
                "number": f"T-{record_id:03d}",
                "name": values["name"],
                "description": values["description"],
                "stage_id": False,
                "priority": values["priority"],
                "user_id": [user_id, self.users[user_id]["name"]] if user_id else False,
                "category_id": (
                    [category_id, self.categories[category_id]["complete_name"]]
                    if category_id
                    else False
                ),
                "partner_id": False,
                "team_id": False,
                "company_id": [1, "Main Company"],
                "closed": False,
                "active": True,
                "create_date": "2026-10-27 02:00:00",
                "write_date": "2026-10-27 02:00:00",
            }
            return [record_id]
        if model == "ir.attachment":
            self.created_attachment_values = copy.deepcopy(values)
            record_id = max(self.attachments) + 1
            self.attachments[record_id] = {
                "id": record_id,
                "file_size": len(base64.b64decode(values["datas"])),
                "create_date": "2026-10-27 04:00:00",
                "create_uid": [7, "Agent Kim"],
                **copy.deepcopy(values),
            }
            return [record_id]
        raise AssertionError(f"Unexpected create model: {model}")

    def write(self, model, record_id, values):
        if model == "helpdesk.ticket" and record_id in self.tickets:
            updated_values = copy.deepcopy(values)
            if "stage_id" in updated_values:
                stage = self.stages[updated_values["stage_id"]]
                self.events.append(("write", stage["id"]))
                updated_values["stage_id"] = [stage["id"], stage["name"]]
                updated_values["closed"] = stage["closed"]
            if "user_id" in updated_values:
                user_id = updated_values["user_id"]
                updated_values["user_id"] = (
                    [user_id, self.users[user_id]["name"]] if user_id else False
                )
            self.tickets[record_id].update(updated_values)
            return True
        if model == "helpdesk.ticket.category" and record_id in self.categories:
            self.categories[record_id].update(copy.deepcopy(values))
            if "name" in values:
                self.categories[record_id]["complete_name"] = values["name"]
            return True
        if model == "ir.config_parameter" and record_id in self.parameters:
            self.parameters[record_id].update(copy.deepcopy(values))
            return True
        if model == "document.page" and record_id in self.document_pages:
            updated_values = copy.deepcopy(values)
            if "parent_id" in updated_values:
                parent_id = updated_values["parent_id"]
                updated_values["parent_id"] = [
                    parent_id,
                    self.document_pages[parent_id]["name"],
                ]
            if "tag_ids" in updated_values:
                updated_values["tag_ids"] = updated_values["tag_ids"][0][2]
            if "content" in updated_values:
                self.document_histories.append(
                    {"page_id": record_id, "content": updated_values["content"]}
                )
            self.document_pages[record_id].update(updated_values)
            self.document_pages[record_id]["write_date"] = "2026-10-27 06:00:00"
            return True
        raise AssertionError("Unexpected write")

    def message_post(
        self,
        model,
        record_id,
        body,
        subtype_xmlid="mail.mt_note",
    ):
        if model != "helpdesk.ticket" or record_id not in self.tickets:
            raise AssertionError("Unexpected message_post")
        self.messages.append(body)
        message_id = 200 + len(self.messages)
        is_internal = subtype_xmlid == "mail.mt_note"
        self.mail_messages[message_id] = {
            "id": message_id,
            "body": body,
            "author_id": [7, "Agent Kim"],
            "date": "2026-10-27 04:00:00",
            "message_type": "comment",
            "subtype_id": [
                2 if is_internal else 1,
                "Note" if is_internal else "Comment",
            ],
            "is_internal": is_internal,
            "model": "helpdesk.ticket",
            "res_id": record_id,
        }
        self.events.append(("message_post", record_id))
        return message_id


class OcaTicketApiTests(unittest.TestCase):
    def setUp(self):
        self.odoo = MemoryOdoo()
        self.search_patch = patch.object(
            odoo, "search_read", side_effect=self.odoo.search_read
        )
        self.write_patch = patch.object(odoo, "write", side_effect=self.odoo.write)
        self.message_patch = patch.object(
            odoo, "message_post", side_effect=self.odoo.message_post
        )
        self.create_patch = patch.object(odoo, "create", side_effect=self.odoo.create)
        self.search_patch.start()
        self.write_mock = self.write_patch.start()
        self.message_mock = self.message_patch.start()
        self.create_mock = self.create_patch.start()

    def tearDown(self):
        patch.stopall()

    def add_tracking(
        self,
        message_id,
        tracking_id,
        field_id,
        old_id,
        old_name,
        new_id,
        new_name,
        date="2026-10-27 05:00:00",
    ):
        self.odoo.mail_messages[message_id] = {
            "id": message_id,
            "date": date,
            "author_id": [7, "Agent Kim"],
            "model": "helpdesk.ticket",
            "res_id": 1,
            "message_type": "notification",
        }
        field = self.odoo.model_fields[field_id]
        self.odoo.tracking_values[tracking_id] = {
            "id": tracking_id,
            "field_id": [field_id, field["field_description"]],
            "mail_message_id": [message_id, f"Message {message_id}"],
            "old_value_integer": old_id,
            "old_value_char": old_name,
            "new_value_integer": new_id,
            "new_value_char": new_name,
        }

    def test_archive_active_ticket(self):
        result = archive.archive_oca_ticket(1)

        self.assertTrue(result["success"])
        self.assertFalse(result["ticket"]["active"])
        self.assertFalse(self.odoo.tickets[1]["active"])

    def test_archived_ticket_is_excluded_from_active_list(self):
        archive.archive_oca_ticket(1)

        result = tickets.get_oca_tickets()

        self.assertEqual(result, {"success": True, "count": 0, "tickets": []})

    def test_archived_ticket_appears_in_archived_list(self):
        archive.archive_oca_ticket(1)

        result = archive.get_archived_oca_tickets()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tickets"][0]["id"], 1)
        self.assertFalse(result["tickets"][0]["active"])

    def test_archiving_an_archived_ticket_returns_409(self):
        archive.archive_oca_ticket(1)

        with self.assertRaises(HTTPException) as caught:
            archive.archive_oca_ticket(1)

        self.assertEqual(caught.exception.status_code, 409)

    def test_restore_archived_ticket(self):
        archive.archive_oca_ticket(1)

        result = archive.restore_oca_ticket(1)

        self.assertTrue(result["success"])
        self.assertTrue(result["ticket"]["active"])

    def test_restored_ticket_reappears_in_active_list(self):
        archive.archive_oca_ticket(1)
        archive.restore_oca_ticket(1)

        result = tickets.get_oca_tickets()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tickets"][0]["id"], 1)

    def test_restoring_an_active_ticket_returns_409(self):
        with self.assertRaises(HTTPException) as caught:
            archive.restore_oca_ticket(1)

        self.assertEqual(caught.exception.status_code, 409)

    def test_non_positive_id_returns_400(self):
        for operation in (archive.archive_oca_ticket, archive.restore_oca_ticket):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(HTTPException) as caught:
                    operation(0)
                self.assertEqual(caught.exception.status_code, 400)

    def test_unknown_id_returns_404(self):
        for operation in (archive.archive_oca_ticket, archive.restore_oca_ticket):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(HTTPException) as caught:
                    operation(999)
                self.assertEqual(caught.exception.status_code, 404)

    def test_archive_restore_preserves_ticket_data(self):
        before = copy.deepcopy(self.odoo.tickets[1])

        archive.archive_oca_ticket(1)
        archive.restore_oca_ticket(1)

        after = self.odoo.tickets[1]
        for field in (
            "name",
            "description",
            "priority",
            "user_id",
            "category_id",
            "partner_id",
            "team_id",
            "stage_id",
        ):
            self.assertEqual(after[field], before[field])

    def test_archived_ticket_cannot_be_read_or_updated_until_restored(self):
        archive.archive_oca_ticket(1)

        with self.assertRaises(HTTPException) as read_error:
            tickets.get_oca_ticket_detail(1)
        self.assertEqual(read_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as update_error:
            tickets.update_oca_ticket(1, OcaTicketUpdate(title="Changed"))
        self.assertEqual(update_error.exception.status_code, 404)

        archive.restore_oca_ticket(1)
        result = tickets.update_oca_ticket(1, OcaTicketUpdate(title="Changed"))
        self.assertEqual(result["ticket"]["title"], "Changed")

    def test_existing_create_read_update_and_project_routes_still_work(self):
        with patch.object(tickets, "odoo_create_ticket", return_value=[22]):
            created = tickets.create_oca_ticket(
                OcaTicketCreate(title="New", description="Description")
            )
        detail = tickets.get_oca_ticket_detail(1)
        updated = tickets.update_oca_ticket(
            1, OcaTicketUpdate(priority="2", assignee_id=7)
        )
        project_list = legacy.get_tickets()

        self.assertEqual(created["ticket_id"], 22)
        self.assertEqual(detail["ticket"]["id"], 1)
        self.assertEqual(updated["ticket"]["priority_code"], "2")
        self.assertEqual(project_list["count"], 0)

    def test_create_leaves_ticket_number_generation_to_odoo(self):
        with patch.object(tickets, "odoo_create_ticket", return_value=[22]) as create:
            tickets.create_oca_ticket(
                OcaTicketCreate(title="New", description="Description")
            )

        values = create.call_args.args[0]
        self.assertNotIn("number", values)

    def test_all_four_priority_levels_are_mapped_consistently(self):
        expected = {"0": "낮음", "1": "보통", "2": "높음", "3": "긴급"}

        for code, label in expected.items():
            with self.subTest(code=code):
                self.odoo.tickets[1]["priority"] = code
                detail = tickets.get_oca_ticket_detail(1)["ticket"]
                listing = tickets.get_oca_tickets()["tickets"][0]
                updated = tickets.update_oca_ticket(
                    1, OcaTicketUpdate(priority=code)
                )["ticket"]

                for ticket in (detail, listing, updated):
                    self.assertEqual(ticket["priority_code"], code)
                    self.assertEqual(ticket["priority"], label)

    def test_invalid_priority_is_rejected_for_create_and_update(self):
        for value in ("-1", "4", "urgent", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    OcaTicketCreate(
                        title="New", description="Description", priority=value
                    )
                with self.assertRaises(ValidationError):
                    OcaTicketUpdate(priority=value)

    def test_archived_static_route_is_registered_before_dynamic_detail(self):
        paths = list(main.app.openapi()["paths"])

        self.assertLess(
            paths.index("/api/oca/tickets/archived"),
            paths.index("/api/oca/tickets/{ticket_id}"),
        )

    def test_stage_change_updates_ticket_and_preserves_response_shape(self):
        result = tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=3))

        self.assertTrue(result["success"])
        self.assertEqual(
            result["ticket"]["status"], {"id": 3, "name": "In progress"}
        )
        self.assertFalse(result["ticket"]["closed"])
        for field in ("assignee", "category", "priority", "auto_assigned"):
            self.assertIn(field, result["ticket"])
        self.write_mock.assert_called_once_with(
            "helpdesk.ticket", 1, {"stage_id": 3}
        )

    def test_stage_change_unknown_ticket_returns_404(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(999, OcaTicketStageUpdate(stage_id=3))

        self.assertEqual(caught.exception.status_code, 404)

    def test_stage_change_non_positive_ticket_id_returns_400(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(0, OcaTicketStageUpdate(stage_id=3))

        self.assertEqual(caught.exception.status_code, 400)

    def test_invalid_stage_id_is_rejected(self):
        for stage_id in (0, -1):
            with self.subTest(stage_id=stage_id):
                with self.assertRaises(ValidationError):
                    OcaTicketStageUpdate(stage_id=stage_id)

        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=999))
        self.assertEqual(caught.exception.status_code, 422)

    def test_inactive_stage_returns_422(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=6))

        self.assertEqual(caught.exception.status_code, 422)

    def test_archived_ticket_stage_change_returns_409(self):
        archive.archive_oca_ticket(1)
        self.write_mock.reset_mock()

        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=3))

        self.assertEqual(caught.exception.status_code, 409)
        self.write_mock.assert_not_called()

    def test_same_stage_does_not_write(self):
        result = tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=2))

        self.assertEqual(result["ticket"]["status"]["id"], 2)
        self.write_mock.assert_not_called()

    def test_stage_unavailable_to_ticket_team_returns_422(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=7))

        self.assertEqual(caught.exception.status_code, 422)
        self.write_mock.assert_not_called()

    def test_stage_unavailable_to_ticket_company_returns_422(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=8))

        self.assertEqual(caught.exception.status_code, 422)
        self.write_mock.assert_not_called()

    def test_stage_change_mismatch_returns_502(self):
        with patch.object(odoo, "write", return_value=True):
            with self.assertRaises(HTTPException) as caught:
                tickets.update_oca_ticket_stage(
                    1, OcaTicketStageUpdate(stage_id=3)
                )

        self.assertEqual(caught.exception.status_code, 502)

    def test_resolve_records_chatter_before_changing_to_resolved(self):
        self.odoo.tickets[1]["stage_id"] = [3, "In progress"]

        result = tickets.resolve_oca_ticket(
            1, OcaTicketResolve(resolution="Replaced <failed> part")
        )

        self.assertEqual(result["ticket"]["status"]["id"], 4)
        self.assertFalse(result["ticket"]["closed"])
        self.assertIn("해결 내용", self.odoo.messages[0])
        self.assertIn("&lt;failed&gt;", self.odoo.messages[0])
        self.assertEqual(
            self.odoo.events,
            [("message_post", 1), ("write", 4)],
        )

    def test_close_changes_only_resolved_ticket_to_done(self):
        self.odoo.tickets[1]["stage_id"] = [4, "Resolved"]

        result = tickets.close_oca_ticket(1)

        self.assertEqual(result["ticket"]["status"]["id"], 5)
        self.assertTrue(result["ticket"]["closed"])
        self.message_mock.assert_not_called()

    def test_reprocess_records_reason_before_returning_to_in_progress(self):
        self.odoo.tickets[1]["stage_id"] = [4, "Resolved"]

        result = tickets.reprocess_oca_ticket(
            1, OcaTicketReprocess(reason="Issue reproduced")
        )

        self.assertEqual(result["ticket"]["status"]["id"], 3)
        self.assertIn("재처리 사유", self.odoo.messages[0])
        self.assertEqual(
            self.odoo.events,
            [("message_post", 1), ("write", 3)],
        )

    def test_resolve_and_reprocess_require_non_blank_notes(self):
        for schema, field in (
            (OcaTicketResolve, "resolution"),
            (OcaTicketReprocess, "reason"),
        ):
            with self.subTest(schema=schema.__name__):
                with self.assertRaises(ValidationError):
                    schema(**{field: "   "})

    def test_workflow_actions_reject_wrong_current_stage(self):
        operations = (
            lambda: tickets.resolve_oca_ticket(
                1, OcaTicketResolve(resolution="Resolved")
            ),
            lambda: tickets.close_oca_ticket(1),
            lambda: tickets.reprocess_oca_ticket(
                1, OcaTicketReprocess(reason="Retry")
            ),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(HTTPException) as caught:
                    operation()
                self.assertEqual(caught.exception.status_code, 409)

    def test_patch_cannot_bypass_workflow_action_rules(self):
        blocked_transitions = ((3, 4), (4, 5), (4, 3), (2, 5))

        for current_stage_id, target_stage_id in blocked_transitions:
            with self.subTest(
                current=current_stage_id,
                target=target_stage_id,
            ):
                current = self.odoo.stages[current_stage_id]
                self.odoo.tickets[1]["stage_id"] = [
                    current_stage_id,
                    current["name"],
                ]
                self.write_mock.reset_mock()
                with self.assertRaises(HTTPException) as caught:
                    tickets.update_oca_ticket_stage(
                        1, OcaTicketStageUpdate(stage_id=target_stage_id)
                    )
                self.assertEqual(caught.exception.status_code, 409)
                self.write_mock.assert_not_called()

    def test_done_ticket_cannot_change_to_another_stage(self):
        self.odoo.tickets[1]["stage_id"] = [5, "Done"]
        self.odoo.tickets[1]["closed"] = True

        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=1))

        self.assertEqual(caught.exception.status_code, 409)
        self.write_mock.assert_not_called()

    def test_chatter_failure_prevents_stage_write(self):
        self.odoo.tickets[1]["stage_id"] = [3, "In progress"]

        with patch.object(
            odoo,
            "message_post",
            side_effect=HTTPException(status_code=502, detail="message failed"),
        ):
            with self.assertRaises(HTTPException) as caught:
                tickets.resolve_oca_ticket(
                    1, OcaTicketResolve(resolution="Resolved")
                )

        self.assertEqual(caught.exception.status_code, 502)
        self.write_mock.assert_not_called()

    def test_stage_failure_after_chatter_leaves_message_only(self):
        self.odoo.tickets[1]["stage_id"] = [3, "In progress"]

        with patch.object(
            odoo,
            "write",
            side_effect=HTTPException(status_code=502, detail="write failed"),
        ):
            with self.assertRaises(HTTPException) as caught:
                tickets.resolve_oca_ticket(
                    1, OcaTicketResolve(resolution="Resolved")
                )

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(len(self.odoo.messages), 1)
        self.assertEqual(self.odoo.tickets[1]["stage_id"][0], 3)

    def test_workflow_configuration_must_have_five_applicable_stages(self):
        self.odoo.stages[9] = {
            "id": 9,
            "name": "Unexpected",
            "sequence": 6,
            "active": True,
            "team_ids": [],
            "company_id": [1, "Main Company"],
            "closed": False,
        }

        with self.assertRaises(HTTPException) as caught:
            tickets.update_oca_ticket_stage(1, OcaTicketStageUpdate(stage_id=3))

        self.assertEqual(caught.exception.status_code, 502)
        self.write_mock.assert_not_called()

    def test_create_and_list_ticket_comments_and_internal_notes(self):
        comment = tickets.create_oca_ticket_comment(
            1,
            OcaTicketCommentCreate(body="Hello <team>", kind="comment"),
        )
        note = tickets.create_oca_ticket_comment(
            1,
            OcaTicketCommentCreate(body="Internal only", kind="note"),
        )

        result = tickets.get_oca_ticket_comments(1)

        self.assertEqual(comment["kind"], "comment")
        self.assertEqual(note["kind"], "note")
        self.assertIn("&lt;team&gt;", self.odoo.messages[0])
        self.assertEqual(result["count"], 2)
        self.assertEqual(
            {item["kind"] for item in result["comments"]},
            {"comment", "note"},
        )
        self.assertEqual(result["comments"][0]["author"]["id"], 7)
        self.assertEqual(result["comments"][0]["message_type"], "comment")
        self.assertEqual(
            self.message_mock.call_args_list[0].kwargs["subtype_xmlid"],
            "mail.mt_comment",
        )
        self.assertEqual(
            self.message_mock.call_args_list[1].kwargs["subtype_xmlid"],
            "mail.mt_note",
        )

    def test_ticket_history_returns_stage_change(self):
        self.add_tracking(300, 400, 1001, 2, "Assigned", 3, "In progress")

        result = tickets.get_oca_ticket_history(1, limit=50)

        self.assertEqual(result["count"], 1)
        change = result["history"][0]
        self.assertEqual(change["change_type"], "status")
        self.assertEqual(change["field"]["name"], "stage_id")
        self.assertEqual(change["old_value"], {"id": 2, "name": "Assigned"})
        self.assertEqual(
            change["new_value"], {"id": 3, "name": "In progress"}
        )
        self.assertEqual(change["changed_by"], {"id": 7, "name": "Agent Kim"})

    def test_ticket_history_represents_multiple_changes_from_one_message(self):
        self.add_tracking(300, 400, 1001, 2, "Assigned", 3, "In progress")
        self.add_tracking(300, 401, 1002, 0, "", 7, "Agent Kim")

        result = tickets.get_oca_ticket_history(1, limit=50)

        self.assertEqual(result["count"], 2)
        self.assertEqual(
            {change["change_type"] for change in result["history"]},
            {"status", "assignee"},
        )
        self.assertEqual(
            {change["message_id"] for change in result["history"]},
            {300},
        )

    def test_ticket_history_returns_empty_when_no_tracking_exists(self):
        result = tickets.get_oca_ticket_history(1, limit=50)

        self.assertEqual(result, {"success": True, "count": 0, "history": []})

    def test_ticket_history_rejects_unknown_ticket(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.get_oca_ticket_history(999, limit=50)

        self.assertEqual(caught.exception.status_code, 404)

    def test_ticket_history_supports_closed_and_archived_ticket(self):
        self.add_tracking(300, 400, 1001, 4, "Resolved", 5, "Done")
        self.odoo.tickets[1]["stage_id"] = [5, "Done"]
        self.odoo.tickets[1]["closed"] = True

        closed = tickets.get_oca_ticket_history(1, limit=50)
        self.odoo.tickets[1]["active"] = False
        archived = tickets.get_oca_ticket_history(1, limit=50)

        self.assertEqual(closed["count"], 1)
        self.assertEqual(archived["count"], 1)

    def test_ticket_history_propagates_tracking_access_error(self):
        self.add_tracking(300, 400, 1001, 2, "Assigned", 3, "In progress")
        self.odoo.deny_tracking_access = True

        with self.assertRaises(HTTPException) as caught:
            tickets.get_oca_ticket_history(1, limit=50)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn("mail.tracking.value", caught.exception.detail)

    def test_ticket_history_is_latest_first_and_limited(self):
        self.add_tracking(
            300,
            400,
            1001,
            1,
            "New",
            2,
            "Assigned",
            date="2026-10-27 03:00:00",
        )
        self.add_tracking(
            301,
            401,
            1001,
            2,
            "Assigned",
            3,
            "In progress",
            date="2026-10-27 04:00:00",
        )
        self.add_tracking(
            302,
            402,
            1002,
            0,
            "",
            7,
            "Agent Kim",
            date="2026-10-27 05:00:00",
        )

        result = tickets.get_oca_ticket_history(1, limit=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(
            [change["id"] for change in result["history"]],
            [402, 401],
        )

    def test_blank_comment_is_rejected(self):
        with self.assertRaises(ValidationError):
            OcaTicketCommentCreate(body="   ")

    def test_attachment_list_returns_only_ticket_files(self):
        self.odoo.attachments[51] = {
            **copy.deepcopy(self.odoo.attachments[50]),
            "id": 51,
            "name": "other.txt",
            "res_id": 999,
        }

        result = tickets.get_oca_ticket_attachments(1)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["attachments"][0]["id"], 50)
        self.assertEqual(result["attachments"][0]["content_type"], "text/plain")

    def test_attachment_upload_validates_and_creates_odoo_record(self):
        result = tickets.upload_oca_ticket_attachment(
            1,
            filename="evidence.txt",
            content_type="text/plain",
            file_data=b"hello",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["attachment"]["size"], 5)
        values = self.odoo.created_attachment_values
        self.assertEqual(values["res_model"], "helpdesk.ticket")
        self.assertEqual(values["res_id"], 1)
        self.assertEqual(base64.b64decode(values["datas"]), b"hello")

    def test_attachment_upload_rejects_invalid_file(self):
        cases = (
            ("empty.txt", "text/plain", b""),
            ("script.exe", "application/octet-stream", b"binary"),
            ("fake.png", "text/plain", b"not an image"),
            ("../escape.txt", "text/plain", b"text"),
        )

        for filename, content_type, file_data in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(HTTPException):
                    tickets.upload_oca_ticket_attachment(
                        1,
                        filename=filename,
                        content_type=content_type,
                        file_data=file_data,
                    )
        self.create_mock.assert_not_called()

    def test_attachment_upload_rejects_oversized_file(self):
        with patch.object(tickets, "MAX_ATTACHMENT_SIZE", 3):
            with self.assertRaises(HTTPException) as caught:
                tickets.upload_oca_ticket_attachment(
                    1,
                    filename="large.txt",
                    content_type="text/plain",
                    file_data=b"four",
                )

        self.assertEqual(caught.exception.status_code, 413)
        self.create_mock.assert_not_called()

    def test_attachment_download_checks_link_and_returns_file(self):
        response = tickets.download_oca_ticket_attachment(1, 50)

        self.assertEqual(response.body, b"error")
        self.assertEqual(response.media_type, "text/plain")
        self.assertIn("error.txt", response.headers["content-disposition"])

        self.odoo.attachments[50]["res_id"] = 999
        with self.assertRaises(HTTPException) as caught:
            tickets.download_oca_ticket_attachment(1, 50)
        self.assertEqual(caught.exception.status_code, 404)

    def test_attachment_download_rejects_corrupt_odoo_data(self):
        self.odoo.attachments[50]["datas"] = "not-base64!"

        with self.assertRaises(HTTPException) as caught:
            tickets.download_oca_ticket_attachment(1, 50)

        self.assertEqual(caught.exception.status_code, 502)

    def test_comments_and_attachments_require_active_ticket(self):
        archive.archive_oca_ticket(1)

        operations = (
            lambda: tickets.get_oca_ticket_comments(1),
            lambda: tickets.get_oca_ticket_attachments(1),
            lambda: tickets.create_oca_ticket_comment(
                1, OcaTicketCommentCreate(body="Comment")
            ),
            lambda: tickets.upload_oca_ticket_attachment(
                1,
                filename="file.txt",
                content_type="text/plain",
                file_data=b"data",
            ),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(HTTPException) as caught:
                    operation()
                self.assertEqual(caught.exception.status_code, 409)

    def test_closed_ticket_rejects_comment_note_and_attachment_upload(self):
        self.odoo.tickets[1]["stage_id"] = [5, "Done"]
        self.odoo.tickets[1]["closed"] = True

        operations = (
            lambda: tickets.create_oca_ticket_comment(
                1, OcaTicketCommentCreate(body="Comment", kind="comment")
            ),
            lambda: tickets.create_oca_ticket_comment(
                1, OcaTicketCommentCreate(body="Internal", kind="note")
            ),
            lambda: tickets.upload_oca_ticket_attachment(
                1,
                filename="file.txt",
                content_type="text/plain",
                file_data=b"data",
            ),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(HTTPException) as caught:
                    operation()
                self.assertEqual(caught.exception.status_code, 409)

        self.message_mock.assert_not_called()
        self.create_mock.assert_not_called()

    def test_closed_ticket_keeps_comment_attachment_read_and_download(self):
        self.odoo.message_post(
            "helpdesk.ticket",
            1,
            "<p>Existing comment</p>",
            subtype_xmlid="mail.mt_comment",
        )
        self.odoo.tickets[1]["stage_id"] = [5, "Done"]
        self.odoo.tickets[1]["closed"] = True

        comments = tickets.get_oca_ticket_comments(1)
        attachments = tickets.get_oca_ticket_attachments(1)
        download = tickets.download_oca_ticket_attachment(1, 50)

        self.assertEqual(comments["count"], 1)
        self.assertEqual(attachments["count"], 1)
        self.assertEqual(download.body, b"error")


class FaqApiTests(unittest.TestCase):
    def setUp(self):
        self.odoo = MemoryOdoo()
        self.search_patch = patch.object(
            odoo, "search_read", side_effect=self.odoo.search_read
        )
        self.write_patch = patch.object(odoo, "write", side_effect=self.odoo.write)
        self.create_patch = patch.object(odoo, "create", side_effect=self.odoo.create)
        self.public_patch = patch.object(
            config, "ODOO_FAQ_PUBLIC_CATEGORY_ID", "100"
        )
        self.draft_patch = patch.object(
            config, "ODOO_FAQ_DRAFT_CATEGORY_ID", "101"
        )
        self.enabled_patch = patch.object(config, "ODOO_FAQ_WRITE_ENABLED", True)
        for active_patch in (
            self.search_patch,
            self.write_patch,
            self.create_patch,
            self.public_patch,
            self.draft_patch,
            self.enabled_patch,
        ):
            active_patch.start()

    def tearDown(self):
        patch.stopall()

    def test_public_list_and_detail_exclude_drafts_and_archived_pages(self):
        result = faqs.get_public_faqs(limit=50)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["faqs"][0]["id"], 110)
        self.assertEqual(result["faqs"][0]["content"], "Restart the router safely.")
        self.assertEqual(faqs.get_public_faq(110)["faq"]["visibility"], "public")
        for faq_id in (111, 112):
            with self.assertRaises(HTTPException) as caught:
                faqs.get_public_faq(faq_id)
            self.assertEqual(caught.exception.status_code, 404)

    def test_suggestions_search_title_content_and_tag_and_limit_results(self):
        self.odoo.document_pages[113] = {
            **copy.deepcopy(self.odoo.document_pages[110]),
            "id": 113,
            "name": "Router guide",
            "content": "<p>network recovery</p>",
        }
        self.odoo.document_pages[114] = {
            **copy.deepcopy(self.odoo.document_pages[110]),
            "id": 114,
            "name": "VPN guide",
            "content": "<p>network access</p>",
        }
        self.odoo.document_pages[115] = {
            **copy.deepcopy(self.odoo.document_pages[110]),
            "id": 115,
            "name": "Network",
            "content": "<p>exact title match</p>",
        }

        result = faqs.get_faq_suggestions(q="network")

        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["faqs"]), 3)
        self.assertEqual(result["faqs"][0]["id"], 115)

    def test_admin_create_update_publish_archive_restore_and_unpublish(self):
        created = faqs.create_faq(
            OcaFaqCreate(name="Printer FAQ", content="Restart printer", tag_ids=[202])
        )["faq"]
        faq_id = created["id"]
        self.assertEqual(created["visibility"], "draft")

        updated = faqs.update_faq(
            faq_id,
            OcaFaqUpdate(content="Power cycle", tag_ids=[201]),
        )["faq"]
        self.assertEqual(updated["content"], "Power cycle")
        self.assertEqual(updated["tags"][0]["name"], "network")
        self.assertGreaterEqual(len(self.odoo.document_histories), 2)

        self.assertEqual(faqs.publish_faq(faq_id)["faq"]["visibility"], "public")
        self.assertFalse(faqs.archive_faq(faq_id)["faq"]["active"])
        self.assertTrue(faqs.restore_faq(faq_id)["faq"]["active"])
        self.assertEqual(
            faqs.unpublish_faq(faq_id)["faq"]["visibility"],
            "draft",
        )
        all_faqs = faqs.get_all_faqs()
        self.assertEqual(all_faqs["count"], 4)

    def test_content_is_escaped_before_storage(self):
        result = faqs.create_faq(
            OcaFaqCreate(
                name="Safe FAQ",
                content="<script>alert(1)</script>\nNext line",
                tag_ids=[],
            )
        )

        stored = self.odoo.document_pages[result["faq"]["id"]]["content"]
        self.assertIn("&lt;script&gt;", stored)
        self.assertNotIn("<script>", stored)
        self.assertEqual(
            result["faq"]["content"],
            "<script>alert(1)</script>\nNext line",
        )

    def test_invalid_category_settings_and_tags_are_rejected(self):
        with patch.object(config, "ODOO_FAQ_PUBLIC_CATEGORY_ID", None):
            with self.assertRaises(HTTPException) as caught:
                faqs.get_public_faqs(limit=50)
            self.assertEqual(caught.exception.status_code, 500)

        with patch.object(config, "ODOO_FAQ_DRAFT_CATEGORY_ID", "100"):
            with self.assertRaises(HTTPException) as caught:
                faqs.get_faq_categories()
            self.assertEqual(caught.exception.status_code, 500)

        with self.assertRaises(HTTPException) as caught:
            faqs.create_faq(
                OcaFaqCreate(name="Bad tag", content="Text", tag_ids=[999])
            )
        self.assertEqual(caught.exception.status_code, 422)

    def test_write_api_is_disabled_by_default_switch(self):
        with patch.object(config, "ODOO_FAQ_WRITE_ENABLED", False):
            with self.assertRaises(HTTPException) as caught:
                faqs.create_faq(
                    OcaFaqCreate(name="Blocked", content="Text", tag_ids=[])
                )

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(len(self.odoo.document_pages), 5)
        self.assertIn("인증·인가", caught.exception.detail)

    def test_resolved_ticket_creates_review_required_private_draft(self):
        self.odoo.tickets[1]["stage_id"] = [4, "Resolved"]
        self.odoo.message_post(
            "helpdesk.ticket",
            1,
            "<p><strong>해결 내용</strong><br>Restarted safely</p>",
            subtype_xmlid="mail.mt_note",
        )

        result = tickets.create_faq_draft_from_ticket(1)

        self.assertTrue(result["review_required"])
        self.assertEqual(result["faq"]["name"], "Printer failure")
        self.assertEqual(result["faq"]["content"], "Restarted safely")
        self.assertEqual(result["faq"]["visibility"], "draft")
        stored = self.odoo.document_pages[result["faq"]["id"]]
        self.assertNotIn("source_ticket_id", stored)

    def test_ticket_draft_rejects_wrong_status_and_unrelated_notes(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.create_faq_draft_from_ticket(1)
        self.assertEqual(caught.exception.status_code, 409)

        self.odoo.tickets[1]["stage_id"] = [5, "Done"]
        self.odoo.tickets[1]["closed"] = True
        self.odoo.message_post(
            "helpdesk.ticket",
            1,
            "<p><strong>재처리 사유</strong><br>Try again</p>",
            subtype_xmlid="mail.mt_note",
        )
        self.odoo.message_post(
            "helpdesk.ticket",
            1,
            "<p>해결 내용은 댓글로만 남김</p>",
            subtype_xmlid="mail.mt_comment",
        )

        with self.assertRaises(HTTPException) as caught:
            tickets.create_faq_draft_from_ticket(1)
        self.assertEqual(caught.exception.status_code, 422)

    def test_odoo_access_and_connection_errors_are_not_returned_as_empty(self):
        for status_code in (403, 502):
            with patch.object(
                odoo,
                "search_read",
                side_effect=HTTPException(status_code=status_code, detail="Odoo error"),
            ):
                with self.assertRaises(HTTPException) as caught:
                    faqs.get_public_faqs(limit=50)
            self.assertEqual(caught.exception.status_code, status_code)


class CategoryApiTests(unittest.TestCase):
    def setUp(self):
        self.odoo = MemoryOdoo()
        patch.object(
            odoo, "search_read", side_effect=self.odoo.search_read
        ).start()
        patch.object(odoo, "write", side_effect=self.odoo.write).start()
        patch.object(odoo, "create", side_effect=self.odoo.create).start()

    def tearDown(self):
        patch.stopall()

    def test_category_create_update_and_list(self):
        created = categories.create_oca_category(OcaCategoryCreate(name="Network"))
        category_id = created["category"]["id"]

        updated = categories.update_oca_category(
            category_id,
            OcaCategoryUpdate(name="Network Support", show_in_portal=False),
        )
        listed = categories.get_oca_categories()["categories"]
        detail = categories.get_oca_category_detail(category_id)["category"]

        self.assertEqual(updated["category"]["name"], "Network Support")
        self.assertFalse(updated["category"]["show_in_portal"])
        self.assertIn(category_id, [category["id"] for category in listed])
        self.assertEqual(detail["name"], "Network Support")

    def test_inactive_category_cannot_be_selected_for_new_ticket(self):
        categories.archive_oca_category(10)

        with self.assertRaises(HTTPException) as caught:
            tickets.create_oca_ticket(
                OcaTicketCreate(
                    title="New", description="Description", category_id=10
                )
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertNotIn(10, [item["id"] for item in categories.get_oca_categories()["categories"]])
        self.assertIn(10, [item["id"] for item in categories.get_all_oca_categories()["categories"]])

    def test_unknown_category_is_rejected_for_new_ticket(self):
        with self.assertRaises(HTTPException) as caught:
            tickets.create_oca_ticket(
                OcaTicketCreate(
                    title="New", description="Description", category_id=999
                )
            )

        self.assertEqual(caught.exception.status_code, 404)

    def test_category_default_assignee_can_be_set_and_read(self):
        result = categories.update_oca_category(
            10, OcaCategoryUpdate(default_assignee_id=7)
        )

        self.assertEqual(result["category"]["default_assignee"]["id"], 7)
        self.assertEqual(len(self.odoo.parameters), 1)

    def test_ticket_creation_with_category_auto_assigns_default_user(self):
        categories.update_oca_category(10, OcaCategoryUpdate(default_assignee_id=7))

        created = tickets.create_oca_ticket(
            OcaTicketCreate(
                title="New", description="Description", category_id=10
            )
        )
        detail = tickets.get_oca_ticket_detail(created["ticket_id"])["ticket"]

        self.assertTrue(created["auto_assigned"])
        self.assertEqual(self.odoo.created_ticket_values["category_id"], 10)
        self.assertEqual(self.odoo.created_ticket_values["user_id"], 7)
        self.assertEqual(detail["category"]["id"], 10)
        self.assertEqual(detail["assignee"]["id"], 7)
        self.assertIsNone(detail["auto_assigned"])

    def test_category_without_default_user_leaves_ticket_unassigned(self):
        created = tickets.create_oca_ticket(
            OcaTicketCreate(
                title="New", description="Description", category_id=11
            )
        )

        self.assertFalse(created["auto_assigned"])
        self.assertFalse(self.odoo.created_ticket_values["user_id"])
        detail = tickets.get_oca_ticket_detail(created["ticket_id"])["ticket"]
        self.assertIsNone(detail["auto_assigned"])

    def test_invalid_default_assignee_is_rejected(self):
        for user_id in (8, 9, 999):
            with self.subTest(user_id=user_id):
                with self.assertRaises(HTTPException) as caught:
                    categories.update_oca_category(
                        10, OcaCategoryUpdate(default_assignee_id=user_id)
                    )
                self.assertEqual(caught.exception.status_code, 422)

    def test_etc_category_is_always_sorted_last(self):
        listed_categories = categories.get_oca_categories()["categories"]

        self.assertEqual(listed_categories[-1]["name"], "기타(ETC)")

    def test_manual_assignment_still_works(self):
        categories.update_oca_category(
            10, OcaCategoryUpdate(default_assignee_id=7)
        )
        self.odoo.tickets[1]["category_id"] = [10, "General"]

        result = tickets.update_oca_ticket(
            1, OcaTicketUpdate(assignee_id=7)
        )

        self.assertEqual(result["ticket"]["assignee"]["id"], 7)
        self.assertIsNone(result["ticket"]["auto_assigned"])

    def test_clearing_default_assignee_keeps_single_parameter_record(self):
        categories.update_oca_category(10, OcaCategoryUpdate(default_assignee_id=7))
        result = categories.update_oca_category(
            10, OcaCategoryUpdate(default_assignee_id=None)
        )

        self.assertIsNone(result["category"]["default_assignee"])
        self.assertEqual(len(self.odoo.parameters), 1)


class OdooJson2Tests(unittest.TestCase):
    def test_search_read_sends_context_as_top_level_json2_argument(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []

        with (
            patch.object(config, "ODOO_API_KEY", "test-key"),
            patch.object(odoo.requests, "post", return_value=response) as post,
        ):
            odoo.search_read(
                "helpdesk.ticket",
                ["id"],
                domain=[["active", "=", False]],
                context={"active_test": False},
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["context"], {"active_test": False})
        self.assertEqual(payload["domain"], [["active", "=", False]])

    def test_search_read_sends_order_argument(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []

        with (
            patch.object(config, "ODOO_API_KEY", "test-key"),
            patch.object(odoo.requests, "post", return_value=response) as post,
        ):
            odoo.search_read(
                "mail.message",
                ["id"],
                order="date desc, id desc",
            )

        self.assertEqual(
            post.call_args.kwargs["json"]["order"],
            "date desc, id desc",
        )

    def test_search_read_preserves_odoo_access_denied_status(self):
        response = Mock()
        response.status_code = 403
        response.raise_for_status.side_effect = odoo.requests.exceptions.HTTPError()

        with (
            patch.object(config, "ODOO_API_KEY", "test-key"),
            patch.object(odoo.requests, "post", return_value=response),
        ):
            with self.assertRaises(HTTPException) as caught:
                odoo.search_read("mail.tracking.value", ["id"])

        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn("access denied", caught.exception.detail)

    def test_message_post_sends_internal_note_through_json2(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [91]

        with (
            patch.object(config, "ODOO_API_KEY", "test-key"),
            patch.object(odoo.requests, "post", return_value=response) as post,
        ):
            result = odoo.message_post("helpdesk.ticket", 7, "<p>Resolved</p>")

        self.assertEqual(result, 91)
        self.assertTrue(
            post.call_args.args[0].endswith("/helpdesk.ticket/message_post")
        )
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "ids": [7],
                "body": "<p>Resolved</p>",
                "body_is_html": True,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_note",
            },
        )

    def test_message_post_accepts_comment_subtype(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [92]

        with (
            patch.object(config, "ODOO_API_KEY", "test-key"),
            patch.object(odoo.requests, "post", return_value=response) as post,
        ):
            odoo.message_post(
                "helpdesk.ticket",
                7,
                "<p>Comment</p>",
                subtype_xmlid="mail.mt_comment",
            )

        self.assertEqual(
            post.call_args.kwargs["json"]["subtype_xmlid"],
            "mail.mt_comment",
        )


if __name__ == "__main__":
    unittest.main()
