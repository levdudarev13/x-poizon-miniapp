import asyncio
import sqlite3
import tempfile
import unittest

import database


class PlatformAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_db_path = database.DB_PATH
        database.DB_PATH = f"{self.temp_dir.name}/platform-accounts.db"
        self.addCleanup(self._restore_db_path)
        asyncio.run(database.init_db())

    def _restore_db_path(self) -> None:
        database.DB_PATH = self.original_db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(database.DB_PATH)
        self.addCleanup(conn.close)
        return conn

    def test_init_db_backfills_legacy_telegram_mapping(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, margin_steps, margin_min_rub)
            VALUES (?,?,?,?,?,?)
            """,
            (777, "legacy777", "Legacy", "Buyer", "[]", 500.0),
        )
        conn.commit()

        asyncio.run(database.init_db())

        row = self._conn().execute(
            """
            SELECT platform, platform_user_id, user_id
            FROM platform_accounts
            WHERE platform=? AND platform_user_id=?
            """,
            (database.ACCOUNT_PLATFORM_TELEGRAM, "777"),
        ).fetchone()

        self.assertEqual(row, (database.ACCOUNT_PLATFORM_TELEGRAM, "777", 777))

    def test_get_or_create_platform_user_reuses_legacy_telegram_user_id(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, margin_steps, margin_min_rub)
            VALUES (?,?,?,?,?,?)
            """,
            (999, "", "Legacy", "Buyer", "[]", 500.0),
        )
        conn.commit()

        user = asyncio.run(
            database.get_or_create_platform_user(
                database.ACCOUNT_PLATFORM_TELEGRAM,
                "999",
                username="legacy_user",
                first_name="Legacy",
                last_name="Buyer",
            )
        )

        self.assertEqual(user["user_id"], 999)
        self.assertEqual(user["username"], "legacy_user")

        mapping_row = self._conn().execute(
            """
            SELECT user_id
            FROM platform_accounts
            WHERE platform=? AND platform_user_id=?
            """,
            (database.ACCOUNT_PLATFORM_TELEGRAM, "999"),
        ).fetchone()

        self.assertEqual(mapping_row, (999,))

    def test_get_or_create_platform_user_creates_separate_internal_id_for_vk(self) -> None:
        user = asyncio.run(
            database.get_or_create_platform_user(
                database.ACCOUNT_PLATFORM_VK,
                "123456",
                username="vk_user",
                first_name="Vasya",
                last_name="Petrov",
            )
        )

        self.assertNotEqual(user["user_id"], 123456)
        self.assertEqual(user["username"], "vk_user")

        mapping_row = self._conn().execute(
            """
            SELECT user_id
            FROM platform_accounts
            WHERE platform=? AND platform_user_id=?
            """,
            (database.ACCOUNT_PLATFORM_VK, "123456"),
        ).fetchone()
        self.assertEqual(mapping_row, (user["user_id"],))

        same_user = asyncio.run(
            database.get_or_create_platform_user(
                database.ACCOUNT_PLATFORM_VK,
                "123456",
                username="vk_buyer",
            )
        )

        self.assertEqual(same_user["user_id"], user["user_id"])
        self.assertEqual(same_user["username"], "vk_buyer")


if __name__ == "__main__":
    unittest.main()
