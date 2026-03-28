import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from miniapp_server import _extract_product_input_url
from config import OPEN_1688_RAPIDAPI_HOST, TAOBAO_DATA_RAPIDAPI_HOST, TAOBAO_TMALL_RAPIDAPI_HOST
from services.parser import _parse_1688, _parse_taobao
from services.poizon_api import fetch_keyword_search, fetch_product_detail
from services.rapidapi_keys import get_rapidapi_keys, reset_rapidapi_key_cache, rotate_rapidapi_key_to_end
from services.taobao_1688_api import (
    Open1688SearchUnavailableError,
    TaobaoSearchUnavailableError,
    _extract_taobao_item_from_payload,
    _build_taobao_tmall_search_results,
    _request_json,
    build_info_from_open_1688_detail,
    build_info_from_taobao_1688_item,
    build_info_from_taobao_data_item,
    fetch_open_1688_keyword_search,
    fetch_taobao_tmall_keyword_search,
)


class MiniAppInputTests(unittest.TestCase):
    def test_extracts_poizon_url_from_share_text(self) -> None:
        share_text = (
            "【得物】得物er-X6J3M5V7发现一件好物， 2 CZ1111 åMGblXmJå  "
            "https://dw4.co/t/A/1ulOJIR8v 定制手表 CASIO卡西欧 改装系列, 点击链接直接打开."
        )

        self.assertEqual(
            _extract_product_input_url(share_text),
            "https://dw4.co/t/A/1ulOJIR8v",
        )


class RapidApiRotationTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_rapidapi_key_cache()

    def test_open_poizon_prefers_primary_key_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("RAPIDAPI_KEYS=key2,key3,key1\nRAPIDAPI_KEY=key1\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "key2,key3,key1",
                    "RAPIDAPI_KEY": "key1",
                    "RAPIDAPI_FALLBACK_KEYS": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()

                self.assertEqual(
                    get_rapidapi_keys("open-poizon-api.p.rapidapi.com"),
                    ("key1", "key2", "key3"),
                )
                self.assertIn(
                    "RAPIDAPI_KEYS=key1,key2,key3",
                    env_path.read_text(encoding="utf-8"),
                )

    def test_rotate_rapidapi_key_to_end_persists_env_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("RAPIDAPI_KEYS=key1,key2,key3\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "key1,key2,key3",
                    "RAPIDAPI_KEY": "",
                    "RAPIDAPI_FALLBACK_KEYS": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()

                self.assertEqual(
                    get_rapidapi_keys("open-poizon-api.p.rapidapi.com"),
                    ("key1", "key2", "key3"),
                )

                rotate_rapidapi_key_to_end("open-poizon-api.p.rapidapi.com", "key1")

                self.assertEqual(
                    get_rapidapi_keys("open-poizon-api.p.rapidapi.com"),
                    ("key2", "key3", "key1"),
                )
                self.assertIn(
                    "RAPIDAPI_KEYS=key2,key3,key1",
                    env_path.read_text(encoding="utf-8"),
                )

    def test_poizon_keyword_search_rotates_key_after_429(self) -> None:
        first_request = httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryList")
        second_request = httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryList")
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                httpx.Response(429, request=first_request),
                httpx.Response(
                    200,
                    request=second_request,
                    json={
                        "data": {
                            "lastId": 17,
                            "spuList": [
                                {
                                    "dwSpuId": "123",
                                    "distSpuTitle": "Nike Dunk Low",
                                    "image": "https://cdn.example.com/1.jpg",
                                    "authPrice": 12345,
                                }
                            ],
                        }
                    },
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("RAPIDAPI_KEYS=pk1,pk2\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "pk1,pk2",
                    "RAPIDAPI_KEY": "",
                    "RAPIDAPI_FALLBACK_KEYS": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                results, last_id = asyncio.run(fetch_keyword_search(client, "Nike"))

                self.assertEqual(last_id, 17)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["spu_id"], "123")
                self.assertEqual(
                    get_rapidapi_keys("open-poizon-api.p.rapidapi.com"),
                    ("pk2", "pk1"),
                )

    def test_poizon_keyword_search_uses_lowest_sku_price(self) -> None:
        request = httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryList")
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=httpx.Response(
                200,
                request=request,
                json={
                    "data": {
                        "lastId": 21,
                        "spuList": [
                            {
                                "dwSpuId": "sku-min-test",
                                "distSpuTitle": "Nike Air Force 1",
                                "image": "https://cdn.example.com/af1.jpg",
                                "authPrice": 219900,
                                "skuList": [
                                    {"size": "40", "minBidPrice": 18900},
                                    {"size": "41", "minBidPrice": 15900},
                                    {"size": "42", "minBidPrice": 17500},
                                ],
                            }
                        ],
                    }
                },
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("RAPIDAPI_KEYS=pk1\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "pk1",
                    "RAPIDAPI_KEY": "",
                    "RAPIDAPI_FALLBACK_KEYS": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                results, last_id = asyncio.run(fetch_keyword_search(client, "Nike"))

                self.assertEqual(last_id, 21)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["price_cny"], 159.0)

    def test_poizon_keyword_search_falls_back_to_last_spu_id_when_cursor_missing(self) -> None:
        request = httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryList")
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=httpx.Response(
                200,
                request=request,
                json={
                    "data": {
                        "total": 20,
                        "spuList": [
                            {
                                "dwSpuId": "101",
                                "distSpuTitle": "Nike Dunk Low",
                                "image": "https://cdn.example.com/1.jpg",
                                "authPrice": 12345,
                            },
                            {
                                "dwSpuId": "202",
                                "distSpuTitle": "Nike Dunk High",
                                "image": "https://cdn.example.com/2.jpg",
                                "authPrice": 23456,
                            },
                        ],
                    }
                },
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("RAPIDAPI_KEYS=pk1\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "pk1",
                    "RAPIDAPI_KEY": "",
                    "RAPIDAPI_FALLBACK_KEYS": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                results, last_id = asyncio.run(fetch_keyword_search(client, "Nike", page_size=2))

                self.assertEqual(len(results), 2)
                self.assertEqual(last_id, "202")

    def test_poizon_product_detail_does_not_repeat_key_cycle(self) -> None:
        requests = [
            httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryDetail"),
            httpx.Request("GET", "https://open-poizon-api.p.rapidapi.com/poizon/product/queryDetail"),
            httpx.Request("GET", "https://open-dewu-api.p.rapidapi.com/poizon/product/queryDetail"),
            httpx.Request("GET", "https://open-dewu-api.p.rapidapi.com/poizon/product/queryDetail"),
        ]
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                httpx.Response(200, request=requests[0], json={"data": {}}),
                httpx.Response(429, request=requests[1]),
                httpx.Response(429, request=requests[2]),
                httpx.Response(429, request=requests[3]),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "RAPIDAPI_KEYS=pk1,pk2\nRAPIDAPI_FALLBACK_KEYS=fk1,fk2\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "RAPIDAPI_KEYS": "pk1,pk2",
                    "RAPIDAPI_KEY": "",
                    "RAPIDAPI_FALLBACK_KEYS": "fk1,fk2",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ), patch(
                "services.poizon_api.httpx.AsyncClient",
                side_effect=AssertionError("detail fetch should not restart the key cycle with a new client"),
            ):
                reset_rapidapi_key_cache()
                payload = asyncio.run(fetch_product_detail(client, "123", sku_id="456"))
                expected_calls = (
                    len(get_rapidapi_keys("open-poizon-api.p.rapidapi.com"))
                    + len(get_rapidapi_keys("open-dewu-api.p.rapidapi.com"))
                )

                self.assertEqual(payload, {})
                self.assertEqual(client.get.await_count, expected_calls)

    def test_taobao_request_rotates_key_after_429(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            async def request(self, method, url, headers=None, params=None, json=None, timeout=None):
                self.calls += 1
                request = httpx.Request(method, url)
                if self.calls == 1:
                    return httpx.Response(429, request=request)
                return httpx.Response(200, request=request, json={"item": {"title": "ok"}})

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("TAOBAO_1688_RAPIDAPI_KEYS=tk1,tk2\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "TAOBAO_1688_RAPIDAPI_KEYS": "tk1,tk2",
                    "TAOBAO_TMALL_RAPIDAPI_KEYS": "",
                    "DATAHUB_1688_RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                payload = asyncio.run(
                    _request_json(
                        FakeClient(),
                        host="taobao-tmall-16881.p.rapidapi.com",
                        keys=(),
                        method="GET",
                        path="/api/test",
                    )
                )

                self.assertEqual(payload, {"item": {"title": "ok"}})
                self.assertEqual(
                    get_rapidapi_keys("taobao-tmall-16881.p.rapidapi.com"),
                    ("tk2", "tk1"),
                )

    def test_taobao_tmall_host_uses_only_dedicated_key_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "TAOBAO_TMALL_RAPIDAPI_KEYS=\nTAOBAO_1688_RAPIDAPI_KEYS=tk1688\nRAPIDAPI_KEYS=shared1,shared2\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "TAOBAO_TMALL_RAPIDAPI_KEYS": "",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "tk1688",
                    "RAPIDAPI_KEYS": "shared1,shared2",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()

                self.assertEqual(
                    get_rapidapi_keys(TAOBAO_TMALL_RAPIDAPI_HOST),
                    (),
                )
                self.assertEqual(
                    get_rapidapi_keys("taobao-tmall-16881.p.rapidapi.com"),
                    ("tk1688", "shared1", "shared2"),
                )

    def test_taobao_data_host_reuses_tmall_key_pool_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "TAOBAO_DATA_RAPIDAPI_KEYS=\nTAOBAO_TMALL_RAPIDAPI_KEYS=tkmain1,tkmain2\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "TAOBAO_DATA_RAPIDAPI_KEYS": "",
                    "TAOBAO_TMALL_RAPIDAPI_KEYS": "tkmain1,tkmain2",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()

                self.assertEqual(
                    get_rapidapi_keys(TAOBAO_DATA_RAPIDAPI_HOST),
                    ("tkmain1", "tkmain2"),
                )

    def test_open_1688_host_prefers_dedicated_then_shared_key_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "OPEN_1688_RAPIDAPI_KEYS=op1,op2\nTAOBAO_1688_RAPIDAPI_KEYS=tk1688\nRAPIDAPI_KEYS=shared1\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "OPEN_1688_RAPIDAPI_KEYS": "op1,op2",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "tk1688",
                    "RAPIDAPI_KEYS": "shared1",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()

                self.assertEqual(
                    get_rapidapi_keys(OPEN_1688_RAPIDAPI_HOST),
                    ("op1", "op2", "tk1688", "shared1"),
                )

    def test_taobao_keyword_search_raises_unavailable_after_key_pool_exhausted(self) -> None:
        class Always429Client:
            def __init__(self) -> None:
                self.calls = 0

            async def request(self, method, url, headers=None, params=None, json=None, timeout=None):
                self.calls += 1
                request = httpx.Request(method, url)
                return httpx.Response(429, request=request)

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "TAOBAO_TMALL_RAPIDAPI_KEYS=tk1,tk2\nRAPIDAPI_KEYS=shared1,shared2\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "TAOBAO_TMALL_RAPIDAPI_KEYS": "tk1,tk2",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEYS": "shared1,shared2",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                client = Always429Client()

                with self.assertRaises(TaobaoSearchUnavailableError):
                    asyncio.run(fetch_taobao_tmall_keyword_search(client, "iphone"))

                self.assertEqual(client.calls, 2)

    def test_open_1688_keyword_search_normalizes_query_and_maps_cards(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.params = None

            async def request(self, method, url, headers=None, params=None, json=None, timeout=None):
                self.params = params
                request = httpx.Request(method, url)
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "code": 200,
                        "data": {
                            "totalRecords": 26,
                            "pageSize": 20,
                            "currentPage": 1,
                            "data": [
                                {
                                    "offerId": "900431404107",
                                    "subject": "莆田鞋AF1",
                                    "subjectTrans": "Putian shoes AF1",
                                    "imageUrl": "https://img.example.com/af1.jpg",
                                    "promotionURL": "https://detail.1688.com/offer/900431404107.html?kjSource=pc",
                                    "priceInfo": {
                                        "price": "125-128",
                                    },
                                    "monthSold": 2150,
                                    "repurchaseRate": "12%",
                                    "minOrderQuantity": 1,
                                }
                            ],
                        },
                    },
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OPEN_1688_RAPIDAPI_KEYS=op1\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "OPEN_1688_RAPIDAPI_KEYS": "op1",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                client = FakeClient()
                results, total_count = asyncio.run(fetch_open_1688_keyword_search(client, "nike sb zoom"))

        self.assertEqual(client.params["keyword"], "Nike sb zoom")
        self.assertEqual(total_count, 26)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["platform"], "1688")
        self.assertEqual(results[0]["item_id"], "900431404107")
        self.assertEqual(results[0]["detail_url"], "https://detail.1688.com/offer/900431404107.html")
        self.assertEqual(results[0]["price_cny"], 125.0)
        self.assertTrue(results[0]["price_is_starting"])

    def test_open_1688_keyword_search_raises_unavailable_after_key_pool_exhausted(self) -> None:
        class Always429Client:
            def __init__(self) -> None:
                self.calls = 0

            async def request(self, method, url, headers=None, params=None, json=None, timeout=None):
                self.calls += 1
                request = httpx.Request(method, url)
                return httpx.Response(429, request=request)

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OPEN_1688_RAPIDAPI_KEYS=op1,op2\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "OPEN_1688_RAPIDAPI_KEYS": "op1,op2",
                    "TAOBAO_1688_RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEYS": "",
                    "RAPIDAPI_KEY": "",
                },
                clear=False,
            ), patch(
                "services.rapidapi_keys.ENV_FILE_PATH",
                env_path,
            ):
                reset_rapidapi_key_cache()
                client = Always429Client()

                with self.assertRaises(Open1688SearchUnavailableError):
                    asyncio.run(fetch_open_1688_keyword_search(client, "nike sb zoom"))

                self.assertEqual(client.calls, 2)

    def test_taobao_search_results_expose_item_ids_and_normalize_images(self) -> None:
        payload = {
            "Result": {
                "Items": {
                    "Items": {
                        "Content": [
                            {
                                "Id": "975702512506",
                                "Title": "Apple, iPhone X",
                                "OriginalTitle": "Apple/苹果 iPhone X",
                                "TaobaoItemUrl": "https://item.taobao.com/item.htm?id=975702512506",
                                "MainPictureUrl": "https://img.alicdn.com/imgextra///img.alicdn.com/imgextra/i4/6000000007385/O1CN01dH9Qud24QO2Mf4uJB_!!6000000007385-0-tao_i18n.jpg",
                                "Price": {
                                    "OriginalPrice": 516.9,
                                    "MarginPrice": 516.9,
                                },
                                "BrandName": "Apple",
                                "VendorName": "诚信商务电话",
                                "Pictures": [
                                    {
                                        "Url": "https://img.alicdn.com/imgextra///img.alicdn.com/imgextra/i4/6000000007385/O1CN01dH9Qud24QO2Mf4uJB_!!6000000007385-0-tao_i18n.jpg"
                                    }
                                ],
                            }
                        ],
                        "TotalCount": 4098,
                    }
                }
            }
        }

        results, total_count = _build_taobao_tmall_search_results(payload)

        self.assertEqual(total_count, 4098)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["platform"], "taobao")
        self.assertEqual(results[0]["item_id"], "975702512506")
        self.assertEqual(results[0]["price_cny"], 516.9)
        self.assertEqual(
            results[0]["image"],
            "https://img.alicdn.com/imgextra/i4/6000000007385/O1CN01dH9Qud24QO2Mf4uJB_!!6000000007385-0-tao_i18n.jpg",
        )
        self.assertEqual(
            results[0]["detail_url"],
            "https://item.taobao.com/item.htm?id=975702512506",
        )

    def test_taobao_search_results_build_canonical_url_when_item_link_missing(self) -> None:
        payload = {
            "Result": {
                "Items": {
                    "Items": {
                        "Content": [
                            {
                                "Id": "123456789012",
                                "Title": "Canvas Bag",
                                "Price": {
                                    "OriginalPrice": 88.0,
                                },
                            }
                        ],
                        "TotalCount": 1,
                    }
                }
            }
        }

        results, total_count = _build_taobao_tmall_search_results(payload)

        self.assertEqual(total_count, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["detail_url"],
            "https://item.taobao.com/item.htm?id=123456789012",
        )
        self.assertEqual(
            results[0]["url"],
            "https://item.taobao.com/item.htm?id=123456789012",
        )

    def test_extract_taobao_item_prefers_new_host_data_block(self) -> None:
        payload = {
            "success": True,
            "data": {
                "productId": "900358656682",
                "productName": "Main payload item",
                "mainImgUrlList": ["https://img.example.com/main.jpg"],
            },
            "noise": {
                "priceRanges": [
                    {"price": 42.49}
                ]
            },
        }

        result = _extract_taobao_item_from_payload(payload)

        self.assertEqual(result["productId"], "900358656682")
        self.assertEqual(result["productName"], "Main payload item")

    def test_build_info_from_taobao_data_item_extracts_gallery_and_variant_prices(self) -> None:
        item = {
            "productId": "900358656682",
            "productName": "WEIRD PUSS set",
            "originalShopName": "WEIRD PUSS",
            "originalProductUrl": "https://item.taobao.com/item.htm?id=900358656682",
            "mainImgUrl": "https://img.example.com/main.jpg",
            "mainImgUrlList": [
                "https://img.example.com/main.jpg",
                "https://img.example.com/gallery-2.jpg",
                "https://img.example.com/gallery-3.jpg",
            ],
            "description": (
                '<div><img src="//img.example.com/detail-1.jpg">'
                '<img src="https://img.example.com/detail-2.jpg"></div>'
            ),
            "priceRanges": [{"price": 42.49}],
            "productPropList": [
                {
                    "originalPropName": "Color",
                    "valueList": [
                        {"originalValueName": "Yellow", "imgUrl": "https://img.example.com/yellow.jpg"},
                        {"originalValueName": "Apricot", "imgUrl": "https://img.example.com/apricot.jpg"},
                    ],
                },
                {
                    "originalPropName": "Size",
                    "valueList": [
                        {"originalValueName": "S"},
                        {"originalValueName": "M"},
                    ],
                },
            ],
            "productSkuInfo": {
                "Yellow_S_": {
                    "price": 42.49,
                    "imgUrl": "https://img.example.com/yellow.jpg",
                    "skuPropList": [
                        {"originalPropName": "Color", "originalValueName": "Yellow"},
                        {"originalPropName": "Size", "originalValueName": "S"},
                    ],
                },
                "Apricot_M_": {
                    "priceRanges": [{"price": 48.03}],
                    "imgUrl": "https://img.example.com/apricot.jpg",
                    "skuPropList": [
                        {"originalPropName": "Color", "originalValueName": "Apricot"},
                        {"originalPropName": "Size", "originalValueName": "M"},
                    ],
                },
            },
        }

        result = build_info_from_taobao_data_item(item)

        self.assertEqual(result["item_id"], "900358656682")
        self.assertEqual(result["price"], 42.49)
        self.assertEqual(result["image_url"], "https://img.example.com/main.jpg")
        self.assertIn("https://img.example.com/gallery-2.jpg", result["extra_images"])
        self.assertIn("https://img.example.com/gallery-3.jpg", result["extra_images"])
        self.assertIn("https://img.example.com/detail-1.jpg", result["extra_images"])
        self.assertEqual(
            result["available_sizes"],
            ["S", "M"],
        )
        self.assertEqual(
            result["variants"],
            [
                {"name": "Color", "options": ["Yellow", "Apricot"]},
                {"name": "Size", "options": ["S", "M"]},
            ],
        )
        self.assertEqual(
            result["variant_price_map"],
            {
                '[["Color", "Yellow"], ["Size", "S"]]': 42.49,
                '[["Color", "Apricot"], ["Size", "M"]]': 48.03,
            },
        )

    def test_build_info_from_taobao_1688_item_extracts_variant_prices(self) -> None:
        item = {
            "num_iid": "900358656682",
            "title": "Fallback item",
            "price": "6.78",
            "pic_url": "https://img.example.com/main.jpg",
            "item_prop_list": [
                {
                    "name": "color",
                    "prop_value": [
                        {"value": "Yellow", "image": "https://img.example.com/yellow.jpg"},
                        {"value": "Apricot", "image": "https://img.example.com/apricot.jpg"},
                    ],
                },
                {
                    "name": "size",
                    "prop_value": [
                        {"value": "S"},
                        {"value": "M"},
                    ],
                },
            ],
            "item_sku_list": [
                {
                    "img_url": "https://img.example.com/yellow.jpg",
                    "price_real": "6.78",
                    "prop_value": '{"color":"Yellow","size":"S"}',
                },
                {
                    "img_url": "https://img.example.com/apricot.jpg",
                    "price_real": "7.12",
                    "prop_value": '{"color":"Apricot","size":"M"}',
                },
            ],
        }

        result = build_info_from_taobao_1688_item(item)

        self.assertIn("https://img.example.com/yellow.jpg", result["extra_images"])
        self.assertIn("https://img.example.com/apricot.jpg", result["extra_images"])
        self.assertEqual(
            result["variant_price_map"],
            {
                '[["color", "Yellow"], ["size", "S"]]': 6.78,
                '[["color", "Apricot"], ["size", "M"]]': 7.12,
            },
        )

    def test_build_info_from_open_1688_detail_extracts_variants_and_prices(self) -> None:
        item = {
            "offerId": "900431404107",
            "subjectTrans": "Putian shoes AF1",
            "promotionUrl": "https://detail.1688.com/offer/900431404107.html?kjSource=pc",
            "description": '<div><img src="//img.example.com/detail-1.jpg"></div>',
            "productImage": {
                "images": [
                    "https://img.example.com/main.jpg",
                    "https://img.example.com/gallery-2.jpg",
                ]
            },
            "productAttribute": [
                {"attributeNameTrans": "Brand", "valueTrans": "Putian shoes"},
                {"attributeNameTrans": "Season", "valueTrans": "Spring"},
                {"attributeNameTrans": "Season", "valueTrans": "Summer"},
            ],
            "productSkuInfos": [
                {
                    "price": "125.0",
                    "skuAttributes": [
                        {"attributeNameTrans": "Color", "valueTrans": "White", "skuImageUrl": "https://img.example.com/white.jpg"},
                        {"attributeNameTrans": "Size", "valueTrans": "36"},
                    ],
                },
                {
                    "promotionPrice": "128.0",
                    "skuAttributes": [
                        {"attributeNameTrans": "Color", "valueTrans": "Black", "skuImageUrl": "https://img.example.com/black.jpg"},
                        {"attributeNameTrans": "Size", "valueTrans": "37"},
                    ],
                },
            ],
            "productPackageInfos": [
                {"weight": 1.0}
            ],
        }

        result = build_info_from_open_1688_detail(item)

        self.assertEqual(result["item_id"], "900431404107")
        self.assertEqual(result["detail_url"], "https://detail.1688.com/offer/900431404107.html")
        self.assertEqual(result["image_url"], "https://img.example.com/main.jpg")
        self.assertIn("https://img.example.com/gallery-2.jpg", result["extra_images"])
        self.assertIn("https://img.example.com/detail-1.jpg", result["extra_images"])
        self.assertIn("https://img.example.com/white.jpg", result["extra_images"])
        self.assertEqual(result["brand"], "Putian shoes")
        self.assertEqual(result["price"], 125.0)
        self.assertTrue(result["price_is_starting"])
        self.assertEqual(result["available_sizes"], ["36", "37"])
        self.assertEqual(
            result["variants"],
            [
                {"name": "Color", "options": ["White", "Black"]},
                {"name": "Size", "options": ["36", "37"]},
            ],
        )
        self.assertEqual(
            result["variant_price_map"],
            {
                '[["Color", "White"], ["Size", "36"]]': 125.0,
                '[["Color", "Black"], ["Size", "37"]]': 128.0,
            },
        )
        self.assertEqual(result["specs"]["Season"], "Spring, Summer")
        self.assertEqual(result["weight_kg"], 1.0)

    def test_parse_taobao_uses_new_primary_then_existing_fallbacks(self) -> None:
        call_order: list[str] = []

        async def primary_detail(*args, **kwargs):
            call_order.append("primary")
            return {}

        async def secondary_by_url(*args, **kwargs):
            call_order.append("secondary-url")
            return {"num_iid": "123456789012"}

        async def secondary_detail(*args, **kwargs):
            call_order.append("secondary-detail")
            return {}

        async def tertiary_detail(*args, **kwargs):
            call_order.append("tertiary")
            return {
                "Id": "123456789012",
                "OriginalTitle": "Canvas Bag",
                "Price": {"OriginalPrice": 88.0},
                "MainPictureUrl": "https://img.example.com/bag.jpg",
                "Attributes": [
                    {
                        "IsConfigurator": True,
                        "OriginalPropertyName": "Size",
                        "OriginalValue": "M",
                    }
                ],
            }

        with patch(
            "services.parser.fetch_taobao_data_item_detail",
            new=AsyncMock(side_effect=primary_detail),
        ), patch(
            "services.parser.fetch_taobao_1688_item_by_url",
            new=AsyncMock(side_effect=secondary_by_url),
        ), patch(
            "services.parser.fetch_taobao_1688_item_detail",
            new=AsyncMock(side_effect=secondary_detail),
        ), patch(
            "services.parser.fetch_taobao_tmall_full_info",
            new=AsyncMock(side_effect=tertiary_detail),
        ):
            result = asyncio.run(
                _parse_taobao(object(), "https://item.taobao.com/item.htm?id=123456789012")
            )

        self.assertEqual(
            call_order,
            ["primary", "secondary-url", "secondary-detail", "tertiary"],
        )
        self.assertEqual(result["item_id"], "123456789012")
        self.assertEqual(result["name"], "Canvas Bag")
        self.assertEqual(result["price"], 88.0)
        self.assertEqual(result["image_url"], "https://img.example.com/bag.jpg")
        self.assertEqual(result["available_sizes"], ["M"])

    def test_parse_1688_uses_open_detail_as_third_fallback(self) -> None:
        call_order: list[str] = []

        async def primary_simple(*args, **kwargs):
            call_order.append("primary-simple")
            return {}

        async def primary_detail(*args, **kwargs):
            call_order.append("primary-detail")
            return {}

        async def secondary_by_url(*args, **kwargs):
            call_order.append("secondary-url")
            return {"num_iid": "900431404107"}

        async def tertiary_open_detail(*args, **kwargs):
            call_order.append("tertiary-open-detail")
            return {
                "offerId": "900431404107",
                "subjectTrans": "Putian shoes AF1",
                "promotionUrl": "https://detail.1688.com/offer/900431404107.html?kjSource=pc",
                "productImage": {
                    "images": ["https://img.example.com/main.jpg"]
                },
                "productSkuInfos": [
                    {
                        "price": "125.0",
                        "skuAttributes": [
                            {"attributeNameTrans": "Color", "valueTrans": "White"},
                            {"attributeNameTrans": "Size", "valueTrans": "36"},
                        ],
                    }
                ],
            }

        with patch(
            "services.parser.fetch_1688_datahub_simple",
            new=AsyncMock(side_effect=primary_simple),
        ), patch(
            "services.parser.fetch_1688_datahub_detail",
            new=AsyncMock(side_effect=primary_detail),
        ), patch(
            "services.parser.fetch_taobao_1688_item_by_url",
            new=AsyncMock(side_effect=secondary_by_url),
        ), patch(
            "services.parser.fetch_open_1688_product_detail",
            new=AsyncMock(side_effect=tertiary_open_detail),
        ):
            result = asyncio.run(
                _parse_1688(object(), "https://detail.1688.com/offer/900431404107.html")
            )

        self.assertEqual(
            call_order,
            ["primary-simple", "primary-detail", "secondary-url", "tertiary-open-detail"],
        )
        self.assertEqual(result["item_id"], "900431404107")
        self.assertEqual(result["name"], "Putian shoes AF1")
        self.assertEqual(result["price"], 125.0)
        self.assertEqual(result["detail_url"], "https://detail.1688.com/offer/900431404107.html")


if __name__ == "__main__":
    unittest.main()
