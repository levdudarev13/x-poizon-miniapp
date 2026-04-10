import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_config(**env_overrides):
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = Path(tmpdir) / ".env"
        env_file.write_text("", encoding="utf-8")

        with patch.dict(
            os.environ,
            {
                "BOT_ENV_FILE": str(env_file),
                "MINI_APP_TELEGRAM_URL": "",
                "MINI_APP_PUBLIC_URL": "",
                "MINI_APP_URL": "",
                **env_overrides,
            },
            clear=False,
        ):
            import config

            return importlib.reload(config)


class MiniAppLaunchUrlConfigTests(unittest.TestCase):
    def test_telegram_launch_url_takes_priority(self) -> None:
        config = _load_config(
            MINI_APP_TELEGRAM_URL="https://app.x-poizon.ru/?v=20260408-live3",
            MINI_APP_PUBLIC_URL="https://app.x-poizon.ru",
            MINI_APP_URL="https://fallback.lhr.life",
        )

        self.assertEqual(
            config.MINI_APP_URL,
            "https://app.x-poizon.ru/?v=20260408-live3",
        )

    def test_public_url_is_used_when_telegram_launch_url_is_missing(self) -> None:
        config = _load_config(
            MINI_APP_PUBLIC_URL="https://app.x-poizon.ru",
            MINI_APP_URL="https://fallback.lhr.life",
        )

        self.assertEqual(config.MINI_APP_URL, "https://app.x-poizon.ru")

    def test_dev_url_is_last_fallback(self) -> None:
        config = _load_config(
            MINI_APP_URL="https://fallback.lhr.life",
        )

        self.assertEqual(config.MINI_APP_URL, "https://fallback.lhr.life")


if __name__ == "__main__":
    unittest.main()
