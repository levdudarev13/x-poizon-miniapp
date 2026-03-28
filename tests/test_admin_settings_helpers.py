import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import miniapp_server
from miniapp_server import (
    ShowcaseValidationError,
    _admin_settings_payload,
    _admin_showcase_payload,
    _admin_showcase_update_payload,
    _build_admin_settings_updates,
    _display_rate_payload,
)


class AdminSettingsHelpersTests(unittest.TestCase):
    def test_track_active_request_restores_counter_after_exception(self) -> None:
        baseline = miniapp_server.active_requests

        with self.assertRaises(RuntimeError):
            with miniapp_server._track_active_request():
                self.assertEqual(miniapp_server.active_requests, baseline + 1)
                raise RuntimeError("boom")

        self.assertEqual(miniapp_server.active_requests, baseline)

    def test_display_rate_payload_uses_manual_rate_for_ui(self) -> None:
        rate = SimpleNamespace(
            cny_rub=12.38,
            usd_rub=90.1,
            eur_rub=98.4,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=2_100,
            age_human="35 \u043c\u0438\u043d. \u043d\u0430\u0437\u0430\u0434",
        )

        payload = _display_rate_payload(
            rate,
            settings={
                "rate_override": "13",
                "rate_override_until": "2000",
            },
            effective_rate=13.0,
            now=1_500.0,
        )

        self.assertEqual(payload["cny_rub"], 13.0)
        self.assertEqual(payload["age_human"], "\u0420\u0443\u0447\u043d\u043e\u0439 \u043a\u0443\u0440\u0441")
        self.assertEqual(payload["source"], "manual")

    def test_display_rate_payload_keeps_cbr_rate_without_override(self) -> None:
        rate = SimpleNamespace(
            cny_rub=12.38,
            usd_rub=90.1,
            eur_rub=98.4,
            updated_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            age_seconds=2_100,
            age_human="35 \u043c\u0438\u043d. \u043d\u0430\u0437\u0430\u0434",
        )

        payload = _display_rate_payload(
            rate,
            settings={
                "rate_override": "",
                "rate_override_until": "0",
            },
            effective_rate=12.38,
            now=1_500.0,
        )

        self.assertEqual(payload["cny_rub"], 12.38)
        self.assertEqual(payload["age_human"], "35 \u043c\u0438\u043d. \u043d\u0430\u0437\u0430\u0434")
        self.assertEqual(payload["source"], "cbr")

    def test_numeric_field_normalizes_commas_and_spaces(self) -> None:
        updates = _build_admin_settings_updates("commission_pct", " 12,5 ")

        self.assertEqual(updates, {"commission_pct": "12.5"})

    def test_rate_override_zero_resets_manual_rate(self) -> None:
        updates = _build_admin_settings_updates("rate_override", "0")

        self.assertEqual(
            updates,
            {"rate_override": "", "rate_override_until": "0"},
        )

    def test_rate_override_sets_expiry_for_24_hours(self) -> None:
        updates = _build_admin_settings_updates("rate_override", "13.4", now=1_000.0)

        self.assertEqual(updates["rate_override"], "13.4")
        self.assertEqual(updates["rate_override_until"], "87400.0")

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _build_admin_settings_updates("unknown_field", "1")

    def test_admin_settings_payload_marks_manual_rate_as_active(self) -> None:
        settings = {
            "commission_pct": "11.0",
            "min_commission_rub": "300.0",
            "logistics_rub": "500.0",
            "insurance_rub": "200.0",
            "price_per_kg": "250.0",
            "delivery_time": "РґРѕ 2 РЅРµРґРµР»СЊ",
            "next_shipment_date": "25.03.2026",
            "rate_override": "12.7",
            "rate_override_until": "2000",
        }

        with patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value=settings),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=12.7),
        ), patch(
            "miniapp_server.time.time",
            return_value=1_500.0,
        ):
            payload = asyncio.run(_admin_settings_payload())

        required_payload_keys = {
            "effective_rate",
            "rate_source",
            "rate_override_active",
            "rate_override_expires_at",
            "settings",
        }

        self.assertTrue(required_payload_keys.issubset(payload.keys()))
        self.assertEqual(payload["rate_source"], "manual")
        self.assertTrue(payload["rate_override_active"])
        self.assertEqual(payload["settings"]["commission_pct"], "11.0")
        self.assertIn("next_shipment_date", payload["settings"])
        self.assertEqual(payload["settings"]["next_shipment_date"], "25.03.2026")
        self.assertEqual(payload["effective_rate"], 12.7)
        self.assertEqual(payload["rate_override_expires_at"], datetime.fromtimestamp(2000).isoformat())

    def test_admin_settings_payload_falls_back_to_cbr_after_expiry(self) -> None:
        settings = {
            "commission_pct": "10.0",
            "min_commission_rub": "300.0",
            "logistics_rub": "500.0",
            "insurance_rub": "200.0",
            "price_per_kg": "250.0",
            "delivery_time": "РґРѕ 2 РЅРµРґРµР»СЊ",
            "next_shipment_date": "00.00.0000",
            "rate_override": "12.7",
            "rate_override_until": "1000",
        }

        with patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value=settings),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=11.9),
        ), patch(
            "miniapp_server.time.time",
            return_value=2_000.0,
        ):
            payload = asyncio.run(_admin_settings_payload())

        required_payload_keys = {
            "effective_rate",
            "rate_source",
            "rate_override_active",
            "rate_override_expires_at",
            "settings",
        }

        self.assertTrue(required_payload_keys.issubset(payload.keys()))
        self.assertEqual(payload["rate_source"], "cbr")
        self.assertFalse(payload["rate_override_active"])
        self.assertIsNone(payload["rate_override_expires_at"])
        self.assertIn("next_shipment_date", payload["settings"])
        self.assertEqual(payload["settings"]["next_shipment_date"], "00.00.0000")
        self.assertEqual(payload["effective_rate"], 11.9)

    def test_admin_showcase_payload_returns_cached_items_and_links(self) -> None:
        slots = [
            {
                "slot": index,
                "url": "",
                "product_json": "",
                "updated_at": 0.0,
            }
            for index in range(1, 11)
        ]
        slots[0] = {
            "slot": 1,
            "url": "https://example.com/a",
            "product_json": '{"url":"https://example.com/a","platform":"poizon","name":"Boot A","brand":"Brand A","price_cny":620,"image_url":"https://img/a.jpg","extra_images":[],"specs":{},"available_sizes":[],"variants":[],"variant_price_map":{},"original_variants":[],"notes":"","auto_detected":[]}',
            "updated_at": 1.0,
        }
        slots[5] = {
            "slot": 6,
            "url": "https://example.com/b",
            "product_json": '{"url":"https://example.com/b","platform":"taobao","name":"Bag B","brand":"Brand B","price_cny":320,"image_url":"https://img/b.jpg","extra_images":[],"specs":{},"available_sizes":[],"variants":[],"variant_price_map":{},"original_variants":[],"notes":"","auto_detected":[]}',
            "updated_at": 2.0,
        }

        with patch(
            "miniapp_server.db.get_admin_showcase_slots",
            new=AsyncMock(return_value=slots),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={
                "commission_pct": "10.0",
                "min_commission_rub": "300.0",
                "logistics_rub": "500.0",
                "insurance_rub": "200.0",
                "price_per_kg": "250.0",
            }),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server.get_typical_weight",
            return_value=1.0,
        ):
            payload = asyncio.run(_admin_showcase_payload())

        self.assertEqual(payload["configured_count"], 2)
        self.assertEqual(len(payload["links"]), 10)
        self.assertEqual(payload["links"][0], "https://example.com/a")
        self.assertEqual(payload["links"][5], "https://example.com/b")
        self.assertEqual([item["slot"] for item in payload["items"]], [1, 6])

    def test_admin_showcase_payload_repairs_incomplete_cached_slots(self) -> None:
        slots = [
            {
                "slot": index,
                "url": "",
                "product_json": "",
                "updated_at": 0.0,
            }
            for index in range(1, 11)
        ]
        slots[5] = {
            "slot": 6,
            "url": "https://example.com/b",
            "product_json": '{"url":"https://example.com/b","platform":"poizon","name":"","brand":"","price_cny":null,"image_url":"https://img/b.jpg","extra_images":[],"specs":{"Р¦РµРЅР° РІС‹РїСѓСЃРєР°":"ВҐ888"},"available_sizes":[],"variants":[],"variant_price_map":{},"original_variants":[],"notes":"","auto_detected":[]}',
            "updated_at": 2.0,
        }
        repaired_product = {
            "url": "https://example.com/b",
            "platform": "poizon",
            "name": "Bag B",
            "brand": "Brand B",
            "price_cny": 888,
            "size": "",
            "category": "",
            "weight_kg": None,
            "weight_estimated": False,
            "city": "",
            "delivery_type": "",
            "image_url": "https://img/b.jpg",
            "extra_images": [],
            "specs": {"Р¦РµРЅР° РІС‹РїСѓСЃРєР°": "ВҐ888"},
            "available_sizes": [],
            "variants": [],
            "variant_price_map": {},
            "original_variants": [],
            "notes": "",
            "auto_detected": ["name", "price"],
        }

        with patch(
            "miniapp_server.db.get_admin_showcase_slots",
            new=AsyncMock(return_value=slots),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={
                "commission_pct": "10.0",
                "min_commission_rub": "300.0",
                "logistics_rub": "500.0",
                "insurance_rub": "200.0",
                "price_per_kg": "250.0",
            }),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server._parse_product",
            new=AsyncMock(return_value=repaired_product),
        ) as parse_product_mock, patch(
            "miniapp_server.db.set_admin_showcase_slot",
            new=AsyncMock(),
        ) as save_slot_mock, patch(
            "miniapp_server.get_typical_weight",
            return_value=1.0,
        ):
            payload = asyncio.run(_admin_showcase_payload())

        self.assertEqual(payload["configured_count"], 1)
        self.assertEqual([item["slot"] for item in payload["items"]], [6])
        parse_product_mock.assert_awaited_once_with("https://example.com/b")
        save_slot_mock.assert_awaited_once_with(6, "https://example.com/b", ANY)

    def test_admin_showcase_payload_keeps_named_slot_without_price(self) -> None:
        slots = [
            {
                "slot": index,
                "url": "",
                "product_json": "",
                "updated_at": 0.0,
            }
            for index in range(1, 11)
        ]
        slots[0] = {
            "slot": 1,
            "url": "https://example.com/a",
            "product_json": '{"url":"https://example.com/a","platform":"poizon","name":"Boot A","brand":"Brand A","price_cny":null,"image_url":"https://img/a.jpg","extra_images":[],"specs":{},"available_sizes":[],"variants":[],"variant_price_map":{},"original_variants":[],"notes":"","auto_detected":["name","image"]}',
            "updated_at": 1.0,
        }

        with patch(
            "miniapp_server.db.get_admin_showcase_slots",
            new=AsyncMock(return_value=slots),
        ), patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={
                "commission_pct": "10.0",
                "min_commission_rub": "300.0",
                "logistics_rub": "500.0",
                "insurance_rub": "200.0",
                "price_per_kg": "250.0",
            }),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server._parse_product",
            new=AsyncMock(),
        ) as parse_product_mock:
            payload = asyncio.run(_admin_showcase_payload())

        self.assertEqual(payload["configured_count"], 1)
        self.assertEqual([item["slot"] for item in payload["items"]], [1])
        self.assertIsNone(payload["items"][0]["subtotal_rub"])
        parse_product_mock.assert_not_awaited()

    def test_admin_showcase_update_rejects_invalid_links(self) -> None:
        with self.assertRaises(ShowcaseValidationError) as raised:
            asyncio.run(_admin_showcase_update_payload({"links": ["broken-link"]}))

        self.assertIn("1", raised.exception.slot_errors)

    def test_admin_showcase_update_rejects_duplicate_links(self) -> None:
        with self.assertRaises(ShowcaseValidationError) as raised:
            asyncio.run(
                _admin_showcase_update_payload(
                    {"links": ["https://example.com/a", "https://example.com/a"]}
                )
            )

        self.assertEqual(str(raised.exception), "duplicate_showcase_links")
        self.assertIn("2", raised.exception.slot_errors)

    def test_admin_showcase_update_reuses_cached_slot_without_reparsing(self) -> None:
        slots = [
            {
                "slot": index,
                "url": "",
                "product_json": "",
                "updated_at": 0.0,
            }
            for index in range(1, 11)
        ]
        slots[0] = {
            "slot": 1,
            "url": "https://example.com/a",
            "product_json": '{"url":"https://example.com/a","platform":"poizon","name":"Boot A","brand":"Brand A","price_cny":620,"image_url":"https://img/a.jpg","extra_images":[],"specs":{},"available_sizes":[],"variants":[],"variant_price_map":{},"original_variants":[],"notes":"","auto_detected":[]}',
            "updated_at": 1.0,
        }

        with patch(
            "miniapp_server.db.get_admin_showcase_slots",
            new=AsyncMock(return_value=slots),
        ), patch(
            "miniapp_server._parse_product",
            new=AsyncMock(),
        ) as parse_product_mock, patch(
            "miniapp_server.db.set_admin_showcase_slot",
            new=AsyncMock(),
        ) as save_slot_mock, patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={
                "commission_pct": "10.0",
                "min_commission_rub": "300.0",
                "logistics_rub": "500.0",
                "insurance_rub": "200.0",
                "price_per_kg": "250.0",
            }),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server.get_typical_weight",
            return_value=1.0,
        ):
            payload = asyncio.run(_admin_showcase_update_payload({"links": ["https://example.com/a"]}))

        self.assertEqual(payload["configured_count"], 1)
        self.assertEqual([item["slot"] for item in payload["items"]], [1])
        parse_product_mock.assert_not_awaited()
        self.assertEqual(save_slot_mock.await_count, 10)

    def test_admin_showcase_update_saves_all_slots(self) -> None:
        slots = [
            {
                "slot": index,
                "url": "",
                "product_json": "",
                "updated_at": 0.0,
            }
            for index in range(1, 11)
        ]

        with patch(
            "miniapp_server.db.get_admin_showcase_slots",
            new=AsyncMock(return_value=slots),
        ), patch(
            "miniapp_server._parse_product",
            new=AsyncMock(return_value={
                "url": "https://example.com/a",
                "platform": "poizon",
                "name": "Boot A",
                "brand": "Brand A",
                "price_cny": 620,
                "size": "",
                "category": "",
                "weight_kg": None,
                "weight_estimated": False,
                "city": "",
                "delivery_type": "",
                "image_url": "https://img/a.jpg",
                "extra_images": [],
                "specs": {},
                "available_sizes": [],
                "variants": [],
                "variant_price_map": {},
                "original_variants": [],
                "notes": "",
                "auto_detected": [],
            }),
        ) as parse_product_mock, patch(
            "miniapp_server.db.get_admin_settings",
            new=AsyncMock(return_value={
                "commission_pct": "10.0",
                "min_commission_rub": "300.0",
                "logistics_rub": "500.0",
                "insurance_rub": "200.0",
                "price_per_kg": "250.0",
            }),
        ), patch(
            "miniapp_server.get_effective_rate",
            new=AsyncMock(return_value=13.0),
        ), patch(
            "miniapp_server.get_typical_weight",
            return_value=1.0,
        ), patch(
            "miniapp_server.db.set_admin_showcase_slot",
            new=AsyncMock(),
        ) as save_slot_mock:
            payload = asyncio.run(_admin_showcase_update_payload({"links": ["https://example.com/a"]}))

        self.assertEqual(payload["configured_count"], 1)
        self.assertEqual(save_slot_mock.await_count, 10)
        save_slot_mock.assert_any_await(1, "https://example.com/a", ANY)
        parse_product_mock.assert_awaited_once_with("https://example.com/a")


if __name__ == "__main__":
    unittest.main()
