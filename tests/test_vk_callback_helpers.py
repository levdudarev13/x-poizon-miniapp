import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import (
    _build_vk_welcome_text,
    _extract_vk_callback_message,
    _handle_vk_message_new,
    _vk_event_group_matches,
    _vk_event_requires_secret,
    _vk_event_secret_matches,
)


class VkCallbackHelperTests(unittest.TestCase):
    def test_group_check_uses_configured_group_id(self) -> None:
        payload = {"group_id": 237541568}

        with patch("miniapp_server.VK_GROUP_ID", 237541568):
            self.assertTrue(_vk_event_group_matches(payload))
            self.assertFalse(_vk_event_group_matches({"group_id": 1}))

    def test_secret_check_uses_callback_secret(self) -> None:
        with patch("miniapp_server.VK_CALLBACK_SECRET", "secret123"):
            self.assertTrue(_vk_event_secret_matches({"secret": "secret123"}))
            self.assertFalse(_vk_event_secret_matches({"secret": "wrong"}))

    def test_confirmation_event_does_not_require_secret(self) -> None:
        self.assertFalse(_vk_event_requires_secret("confirmation"))
        self.assertTrue(_vk_event_requires_secret("message_new"))

    def test_extract_vk_message_supports_nested_callback_payload(self) -> None:
        payload = {
            "type": "message_new",
            "object": {
                "message": {
                    "from_id": 55,
                    "peer_id": 55,
                    "text": "start",
                }
            },
        }

        self.assertEqual(
            _extract_vk_callback_message(payload),
            {"from_id": 55, "peer_id": 55, "text": "start"},
        )

    def test_build_vk_welcome_text_includes_mini_app_url(self) -> None:
        with patch("miniapp_server.VK_MINI_APP_URL", "https://app.poizon-x.site"):
            message = _build_vk_welcome_text()

        self.assertIn("https://app.poizon-x.site", message)
        self.assertIn("Бот VK подключен.", message)

    def test_handle_vk_message_new_registers_platform_user_and_sends_reply(self) -> None:
        payload = {
            "type": "message_new",
            "object": {
                "message": {
                    "from_id": 123,
                    "peer_id": 123,
                    "text": "Привет",
                }
            },
        }

        with patch(
            "miniapp_server.db.get_or_create_platform_user",
            new=AsyncMock(return_value={"user_id": 1}),
        ) as get_or_create_platform_user, patch(
            "miniapp_server._send_vkontakte_message",
            new=AsyncMock(return_value=True),
        ) as send_vkontakte_message, patch(
            "miniapp_server._build_vk_welcome_text",
            return_value="VK ready",
        ):
            asyncio.run(_handle_vk_message_new(payload))

        get_or_create_platform_user.assert_awaited_once_with("vk", "123")
        send_vkontakte_message.assert_awaited_once_with(123, "VK ready")

    def test_handle_vk_message_new_ignores_group_chats(self) -> None:
        payload = {
            "type": "message_new",
            "object": {
                "message": {
                    "from_id": 123,
                    "peer_id": 2_000_000_123,
                    "text": "Привет",
                }
            },
        }

        with patch(
            "miniapp_server.db.get_or_create_platform_user",
            new=AsyncMock(),
        ) as get_or_create_platform_user, patch(
            "miniapp_server._send_vkontakte_message",
            new=AsyncMock(),
        ) as send_vkontakte_message:
            asyncio.run(_handle_vk_message_new(payload))

        get_or_create_platform_user.assert_not_awaited()
        send_vkontakte_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
