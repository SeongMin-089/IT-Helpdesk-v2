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
from app.routers import archive, categories, legacy, tickets  # noqa: E402
from app.schemas import (  # noqa: E402
    OcaCategoryCreate,
    OcaCategoryUpdate,
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
        self.events = []

    @staticmethod
    def _matches(record, domain):
        for field, operator, value in domain or []:
            current = record.get(field)
            if operator == "=" and current != value:
                return False
            if operator == "!=" and current == value:
                return False
            if operator == "in":
                if isinstance(current, list):
                    if not any(item in value for item in current):
                        return False
                elif current not in value:
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

    def search_read(self, model, fields, domain=None, limit=50, context=None):
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
                }
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
        raise AssertionError("Unexpected write")

    def message_post(self, model, record_id, body):
        if model != "helpdesk.ticket" or record_id not in self.tickets:
            raise AssertionError("Unexpected message_post")
        self.messages.append(body)
        self.events.append(("message_post", record_id))
        return len(self.messages)


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
        self.search_patch.start()
        self.write_mock = self.write_patch.start()
        self.message_mock = self.message_patch.start()

    def tearDown(self):
        patch.stopall()

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


if __name__ == "__main__":
    unittest.main()
