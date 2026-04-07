import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from miniapp_server import _save_promo_banner_image


class AdminBannerUploadFormatsTests(unittest.TestCase):
    def test_png_upload_is_saved_with_png_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("miniapp_server.PROMO_BANNER_UPLOADS_DIR", Path(temp_dir)):
                payload = _save_promo_banner_image(
                    "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii"),
                    prefix="banner",
                )

        self.assertTrue(payload["url"].endswith(".png"))
        self.assertEqual(payload["mime_type"], "image/png")

    def test_jpeg_upload_is_saved_with_jpg_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("miniapp_server.PROMO_BANNER_UPLOADS_DIR", Path(temp_dir)):
                payload = _save_promo_banner_image(
                    "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode("ascii"),
                    prefix="banner",
                )

        self.assertTrue(payload["url"].endswith(".jpg"))
        self.assertEqual(payload["mime_type"], "image/jpeg")


if __name__ == "__main__":
    unittest.main()
