import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import miniapp_server

from miniapp_server import (
    _normalize_delivery_payload,
    _save_delivery_profile_payload,
    _submit_order_payload,
)


class DeliveryProfileHelpersTests(unittest.TestCase):
    def test_normalize_delivery_payload_trims_and_preserves_exact_keys(self) -> None:
        payload = _normalize_delivery_payload(
            {
                "recipient_name": "  Alice Example  ",
                "phone": "  +7 999 000-00-00 ",
                "city": " Moscow ",
                "street": " Tverskaya ",
                "house": " 7B ",
                "apartment": " 14 ",
                "comment": " call first ",
                "ignored": "value",
            }
        )

        self.assertEqual(
            list(payload.keys()),
            [
                "recipient_name",
                "phone",
                "city",
                "street",
                "house",
                "apartment",
                "comment",
            ],
        )
        self.assertEqual(
            payload,
            {
                "recipient_name": "Alice Example",
                "phone": "+7 999 000-00-00",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "7B",
                "apartment": "14",
                "comment": "call first",
            },
        )

    def test_save_delivery_profile_payload_normalizes_and_reports_completion(self) -> None:
        saved_delivery = {
            "recipient_name": "Alice Example",
            "phone": "+7 999 000-00-00",
            "city": "Moscow",
            "street": "Tverskaya",
            "house": "7B",
            "apartment": "",
            "comment": "call first",
            "updated_at": "2026-03-24 18:00:00",
        }

        with patch(
            "miniapp_server.db.save_delivery_profile",
            new=AsyncMock(return_value=saved_delivery),
        ) as save_mock:
            payload = asyncio.run(
                _save_delivery_profile_payload(
                    {
                        "user_id": 42,
                        "delivery_data": {
                            "recipient_name": " Alice Example ",
                            "phone": " +7 999 000-00-00 ",
                            "city": " Moscow ",
                            "street": " Tverskaya ",
                            "house": " 7B ",
                            "apartment": " ",
                            "comment": " call first ",
                        },
                    }
                )
            )

        save_mock.assert_awaited_once_with(
            42,
            {
                "recipient_name": "Alice Example",
                "phone": "+7 999 000-00-00",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "7B",
                "apartment": "",
                "comment": "call first",
            },
        )
        self.assertTrue(payload["is_complete"])
        self.assertEqual(payload["delivery_data"]["city"], "Moscow")
        self.assertEqual(payload["updated_at"], "2026-03-24 18:00:00")

    def test_submit_order_payload_rejects_incomplete_delivery_profile(self) -> None:
        with patch(
            "miniapp_server.db.get_delivery_profile",
            new=AsyncMock(
                return_value={
                    "recipient_name": "Alice Example",
                    "phone": "+7 999 000-00-00",
                    "city": "",
                    "street": "Tverskaya",
                    "house": "7B",
                    "apartment": "",
                    "comment": "",
                    "updated_at": "2026-03-24 18:00:00",
                }
            ),
        ), patch(
            "miniapp_server.db.cart_apply_delivery_snapshot",
            new=AsyncMock(),
        ) as snapshot_mock, patch(
            "miniapp_server.db.cart_submit_order",
            new=AsyncMock(),
        ) as submit_mock:
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(_submit_order_payload({"user_id": 42}))

        self.assertEqual(str(ctx.exception), "delivery_data_incomplete")
        self.assertEqual(getattr(ctx.exception, "missing_required", None), ["city"])
        snapshot_mock.assert_not_awaited()
        submit_mock.assert_not_awaited()

    def test_submit_order_payload_stamps_batch_and_submitted_at(self) -> None:
        call_order: list[str] = []
        fixed_submitted_at = "2026-03-24T18:00:00"

        async def record_snapshot(*args):
            call_order.append("snapshot")

        async def record_submit(*args):
            call_order.append("submit")

        with patch(
            "miniapp_server.db.get_delivery_profile",
            new=AsyncMock(
                return_value={
                    "recipient_name": "Alice Example",
                    "phone": "+7 999 000-00-00",
                    "city": "Moscow",
                    "street": "Tverskaya",
                    "house": "7B",
                    "apartment": "14",
                    "comment": "call first",
                    "updated_at": "2026-03-24 18:00:00",
                }
            ),
        ), patch(
            "miniapp_server.db.cart_get_pending_order_items",
            new=AsyncMock(
                return_value=[
                    {"subtotal_rub": 1250.4},
                    {"subtotal_rub": 4000.0},
                ]
            ),
        ), patch(
            "miniapp_server.db.cart_apply_delivery_snapshot",
            new=AsyncMock(side_effect=record_snapshot),
        ) as snapshot_mock, patch(
            "miniapp_server.db.cart_submit_order",
            new=AsyncMock(side_effect=record_submit),
        ) as submit_mock, patch(
            "miniapp_server._dispatch_admin_order_submission_notification",
            new=MagicMock(side_effect=lambda **kwargs: call_order.append("notify")),
        ) as notify_mock, patch(
            "miniapp_server._apply_order_delivery_pricing",
            new=AsyncMock(side_effect=lambda *args, **kwargs: call_order.append("pricing")),
        ) as pricing_mock, patch(
            "miniapp_server.time.time",
            return_value=1_700_000_000.123,
        ), patch(
            "miniapp_server.datetime",
        ) as datetime_mock:
            datetime_mock.utcnow.return_value = datetime.fromisoformat(fixed_submitted_at)
            payload = asyncio.run(_submit_order_payload({"user_id": 42}))

        submission_batch_id = payload["submission_batch_id"]
        submitted_at = payload["submitted_at"]
        self.assertEqual(submission_batch_id, "sub-42-1700000000123")
        self.assertEqual(submitted_at, fixed_submitted_at)
        datetime.fromisoformat(submitted_at)
        pricing_mock.assert_awaited_once_with(
            42,
            {
                "recipient_name": "Alice Example",
                "phone": "+7 999 000-00-00",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "7B",
                "apartment": "14",
                "comment": "call first",
            },
            delivery_type="standard",
        )
        snapshot_mock.assert_awaited_once_with(
            42,
            {
                "recipient_name": "Alice Example",
                "phone": "+7 999 000-00-00",
                "city": "Moscow",
                "street": "Tverskaya",
                "house": "7B",
                "apartment": "14",
                "comment": "call first",
            },
            submission_batch_id,
            submitted_at,
        )
        submit_mock.assert_awaited_once_with(42)
        notify_mock.assert_called_once_with(user_id=42, order_total_rub=5250.4)
        self.assertEqual(call_order, ["pricing", "snapshot", "submit", "notify"])
        self.assertEqual(
            payload,
            {
                "ok": True,
                "submission_batch_id": "sub-42-1700000000123",
                "submitted_at": fixed_submitted_at,
            },
        )

    def test_notify_admin_order_submission_formats_message_for_all_admins(self) -> None:
        expected_text = (
            "Пользователь Alice Example (@alice) оформил заказ на сумму 12 345 ₽.\n\n"
            "Свяжитесь с ним для уточнения деталей и оплаты."
        )

        with patch.object(miniapp_server, "ADMIN_USER_IDS", (101, 202)), patch(
            "miniapp_server.db.get_or_create_user",
            new=AsyncMock(
                return_value={
                    "user_id": 42,
                    "username": "alice",
                    "first_name": "Alice",
                    "last_name": "Example",
                }
            ),
        ), patch(
            "miniapp_server._send_telegram_message",
            new=AsyncMock(return_value=True),
        ) as send_mock:
            asyncio.run(
                miniapp_server._notify_admin_order_submission(
                    user_id=42,
                    order_total_rub=12345.0,
                )
            )

        self.assertEqual(send_mock.await_count, 2)
        self.assertEqual(send_mock.await_args_list[0].args, (101, expected_text))
        self.assertEqual(send_mock.await_args_list[1].args, (202, expected_text))

    def test_send_telegram_message_retries_transport_errors(self) -> None:
        class FakeAsyncClient:
            attempts = 0
            requests = []

            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                type(self).attempts += 1
                type(self).requests.append((url, json))
                if type(self).attempts < 3:
                    raise httpx.ConnectTimeout("timed out")
                response = MagicMock()
                response.raise_for_status.return_value = None
                response.json.return_value = {"ok": True}
                return response

        with patch.object(miniapp_server, "BOT_TOKEN", "test-token"), patch(
            "miniapp_server.httpx.AsyncClient",
            new=FakeAsyncClient,
        ), patch(
            "miniapp_server.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            delivered = asyncio.run(miniapp_server._send_telegram_message(101, "hello"))

        self.assertTrue(delivered)
        self.assertEqual(FakeAsyncClient.attempts, 3)
        self.assertEqual(len(FakeAsyncClient.requests), 3)
        self.assertEqual(sleep_mock.await_args_list[0].args, (0.75,))
        self.assertEqual(sleep_mock.await_args_list[1].args, (1.5,))
        self.assertEqual(FakeAsyncClient.requests[0][1]["chat_id"], 101)
        self.assertEqual(FakeAsyncClient.requests[0][1]["text"], "hello")

    def test_dispatch_admin_order_submission_notification_starts_daemon_thread(self) -> None:
        started_threads = []
        notify_coro = SimpleNamespace(name="notify-coro")

        class FakeThread:
            def __init__(self, *, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon

            def start(self):
                started_threads.append(
                    {
                        "name": self.name,
                        "daemon": self.daemon,
                    }
                )
                self.target()

        with patch(
            "miniapp_server.threading.Thread",
            new=FakeThread,
        ), patch(
            "miniapp_server._notify_admin_order_submission",
            new=MagicMock(return_value=notify_coro),
        ) as notify_mock, patch(
            "miniapp_server.asyncio.run",
            new=MagicMock(),
        ) as run_mock:
            miniapp_server._dispatch_admin_order_submission_notification(
                user_id=42,
                order_total_rub=9900.0,
            )

        notify_mock.assert_called_once_with(user_id=42, order_total_rub=9900.0)
        run_mock.assert_called_once_with(notify_coro)
        self.assertEqual(
            started_threads,
            [
                {
                    "name": "submitted-order-notify-42",
                    "daemon": True,
                }
            ],
        )

    def test_submit_order_payload_passes_express_delivery_type_to_repricing(self) -> None:
        with patch(
            "miniapp_server.db.get_delivery_profile",
            new=AsyncMock(
                return_value={
                    "recipient_name": "Alice Example",
                    "phone": "+7 999 000-00-00",
                    "city": "Saint Petersburg",
                    "street": "Nevsky",
                    "house": "10",
                    "apartment": "",
                    "comment": "",
                    "updated_at": "2026-03-24 18:00:00",
                }
            ),
        ), patch(
            "miniapp_server._apply_order_delivery_pricing",
            new=AsyncMock(),
        ) as pricing_mock, patch(
            "miniapp_server.db.cart_get_pending_order_items",
            new=AsyncMock(return_value=[]),
        ), patch(
            "miniapp_server.db.cart_apply_delivery_snapshot",
            new=AsyncMock(),
        ), patch(
            "miniapp_server.db.cart_submit_order",
            new=AsyncMock(),
        ), patch(
            "miniapp_server.time.time",
            return_value=1_700_000_100.0,
        ), patch(
            "miniapp_server.datetime",
        ) as datetime_mock:
            datetime_mock.utcnow.return_value = datetime.fromisoformat("2026-03-24T18:00:00")
            asyncio.run(_submit_order_payload({"user_id": 42, "delivery_type": "express"}))

        pricing_mock.assert_awaited_once()
        self.assertEqual(pricing_mock.await_args.args[0], 42)
        self.assertEqual(pricing_mock.await_args.kwargs["delivery_type"], "express")


if __name__ == "__main__":
    unittest.main()
