import unittest

from miniapp_server import _build_search_pagination


class MiniAppSearchPaginationTests(unittest.TestCase):
    def test_1688_keeps_load_more_when_provider_total_is_cumulative(self) -> None:
        next_start_id, has_more = _build_search_pagination(
            "1688",
            start_id=0,
            count=20,
            loaded_count=20,
            total_count=20,
        )

        self.assertEqual(next_start_id, 20)
        self.assertTrue(has_more)

    def test_taobao_uses_total_count_with_frame_offsets(self) -> None:
        next_start_id, has_more = _build_search_pagination(
            "taobao",
            start_id=20,
            count=20,
            loaded_count=20,
            total_count=55,
        )

        self.assertEqual(next_start_id, 40)
        self.assertTrue(has_more)

        next_start_id, has_more = _build_search_pagination(
            "taobao",
            start_id=40,
            count=20,
            loaded_count=15,
            total_count=55,
        )

        self.assertEqual(next_start_id, 60)
        self.assertFalse(has_more)

    def test_poizon_uses_provider_cursor(self) -> None:
        next_start_id, has_more = _build_search_pagination(
            "poizon",
            start_id=0,
            count=20,
            loaded_count=20,
            total_count=20,
            provider_cursor=77,
        )

        self.assertEqual(next_start_id, 77)
        self.assertTrue(has_more)


if __name__ == "__main__":
    unittest.main()
