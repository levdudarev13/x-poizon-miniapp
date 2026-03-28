import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import _admin_avatar_bytes, _admin_avatar_cache, _admin_carts_payload


class _FakeHttpxResponse:
    def __init__(self, *, json_data=None, content=b"", headers=None) -> None:
        self._json_data = json_data
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._json_data


class _FakeHttpxClient:
    def __init__(self, responses: list[_FakeHttpxResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params=None):
        self.calls.append((url, params))
        if not self.responses:
            raise AssertionError("Unexpected extra HTTP request")
        return self.responses.pop(0)


class AdminCartsHelpersTests(unittest.TestCase):
    def tearDown(self) -> None:
        _admin_avatar_cache.clear()

    def test_admin_carts_payload_groups_users_and_sums_stats(self) -> None:
        rows = [
            {
                "user_id": 101,
                "username": "alpha",
                "calc_id": 11,
                "name": "Product A",
                "short_name": "Alpha A",
                "product_url": "https://example.com/a",
                "price_cny": 1200,
                "subtotal_rub": 15250,
                "total_with_margin_rub": 15250,
                "platform": "poizon",
                "calc_json": json.dumps({
                    "product": {
                        "image_url": "https://img.example.com/a.jpg",
                        "selected_variants": [{"label": "Размер", "value": "42"}],
                    },
                    "breakdown": [{"label": "Товар", "amount_rub": 14160}],
                }),
                "in_order": 0,
            },
            {
                "user_id": 101,
                "username": "alpha",
                "calc_id": 12,
                "name": "Product B",
                "short_name": "",
                "product_url": "https://example.com/b",
                "price_cny": 980,
                "subtotal_rub": 12400,
                "total_with_margin_rub": 12400,
                "platform": "taobao",
                "calc_json": json.dumps({
                    "exchange_rate": {"cny_rub": 12.5},
                }),
                "in_order": 1,
            },
            {
                "user_id": 202,
                "username": "",
                "calc_id": 21,
                "name": "Product C",
                "short_name": "Client C",
                "product_url": "",
                "price_cny": 640,
                "subtotal_rub": 8800,
                "total_with_margin_rub": 9100,
                "platform": "1688",
                "calc_json": "",
                "in_order": 0,
            },
        ]

        with patch(
            "miniapp_server.db.cart_get_all_carts",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_carts_payload())

        required_stats_keys = {
            "users_total",
            "items_total",
            "total_with_margin_rub",
        }
        required_item_keys = {
            "platform",
            "product_url",
            "image_url",
            "selected_variants",
            "total_with_margin_rub",
        }

        self.assertTrue(required_stats_keys.issubset(payload["stats"].keys()))
        self.assertEqual(payload["stats"]["users_total"], 2)
        self.assertEqual(payload["stats"]["items_total"], 3)
        self.assertEqual(payload["stats"]["items_in_order"], 1)
        self.assertEqual(payload["stats"]["total_with_margin_rub"], 36750.0)

        first_user = payload["users"][0]
        self.assertEqual(first_user["user_id"], 101)
        self.assertEqual(first_user["display_name"], "@alpha")
        self.assertEqual(first_user["contact_label"], "@alpha")
        self.assertEqual(first_user["total_items"], 2)
        self.assertEqual(first_user["items_in_order"], 1)
        self.assertEqual(first_user["total_with_margin_rub"], 27650.0)
        self.assertEqual(first_user["items"][0]["platform"], "poizon")
        self.assertEqual(first_user["items"][0]["product_url"], "https://example.com/a")
        self.assertEqual(first_user["items"][0]["total_with_margin_rub"], 15250.0)
        self.assertEqual(first_user["items"][1]["calc_id"], 12)
        self.assertTrue(first_user["items"][1]["in_order"])
        self.assertEqual(first_user["items"][1]["platform"], "taobao")
        self.assertEqual(first_user["items"][1]["product_url"], "https://example.com/b")
        self.assertEqual(first_user["items"][1]["total_with_margin_rub"], 12400.0)
        self.assertEqual(first_user["items"][0]["image_url"], "https://img.example.com/a.jpg")
        self.assertEqual(first_user["items"][0]["selected_variants"], [{"label": "Размер", "value": "42"}])
        self.assertEqual(first_user["items"][1]["selected_variants"], [])
        self.assertEqual(first_user["items"][0]["goods_rub"], 14160.0)
        self.assertEqual(first_user["items"][1]["goods_rub"], 12250.0)

        second_user = payload["users"][1]
        self.assertEqual(second_user["display_name"], "Пользователь #202")
        self.assertEqual(second_user["contact_label"], "id:202")
        self.assertEqual(second_user["items_in_order"], 0)
        self.assertEqual(second_user["total_with_margin_rub"], 9100.0)
        self.assertEqual(second_user["items"][0]["short_name"], "Client C")
        self.assertEqual(second_user["items"][0]["platform"], "1688")
        self.assertEqual(second_user["items"][0]["product_url"], "")
        self.assertEqual(second_user["items"][0]["total_with_margin_rub"], 9100.0)
        self.assertEqual(second_user["items"][0]["image_url"], "")
        self.assertEqual(second_user["items"][0]["selected_variants"], [])
        for user in payload["users"]:
            for item in user["items"]:
                self.assertTrue(required_item_keys.issubset(item.keys()))

    def test_admin_carts_payload_handles_empty_state(self) -> None:
        with patch(
            "miniapp_server.db.cart_get_all_carts",
            new=AsyncMock(return_value=[]),
        ):
            payload = asyncio.run(_admin_carts_payload())

        self.assertEqual(payload["users"], [])
        self.assertEqual(payload["stats"]["users_total"], 0)
        self.assertEqual(payload["stats"]["items_total"], 0)
        self.assertEqual(payload["stats"]["items_in_order"], 0)
        self.assertEqual(payload["stats"]["total_with_margin_rub"], 0.0)

    def test_admin_avatar_bytes_downloads_avatar_via_telegram_api(self) -> None:
        fake_client = _FakeHttpxClient([
            _FakeHttpxResponse(json_data={
                "ok": True,
                "result": {
                    "photos": [[
                        {"file_id": "small"},
                        {"file_id": "large"},
                    ]],
                },
            }),
            _FakeHttpxResponse(json_data={
                "ok": True,
                "result": {
                    "file_path": "photos/file_0.jpg",
                },
            }),
            _FakeHttpxResponse(
                content=b"avatar-bytes",
                headers={"content-type": "image/jpeg; charset=binary"},
            ),
        ])

        with patch("miniapp_server.BOT_TOKEN", "test-token"), patch(
            "miniapp_server.httpx.AsyncClient",
            return_value=fake_client,
        ):
            payload = asyncio.run(_admin_avatar_bytes(777))

        self.assertEqual(payload, ("image/jpeg", b"avatar-bytes"))
        self.assertEqual(len(fake_client.calls), 3)
        self.assertIn(777, _admin_avatar_cache)

    def test_admin_avatar_bytes_caches_missing_avatar(self) -> None:
        fake_client = _FakeHttpxClient([
            _FakeHttpxResponse(json_data={
                "ok": True,
                "result": {
                    "photos": [],
                },
            }),
        ])

        with patch("miniapp_server.BOT_TOKEN", "test-token"), patch(
            "miniapp_server.httpx.AsyncClient",
            return_value=fake_client,
        ):
            self.assertIsNone(asyncio.run(_admin_avatar_bytes(888)))
            self.assertIsNone(asyncio.run(_admin_avatar_bytes(888)))

        self.assertEqual(len(fake_client.calls), 1)
        self.assertIn(888, _admin_avatar_cache)


if __name__ == "__main__":
    unittest.main()
