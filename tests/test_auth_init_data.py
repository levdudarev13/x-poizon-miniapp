import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode

from auth import get_user_id_from_init_data, get_user_profile_from_init_data


TEST_BOT_TOKEN = "test-bot-token"


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


if __name__ == "__main__":
    unittest.main()
