import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import (
    _admin_faq_delete_payload,
    _admin_faq_payload,
    _admin_faq_save_payload,
    _faq_payload,
)


class AdminFaqHelpersTests(unittest.TestCase):
    def test_faq_payload_returns_entries_and_contact(self) -> None:
        faq_rows = [
            {
                "id": 1,
                "question": "Что такое сервис?",
                "answer": "Помогаем с заказами.",
                "link_url": "https://vk.ru/@logisticsx-pricing",
                "button_label": "Подробнее",
                "position": 1,
                "updated_at": 1_744_000_000.0,
            },
        ]

        with patch(
            "miniapp_server.db.get_faq_entries",
            new=AsyncMock(return_value=faq_rows),
        ), patch(
            "miniapp_server._admin_contact_url",
            return_value="https://t.me/example_support",
        ), patch(
            "miniapp_server._admin_contact_username",
            return_value="example_support",
        ), patch(
            "miniapp_server._admin_contact_user_id",
            return_value=101,
        ):
            payload = asyncio.run(_faq_payload())

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["question"], "Что такое сервис?")
        self.assertEqual(payload["items"][0]["link_url"], "https://vk.ru/@logisticsx-pricing")
        self.assertEqual(payload["items"][0]["button_label"], "Подробнее")
        self.assertEqual(payload["contact"]["url"], "https://t.me/example_support")
        self.assertEqual(payload["contact"]["username"], "example_support")
        self.assertEqual(payload["contact"]["user_id"], 101)

    def test_admin_faq_payload_returns_stats(self) -> None:
        faq_rows = [
            {
                "id": 1,
                "question": "Q1",
                "answer": "A1",
                "link_url": "",
                "button_label": "",
                "position": 1,
                "updated_at": 100.0,
            },
            {
                "id": 2,
                "question": "Q2",
                "answer": "A2",
                "link_url": "https://example.com/details",
                "button_label": "Подробнее",
                "position": 2,
                "updated_at": 200.0,
            },
        ]

        with patch(
            "miniapp_server.db.get_faq_entries",
            new=AsyncMock(return_value=faq_rows),
        ):
            payload = asyncio.run(_admin_faq_payload())

        self.assertEqual(payload["stats"]["total"], 2)
        self.assertEqual(payload["stats"]["latest_updated_at"], 200.0)
        self.assertEqual([item["id"] for item in payload["items"]], [1, 2])

    def test_admin_faq_save_payload_normalizes_create_flow(self) -> None:
        saved_entry = {
            "id": 3,
            "question": "Новый вопрос",
            "answer": "Новый ответ",
            "link_url": "https://vk.ru/@logisticsx-pricing",
            "button_label": "Пройти обучение",
            "position": 3,
            "updated_at": 300.0,
        }

        with patch(
            "miniapp_server.db.save_faq_entry",
            new=AsyncMock(return_value=saved_entry),
        ) as save_mock, patch(
            "miniapp_server.db.get_faq_entries",
            new=AsyncMock(return_value=[saved_entry]),
        ):
            payload = asyncio.run(
                _admin_faq_save_payload(
                    {
                        "id": 0,
                        "question": "Новый вопрос",
                        "answer": "Новый ответ",
                        "link_url": "https://vk.ru/@logisticsx-pricing",
                        "button_label": "Пройти обучение",
                    }
                )
            )

        save_mock.assert_awaited_once_with(
            0,
            "Новый вопрос",
            "Новый ответ",
            "https://vk.ru/@logisticsx-pricing",
            "Пройти обучение",
        )
        self.assertEqual(payload["stats"]["total"], 1)
        self.assertEqual(payload["items"][0]["id"], 3)

    def test_admin_faq_delete_payload_removes_entry(self) -> None:
        delete_mock = AsyncMock()

        with patch(
            "miniapp_server.db.delete_faq_entry",
            new=delete_mock,
        ), patch(
            "miniapp_server.db.get_faq_entries",
            new=AsyncMock(return_value=[]),
        ):
            payload = asyncio.run(_admin_faq_delete_payload({"id": 4}))

        delete_mock.assert_awaited_once_with(4)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["stats"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
