from base64 import b64encode
import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode

from auth import (
    get_user_id_from_init_data,
    get_user_id_from_vk_launch_params,
    get_user_profile_from_init_data,
    get_user_profile_from_vk_launch_params,
)


TEST_BOT_TOKEN = "test-bot-token"
TEST_VK_SECURE_KEY = "test-vk-secure-key"


def build_signed_init_data(
    user_id: int,
    bot_token: str = TEST_BOT_TOKEN,
    *,
    username: str = "",
    first_name: str = "Admin",
    last_name: str = "",
) -> str:
    payload = {
        "auth_date": "1710000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(payload.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode(),
        hashlib.sha256,
    ).digest()
    payload["hash"] = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(payload)


def build_signed_vk_launch_params(
    user_id: int,
    secure_key: str = TEST_VK_SECURE_KEY,
    *,
    app_id: int = 6736218,
    platform: str = "desktop_web",
) -> str:
    payload = {
        "vk_app_id": str(app_id),
        "vk_are_notifications_enabled": "0",
        "vk_is_app_user": "1",
        "vk_language": "ru",
        "vk_platform": platform,
        "vk_user_id": str(user_id),
    }
    payload["sign"] = b64encode(
        hmac.new(
            secure_key.encode(),
            urlencode(payload, doseq=True).encode(),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8").rstrip("=").replace("+", "-").replace("/", "_")
    return urlencode(payload)


class GetUserIdFromInitDataTests(unittest.TestCase):
    def test_resolves_trusted_user_id_from_signed_init_data(self) -> None:
        raw_init_data = build_signed_init_data(424242)

        self.assertEqual(
            get_user_id_from_init_data(raw_init_data, bot_token=TEST_BOT_TOKEN),
            424242,
        )

    def test_rejects_missing_hash_instead_of_falling_back(self) -> None:
        with self.assertRaises(ValueError):
            get_user_id_from_init_data("auth_date=1710000000&user=%7B%7D", bot_token=TEST_BOT_TOKEN)

    def test_resolves_trusted_user_profile_from_signed_init_data(self) -> None:
        raw_init_data = build_signed_init_data(
            777888,
            username="logistics_buyer",
            first_name="Ivan",
            last_name="Petrov",
        )

        self.assertEqual(
            get_user_profile_from_init_data(raw_init_data, bot_token=TEST_BOT_TOKEN),
            {
                "id": 777888,
                "username": "logistics_buyer",
                "first_name": "Ivan",
                "last_name": "Petrov",
            },
        )

    def test_resolves_trusted_vk_user_id_from_signed_launch_params(self) -> None:
        raw_launch_params = build_signed_vk_launch_params(424242)

        self.assertEqual(
            get_user_id_from_vk_launch_params(raw_launch_params, secure_key=TEST_VK_SECURE_KEY),
            424242,
        )

    def test_rejects_vk_launch_params_with_invalid_sign(self) -> None:
        raw_launch_params = build_signed_vk_launch_params(424242) + "broken"

        with self.assertRaises(ValueError):
            get_user_id_from_vk_launch_params(raw_launch_params, secure_key=TEST_VK_SECURE_KEY)

    def test_resolves_vk_profile_shape_from_signed_launch_params(self) -> None:
        raw_launch_params = build_signed_vk_launch_params(777888)

        self.assertEqual(
            get_user_profile_from_vk_launch_params(raw_launch_params, secure_key=TEST_VK_SECURE_KEY),
            {
                "id": 777888,
                "username": "",
                "first_name": "",
                "last_name": "",
            },
        )


if __name__ == "__main__":
    unittest.main()
