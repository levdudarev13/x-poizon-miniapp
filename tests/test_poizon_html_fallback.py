import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from miniapp_server import _parse_product, _product_by_spu
from models import ProductDraft
from services.parser import _find_variants_from_html, _parse_dewu, parse_poizon_html_specs, parse_url


class PoizonHtmlFallbackTests(unittest.TestCase):
    def test_find_variants_from_html_reads_sale_properties_list(self) -> None:
        html = """
        "saleProperties":{"list":[
          {"propertyId":1153790,"name":"颜色","value":"古银康斯坦丁","propertyValueId":839161488,"level":1,"sort":1},
          {"propertyId":1159751,"name":"套装","value":"标准单机套装","propertyValueId":839155780,"level":2,"sort":2},
          {"propertyId":1159751,"name":"套装","value":"标准小油套装","propertyValueId":839145530,"level":2,"sort":3},
          {"propertyId":1181346,"name":"礼盒","value":"心动Love","propertyValueId":839167172,"level":3,"sort":5},
          {"propertyId":1181406,"name":"是否含油","value":"不含油","propertyValueId":950882256,"level":4,"sort":7},
          {"propertyId":1181406,"name":"是否含油","value":"含油","propertyValueId":950882257,"level":4,"sort":8}
        ]}
        """

        result = _find_variants_from_html(html)

        self.assertEqual(
            result,
            [
                {"name": "颜色", "options": ["古银康斯坦丁"]},
                {"name": "套装", "options": ["标准单机套装", "标准小油套装"]},
                {"name": "礼盒", "options": ["心动Love"]},
                {"name": "是否含油", "options": ["不含油", "含油"]},
            ],
        )

    def test_parse_url_skips_html_when_api_has_core_fields(self) -> None:
        url = "https://www.poizon.com/product/123"

        with patch(
            "services.parser.resolve_url",
            new=AsyncMock(return_value=url),
        ), patch(
            "services.parser.detect_platform",
            return_value="poizon",
        ), patch(
            "services.parser.canonicalize_dewu_url",
            side_effect=lambda value: value,
        ), patch(
            "services.parser._parse_dewu",
            new=AsyncMock(return_value={
                "name": "Nike Dunk Low",
                "price": 129.0,
                "image_url": "https://img.example.com/dunk.jpg",
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={"price": 999.0}),
        ) as html_mock, patch(
            "services.translator.translate_if_cn",
            new=AsyncMock(side_effect=lambda value: value),
        ), patch(
            "services.translator.translate_specs_values",
            new=AsyncMock(side_effect=lambda value: value),
        ):
            draft = asyncio.run(parse_url(url))

        self.assertEqual(draft.name, "Nike Dunk Low")
        self.assertEqual(draft.price_cny, 129.0)
        self.assertFalse(draft.price_is_starting)
        self.assertEqual(draft.image_url, "https://img.example.com/dunk.jpg")
        html_mock.assert_not_awaited()

    def test_parse_url_keeps_price_empty_when_html_fallback_has_only_price(self) -> None:
        url = "https://www.poizon.com/product/456"

        with patch(
            "services.parser.resolve_url",
            new=AsyncMock(return_value=url),
        ), patch(
            "services.parser.detect_platform",
            return_value="poizon",
        ), patch(
            "services.parser.canonicalize_dewu_url",
            side_effect=lambda value: value,
        ), patch(
            "services.parser._parse_dewu",
            new=AsyncMock(return_value={
                "name": "Nike Air Max",
                "image_url": "https://img.example.com/airmax.jpg",
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={"price": 188.0, "price_is_starting": True}),
        ) as html_mock, patch(
            "services.translator.translate_if_cn",
            new=AsyncMock(side_effect=lambda value: value),
        ), patch(
            "services.translator.translate_specs_values",
            new=AsyncMock(side_effect=lambda value: value),
        ):
            draft = asyncio.run(parse_url(url))

        self.assertIsNone(draft.price_cny)
        self.assertFalse(draft.price_is_starting)
        html_mock.assert_awaited_once()

    def test_parse_url_shortens_name_from_html_fallback(self) -> None:
        url = "https://www.poizon.com/product/321"

        with patch(
            "services.parser.resolve_url",
            new=AsyncMock(return_value=url),
        ), patch(
            "services.parser.detect_platform",
            return_value="poizon",
        ), patch(
            "services.parser.canonicalize_dewu_url",
            side_effect=lambda value: value,
        ), patch(
            "services.parser._parse_dewu",
            new=AsyncMock(return_value={
                "name": "Nike Dunk Low White Black Panda Special Edition 2026",
                "price": 199.0,
                "image_url": "https://img.example.com/panda.jpg",
                "name_needs_shortening": True,
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={}),
        ), patch(
            "services.market_compare.extract_search_query",
            new=AsyncMock(return_value="Nike Dunk Panda"),
        ) as shorten_mock, patch(
            "services.translator.translate_if_cn",
            new=AsyncMock(side_effect=lambda value: value),
        ), patch(
            "services.translator.translate_specs_values",
            new=AsyncMock(side_effect=lambda value: value),
        ):
            draft = asyncio.run(parse_url(url))

        self.assertEqual(draft.name, "Nike Dunk Panda")
        shorten_mock.assert_awaited_once()

    def test_parse_dewu_uses_fast_dewu_html_only_for_fallback(self) -> None:
        html_info = {
            "variants": [{"name": "Color", "options": ["Black", "White"]}],
            "specs": {"Material": "Leather"},
            "extra_images": ["https://img.example.com/detail-2.jpg"],
        }

        async def run_parse() -> dict:
            async with httpx.AsyncClient() as client:
                return await _parse_dewu(
                    client,
                    "https://fast.dewu.com/page/productDetail?spuId=123456&skuId=789&sourceName=shareDetail",
                )

        with patch(
            "services.parser.fetch_product_detail",
            new=AsyncMock(return_value={
                "name": "Nike Vomero",
                "image_url": "https://img.example.com/vomero.jpg",
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value=html_info),
        ) as html_mock, patch(
            "services.parser._fetch",
            new=AsyncMock(side_effect=AssertionError("desktop fallback should not run")),
        ), patch(
            "services.parser._dewu_price_playwright",
            new=AsyncMock(side_effect=AssertionError("playwright fallback should not run")),
        ):
            result = asyncio.run(run_parse())

        self.assertEqual(result["name"], "Nike Vomero")
        self.assertEqual(result["image_url"], "https://img.example.com/vomero.jpg")
        self.assertNotIn("price", result)
        self.assertNotIn("price_is_starting", result)
        self.assertEqual(result["variants"], html_info["variants"])
        self.assertEqual(result["specs"], html_info["specs"])
        self.assertEqual(result["extra_images"], html_info["extra_images"])
        html_mock.assert_awaited_once_with(
            "https://fast.dewu.com/page/productDetail?spuId=123456&skuId=789&sourceName=shareDetail"
        )

    def test_parse_product_does_not_repeat_poizon_html_fetch(self) -> None:
        url = "https://www.poizon.com/product/789"
        draft = ProductDraft(
            url=url,
            platform="poizon",
            name="Nike Zoom",
            price_cny=222.0,
            image_url="https://img.example.com/zoom.jpg",
        )

        with patch(
            "miniapp_server.parse_url",
            new=AsyncMock(return_value=draft),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={"price": 999.0}),
        ) as html_mock:
            payload = asyncio.run(_parse_product(url))

        self.assertEqual(payload["price_cny"], 222.0)
        html_mock.assert_not_awaited()

    def test_product_by_spu_skips_html_when_api_has_core_fields(self) -> None:
        with patch(
            "services.poizon_api.fetch_product_detail",
            new=AsyncMock(return_value={
                "name": "Nike Vomero",
                "price": 199.0,
                "image_url": "https://img.example.com/vomero.jpg",
                "specs": {"Color": "Black"},
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={"price": 999.0}),
        ) as html_mock, patch(
            "services.parser.infer_category",
            return_value="sneakers",
        ), patch(
            "services.translator.translate_if_cn",
            new=AsyncMock(side_effect=lambda value: value),
        ), patch(
            "services.translator.translate_specs_with_groq",
            new=AsyncMock(side_effect=lambda value: value),
        ):
            payload = asyncio.run(_product_by_spu("123456"))

        self.assertEqual(payload["price_cny"], 199.0)
        self.assertEqual(payload["image_url"], "https://img.example.com/vomero.jpg")
        self.assertFalse(payload["price_is_starting"])
        html_mock.assert_not_awaited()

    def test_product_by_spu_keeps_price_empty_when_html_fallback_has_only_price(self) -> None:
        with patch(
            "services.poizon_api.fetch_product_detail",
            new=AsyncMock(return_value={
                "name": "Nike Vomero",
            }),
        ), patch(
            "services.parser.parse_poizon_html_specs",
            new=AsyncMock(return_value={
                "price": 188.0,
                "price_is_starting": True,
                "image_url": "https://img.example.com/vomero-html.jpg",
            }),
        ) as html_mock, patch(
            "services.parser.infer_category",
            return_value="sneakers",
        ), patch(
            "services.translator.translate_if_cn",
            new=AsyncMock(side_effect=lambda value: value),
        ), patch(
            "services.translator.translate_specs_with_groq",
            new=AsyncMock(side_effect=lambda value: value),
        ):
            payload = asyncio.run(_product_by_spu("123456"))

        self.assertIsNone(payload["price_cny"])
        self.assertFalse(payload["price_is_starting"])
        self.assertEqual(payload["image_url"], "https://img.example.com/vomero-html.jpg")
        html_mock.assert_awaited_once()

    def test_parse_poizon_html_specs_never_returns_html_price(self) -> None:
        html = """
        <html>
          <body>
            "title":"Huazi earrings"
            "saleProperties":{"list":[
              {"propertyId":1,"name":"Color","value":"Green"},
              {"propertyId":2,"name":"Box","value":"Gift"}
            ]}
            "key":"发售价","value":"¥888"
            "lowestPrice":"888"
          </body>
        </html>
        """

        with patch(
            "services.parser.resolve_url",
            new=AsyncMock(return_value="https://fast.dewu.com/page/productDetail?spuId=123456&sourceName=shareDetail"),
        ), patch(
            "services.parser._fetch",
            new=AsyncMock(return_value=html),
        ):
            result = asyncio.run(
                parse_poizon_html_specs("https://fast.dewu.com/page/productDetail?spuId=123456&sourceName=shareDetail")
            )

        self.assertNotIn("price", result)
        self.assertNotIn("price_is_starting", result)


if __name__ == "__main__":
    unittest.main()
