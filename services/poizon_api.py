"""RapidAPI client for Poizon/Dewu product details."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from config import RAPIDAPI_FALLBACK_HOST, RAPIDAPI_HOST, rapidapi_quota_period
from services.rapidapi_keys import get_rapidapi_keys, rotate_rapidapi_key_to_end

log = logging.getLogger(__name__)
POIZON_PROVIDER_PRICE_OFFSET_CNY = 2.0


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.isdigit():
            return float(cleaned)
    return None


def _apply_provider_price_offset(price: float | None) -> float | None:
    if price is None:
        return None
    return round(float(price) + POIZON_PROVIDER_PRICE_OFFSET_CNY, 2)


def _pick_price(data: dict[str, Any]) -> float | None:
    direct_candidates = [
        data.get("price"),
        data.get("currentPrice"),
        data.get("salePrice"),
        data.get("lowestPrice"),
        data.get("showPrice"),
    ]
    scaled_candidates = [data.get("authPrice")]
    for item in data.get("skuList") or []:
        if not isinstance(item, dict):
            continue
        direct_candidates.extend(
            [
                item.get("price"),
                item.get("currentPrice"),
                item.get("salePrice"),
                item.get("lowestPrice"),
            ]
        )
        scaled_candidates.append(item.get("minBidPrice"))
    for candidate in direct_candidates:
        price = _to_float(candidate)
        if price and 10 <= price <= 50000:
            return _apply_provider_price_offset(price)
    for candidate in scaled_candidates:
        price = _to_float(candidate)
        if price and 1000 <= price <= 5_000_000:
            normalized = price / 100
            if 10 <= normalized <= 50000:
                return _apply_provider_price_offset(normalized)
    return None


def _pick_lowest_price(data: dict[str, Any]) -> float | None:
    lowest_price = None
    for item in data.get("skuList") or []:
        if not isinstance(item, dict):
            continue
        price = _extract_sku_price(item)
        if price is None:
            continue
        lowest_price = price if lowest_price is None else min(lowest_price, price)
    return lowest_price if lowest_price is not None else _pick_price(data)


def _extract_sku_price(item: dict[str, Any]) -> float | None:
    min_bid = _to_float(item.get("minBidPrice"))
    if min_bid and 1000 <= min_bid <= 5_000_000:
        normalized = min_bid / 100
        if 10 <= normalized <= 50000:
            return _apply_provider_price_offset(normalized)
    return _pick_price({"skuList": [item], "authPrice": None})


def _pick_sizes(data: dict[str, Any]) -> list[str]:
    def _looks_like_size_name(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        lowered = value.strip().lower()
        if not lowered:
            return False
        return any(token in lowered for token in ("size", "尺码", "码数", "shoe size", "eu", "us"))

    sizes: list[str] = []
    for item in data.get("skuList") or []:
        if not isinstance(item, dict):
            continue
        if _extract_sku_price(item) is None:
            continue
        for key in ("size", "sizeName", "skuName", "skuTitle"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                size = value.strip()
                if size not in sizes:
                    sizes.append(size)
                break
        for attr in item.get("saleAttr") or []:
            if not isinstance(attr, dict):
                continue
            if not (
                _looks_like_size_name(attr.get("enName"))
                or _looks_like_size_name(attr.get("cnName"))
            ):
                continue
            value = attr.get("enValue") or attr.get("cnValue")
            if isinstance(value, str) and value.strip():
                size = value.strip()
                if size not in sizes:
                    sizes.append(size)
    return sizes


def _format_timestamp_ms(value: Any) -> str | None:
    try:
        numeric = int(str(value).strip())
    except Exception:
        return None
    if numeric <= 0:
        return None
    # Python 3.10 does not expose datetime.UTC; use timezone.utc instead.
    from datetime import datetime, timezone

    try:
        dt = datetime.fromtimestamp(numeric / 1000, tz=timezone.utc)
    except Exception:
        return None
    return dt.strftime("%Y-%m-%d")


def _extract_specs(data: dict[str, Any], selected_sku: dict[str, Any] | None = None) -> dict[str, str]:
    specs: dict[str, str] = {}
    field_map = [
        ("Brand", data.get("distBrandName")),
        ("Series", data.get("dwDesignerId")),
        ("Material", data.get("material")),
        ("Fit", data.get("distFitPeopleName")),
        ("Season", data.get("season")),
        ("Style", data.get("style")),
        ("Category", data.get("distCategoryl3Name") or data.get("distCategory3Name")),
        ("Category L2", data.get("distCategoryl2Name")),
        ("Category L1", data.get("distCategoryl1Name")),
        ("Release Date", _format_timestamp_ms(data.get("sellDate"))),
    ]
    for key, value in field_map:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                specs[key] = cleaned
    if selected_sku:
        barcode = str(selected_sku.get("barcode") or "").strip()
        if barcode:
            specs["Barcode"] = barcode
        sales = selected_sku.get("sales")
        if isinstance(sales, int | float) and sales > 0:
            specs["Sales"] = str(int(sales))
    return specs


def _extract_extra_images(data: dict[str, Any], primary_image: str | None) -> list[str]:
    images: list[str] = []
    for candidate in data.get("baseImage") or []:
        if not isinstance(candidate, str):
            continue
        image = candidate.strip()
        if not image:
            continue
        if primary_image and image == primary_image:
            continue
        if image not in images:
            images.append(image)
    return images


def _variant_price_key(pairs: list[tuple[str, str]]) -> str:
    normalized = sorted(
        (str(name).strip(), str(value).strip())
        for name, value in pairs
        if str(name).strip() and str(value).strip()
    )
    return json.dumps(normalized, ensure_ascii=False)


def _extract_variants_and_prices(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    groups: dict[str, dict[str, Any]] = {}
    sku_pairs: list[tuple[list[tuple[str, str]], float]] = []
    variant_price_map: dict[str, float] = {}

    for item in data.get("skuList") or []:
        if not isinstance(item, dict):
            continue
        price = _extract_sku_price(item)
        if price is None:
            continue
        sale_attrs = item.get("saleAttr") or []
        item_pairs: list[tuple[str, str]] = []
        for index, attr in enumerate(sale_attrs):
            if not isinstance(attr, dict):
                continue
            name = str(attr.get("enName") or attr.get("cnName") or "").strip()
            value = str(attr.get("enValue") or attr.get("cnValue") or "").strip()
            if not name or not value:
                continue
            try:
                level = int(str(attr.get("level") or "").strip())
            except Exception:
                level = index + 1
            group = groups.setdefault(name, {"name": name, "options": [], "level": level})
            group["level"] = min(int(group.get("level", level)), level)
            if value not in group["options"]:
                group["options"].append(value)
            item_pairs.append((name, value))

        if not item_pairs:
            continue
        sku_pairs.append((item_pairs, price))

    active_names = {
        group["name"]
        for group in groups.values()
        if len(group.get("options") or []) >= 2
    }
    for item_pairs, price in sku_pairs:
        active_pairs = [(name, value) for name, value in item_pairs if name in active_names]
        if active_pairs:
            variant_price_map[_variant_price_key(active_pairs)] = price

    variants = [
        {"name": group["name"], "options": group["options"]}
        for group in sorted(groups.values(), key=lambda item: (int(item.get("level", 999)), item["name"]))
        if len(group.get("options") or []) >= 2
    ]
    return variants, variant_price_map


async def fetch_keyword_search(
    client: httpx.AsyncClient,
    query: str,
    page_size: int = 20,
    start_id: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search Poizon/Dewu products by English keyword."""
    host_key_groups = [(RAPIDAPI_HOST, get_rapidapi_keys(RAPIDAPI_HOST))]
    if RAPIDAPI_FALLBACK_HOST:
        host_key_groups.append((RAPIDAPI_FALLBACK_HOST, get_rapidapi_keys(RAPIDAPI_FALLBACK_HOST)))

    if not any(keys for _, keys in host_key_groups):
        return [], 0

    params: dict[str, Any] = {
        "startId": start_id,
        "pageSize": page_size,
        "distSpuTitle": query,
    }

    payload = None
    for transport_client in (client, httpx.AsyncClient(timeout=15.0)):
        try:
            for host, keys in host_key_groups:
                if not keys:
                    continue
                for key_index, rapidapi_key in enumerate(keys, start=1):
                    headers = {
                        "x-rapidapi-key": rapidapi_key,
                        "x-rapidapi-host": host,
                    }
                    try:
                        response = await transport_client.get(
                            f"https://{host}/poizon/product/queryList",
                            headers=headers,
                            params=params,
                            timeout=15.0,
                        )
                        if response.status_code == 429:
                            rotate_rapidapi_key_to_end(host, rapidapi_key)
                            log.warning(
                                "keyword search quota hit host=%s key %s/%s",
                                host,
                                key_index,
                                len(keys),
                            )
                            continue
                        response.raise_for_status()
                        candidate = response.json()
                        data = candidate.get("data") if isinstance(candidate, dict) else None
                        if isinstance(data, dict) and data.get("spuList"):
                            payload = candidate
                            break
                        log.info(
                            "keyword search empty host=%s key %s/%s",
                            host,
                            key_index,
                            len(keys),
                        )
                    except Exception as e:
                        log.info("keyword search request error host=%s: %s", host, e)
                if payload is not None:
                    break
            if payload is not None:
                break
        finally:
            if transport_client is not client:
                await transport_client.aclose()

    if not payload:
        return [], 0

    data = payload.get("data", {})
    spu_list = data.get("spuList") or []

    last_id = data.get("lastId") or data.get("cursor") or 0
    if not last_id and len(spu_list) >= page_size:
        last_item = spu_list[-1] if spu_list else {}
        if isinstance(last_item, dict):
            last_id = (
                last_item.get("dwSpuId")
                or last_item.get("distSpuId")
                or last_item.get("id")
                or 0
            )

    results: list[dict[str, Any]] = []
    for item in spu_list:
        if not isinstance(item, dict):
            continue

        title = item.get("distSpuTitle") or item.get("dwSpuTitle") or ""
        image = item.get("image") or ""
        spu_id = str(item.get("dwSpuId") or "")
        category = (
            item.get("distCategoryl3Name")
            or item.get("distCategory3Name")
            or item.get("categoryName")
            or ""
        )

        # Search cards should use the lowest live SKU price, not the release price.
        price = _pick_lowest_price(item)

        # Extract full detail from the same item (same structure as queryDetail)
        sizes = _pick_sizes(item)
        variants, variant_price_map = _extract_variants_and_prices(item)
        specs = _extract_specs(item)
        extra_images = _extract_extra_images(item, image.strip() if isinstance(image, str) else None)

        entry: dict[str, Any] = {
            "spu_id": spu_id,
            "title": title.strip() if title else "",
            "image": image.strip() if image else "",
            "category": category.strip() if category else "",
            "price_cny": price,
        }
        if sizes:
            entry["available_sizes"] = sizes
        if variants:
            entry["variants"] = variants
        if variant_price_map:
            entry["variant_price_map"] = variant_price_map
        if specs:
            entry["specs"] = specs
        if extra_images:
            entry["extra_images"] = extra_images
        brand = item.get("distBrandName")
        if isinstance(brand, str) and brand.strip():
            entry["brand"] = brand.strip()

        results.append(entry)

    # Attach last_id for cursor-based pagination
    return results, last_id


