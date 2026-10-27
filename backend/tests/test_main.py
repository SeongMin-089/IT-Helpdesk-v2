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


class MemoryOdoo:
    def __init__(self):
        self.tickets = {
            1: {
                "id": 1,
                "number": "T-001",
                "name": "Printer failure",
                "description": "Keep <b>all</b> fields",
                "stage_id": [2, "In progress"],
                "priority": "3",
                "user_id": [7, "Agent Kim"],
                "category_id": [4, "Hardware"],
                "partner_id": [9, "Requester Lee"],
                "team_id": [3, "IT"],
                "closed": False,
                "active": True,
                "create_date": "2026-10-27 01:00:00",
                "write_date": "2026-10-27 01:00:00",
            }
        }

    def search_read(self, model, fields, domain=None, limit=50, context=None):
        if model == "res.users":
            return [{"id": 7, "name": "Agent Kim"}]
        if model == "project.task":
            return []
        if model != "helpdesk.ticket":
            return []

        records = list(self.tickets.values())
        if not (context or {}).get("active_test") is False:
            records = [record for record in records if record["active"]]

        for field, operator, value in domain or []:
            if operator != "=":
                raise AssertionError(f"Unsupported test operator: {operator}")
            records = [record for record in records if record.get(field) == value]

        return [
            {field: copy.deepcopy(record.get(field)) for field in fields}
            for record in records[:limit]
        ]

    def write(self, model, record_id, values):
        if model != "helpdesk.ticket" or record_id not in self.tickets:
            raise AssertionError("Unexpected write")
        self.tickets[record_id].update(copy.deepcopy(values))
        return True


class OcaTicketApiTests(unittest.TestCase):
    def setUp(self):
        self.odoo = MemoryOdoo()
        self.search_patch = patch.object(
            main, "odoo_search_read", side_effect=self.odoo.search_read
        )
        self.write_patch = patch.object(main, "odoo_write", side_effect=self.odoo.write)
        self.search_patch.start()
        self.write_patch.start()

    def tearDown(self):
        patch.stopall()

    def test_archive_active_ticket(self):
        result = main.archive_oca_ticket(1)

        self.assertTrue(result["success"])
        self.assertFalse(result["ticket"]["active"])
        self.assertFalse(self.odoo.tickets[1]["active"])

    def test_archived_ticket_is_excluded_from_active_list(self):
        main.archive_oca_ticket(1)

        result = main.get_oca_tickets()

        self.assertEqual(result, {"success": True, "count": 0, "tickets": []})

    def test_archived_ticket_appears_in_archived_list(self):
        main.archive_oca_ticket(1)

        result = main.get_archived_oca_tickets()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tickets"][0]["id"], 1)
        self.assertFalse(result["tickets"][0]["active"])

    def test_archiving_an_archived_ticket_returns_409(self):
        main.archive_oca_ticket(1)

        with self.assertRaises(HTTPException) as caught:
            main.archive_oca_ticket(1)

        self.assertEqual(caught.exception.status_code, 409)

    def test_restore_archived_ticket(self):
        main.archive_oca_ticket(1)

        result = main.restore_oca_ticket(1)

        self.assertTrue(result["success"])
        self.assertTrue(result["ticket"]["active"])

    def test_restored_ticket_reappears_in_active_list(self):
        main.archive_oca_ticket(1)
        main.restore_oca_ticket(1)

        result = main.get_oca_tickets()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tickets"][0]["id"], 1)

    def test_restoring_an_active_ticket_returns_409(self):
        with self.assertRaises(HTTPException) as caught:
            main.restore_oca_ticket(1)

        self.assertEqual(caught.exception.status_code, 409)

    def test_non_positive_id_returns_400(self):
        for operation in (main.archive_oca_ticket, main.restore_oca_ticket):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(HTTPException) as caught:
                    operation(0)
                self.assertEqual(caught.exception.status_code, 400)

    def test_unknown_id_returns_404(self):
        for operation in (main.archive_oca_ticket, main.restore_oca_ticket):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(HTTPException) as caught:
                    operation(999)
                self.assertEqual(caught.exception.status_code, 404)

    def test_archive_restore_preserves_ticket_data(self):
        before = copy.deepcopy(self.odoo.tickets[1])

        main.archive_oca_ticket(1)
        main.restore_oca_ticket(1)

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
        main.archive_oca_ticket(1)

        with self.assertRaises(HTTPException) as read_error:
            main.get_oca_ticket_detail(1)
        self.assertEqual(read_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as update_error:
            main.update_oca_ticket(1, main.OcaTicketUpdate(title="Changed"))
        self.assertEqual(update_error.exception.status_code, 404)

        main.restore_oca_ticket(1)
        result = main.update_oca_ticket(1, main.OcaTicketUpdate(title="Changed"))
        self.assertEqual(result["ticket"]["title"], "Changed")

    def test_existing_create_read_update_and_project_routes_still_work(self):
        with patch.object(main, "odoo_create_ticket", return_value=[22]):
            created = main.create_oca_ticket(
                main.OcaTicketCreate(title="New", description="Description")
            )
        detail = main.get_oca_ticket_detail(1)
        updated = main.update_oca_ticket(
            1, main.OcaTicketUpdate(priority="2", assignee_id=7)
        )
        project_list = main.get_tickets()

        self.assertEqual(created["ticket_id"], 22)
        self.assertEqual(detail["ticket"]["id"], 1)
        self.assertEqual(updated["ticket"]["priority_code"], "2")
        self.assertEqual(project_list["count"], 0)

    def test_create_leaves_ticket_number_generation_to_odoo(self):
        with patch.object(main, "odoo_create_ticket", return_value=[22]) as create:
            main.create_oca_ticket(
                main.OcaTicketCreate(title="New", description="Description")
            )

        values = create.call_args.args[0]
        self.assertNotIn("number", values)

    def test_all_four_priority_levels_are_mapped_consistently(self):
        expected = {"0": "낮음", "1": "보통", "2": "높음", "3": "긴급"}

        for code, label in expected.items():
            with self.subTest(code=code):
                self.odoo.tickets[1]["priority"] = code
                detail = main.get_oca_ticket_detail(1)["ticket"]
                listing = main.get_oca_tickets()["tickets"][0]
                updated = main.update_oca_ticket(
                    1, main.OcaTicketUpdate(priority=code)
                )["ticket"]

                for ticket in (detail, listing, updated):
                    self.assertEqual(ticket["priority_code"], code)
                    self.assertEqual(ticket["priority"], label)

    def test_invalid_priority_is_rejected_for_create_and_update(self):
        for value in ("-1", "4", "urgent", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    main.OcaTicketCreate(
                        title="New", description="Description", priority=value
                    )
                with self.assertRaises(ValidationError):
                    main.OcaTicketUpdate(priority=value)

    def test_archived_static_route_is_registered_before_dynamic_detail(self):
        paths = [route.path for route in main.app.routes]

        self.assertLess(
            paths.index("/api/oca/tickets/archived"),
            paths.index("/api/oca/tickets/{ticket_id}"),
        )


class OdooJson2Tests(unittest.TestCase):
    def test_search_read_sends_context_as_top_level_json2_argument(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []

        with (
            patch.object(main, "ODOO_API_KEY", "test-key"),
            patch.object(main.requests, "post", return_value=response) as post,
        ):
            main.odoo_search_read(
                "helpdesk.ticket",
                ["id"],
                domain=[["active", "=", False]],
                context={"active_test": False},
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["context"], {"active_test": False})
        self.assertEqual(payload["domain"], [["active", "=", False]])


if __name__ == "__main__":
    unittest.main()
