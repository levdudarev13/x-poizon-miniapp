import asyncio
from base64 import b64encode
from contextlib import ExitStack
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


def patch_bootstrap_content_payloads() -> ExitStack:
    stack = ExitStack()
    stack.enter_context(
        patch(
            "miniapp_server._showcase_payload",
            new=AsyncMock(return_value={"items": [], "configured_count": 0}),
        )
    )
    stack.enter_context(
        patch(
            "miniapp_server._about_details_payload",
            new=AsyncMock(return_value={"items": []}),
        )
    )
    stack.enter_context(
        patch(
            "miniapp_server._promo_banners_payload",
            new=AsyncMock(return_value={"items": [], "entry_banner_id": 0}),
        )
    )
    stack.enter_context(
        patch(
            "miniapp_server._track_miniapp_activity",
            new=AsyncMock(return_value=None),
        )
    )
    return stack


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

    def test_signed_vk_launch_params_use_trusted_identity_without_admin(self) -> None:
        raw_launch_params = build_signed_vk_launch_params(585780201)

        with patch("miniapp_server.is_admin", return_value=True) as is_admin_mock:
            self.assertEqual(
                _resolve_bootstrap_identity(
                    None,
                    "",
                    raw_launch_params,
                    vk_secure_key=TEST_VK_SECURE_KEY,
                ),
                (585780201, False),
            )

        is_admin_mock.assert_not_called()

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

        with patch(
            "miniapp_server.er.get_rate",
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
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=True))

        self.assertIs(payload["is_admin"], True)

    def test_bootstrap_payload_persists_profile_from_signed_init_data(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )
        get_or_create_user = AsyncMock(
            return_value={
                "margin_steps": "[]",
                "margin_min_rub": "500.0",
                "username": "buyer404",
                "first_name": "Ivan",
                "last_name": "Petrov",
            }
        )

        with patch(
            "miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={"commission_pct": "10.0"}),
        ), patch(
            "miniapp_server.db.get_or_create_user",
            new=get_or_create_user,
        ), patch(
            "miniapp_server.get_user_profile_from_init_data",
            return_value={
                "id": 404,
                "username": "buyer404",
                "first_name": "Ivan",
                "last_name": "Petrov",
            },
        ), patch_bootstrap_content_payloads(
        ):
            asyncio.run(
                _bootstrap_payload(
                    404,
                    is_admin_user=False,
                    init_data_raw=build_signed_init_data(
                        404,
                        username="buyer404",
                        first_name="Ivan",
                        last_name="Petrov",
                    ),
                )
            )

        get_or_create_user.assert_awaited_once_with(404, "buyer404", "Ivan", "Petrov")

    def test_bootstrap_payload_maps_vk_platform_user_to_internal_user(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )
        get_or_create_platform_user = AsyncMock(
            return_value={
                "user_id": 7806888522,
                "margin_steps": "[]",
                "margin_min_rub": "500.0",
            }
        )

        with patch(
            "miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={"commission_pct": "10.0"}),
        ), patch(
            "miniapp_server.db.get_or_create_platform_user",
            new=get_or_create_platform_user,
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(
                _bootstrap_payload(
                    585780201,
                    is_admin_user=False,
                    auth_platform="vk",
                )
            )

        get_or_create_platform_user.assert_awaited_once_with(
            "vk",
            "585780201",
            "",
            "",
            "",
        )
        self.assertEqual(payload["user_id"], 7806888522)
        self.assertEqual(payload["platform_user_id"], 585780201)
        self.assertEqual(payload["launch_platform"], "vk")

    def test_bootstrap_payload_persists_vk_profile_identity_fields(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )
        get_or_create_platform_user = AsyncMock(
            return_value={
                "user_id": 7806888522,
                "margin_steps": "[]",
                "margin_min_rub": "500.0",
                "first_name": "Lev",
                "last_name": "Dumaet",
            }
        )

        with patch(
            "miniapp_server.er.get_rate",
            new=AsyncMock(return_value=rate),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={"commission_pct": "10.0"}),
        ), patch(
            "miniapp_server.db.get_or_create_platform_user",
            new=get_or_create_platform_user,
        ), patch_bootstrap_content_payloads(
        ):
            asyncio.run(
                _bootstrap_payload(
                    585780201,
                    is_admin_user=False,
                    auth_platform="vk",
                    vk_user_profile={
                        "id": 585780201,
                        "first_name": "Lev",
                        "last_name": "Dumaet",
                    },
                )
            )

        get_or_create_platform_user.assert_awaited_once_with(
            "vk",
            "585780201",
            "",
            "Lev",
            "Dumaet",
        )

    def test_bootstrap_payload_includes_admin_contact_url(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )

        with patch(
            "miniapp_server.er.get_rate",
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
            "miniapp_server.ADMIN_USER_IDS",
            (777001,),
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USER_ID",
            0,
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USERNAME",
            "",
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["admin_contact_url"], "https://t.me/china_bayer2")
        self.assertEqual(payload["admin_contact_username"], "china_bayer2")
        self.assertEqual(payload["admin_contact_user_id"], 777001)

    def test_bootstrap_payload_prefers_explicit_admin_contact_user_id(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )

        with patch(
            "miniapp_server.er.get_rate",
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
            "miniapp_server.ADMIN_USER_IDS",
            (777001, 1012099394),
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USER_ID",
            1012099394,
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USERNAME",
            "",
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["admin_contact_url"], "tg://user?id=1012099394")
        self.assertEqual(payload["admin_contact_username"], "")
        self.assertEqual(payload["admin_contact_user_id"], 1012099394)

    def test_bootstrap_payload_prefers_explicit_admin_contact_username(self) -> None:
        rate = SimpleNamespace(
            cny_rub=11.1,
            usd_rub=12.2,
            eur_rub=13.3,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=5,
            age_human="5s",
        )

        with patch(
            "miniapp_server.er.get_rate",
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
            "miniapp_server.ADMIN_USER_IDS",
            (777001, 1012099394),
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USER_ID",
            1012099394,
        ), patch(
            "miniapp_server.ADMIN_CONTACT_USERNAME",
            "sofa_onli",
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["admin_contact_url"], "https://t.me/sofa_onli")
        self.assertEqual(payload["admin_contact_username"], "sofa_onli")
        self.assertEqual(payload["admin_contact_user_id"], 1012099394)

    def test_bootstrap_payload_uses_effective_rate_for_display(self) -> None:
        rate = SimpleNamespace(
            cny_rub=12.38,
            usd_rub=90.0,
            eur_rub=98.0,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=2_100,
            age_human="35 мин. назад",
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
            "miniapp_server.db.get_or_create_user",
            new=AsyncMock(
                return_value={
                    "margin_steps": "[]",
                    "margin_min_rub": "500.0",
                }
            ),
        ), patch(
            "miniapp_server.time.time",
            return_value=1_500.0,
        ), patch_bootstrap_content_payloads(
        ):
            payload = asyncio.run(_bootstrap_payload(321, is_admin_user=False))

        self.assertEqual(payload["rate"]["cny_rub"], 13.0)
        self.assertEqual(payload["rate"]["age_human"], "\u0420\u0443\u0447\u043d\u043e\u0439 \u043a\u0443\u0440\u0441")
        self.assertEqual(payload["rate"]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
