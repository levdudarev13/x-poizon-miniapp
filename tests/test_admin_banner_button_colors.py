import asyncio
import tempfile
import unittest

import database


class AdminBannerButtonColorTests(unittest.TestCase):
    def test_normalize_banner_entry_keeps_explicit_label(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Old label",
                "title": "New title",
                "subtitle": "Description",
                "button_label": "Read more",
                "button_url": "https://example.com/banner",
                "button_color": "hyper-pink",
                "image_url": "/uploads/promo-banners/banner.webp",
                "image_alt": "Banner",
                "blocks": [{"id": "b1", "type": "text", "text": "Content"}],
            }
        )

        self.assertEqual(normalized["label"], "Old label")
        self.assertEqual(normalized["button_color"], "hyper-pink")

    def test_normalize_banner_entry_allows_empty_title_label_and_image(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "",
                "title": "",
                "subtitle": "",
                "image_url": "",
                "image_alt": "",
                "story_image_url": "",
                "story_image_alt": "",
                "blocks": [],
            }
        )

        self.assertEqual(normalized["label"], "")
        self.assertEqual(normalized["title"], "")
        self.assertEqual(normalized["image_url"], "")

    def test_normalize_banner_entry_falls_back_to_default_button_color(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "button_color": "unknown-theme",
            }
        )

        self.assertEqual(
            normalized["button_color"],
            database.DEFAULT_PROMO_BANNER_BUTTON_COLOR,
        )

    def test_normalize_banner_entry_maps_legacy_yellow_theme_to_acid_red(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "button_color": "volt-yellow",
            }
        )

        self.assertEqual(normalized["button_color"], "acid-red")

    def test_normalize_banner_entry_keeps_story_image_optional(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "image_url": "/uploads/promo-banners/banner.webp",
                "image_alt": "Launch",
                "story_image_url": "",
                "story_image_alt": "Should be dropped",
            }
        )

        self.assertEqual(normalized["story_image_url"], "")
        self.assertEqual(normalized["story_image_alt"], "")

    def test_normalize_banner_entry_adds_story_alt_when_story_image_exists(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Popup Launch",
                "image_url": "/uploads/promo-banners/banner.webp",
                "story_image_url": "/uploads/promo-banners/story.webp",
                "story_image_alt": "",
            }
        )

        self.assertEqual(normalized["story_image_url"], "/uploads/promo-banners/story.webp")
        self.assertEqual(normalized["story_image_alt"], "Popup Launch")

    def test_normalize_banner_entry_promotes_legacy_button_to_blocks(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "button_label": "Open",
                "button_url": "https://example.com/banner",
                "button_color": "solar-orange",
            }
        )

        self.assertEqual(len(normalized["blocks"]), 1)
        self.assertEqual(normalized["blocks"][0]["type"], "button")
        self.assertEqual(normalized["blocks"][0]["button_label"], "Open")
        self.assertEqual(normalized["blocks"][0]["button_url"], "https://example.com/banner")
        self.assertEqual(normalized["blocks"][0]["button_color"], "solar-orange")

    def test_normalize_banner_entry_prefers_inline_button_block_for_action_fields(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "button_label": "Legacy",
                "button_url": "https://example.com/legacy",
                "button_color": "hyper-pink",
                "blocks": [
                    {
                        "id": "cta-main",
                        "type": "button",
                        "button_label": "Inline CTA",
                        "button_url": "https://example.com/inline",
                        "button_color": "laser-cyan",
                    }
                ],
            }
        )

        self.assertEqual(normalized["button_label"], "Inline CTA")
        self.assertEqual(normalized["button_url"], "https://example.com/inline")
        self.assertEqual(normalized["button_color"], "hyper-pink")
        self.assertEqual(len(normalized["blocks"]), 1)

    def test_normalize_banner_entry_does_not_restore_default_button_label(self) -> None:
        normalized = database._normalize_banner_entry_payload(
            {
                "label": "Launch",
                "title": "Launch",
                "button_label": "",
                "button_url": "https://example.com/inline",
                "button_color": "laser-cyan",
            }
        )

        self.assertEqual(normalized["button_label"], "")
        self.assertEqual(normalized["button_url"], "https://example.com/inline")
        self.assertEqual(normalized["blocks"][0]["button_label"], "")

    def test_save_admin_banner_allows_empty_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_db_path = database.DB_PATH
            database.DB_PATH = f"{temp_dir}/test-banners.db"

            try:
                asyncio.run(database.init_db())
                saved = asyncio.run(
                    database.save_admin_banner(
                        0,
                        "",
                        "",
                        "",
                        "",
                        "",
                        database.DEFAULT_PROMO_BANNER_BUTTON_COLOR,
                        "",
                        "",
                        "",
                        "",
                        False,
                        [],
                    )
                )
            finally:
                database.DB_PATH = original_db_path

        self.assertEqual(saved["label"], "")
        self.assertEqual(saved["title"], "")
        self.assertEqual(saved["image_url"], "")
        self.assertEqual(saved["blocks"], [])


if __name__ == "__main__":
    unittest.main()
