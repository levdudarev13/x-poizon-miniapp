import asyncio
import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

from miniapp_server import _bootstrap_payload, _resolve_bootstrap_identity


TEST_BOT_TOKEN = "test-bot-token"


def build_signed_init_data(user_id: int, bot_token: str = TEST_BOT_TOKEN) -> str:
    payload = {
        "auth_date": "1710000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {"id": user_id, "first_name": "Admin"},
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


class BootstrapIdentityTests(unittest.TestCase):
    def test_query_only_identity_never_sets_admin(self) -> None:
        self.assertEqual(
            _resolve_bootstrap_identity(321, "", bot_token=TEST_BOT_TOKEN),
            (321, False),
        )

    def test_signed_init_data_uses_trusted_identity_and_admin_check(self) -> None:
        raw_init_data = build_signed_init_data(999001)

        with patch("miniapp_server.is_admin", return_value=True) as is_admin_mock:
            self.assertEqual(
                _resolve_bootstrap_identity(321, raw_init_data, bot_token=TEST_BOT_TOKEN),
                (999001, True),
            )

        is_admin_mock.assert_called_once_with(999001)

    def test_invalid_init_data_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_bootstrap_identity(None, "broken=payload", bot_token=TEST_BOT_TOKEN)

    def test_bootstrap_payload_uses_explicit_is_admin_flag(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )

        with patch("miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={"commission_pct": "10.0"}),
        ), patch(
            "miniapp_server.db.get_or_create_user",
            new=AsyncMock(
                return_value={
                    "margin_steps": "[]",
                    "margin_min_rub": "500.0",
                }
            ),
        ), patch(
            "miniapp_server._showcase_payload",
            new=AsyncMock(return_value={"items": [], "configured_count": 0}),
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=True))

        self.assertIs(payload["is_admin"], True)

    def test_bootstrap_payload_includes_admin_contact_url(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )

        with patch("miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={"commission_pct": "10.0"}),
        ), patch(
            "miniapp_server.db.get_or_create_user",
            new=AsyncMock(
                return_value={
                    "margin_steps": "[]",
                    "margin_min_rub": "500.0",
                }
            ),
        ), patch(
            "miniapp_server.ADMIN_USERNAME",
            "china_bayer2",
        ), patch(
            "miniapp_server.ADMIN_USER_ID",
            777001,
        ), patch(
            "miniapp_server._showcase_payload",
            new=AsyncMock(return_value={"items": [], "configured_count": 0}),
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["admin_contact_url"], "https://t.me/china_bayer2")
        self.assertEqual(payload["admin_contact_username"], "china_bayer2")
        self.assertEqual(payload["admin_contact_user_id"], 777001)

    def test_bootstrap_payload_uses_effective_rate_for_display(self) -> None:
        rate = SimpleNamespace(
            cny_rub=12.38,
            usd_rub=90.0,
            eur_rub=98.0,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=2_100,
            age_human="35 РјРёРЅ. РЅР°Р·Р°Рґ",
        )

        with patch(
            "miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(
                return_value={
                    "commission_pct": "10.0",
                    "rate_override": "13",
                    "rate_override_until": "2000",
                }
            ),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server.time.time",
            return_value=1_500.0,
        ), patch(
            "miniapp_server._showcase_payload",
            new=AsyncMock(return_value={"items": [], "configured_count": 0}),
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["rate"]["cny_rub"], 13.0)
        self.assertEqual(payload["rate"]["age_human"], "\u0420\u0443\u0447\u043d\u043e\u0439 \u043a\u0443\u0440\u0441")
        self.assertEqual(payload["rate"]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
