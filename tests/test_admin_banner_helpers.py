import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_server import (
    _admin_promo_banner_delete_payload,
    _admin_promo_banner_save_payload,
    _admin_promo_banners_payload,
    _promo_banners_payload,
)


class AdminBannerHelpersTests(unittest.TestCase):
    def test_public_banner_payload_returns_entry_banner(self) -> None:
        banner_rows = [
            {
                "id": 1,
                "label": "Logistics X",
                "title": "Banner One",
                "subtitle": "Details",
                "button_label": "Read more",
                "button_url": "https://vk.ru/logisticsx",
                "button_color": "acid-lime",
                "image_url": "/uploads/promo-banners/banner-1.webp",
                "image_alt": "Banner One",
                "story_image_url": "/uploads/promo-banners/story-1.webp",
                "story_image_alt": "Story One",
                "blocks": [
                    {"id": "copy", "type": "text", "text": "Text"},
                    {
                        "id": "cta",
                        "type": "button",
                        "button_label": "Read more",
                        "button_url": "https://vk.ru/logisticsx",
                        "button_color": "acid-lime",
                    },
                ],
                "position": 1,
                "show_on_entry": 1,
                "updated_at": 100.0,
            },
            {
                "id": 2,
                "label": "Partner",
                "title": "Banner Two",
                "subtitle": "Partner flow",
                "button_label": "Open",
                "button_url": "https://vk.ru/@logisticsx-partner",
                "button_color": "hyper-pink",
                "image_url": "/uploads/promo-banners/banner-2.webp",
                "image_alt": "Banner Two",
                "story_image_url": "",
                "story_image_alt": "",
                "blocks": [],
                "position": 2,
                "show_on_entry": 0,
                "updated_at": 90.0,
            },
        ]

        with patch(
            "miniapp_server.db.get_admin_banners",
            new=AsyncMock(return_value=banner_rows),
        ):
            payload = asyncio.run(_promo_banners_payload())

        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["entry_banner_id"], 1)
        self.assertTrue(payload["items"][0]["show_on_entry"])
        self.assertEqual(
            payload["items"][0]["story_image_url"],
            "https://api.x-poizon.ru/uploads/promo-banners/story-1.webp",
        )
        self.assertEqual(payload["items"][0]["blocks"][1]["type"], "button")
        self.assertEqual(payload["items"][0]["blocks"][1]["button_url"], "https://vk.ru/logisticsx")

    def test_admin_banner_payload_returns_stats(self) -> None:
        banner_rows = [
            {
                "id": 1,
                "label": "One",
                "title": "Banner One",
                "subtitle": "",
                "button_label": "Read more",
                "button_url": "https://example.com/one",
                "button_color": "acid-lime",
                "image_url": "/uploads/promo-banners/one.webp",
                "image_alt": "One",
                "story_image_url": "/uploads/promo-banners/story-one.webp",
                "story_image_alt": "Story One",
                "blocks": [],
                "position": 1,
                "show_on_entry": 1,
                "updated_at": 100.0,
            },
            {
                "id": 2,
                "label": "Two",
                "title": "Banner Two",
                "subtitle": "",
                "button_label": "",
                "button_url": "",
                "button_color": "laser-cyan",
                "image_url": "/uploads/promo-banners/two.webp",
                "image_alt": "Two",
                "story_image_url": "",
                "story_image_alt": "",
                "blocks": [],
                "position": 2,
                "show_on_entry": 0,
                "updated_at": 200.0,
            },
        ]

        with patch(
            "miniapp_server.db.get_admin_banners",
            new=AsyncMock(return_value=banner_rows),
        ):
            payload = asyncio.run(_admin_promo_banners_payload())

        self.assertEqual(payload["stats"]["total"], 2)
        self.assertEqual(payload["stats"]["auto_open_count"], 1)
        self.assertEqual(payload["stats"]["latest_updated_at"], 200.0)
        self.assertEqual(payload["upload"]["format"], "WEBP")
        self.assertEqual(
            payload["items"][0]["story_image_url"],
            "https://api.x-poizon.ru/uploads/promo-banners/story-one.webp",
        )

    def test_admin_banner_save_payload_passes_expected_fields(self) -> None:
        saved_banner = {
            "id": 3,
            "label": "Launch",
            "title": "New banner",
            "subtitle": "Description",
            "button_label": "Read more",
            "button_url": "https://example.com/banner",
            "button_color": "solar-orange",
            "image_url": "/uploads/promo-banners/new.webp",
            "image_alt": "New banner",
            "story_image_url": "",
            "story_image_alt": "",
            "blocks": [{"id": "b1", "type": "heading", "text": "Title"}],
            "position": 3,
            "show_on_entry": 1,
            "updated_at": 300.0,
        }

        with patch(
            "miniapp_server.db.save_admin_banner",
            new=AsyncMock(return_value=saved_banner),
        ) as save_mock, patch(
            "miniapp_server.db.get_admin_banners",
            new=AsyncMock(return_value=[saved_banner]),
        ):
            payload = asyncio.run(
                _admin_promo_banner_save_payload(
                    {
                        "id": 0,
                        "label": "Launch",
                        "title": "New banner",
                        "subtitle": "Description",
                        "button_label": "Read more",
                        "button_url": "https://example.com/banner",
                        "button_color": "solar-orange",
                        "image_url": "/uploads/promo-banners/new.webp",
                        "image_alt": "New banner",
                        "story_image_url": "",
                        "story_image_alt": "",
                        "show_on_entry": True,
                        "blocks": [{"id": "b1", "type": "heading", "text": "Title"}],
                    }
                )
            )

        save_mock.assert_awaited_once_with(
            0,
            "Launch",
            "New banner",
            "Description",
            "Read more",
            "https://example.com/banner",
            "solar-orange",
            "/uploads/promo-banners/new.webp",
            "New banner",
            "",
            "",
            True,
            [{"id": "b1", "type": "heading", "text": "Title"}],
        )
        self.assertEqual(payload["stats"]["total"], 1)
        self.assertEqual(payload["items"][0]["id"], 3)
        self.assertEqual(payload["items"][0]["button_color"], "solar-orange")
        self.assertEqual(payload["items"][0]["story_image_url"], "")

    def test_public_banner_payload_expands_uploaded_image_urls(self) -> None:
        banner_rows = [
            {
                "id": 8,
                "label": "Launch",
                "title": "Uploaded banner",
                "subtitle": "",
                "button_label": "",
                "button_url": "",
                "button_color": "acid-lime",
                "image_url": "/uploads/promo-banners/cover.webp",
                "image_alt": "Uploaded banner",
                "story_image_url": "/uploads/promo-banners/story.webp",
                "story_image_alt": "Uploaded story",
                "blocks": [
                    {
                        "id": "image-1",
                        "type": "image",
                        "image_url": "/uploads/promo-banners/inline.webp",
                        "alt_text": "Inline",
                        "caption": "",
                    }
                ],
                "position": 1,
                "show_on_entry": 1,
                "updated_at": 500.0,
            }
        ]

        with patch(
            "miniapp_server.db.get_admin_banners",
            new=AsyncMock(return_value=banner_rows),
        ):
            payload = asyncio.run(_promo_banners_payload())

        banner = payload["items"][0]
        self.assertEqual(
            banner["image_url"],
            "https://api.x-poizon.ru/uploads/promo-banners/cover.webp",
        )
        self.assertEqual(
            banner["story_image_url"],
            "https://api.x-poizon.ru/uploads/promo-banners/story.webp",
        )
        self.assertEqual(
            banner["blocks"][0]["image_url"],
            "https://api.x-poizon.ru/uploads/promo-banners/inline.webp",
        )

    def test_admin_banner_delete_payload_removes_entry(self) -> None:
        delete_mock = AsyncMock()

        with patch(
            "miniapp_server.db.delete_admin_banner",
            new=delete_mock,
        ), patch(
            "miniapp_server.db.get_admin_banners",
            new=AsyncMock(return_value=[]),
        ):
            payload = asyncio.run(_admin_promo_banner_delete_payload({"id": 4}))

        delete_mock.assert_awaited_once_with(4)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["stats"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
