import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import database


MSK = ZoneInfo("Europe/Moscow")


def _to_utc_sql(year: int, month: int, day: int, hour: int, minute: int = 0, *, tz=MSK) -> str:
    return (
        datetime(year, month, day, hour, minute, tzinfo=tz)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
        .strftime("%Y-%m-%d %H:%M:%S")
    )


class AdminDashboardHelpersTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_db_path = database.DB_PATH
        database.DB_PATH = f"{self.temp_dir.name}/admin-dashboard.db"
        self.addCleanup(self._restore_db_path)
        asyncio.run(database.init_db())

    def _restore_db_path(self) -> None:
        database.DB_PATH = self.original_db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(database.DB_PATH)
        self.addCleanup(conn.close)
        return conn

    def test_record_miniapp_activity_creates_daily_row_and_user(self) -> None:
        now = datetime(2026, 4, 8, 14, 30, tzinfo=MSK)

        asyncio.run(database.record_miniapp_activity(999, occurred_at=now))
        asyncio.run(database.record_miniapp_activity(999, occurred_at=now))

        conn = self._conn()
        user_row = conn.execute("SELECT user_id FROM users WHERE user_id=999").fetchone()
        activity_row = conn.execute(
            "SELECT activity_date, request_count FROM miniapp_activity_daily WHERE user_id=999"
        ).fetchone()

        self.assertEqual(user_row[0], 999)
        self.assertEqual(activity_row[0], "2026-04-08")
        self.assertEqual(activity_row[1], 2)

    def test_admin_stats_and_broadcast_segments_use_real_db_state(self) -> None:
        conn = self._conn()

        users = [
            (101, "paid_user", _to_utc_sql(2026, 4, 1, 12)),
            (202, "ordered_user", _to_utc_sql(2026, 4, 2, 12)),
            (303, "request_user", _to_utc_sql(2026, 4, 3, 12)),
            (404, "cart_user", _to_utc_sql(2026, 4, 8, 0, 30)),
            (505, "active_user", _to_utc_sql(2026, 4, 8, 10, 0)),
            (606, "inactive_user", _to_utc_sql(2026, 4, 4, 12)),
        ]
        conn.executemany(
            "INSERT INTO users (user_id, username, margin_steps, margin_min_rub, created_at) VALUES (?,?,?,?,?)",
            [(user_id, username, "[]", 500.0, created_at) for user_id, username, created_at in users],
        )

        calculations = [
            (1, 101, "https://example.com/paid", 1500.0),
            (2, 202, "https://example.com/order", 2000.0),
            (3, 303, "https://example.com/request", 3000.0),
            (4, 404, "https://example.com/cart", 4000.0),
        ]
        conn.executemany(
            "INSERT INTO calculations (id, user_id, product_url, total_with_margin_rub, calc_json) VALUES (?,?,?,?,?)",
            [(calc_id, user_id, product_url, total_rub, "{}") for calc_id, user_id, product_url, total_rub in calculations],
        )

        cart_items = [
            (
                101,
                1,
                1,
                _to_utc_sql(2026, 4, 8, 10, 0),
                _to_utc_sql(2026, 4, 8, 10, 5),
                1,
                _to_utc_sql(2026, 4, 8, 11, 0),
            ),
            (
                202,
                2,
                1,
                _to_utc_sql(2026, 4, 5, 10, 0),
                _to_utc_sql(2026, 4, 5, 10, 5),
                0,
                _to_utc_sql(2026, 4, 5, 11, 0),
            ),
            (
                303,
                3,
                1,
                _to_utc_sql(2026, 4, 6, 9, 0),
                _to_utc_sql(2026, 4, 6, 9, 5),
                0,
                None,
            ),
            (
                404,
                4,
                0,
                _to_utc_sql(2026, 4, 8, 9, 30),
                None,
                0,
                None,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO cart_items (
                user_id, calculation_id, in_order, added_at, order_added_at,
                paid, order_submitted, submitted_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            [
                (
                    user_id,
                    calc_id,
                    in_order,
                    added_at,
                    order_added_at,
                    paid,
                    1 if submitted_at else 0,
                    submitted_at,
                )
                for user_id, calc_id, in_order, added_at, order_added_at, paid, submitted_at in cart_items
            ],
        )

        activity_rows = [
            (101, "2026-04-08", _to_utc_sql(2026, 4, 8, 10, 0), _to_utc_sql(2026, 4, 8, 10, 0), 1),
            (202, "2026-04-03", _to_utc_sql(2026, 4, 3, 12, 0), _to_utc_sql(2026, 4, 3, 12, 0), 1),
            (404, "2026-04-08", _to_utc_sql(2026, 4, 8, 9, 30), _to_utc_sql(2026, 4, 8, 9, 30), 1),
            (505, "2026-04-08", _to_utc_sql(2026, 4, 8, 13, 0), _to_utc_sql(2026, 4, 8, 13, 0), 1),
        ]
        conn.executemany(
            """
            INSERT INTO miniapp_activity_daily (user_id, activity_date, first_seen_at, last_seen_at, request_count)
            VALUES (?,?,?,?,?)
            """,
            activity_rows,
        )
        conn.commit()

        now = datetime(2026, 4, 8, 15, 0, tzinfo=MSK)
        stats = asyncio.run(database.get_admin_stats(now=now))
        counts = asyncio.run(database.get_admin_broadcast_segment_counts(now=now))

        self.assertEqual(stats["users"]["total"], 6)
        self.assertEqual(stats["users"]["active_today"], 3)
        self.assertEqual(stats["users"]["new_today"], 2)

        self.assertEqual(stats["cart"]["items_total"], 1)
        self.assertEqual(stats["cart"]["amount_total_rub"], 4000.0)
        self.assertEqual(stats["cart"]["items_new_today"], 1)
        self.assertEqual(stats["cart"]["amount_new_today_rub"], 4000.0)

        self.assertEqual(stats["orders"]["items_total"], 2)
        self.assertEqual(stats["orders"]["amount_total_rub"], 3500.0)
        self.assertEqual(stats["orders"]["items_new_today"], 1)
        self.assertEqual(stats["orders"]["amount_new_today_rub"], 1500.0)

        segment_counts = {segment["key"]: segment["count"] for segment in stats["segments"]}
        self.assertEqual(
            segment_counts,
            {
                "ordered_customers": 2,
                "request_builders": 1,
                "cart_holders": 1,
                "other_users": 2,
            },
        )

        self.assertEqual(counts["all_users"], 6)
        self.assertEqual(counts["active_miniapp_7d"], 4)
        self.assertEqual(counts["cart_holders"], 1)
        self.assertEqual(counts["request_builders"], 1)
        self.assertEqual(counts["ordered_customers"], 2)

        self.assertEqual(
            asyncio.run(database.get_admin_broadcast_recipient_ids("all_users", now=now)),
            [101, 202, 303, 404, 505, 606],
        )
        self.assertEqual(
            asyncio.run(database.get_admin_broadcast_recipient_ids("active_miniapp_7d", now=now)),
            [101, 202, 404, 505],
        )
        self.assertEqual(
            asyncio.run(database.get_admin_broadcast_recipient_ids("cart_holders", now=now)),
            [404],
        )
        self.assertEqual(
            asyncio.run(database.get_admin_broadcast_recipient_ids("request_builders", now=now)),
            [303],
        )
        self.assertEqual(
            asyncio.run(database.get_admin_broadcast_recipient_ids("ordered_customers", now=now)),
            [101, 202],
        )


if __name__ == "__main__":
    unittest.main()
