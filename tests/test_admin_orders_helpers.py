import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import _admin_orders_payload, _admin_orders_update_payload


class AdminOrdersHelpersTests(unittest.TestCase):
    def test_admin_orders_payload_groups_users_and_builds_statuses(self) -> None:
        rows = [
            {
                "user_id": 101,
                "username": "alpha",
                "calc_id": 11,
                "paid": 0,
                "shipped": 0,
                "arrived": 0,
                "tracking_number": "",
                "item_number": "501",
                "order_submitted": 1,
                "delivery_snapshot_json": json.dumps({
                    "recipient_name": "Alice Example",
                    "phone": "+7 999 000-00-00",
                    "city": "Moscow",
                    "street": "Tverskaya",
                    "house": "7B",
                    "apartment": "",
                    "comment": "call first",
                }),
                "submission_batch_id": "sub-101-001",
                "submitted_at": "2026-03-20T09:15:00",
                "order_added_at": "2026-03-20 09:15:00",
                "name": "Product A",
                "short_name": "Alpha A",
                "product_url": "https://example.com/a",
                "price_cny": 1200,
                "subtotal_rub": 15250,
                "total_with_margin_rub": 16400,
                "platform": "poizon",
                "size": "38",
                "calc_json": json.dumps({
                    "product": {
                        "image_url": "https://img.example.com/a.jpg",
                        "size": "38",
                        "variants": [{"name": "Size", "options": ["37", "38", "39"]}],
                    },
                    "breakdown": [{"label": "Товар", "amount_rub": 14160}],
                }),
            },
            {
                "user_id": 101,
                "username": "alpha",
                "calc_id": 13,
                "paid": 0,
                "shipped": 0,
                "arrived": 0,
                "tracking_number": "",
                "item_number": "",
                "order_submitted": 0,
                "delivery_snapshot_json": "",
                "submission_batch_id": "",
                "submitted_at": "",
                "order_added_at": "2026-03-21 15:00:00",
                "name": "Draft Product",
                "short_name": "",
                "product_url": "https://example.com/draft",
                "price_cny": 1500,
                "subtotal_rub": 17000,
                "total_with_margin_rub": 18200,
                "platform": "poizon",
                "size": "",
                "calc_json": "",
            },
            {
                "user_id": 101,
                "username": "alpha",
                "calc_id": 12,
                "paid": 1,
                "shipped": 0,
                "arrived": 0,
                "tracking_number": "CDEK-778899",
                "item_number": "",
                "order_submitted": 1,
                "delivery_snapshot_json": json.dumps({
                    "recipient_name": "Alice Example",
                    "phone": "+7 999 000-00-00",
                    "city": "Moscow",
                    "street": "Tverskaya",
                    "house": "7B",
                    "apartment": "14",
                    "comment": "call first",
                }),
                "submission_batch_id": "sub-101-002",
                "submitted_at": "2026-03-20T12:31:00",
                "order_added_at": "2026-03-20 12:30:00",
                "name": "Product B",
                "short_name": "",
                "product_url": "https://example.com/b",
                "price_cny": 980,
                "subtotal_rub": 12400,
                "total_with_margin_rub": 13600,
                "platform": "taobao",
                "size": "",
                "calc_json": json.dumps({
                    "exchange_rate": {"cny_rub": 12.5},
                }),
            },
            {
                "user_id": 202,
                "username": "",
                "calc_id": 21,
                "paid": 1,
                "shipped": 1,
                "arrived": 0,
                "tracking_number": "",
                "item_number": "",
                "order_submitted": 1,
                "delivery_snapshot_json": json.dumps({
                    "recipient_name": "",
                    "phone": "",
                    "city": "",
                    "street": "",
                    "house": "",
                    "apartment": "",
                    "comment": "",
                }),
                "submission_batch_id": "",
                "submitted_at": "",
                "order_added_at": "2026-03-19 18:00:00",
                "name": "Product C",
                "short_name": "Client C",
                "product_url": "",
                "price_cny": 640,
                "subtotal_rub": 8800,
                "total_with_margin_rub": 9100,
                "platform": "1688",
                "size": "",
                "calc_json": "",
            },
        ]

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_orders_payload())

        required_item_keys = {
            "delivery_data",
            "delivery_complete",
            "item_number",
            "selected_variants",
            "size_text",
            "submission_batch_id",
            "submitted_at",
            "status_key",
            "tracking_number",
        }

        self.assertEqual(payload["stats"]["users_total"], 2)
        self.assertEqual(payload["stats"]["items_total"], 3)
        self.assertEqual(payload["stats"]["pending_items"], 1)
        self.assertEqual(payload["stats"]["submitted_items"], 3)
        self.assertEqual(payload["stats"]["paid_items"], 2)
        self.assertEqual(payload["stats"]["shipped_items"], 1)
        self.assertEqual(payload["stats"]["arrived_items"], 0)
        self.assertEqual(payload["stats"]["total_with_margin_rub"], 39100.0)
        self.assertEqual(payload["stats"]["latest_order_added_at_label"], "20.03.2026 в 12:30")

        first_user = payload["users"][0]
        self.assertEqual(first_user["user_id"], 101)
        self.assertEqual(first_user["display_name"], "@alpha")
        self.assertEqual(first_user["total_items"], 2)
        self.assertEqual(first_user["pending_items"], 1)
        self.assertEqual(first_user["submitted_items"], 2)
        self.assertEqual(first_user["paid_items"], 1)
        self.assertEqual(first_user["latest_order_added_at_label"], "20.03.2026 в 12:30")
        self.assertEqual([item["calc_id"] for item in first_user["items"]], [12, 11])
        self.assertIn("delivery_data", first_user["items"][0])
        self.assertEqual(first_user["items"][0]["status_key"], "paid")
        self.assertEqual(first_user["items"][0]["tracking_number"], "CDEK-778899")
        self.assertEqual(first_user["items"][0]["item_number"], "")
        self.assertEqual(first_user["items"][0]["selected_variants"], [])
        self.assertEqual(first_user["items"][0]["size_text"], "")
        self.assertEqual(first_user["items"][0]["delivery_data"]["city"], "Moscow")
        self.assertTrue(first_user["items"][0]["delivery_complete"])
        self.assertEqual(first_user["items"][0]["submission_batch_id"], "sub-101-002")
        self.assertEqual(first_user["items"][0]["submitted_at"], "2026-03-20T12:31:00")
        self.assertIn("delivery_data", first_user["items"][1])
        self.assertEqual(first_user["items"][1]["status_key"], "submitted")
        self.assertEqual(first_user["items"][1]["tracking_number"], "")
        self.assertEqual(first_user["items"][1]["item_number"], "501")
        self.assertEqual(
            first_user["items"][1]["selected_variants"],
            [{"label": "Size", "value": "38"}],
        )
        self.assertEqual(first_user["items"][1]["size_text"], "38")
        self.assertEqual(first_user["items"][1]["delivery_data"]["street"], "Tverskaya")
        self.assertTrue(first_user["items"][1]["delivery_complete"])
        self.assertEqual(first_user["items"][1]["submission_batch_id"], "sub-101-001")
        self.assertEqual(first_user["items"][1]["submitted_at"], "2026-03-20T09:15:00")
        self.assertEqual(first_user["items"][1]["image_url"], "https://img.example.com/a.jpg")
        self.assertEqual(first_user["items"][1]["goods_rub"], 14160.0)
        self.assertEqual(first_user["items"][0]["goods_rub"], 12250.0)
        for user in payload["users"]:
            for item in user["items"]:
                self.assertTrue(required_item_keys.issubset(item.keys()))

        second_user = payload["users"][1]
        self.assertEqual(second_user["display_name"], "Пользователь #202")
        self.assertEqual(second_user["contact_label"], "id:202")
        self.assertEqual(second_user["items"][0]["status_key"], "shipped")
        self.assertIn("delivery_data", second_user["items"][0])
        self.assertIn("delivery_complete", second_user["items"][0])
        self.assertIn("submission_batch_id", second_user["items"][0])
        self.assertIn("submitted_at", second_user["items"][0])
        self.assertFalse(second_user["items"][0]["delivery_complete"])

    def test_admin_orders_payload_prefers_explicit_selected_variants_from_calc_json(self) -> None:
        rows = [
            {
                "user_id": 505,
                "username": "variant-user",
                "calc_id": 88,
                "paid": 0,
                "shipped": 0,
                "arrived": 0,
                "tracking_number": "",
                "item_number": "",
                "order_submitted": 1,
                "delivery_snapshot_json": json.dumps({
                    "recipient_name": "Variant User",
                    "phone": "+7 999 123-45-67",
                    "city": "Moscow",
                    "street": "Tverskaya",
                    "house": "1",
                    "apartment": "",
                    "comment": "",
                }),
                "submission_batch_id": "sub-505-001",
                "submitted_at": "2026-03-25T10:10:10",
                "order_added_at": "2026-03-25 10:10:00",
                "name": "Configurable Product",
                "short_name": "Configurable Product",
                "product_url": "https://example.com/configurable",
                "price_cny": 888,
                "subtotal_rub": 12000,
                "total_with_margin_rub": 12800,
                "platform": "poizon",
                "size": "",
                "calc_json": json.dumps({
                    "selected_variants": [
                        {"label": "Цвет", "value": "Синий"},
                        {"label": "Вариант", "value": "Pro"},
                    ],
                }),
            },
        ]

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_orders_payload())

        item = payload["users"][0]["items"][0]
        self.assertEqual(
            item["selected_variants"],
            [
                {"label": "Цвет", "value": "Синий"},
                {"label": "Вариант", "value": "Pro"},
            ],
        )
        self.assertEqual(item["size_text"], "")

    def test_admin_orders_payload_handles_empty_state(self) -> None:
        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[]),
        ):
            payload = asyncio.run(_admin_orders_payload())

        self.assertEqual(payload["users"], [])
        self.assertEqual(payload["stats"]["users_total"], 0)
        self.assertEqual(payload["stats"]["items_total"], 0)
        self.assertEqual(payload["stats"]["pending_items"], 0)
        self.assertEqual(payload["stats"]["latest_order_added_at_label"], "—")

    def test_admin_orders_payload_keeps_latest_batch_snapshot_metadata_stable(self) -> None:
        old_snapshot = {
            "recipient_name": "Alice Example",
            "phone": "+7 999 000-00-00",
            "city": "Moscow",
            "street": "Arbat",
            "house": "7B",
            "apartment": "",
            "comment": "old gate",
        }
        latest_snapshot = {
            "recipient_name": "Alice Example",
            "phone": "+7 999 000-00-00",
            "city": "Saint Petersburg",
            "street": "Nevsky",
            "house": "9A",
            "apartment": "12",
            "comment": "",
        }

        def build_row(
            calc_id: int,
            *,
            order_added_at: str,
            order_submitted: int,
            delivery_snapshot: dict | None,
            submission_batch_id: str,
            submitted_at: str,
        ) -> dict:
            return {
                "user_id": 303,
                "username": "batch-user",
                "calc_id": calc_id,
                "paid": 0,
                "shipped": 0,
                "arrived": 0,
                "tracking_number": "",
                "item_number": "",
                "order_submitted": order_submitted,
                "delivery_snapshot_json": json.dumps(delivery_snapshot) if delivery_snapshot is not None else "",
                "submission_batch_id": submission_batch_id,
                "submitted_at": submitted_at,
                "order_added_at": order_added_at,
                "name": f"Product {calc_id}",
                "short_name": "",
                "product_url": f"https://example.com/{calc_id}",
                "price_cny": 500,
                "subtotal_rub": 7500,
                "total_with_margin_rub": 8100,
                "platform": "poizon",
                "size": "",
                "calc_json": "",
            }

        rows = [
            build_row(
                34,
                order_added_at="2026-03-22 18:00:00",
                order_submitted=0,
                delivery_snapshot=None,
                submission_batch_id="",
                submitted_at="",
            ),
            build_row(
                31,
                order_added_at="2026-03-21 15:00:00",
                order_submitted=1,
                delivery_snapshot=old_snapshot,
                submission_batch_id="sub-303-001",
                submitted_at="2026-03-21T08:00:00",
            ),
            build_row(
                32,
                order_added_at="2026-03-20 11:00:00",
                order_submitted=1,
                delivery_snapshot=latest_snapshot,
                submission_batch_id="sub-303-002",
                submitted_at="2026-03-21T12:45:00",
            ),
            build_row(
                33,
                order_added_at="2026-03-19 09:00:00",
                order_submitted=1,
                delivery_snapshot=latest_snapshot,
                submission_batch_id="sub-303-002",
                submitted_at="2026-03-21T12:45:00",
            ),
        ]

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=rows),
        ):
            payload = asyncio.run(_admin_orders_payload())

        user = payload["users"][0]
        self.assertEqual(user["user_id"], 303)
        self.assertEqual([item["calc_id"] for item in user["items"]], [31, 32, 33])
        self.assertEqual(user["total_items"], 3)
        self.assertEqual(user["pending_items"], 3)
        self.assertIn("21.03.2026", user["latest_order_added_at_label"])
        self.assertTrue(user["latest_order_added_at_label"].endswith("15:00"))
        self.assertEqual(user["items"][0]["delivery_data"]["house"], "7B")
        self.assertEqual(user["items"][0]["submission_batch_id"], "sub-303-001")
        self.assertEqual(user["items"][0]["submitted_at"], "2026-03-21T08:00:00")

        latest_submission = max(
            (
                (item["submitted_at"], item["submission_batch_id"])
                for item in user["items"]
                if item["submitted_at"] and item["submission_batch_id"]
            )
        )
        latest_batch_items = [
            item
            for item in user["items"]
            if (item["submitted_at"], item["submission_batch_id"]) == latest_submission
        ]

        self.assertEqual(latest_submission, ("2026-03-21T12:45:00", "sub-303-002"))
        self.assertEqual([item["calc_id"] for item in latest_batch_items], [32, 33])
        self.assertTrue(all(item["delivery_complete"] for item in latest_batch_items))
        self.assertEqual(
            [item["submission_batch_id"] for item in latest_batch_items],
            ["sub-303-002", "sub-303-002"],
        )
        self.assertEqual(
            [item["submitted_at"] for item in latest_batch_items],
            ["2026-03-21T12:45:00", "2026-03-21T12:45:00"],
        )
        self.assertEqual(
            [item["delivery_data"] for item in latest_batch_items],
            [latest_snapshot, latest_snapshot],
        )
        self.assertEqual(user["items"][1]["delivery_data"]["city"], "Saint Petersburg")
        self.assertNotEqual(
            user["items"][0]["submission_batch_id"],
            latest_batch_items[0]["submission_batch_id"],
        )

    def test_admin_orders_update_payload_marks_paid_and_returns_fresh_payload(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 0,
            "shipped": 0,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }
        set_paid = AsyncMock()
        notify = AsyncMock()
        refreshed_payload = {"users": [{"user_id": 101}], "stats": {"items_total": 1}}

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ), patch(
            "miniapp_server.db.cart_set_paid",
            new=set_paid,
        ), patch(
            "miniapp_server._notify_admin_order_action",
            new=notify,
        ), patch(
            "miniapp_server._admin_orders_payload",
            new=AsyncMock(return_value=refreshed_payload),
        ):
            payload = asyncio.run(_admin_orders_update_payload({
                "action": "mark_paid",
                "user_id": 101,
                "calc_id": 11,
            }))

        set_paid.assert_awaited_once_with(101, 11, True)
        notify.assert_awaited_once_with("mark_paid", row)
        self.assertEqual(payload, refreshed_payload)

    def test_admin_orders_update_payload_sets_tracking_number(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 1,
            "shipped": 1,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }
        set_tracking_number = AsyncMock()
        notify = AsyncMock()
        refreshed_payload = {"users": [{"user_id": 101}], "stats": {"items_total": 1}}

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ), patch(
            "miniapp_server.db.cart_set_tracking_number",
            new=set_tracking_number,
        ), patch(
            "miniapp_server._notify_admin_order_action",
            new=notify,
        ), patch(
            "miniapp_server._admin_orders_payload",
            new=AsyncMock(return_value=refreshed_payload),
        ):
            payload = asyncio.run(_admin_orders_update_payload({
                "action": "set_tracking",
                "user_id": 101,
                "calc_id": 11,
                "tracking_number": "CDEK-123456",
            }))

        set_tracking_number.assert_awaited_once_with(101, 11, "CDEK-123456")
        notify.assert_awaited_once_with("set_tracking", {**row, "tracking_number": "CDEK-123456"})
        self.assertEqual(payload, refreshed_payload)

    def test_admin_orders_update_payload_sets_item_number(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 1,
            "shipped": 1,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }
        set_item_number = AsyncMock()
        refreshed_payload = {"users": [{"user_id": 101}], "stats": {"items_total": 1}}

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ), patch(
            "miniapp_server.db.cart_set_item_number",
            new=set_item_number,
        ), patch(
            "miniapp_server._admin_orders_payload",
            new=AsyncMock(return_value=refreshed_payload),
        ):
            payload = asyncio.run(_admin_orders_update_payload({
                "action": "set_item_number",
                "user_id": 101,
                "calc_id": 11,
                "item_number": "#295A",
            }))

        set_item_number.assert_awaited_once_with(101, 11, "295A")
        self.assertEqual(payload, refreshed_payload)

    def test_admin_orders_update_payload_rejects_missing_tracking_number(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 1,
            "shipped": 1,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ):
            with self.assertRaises(ValueError):
                asyncio.run(_admin_orders_update_payload({
                    "action": "set_tracking",
                    "user_id": 101,
                    "calc_id": 11,
                    "tracking_number": "   ",
                }))

    def test_admin_orders_update_payload_rejects_missing_item_number(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 1,
            "shipped": 1,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ):
            with self.assertRaises(ValueError):
                asyncio.run(_admin_orders_update_payload({
                    "action": "set_item_number",
                    "user_id": 101,
                    "calc_id": 11,
                    "item_number": "   ",
                }))

    def test_admin_orders_update_payload_rejects_unknown_action(self) -> None:
        row = {
            "user_id": 101,
            "username": "alpha",
            "calc_id": 11,
            "paid": 0,
            "shipped": 0,
            "arrived": 0,
            "tracking_number": "",
            "item_number": "",
            "order_submitted": 1,
            "order_added_at": "2026-03-20 09:15:00",
            "name": "Product A",
            "short_name": "Alpha A",
            "product_url": "https://example.com/a",
            "price_cny": 1200,
            "subtotal_rub": 15250,
            "total_with_margin_rub": 16400,
            "platform": "poizon",
            "size": "",
            "calc_json": "",
        }

        with patch(
            "miniapp_server.db.cart_get_all_orders",
            new=AsyncMock(return_value=[row]),
        ):
            with self.assertRaises(ValueError):
                asyncio.run(_admin_orders_update_payload({
                    "action": "unknown",
                    "user_id": 101,
                    "calc_id": 11,
                }))


if __name__ == "__main__":
    unittest.main()
