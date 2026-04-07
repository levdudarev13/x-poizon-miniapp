import mimetypes
import unittest

import miniapp_server  # noqa: F401


class MiniAppStaticFileTypesTests(unittest.TestCase):
    def test_webp_static_files_use_image_mime_type(self) -> None:
        self.assertEqual(mimetypes.guess_type("banner.webp")[0], "image/webp")


if __name__ == "__main__":
    unittest.main()
