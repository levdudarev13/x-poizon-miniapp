import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import _admin_messages_clear_payload, _admin_messages_payload


class AdminMessagesHelpersTests(unittest.TestCase):
    def test_admin_messages_payload_returns_newest_first_with_stats(self) -> None:
        rows = [
            {
                "id": 1,
                "user_id": 101,
                "username": "first_user",
                "msg_type": "contact",
                "text": "Первое сообщение",
                "sent_at": "2026-03-20 10:15:00",
            },
            {
                "id": 2,
                "user_id": 202,
                "username": "",
                "msg_type": "problem",
                "text": "Есть проблема",
                "sent_at": "2026-03-20 12:45:00",
            },
        ]

        with patch(
            "miniapp_server.db.msg_get_all",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_messages_payload({"page": 1, "page_size": 1}))

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], 2)
        self.assertEqual(payload["items"][0]["contact_label"], "id:202")
        self.assertEqual(payload["items"][0]["type_label"], "Сообщение о проблеме")
        self.assertEqual(payload["pagination"]["page"], 1)
        self.assertEqual(payload["pagination"]["total_pages"], 2)
        self.assertTrue(payload["pagination"]["has_next"])
        self.assertEqual(payload["stats"]["total"], 2)
        self.assertEqual(payload["stats"]["by_type"]["contact"], 1)
        self.assertEqual(payload["stats"]["by_type"]["problem"], 1)
        self.assertEqual(payload["stats"]["latest_sent_at_label"], "20.03.2026 в 12:45")

    def test_admin_messages_payload_clamps_page_to_last_page(self) -> None:
        rows = [
            {
                "id": 1,
                "user_id": 101,
                "username": "alpha",
                "msg_type": "contact",
                "text": "Сообщение 1",
                "sent_at": "2026-03-20 10:15:00",
            },
            {
                "id": 2,
                "user_id": 202,
                "username": "beta",
                "msg_type": "calc_request",
                "text": "Сообщение 2",
                "sent_at": "2026-03-20 11:15:00",
            },
            {
                "id": 3,
                "user_id": 303,
                "username": "gamma",
                "msg_type": "problem",
                "text": "Сообщение 3",
                "sent_at": "2026-03-20 12:15:00",
            },
        ]

        with patch(
            "miniapp_server.db.msg_get_all",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_messages_payload({"page": 99, "page_size": 2}))

        self.assertEqual(payload["pagination"]["page"], 2)
        self.assertFalse(payload["pagination"]["has_next"])
        self.assertTrue(payload["pagination"]["has_prev"])
        self.assertEqual([item["id"] for item in payload["items"]], [1])

    def test_admin_messages_clear_payload_deletes_all_messages(self) -> None:
        delete_all = AsyncMock()

        with patch(
            "miniapp_server.db.msg_delete_all",
            new=delete_all,
        ), patch(
            "miniapp_server.db.msg_get_all",
            new=AsyncMock(return_value=[]),
        ):
            payload = asyncio.run(_admin_messages_clear_payload())

        delete_all.assert_awaited_once()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["stats"]["total"], 0)
        self.assertEqual(payload["pagination"]["page"], 1)
        self.assertFalse(payload["pagination"]["has_next"])


if __name__ == "__main__":
    unittest.main()