async def fetch_product_detail(
    client: httpx.AsyncClient,
    spu_id: str,
    sku_id: str | None = None,
    designer_id: str | None = None,
) -> dict[str, Any]:
    host_key_groups = [(RAPIDAPI_HOST, get_rapidapi_keys(RAPIDAPI_HOST))]
    if RAPIDAPI_FALLBACK_HOST:
        host_key_groups.append((RAPIDAPI_FALLBACK_HOST, get_rapidapi_keys(RAPIDAPI_FALLBACK_HOST)))

    if not any(keys for _, keys in host_key_groups):
        return {}
    params = {"dwSpuId": spu_id}
    if sku_id:
        params["dwSkuId"] = sku_id
    if designer_id:
        params["dwDesignerId"] = designer_id

    payload = None
    for host, keys in host_key_groups:
        if not keys:
            continue
        for key_index, rapidapi_key in enumerate(keys, start=1):
            headers = {
                "x-rapidapi-key": rapidapi_key,
                "x-rapidapi-host": host,
                "Content-Type": "application/json",
            }
            try:
                response = await client.get(
                    f"https://{host}/poizon/product/queryDetail",
                    headers=headers,
                    params=params,
                    timeout=15.0,
                )
                if response.status_code == 429:
                    rotate_rapidapi_key_to_end(host, rapidapi_key)
                    log.warning(
                        "rapidapi poizon quota hit for host=%s key %s/%s (quota resets: %s)",
                        host,
                        key_index,
                        len(keys),
                        rapidapi_quota_period(host),
                    )
                    continue
                response.raise_for_status()
                candidate_payload = response.json()
                data = candidate_payload.get("data") if isinstance(candidate_payload, dict) else None
                if isinstance(data, dict) and data:
                    payload = candidate_payload
                    break
                log.info(
                    "rapidapi poizon empty payload for host=%s key %s/%s",
                    host,
                    key_index,
                    len(keys),
                )
            except Exception as e:
                log.info(
                    "rapidapi poizon error host=%s key %s/%s: %s",
                    host,
                    key_index,
                    len(keys),
                    e,
                )
        if payload is not None:
            break

    if payload is None:
        return {}

    data = payload.get("data")
    if not isinstance(data, dict):
        return {}

    result: dict[str, Any] = {}
    title = data.get("distSpuTitle") or data.get("dwSpuTitle")
    image = data.get("image")
    category = (
        data.get("distCategory3Name")
        or data.get("distCategoryl3Name")
        or data.get("categoryName")
    )
    price = None
    selected_sku = None
    if sku_id:
        for item in data.get("skuList") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("dwSkuId")) == str(sku_id) or str(item.get("distSkuId")) == str(sku_id):
                selected_sku = item
                break

    if selected_sku:
        selected_min_bid = _to_float(selected_sku.get("minBidPrice"))
        if selected_min_bid and 1000 <= selected_min_bid <= 5_000_000:
            normalized = selected_min_bid / 100
            if 10 <= normalized <= 50000:
                price = _apply_provider_price_offset(normalized)
        if price is None:
            selected_data = dict(data)
            selected_data["skuList"] = [selected_sku]
            selected_data["authPrice"] = None
            price = _pick_price(selected_data)
        if isinstance(selected_sku.get("image"), str) and selected_sku.get("image").strip():
            image = selected_sku.get("image").strip()
        sale_attrs = selected_sku.get("saleAttr") or []
        selected_values = []
        for attr in sale_attrs:
            if not isinstance(attr, dict):
                continue
            value = attr.get("enValue") or attr.get("cnValue")
            if isinstance(value, str) and value.strip():
                selected_values.append(value.strip())
        if selected_values:
            result["selected_variant"] = " / ".join(selected_values)

    if price is None:
        price = _pick_price(data)
    sizes = _pick_sizes(data)
    variants, variant_price_map = _extract_variants_and_prices(data)
    specs = _extract_specs(data, selected_sku=selected_sku)
    extra_images = _extract_extra_images(data, image.strip() if isinstance(image, str) else None)

    if isinstance(title, str) and title.strip():
        result["name"] = title.strip()
    if isinstance(image, str) and image.strip():
        result["image_url"] = image.strip()
    if isinstance(category, str) and category.strip():
        result["cn_category"] = category.strip()
    if price is not None:
        result["price"] = price
    if sizes:
        result["available_sizes"] = sizes
    if specs:
        result["specs"] = specs
    if extra_images:
        result["extra_images"] = extra_images
    if variants:
        result["variants"] = variants
    if variant_price_map:
        result["variant_price_map"] = variant_price_map

    return result
