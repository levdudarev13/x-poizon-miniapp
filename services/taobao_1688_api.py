"""RapidAPI clients for Taobao/Tmall/1688 providers."""

from __future__ import annotations

import logging
import re
import json
from typing import Any

import httpx

from config import (
    DATAHUB_1688_RAPIDAPI_HOST,
    DATAHUB_1688_RAPIDAPI_KEYS,
    OPEN_1688_RAPIDAPI_HOST,
    OPEN_1688_RAPIDAPI_KEYS,
    rapidapi_quota_period,
    TAOBAO_DATA_RAPIDAPI_HOST,
    TAOBAO_DATA_RAPIDAPI_KEYS,
    TAOBAO_1688_RAPIDAPI_HOST,
    TAOBAO_1688_RAPIDAPI_KEYS,
    TAOBAO_TMALL_RAPIDAPI_HOST,
    TAOBAO_TMALL_RAPIDAPI_KEYS,
)
from services.rapidapi_keys import get_rapidapi_keys, rotate_rapidapi_key_to_end

log = logging.getLogger(__name__)


class TaobaoSearchUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("taobao_search_unavailable")


class Open1688SearchUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("1688_search_unavailable")


def _normalize_image(url: str | None) -> str:
    if not isinstance(url, str) or not url.strip():
        return ""
    normalized = url.strip()
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    if normalized.startswith("https://img.alicdn.com/imgextra///img.alicdn.com/"):
        normalized = normalized.replace(
            "https://img.alicdn.com/imgextra///img.alicdn.com/",
            "https://img.alicdn.com/",
            1,
        )
    if normalized.startswith("http://img.alicdn.com/imgextra///img.alicdn.com/"):
        normalized = normalized.replace(
            "http://img.alicdn.com/imgextra///img.alicdn.com/",
            "https://img.alicdn.com/",
            1,
        )
    return normalized


def _canonicalize_taobao_item_url(detail_url: str | None, item_id: str) -> str:
    if isinstance(detail_url, str) and detail_url.strip():
        return detail_url.strip()
    return f"https://item.taobao.com/item.htm?id={item_id}" if item_id else ""


def _canonicalize_1688_item_url(detail_url: str | None, item_id: str) -> str:
    if item_id:
        return f"https://detail.1688.com/offer/{item_id}.html"
    if not isinstance(detail_url, str) or not detail_url.strip():
        return ""
    normalized = detail_url.strip()
    if normalized.startswith("//"):
        normalized = f"https:{normalized}"
    elif normalized.startswith("http://"):
        normalized = f"https://{normalized[7:]}"
    return normalized


def _contains_non_latin_script(value: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF\u4E00-\u9FFF]", value or ""))


def _normalize_open_1688_keyword_query(query: str) -> str:
    normalized = str(query or "").strip()
    if not normalized:
        return ""
    if re.search(r"[A-Z]", normalized):
        return normalized
    first_latin = re.search(r"[A-Za-z]", normalized)
    if not first_latin:
        return normalized
    index = first_latin.start()
    return f"{normalized[:index]}{normalized[index].upper()}{normalized[index + 1:]}"


def build_open_1688_keyword_search_query(original_query: str, translated_query: str) -> str:
    original = str(original_query or "").strip()
    translated = str(translated_query or "").strip()
    if re.search(r"[A-Za-z]", original) and not _contains_non_latin_script(original):
        return _normalize_open_1688_keyword_query(original)
    return _normalize_open_1688_keyword_query(translated or original)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _extract_numeric_values(value: Any) -> list[float]:
    if value is None or value == "":
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, (list, tuple, set)):
        numbers: list[float] = []
        for entry in value:
            numbers.extend(_extract_numeric_values(entry))
        return numbers
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        direct = _to_float(cleaned)
        if direct is not None:
            return [direct]
        return [float(match) for match in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    return []


def _extract_price_value_and_starting(*candidates: Any) -> tuple[float | None, bool]:
    for candidate in candidates:
        numbers = _extract_numeric_values(candidate)
        if not numbers:
            continue
        return min(numbers), len(numbers) > 1
    return None, False


def _looks_like_size(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("size", "尺码", "码数"))


def _extract_variants(prop_list: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    variants: list[dict[str, Any]] = []
    sizes: list[str] = []
    if not isinstance(prop_list, list):
        return variants, sizes

    for group in prop_list:
        if not isinstance(group, dict):
            continue
        name = str(
            group.get("originalPropName")
            or group.get("propName")
            or group.get("name")
            or ""
        ).strip()
        options: list[str] = []
        for item in group.get("prop_value") or group.get("prop_value_list") or group.get("valueList") or []:
            if not isinstance(item, dict):
                continue
            value = str(
                item.get("originalValueName")
                or item.get("valueName")
                or item.get("value")
                or item.get("name")
                or ""
            ).strip()
            if value and value not in options:
                options.append(value)
        if name and options:
            variants.append({"name": name, "options": options})
            if _looks_like_size(name):
                for option in options:
                    if option not in sizes:
                        sizes.append(option)
    return variants, sizes


def _split_property_options(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    parts = re.split(r"[,，/]", value)
    options: list[str] = []
    for part in parts:
        normalized = str(part).strip()
        if normalized and normalized not in options:
            options.append(normalized)
    return options


def _extract_variants_from_properties(prop_list: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    variants: list[dict[str, Any]] = []
    sizes: list[str] = []
    if not isinstance(prop_list, list):
        return variants, sizes

    for item in prop_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        raw_value = item.get("value")
        options = _split_property_options(raw_value)
        if len(options) < 2:
            continue
        variants.append({"name": name, "options": options})
        if _looks_like_size(name) or any(token in name for token in ("尺码", "码数")):
            for option in options:
                if option not in sizes:
                    sizes.append(option)
    return variants, sizes


def _variant_price_key(pairs: list[tuple[str, str]]) -> str:
    normalized = sorted((str(name).strip(), str(value).strip()) for name, value in pairs if str(name).strip() and str(value).strip())
    return json.dumps(normalized, ensure_ascii=False)


def _merge_missing_fields(preferred: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(preferred)
    for key, value in fallback.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def _append_unique(values: list[str], candidate: str | None) -> None:
    normalized = _normalize_image(candidate)
    if normalized and normalized not in values:
        values.append(normalized)


def _looks_like_taobao_item(candidate: Any) -> bool:
    return isinstance(candidate, dict) and any(
        key in candidate
        for key in (
            "title",
            "price",
            "pic_url",
            "item_imgs",
            "num_iid",
            "item_prop_list",
            "detail_url",
            "Title",
            "OriginalTitle",
            "Price",
            "MainPictureUrl",
            "Pictures",
            "Id",
            "Attributes",
            "Props",
            "itemId",
            "item_id",
            "mainImgUrlList",
            "productPropList",
            "productSkuInfo",
            "productName",
            "originalProductName",
        )
    )


def _extract_taobao_item_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data_block = payload.get("data")
    if _looks_like_taobao_item(data_block):
        return data_block

    if _looks_like_taobao_item(payload):
        return payload

    queue: list[dict[str, Any]] = [payload]
    while queue:
        current = queue.pop(0)
        for value in current.values():
            if isinstance(value, dict):
                if _looks_like_taobao_item(value):
                    return value
                queue.append(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        if _looks_like_taobao_item(entry):
                            return entry
                        queue.append(entry)
    return {}


def _extract_html_image_urls(html: Any) -> list[str]:
    if not isinstance(html, str) or not html.strip():
        return []

    images: list[str] = []
    for match in re.finditer(r"""<img[^>]+src=["']([^"']+)["']""", html, flags=re.IGNORECASE):
        _append_unique(images, match.group(1))
    return images


def _build_variant_price_map_from_1688_skus(item: dict[str, Any], active_variant_names: set[str]) -> dict[str, float]:
    variant_price_map: dict[str, float] = {}
    for sku in item.get("item_sku_list") or []:
        if not isinstance(sku, dict):
            continue

        price_value = _to_float(sku.get("price_real")) or _to_float(sku.get("price"))
        if price_value is None:
            continue

        raw_prop_value = sku.get("prop_value")
        pairs: list[tuple[str, str]] = []
        if isinstance(raw_prop_value, str) and raw_prop_value.strip():
            try:
                prop_map = json.loads(raw_prop_value)
            except Exception:
                prop_map = None
            if isinstance(prop_map, dict):
                for name, value in prop_map.items():
                    label = str(name or "").strip()
                    option = str(value or "").strip()
                    if label and option and label in active_variant_names:
                        pairs.append((label, option))

        if not pairs:
            continue
        variant_price_map[_variant_price_key(pairs)] = price_value

    return variant_price_map


def _build_variant_price_map_from_data_item(item: dict[str, Any], active_variant_names: set[str]) -> dict[str, float]:
    variant_price_map: dict[str, float] = {}
    sku_info = item.get("productSkuInfo")
    if not isinstance(sku_info, dict):
        return variant_price_map

    for sku in sku_info.values():
        if not isinstance(sku, dict):
            continue

        price_value = _to_float(sku.get("price"))
        if price_value is None:
            for price_range in sku.get("priceRanges") or []:
                if not isinstance(price_range, dict):
                    continue
                price_value = _to_float(price_range.get("price"))
                if price_value is not None:
                    break
        if price_value is None:
            continue

        pairs: list[tuple[str, str]] = []
        for prop in sku.get("skuPropList") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("originalPropName") or prop.get("propName") or "").strip()
            value = str(prop.get("originalValueName") or prop.get("valueName") or "").strip()
            if name and value and name in active_variant_names:
                pairs.append((name, value))
        if not pairs:
            continue
        variant_price_map[_variant_price_key(pairs)] = price_value

    return variant_price_map


def _build_variant_groups_from_open_1688_skus(
    sku_list: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    variants: list[dict[str, Any]] = []
    sizes: list[str] = []
    groups_by_name: dict[str, dict[str, Any]] = {}

    if not isinstance(sku_list, list):
        return variants, sizes

    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        for attr in sku.get("skuAttributes") or []:
            if not isinstance(attr, dict):
                continue
            name = str(attr.get("attributeNameTrans") or attr.get("attributeName") or "").strip()
            value = str(attr.get("valueTrans") or attr.get("value") or "").strip()
            if not name or not value:
                continue
            group = groups_by_name.get(name)
            if group is None:
                group = {"name": name, "options": []}
                groups_by_name[name] = group
                variants.append(group)
            if value not in group["options"]:
                group["options"].append(value)
            if _looks_like_size(name) and value not in sizes:
                sizes.append(value)

    return variants, sizes


def _build_variant_price_map_from_open_1688_skus(
    sku_list: list[dict[str, Any]] | None,
    active_variant_names: set[str],
) -> dict[str, float]:
    variant_price_map: dict[str, float] = {}
    if not isinstance(sku_list, list):
        return variant_price_map

    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        fenxiao_price = sku.get("fenxiaoPriceInfo") if isinstance(sku.get("fenxiaoPriceInfo"), dict) else {}
        price_value, _ = _extract_price_value_and_starting(
            sku.get("promotionPrice"),
            sku.get("consignPrice"),
            sku.get("price"),
            fenxiao_price.get("offerPrice"),
        )
        if price_value is None:
            continue

        pairs: list[tuple[str, str]] = []
        for attr in sku.get("skuAttributes") or []:
            if not isinstance(attr, dict):
                continue
            name = str(attr.get("attributeNameTrans") or attr.get("attributeName") or "").strip()
            value = str(attr.get("valueTrans") or attr.get("value") or "").strip()
            if name and value and name in active_variant_names:
                pairs.append((name, value))
        if not pairs:
            continue
        variant_price_map[_variant_price_key(pairs)] = price_value

    return variant_price_map


def _append_spec_value(specs: dict[str, str], name: str, value: str) -> None:
    normalized_name = str(name or "").strip()
    normalized_value = str(value or "").strip()
    if not normalized_name or not normalized_value:
        return

    current = specs.get(normalized_name)
    if not current:
        specs[normalized_name] = normalized_value
        return

    existing_values = [part.strip() for part in current.split(",")]
    if normalized_value not in existing_values:
        specs[normalized_name] = f"{current}, {normalized_value}"


def _extract_open_1688_weight(item: dict[str, Any]) -> float | None:
    package_info = item.get("packageInfo")
    if isinstance(package_info, dict):
        for key in ("weight", "totalWeight", "officialWeight", "aiWeight"):
            weight = _to_float(package_info.get(key))
            if weight and weight > 0:
                return weight

    for package in item.get("productPackageInfos") or []:
        if not isinstance(package, dict):
            continue
        for key in ("weight", "officialWeight", "aiWeight"):
            weight = _to_float(package.get(key))
            if weight and weight > 0:
                return weight

    return None


async def _request_json(
    client: httpx.AsyncClient,
    *,
    host: str,
    keys: tuple[str, ...],
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    current_keys = get_rapidapi_keys(host) or keys
    if not current_keys:
        return {}

    for key_index, rapidapi_key in enumerate(current_keys, start=1):
        headers = {
            "x-rapidapi-key": rapidapi_key,
            "x-rapidapi-host": host,
            "Content-Type": "application/json",
        }
        try:
            response = await client.request(
                method,
                f"https://{host}{path}",
                headers=headers,
                params=params,
                json=json_body,
                timeout=timeout_seconds,
            )
            if response.status_code == 429:
                rotate_rapidapi_key_to_end(host, rapidapi_key)
                log.warning(
                    "rapidapi quota hit for %s key %s/%s (quota resets: %s)",
                    host,
                    key_index,
                    len(current_keys),
                    rapidapi_quota_period(host),
                )
                continue
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception as e:
            log.info("rapidapi request error host=%s path=%s: %s", host, path, e)
    return {}


async def fetch_taobao_1688_item_by_url(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=TAOBAO_1688_RAPIDAPI_HOST,
        keys=TAOBAO_1688_RAPIDAPI_KEYS,
        method="POST",
        path="/api/tkl/item/url",
        json_body={"url": url},
        timeout_seconds=8.0,
    )
    item = payload.get("item")
    return item if isinstance(item, dict) else {}


async def fetch_taobao_data_item_detail(client: httpx.AsyncClient, item_id: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=TAOBAO_DATA_RAPIDAPI_HOST,
        keys=TAOBAO_DATA_RAPIDAPI_KEYS,
        method="GET",
        path="/sunie/detail",
        params={"site": "taobao", "itemId": item_id},
        timeout_seconds=10.0,
    )
    item = _extract_taobao_item_from_payload(payload)
    if not item:
        return {}
    if not any(item.get(key) for key in ("num_iid", "Id", "itemId", "item_id")):
        item = {**item, "num_iid": item_id}
    return item


async def fetch_taobao_1688_item_detail(
    client: httpx.AsyncClient,
    *,
    provider: str,
    item_id: str,
) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=TAOBAO_1688_RAPIDAPI_HOST,
        keys=TAOBAO_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/api/tkl/item/detail",
        params={"provider": provider, "id": item_id},
        timeout_seconds=8.0,
    )
    item = payload.get("item")
    return item if isinstance(item, dict) else {}


async def fetch_taobao_tmall_full_info(client: httpx.AsyncClient, item_id: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=TAOBAO_TMALL_RAPIDAPI_HOST,
        keys=TAOBAO_TMALL_RAPIDAPI_KEYS,
        method="GET",
        path="/BatchGetItemFullInfo",
        params={"language": "en", "itemId": item_id},
        timeout_seconds=10.0,
    )
    result = payload.get("Result")
    if not isinstance(result, dict):
        return {}
    item = result.get("Item")
    return item if isinstance(item, dict) else {}


def _build_taobao_tmall_search_results(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    result = payload.get("Result")
    if not isinstance(result, dict):
        return [], 0

    items_block = result.get("Items")
    if not isinstance(items_block, dict):
        return [], 0

    items = items_block.get("Items")
    if not isinstance(items, dict):
        return [], 0

    content = items.get("Content") or []
    if not isinstance(content, list):
        return [], 0

    try:
        total_count = int(items.get("TotalCount") or 0)
    except (TypeError, ValueError):
        total_count = 0

    results: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict) or item.get("HasError"):
            continue

        item_id = str(item.get("Id") or "").strip()
        title = str(item.get("Title") or item.get("OriginalTitle") or "").strip()
        detail_url = _canonicalize_taobao_item_url(
            item.get("TaobaoItemUrl") or item.get("ExternalItemUrl"),
            item_id,
        )
        image_url = _normalize_image(item.get("MainPictureUrl"))

        extra_images: list[str] = []
        for picture in item.get("Pictures") or []:
            if not isinstance(picture, dict):
                continue
            normalized = _normalize_image(picture.get("Url"))
            if normalized and normalized not in extra_images:
                extra_images.append(normalized)

        if not image_url and extra_images:
            image_url = extra_images[0]

        price_block = item.get("Price") if isinstance(item.get("Price"), dict) else {}
        price_value = _to_float(price_block.get("OriginalPrice")) or _to_float(price_block.get("MarginPrice"))

        entry: dict[str, Any] = {
            "platform": "taobao",
            "item_id": item_id,
            "title": title,
            "image": image_url,
            "price_cny": price_value,
            "detail_url": detail_url,
            "url": detail_url,
            "category": str(item.get("ExternalCategoryId") or item.get("CategoryId") or "").strip(),
        }

        original_title = str(item.get("OriginalTitle") or "").strip()
        if original_title:
            entry["original_title"] = original_title

        brand_name = str(item.get("BrandName") or "").strip()
        if brand_name:
            entry["brand"] = brand_name

        vendor_name = str(item.get("VendorDisplayName") or item.get("VendorName") or "").strip()
        if vendor_name:
            entry["vendor"] = vendor_name

        if extra_images:
            entry["extra_images"] = extra_images

        results.append(entry)

    return results, total_count


async def fetch_taobao_tmall_keyword_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    frame_size: int = 20,
    frame_position: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    payload = await _request_json(
        client,
        host=TAOBAO_TMALL_RAPIDAPI_HOST,
        keys=TAOBAO_TMALL_RAPIDAPI_KEYS,
        method="GET",
        path="/BatchSearchItemsFrame",
        params={
            "framePosition": frame_position,
            "frameSize": frame_size,
            "ItemTitle": query,
        },
        timeout_seconds=10.0,
    )
    if not payload:
        raise TaobaoSearchUnavailableError()
    return _build_taobao_tmall_search_results(payload)


def _build_open_1688_search_results(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    data_block = payload.get("data")
    if not isinstance(data_block, dict):
        return [], 0

    raw_items = data_block.get("data") or []
    if not isinstance(raw_items, list):
        return [], 0

    try:
        total_count = int(data_block.get("totalRecords") or 0)
    except (TypeError, ValueError):
        total_count = 0

    results: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        item_id = str(item.get("offerId") or "").strip()
        title = str(item.get("subjectTrans") or item.get("subject") or "").strip()
        original_title = str(item.get("subject") or "").strip()
        detail_url = _canonicalize_1688_item_url(
            item.get("promotionURL") or item.get("promotionUrl"),
            item_id,
        )
        image_url = _normalize_image(item.get("imageUrl") or item.get("image"))
        price_info = item.get("priceInfo") if isinstance(item.get("priceInfo"), dict) else {}
        price_value, price_is_starting = _extract_price_value_and_starting(
            price_info.get("promotionPrice"),
            price_info.get("price"),
            price_info.get("offerPrice"),
        )

        entry: dict[str, Any] = {
            "platform": "1688",
            "item_id": item_id,
            "title": title or original_title,
            "image": image_url,
            "price_cny": price_value,
            "price_is_starting": price_is_starting,
            "detail_url": detail_url,
            "url": detail_url,
        }

        if original_title and original_title != entry["title"]:
            entry["original_title"] = original_title

        company_name = str(item.get("companyName") or "").strip()
        if company_name:
            entry["vendor"] = company_name

        month_sold = item.get("monthSold")
        if month_sold not in (None, ""):
            entry["month_sold"] = month_sold

        repurchase_rate = item.get("repurchaseRate")
        if repurchase_rate not in (None, ""):
            entry["repurchase_rate"] = repurchase_rate

        min_order_quantity = _to_float(item.get("minOrderQuantity"))
        if min_order_quantity is not None:
            entry["min_order_quantity"] = int(min_order_quantity)

        results.append(entry)

    return results, total_count


async def fetch_open_1688_keyword_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    page_size: int = 20,
    start_id: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    safe_page_size = max(1, min(50, int(page_size or 20)))
    safe_start_id = max(0, int(start_id or 0))
    begin_page = (safe_start_id // safe_page_size) + 1
    payload = await _request_json(
        client,
        host=OPEN_1688_RAPIDAPI_HOST,
        keys=OPEN_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/alibaba/product/keywordQuery",
        params={
            "keyword": _normalize_open_1688_keyword_query(query),
            "country": "en",
            "beginPage": begin_page,
        },
        timeout_seconds=12.0,
    )
    if not payload:
        raise Open1688SearchUnavailableError()
    return _build_open_1688_search_results(payload)


async def fetch_open_1688_product_detail(client: httpx.AsyncClient, offer_id: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=OPEN_1688_RAPIDAPI_HOST,
        keys=OPEN_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/alibaba/product/queryProductDetail",
        params={
            "offerId": offer_id,
            "country": "en",
        },
        timeout_seconds=12.0,
    )
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


async def fetch_1688_datahub_simple(client: httpx.AsyncClient, item_id: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=DATAHUB_1688_RAPIDAPI_HOST,
        keys=DATAHUB_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/item_detail_simple",
        params={"itemId": item_id},
        timeout_seconds=10.0,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    result_list = result.get("resultList") or []
    if isinstance(result_list, list) and result_list and isinstance(result_list[0], dict):
        return result_list[0]
    return {}


async def fetch_1688_datahub_detail(client: httpx.AsyncClient, item_id: str) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=DATAHUB_1688_RAPIDAPI_HOST,
        keys=DATAHUB_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/item_detail",
        params={"itemId": item_id},
        timeout_seconds=10.0,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    item = result.get("item")
    return item if isinstance(item, dict) else {}


async def fetch_1688_datahub_package(
    client: httpx.AsyncClient,
    *,
    item_id: str,
    store_id: str,
) -> dict[str, Any]:
    payload = await _request_json(
        client,
        host=DATAHUB_1688_RAPIDAPI_HOST,
        keys=DATAHUB_1688_RAPIDAPI_KEYS,
        method="GET",
        path="/package_detail",
        params={"itemId": item_id, "storeId": store_id},
        timeout_seconds=10.0,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        return {}
    delivery = result.get("delivery")
    return delivery if isinstance(delivery, dict) else {}


def build_info_from_taobao_1688_item(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}

    result: dict[str, Any] = {}
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        result["name"] = title.strip()

    price = _to_float(item.get("price"))
    if price is not None:
        result["price"] = price

    image_url = _normalize_image(item.get("pic_url"))
    if image_url:
        result["image_url"] = image_url

    extra_images = []
    for image in item.get("item_imgs") or []:
        if not isinstance(image, dict):
            continue
        normalized = _normalize_image(image.get("url"))
        if normalized and normalized not in extra_images:
            extra_images.append(normalized)

    for group in item.get("item_prop_list") or []:
        if not isinstance(group, dict):
            continue
        for value in group.get("prop_value_list") or group.get("prop_value") or []:
            if not isinstance(value, dict):
                continue
            _append_unique(extra_images, value.get("image"))

    for sku in item.get("item_sku_list") or []:
        if not isinstance(sku, dict):
            continue
        _append_unique(extra_images, sku.get("img_url"))

    if extra_images:
        result["extra_images"] = extra_images
        if "image_url" not in result:
            result["image_url"] = extra_images[0]

    shop_name = item.get("shop_name")
    if isinstance(shop_name, str) and shop_name.strip():
        result["brand"] = shop_name.strip()

    variants, sizes = _extract_variants(item.get("item_prop_list"))
    if variants:
        result["variants"] = variants
    if sizes:
        result["available_sizes"] = sizes

    active_variant_names = {
        str(group.get("name") or "").strip()
        for group in variants
        if len(group.get("options") or []) >= 2
    }
    variant_price_map = _build_variant_price_map_from_1688_skus(item, active_variant_names)
    if variant_price_map:
        result["variant_price_map"] = variant_price_map

    item_id = str(item.get("num_iid") or "").strip()
    if item_id:
        result["item_id"] = item_id

    detail_url = _canonicalize_taobao_item_url(item.get("detail_url"), item_id)
    if detail_url:
        result["detail_url"] = detail_url

    return result


def build_info_from_taobao_data_item(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}

    result = build_info_from_taobao_1688_item(item)
    result = _merge_missing_fields(result, build_info_from_taobao_tmall_full_info(item))

    title = (
        item.get("productName")
        or item.get("originalProductName")
        or item.get("name")
        or item.get("item_title")
    )
    if isinstance(title, str) and title.strip() and not result.get("name"):
        result["name"] = title.strip()

    price = (
        _to_float(item.get("skuPriceRanges", {}).get("minPrice") if isinstance(item.get("skuPriceRanges"), dict) else None)
        or _to_float((item.get("priceRanges") or [{}])[0].get("price") if isinstance(item.get("priceRanges"), list) and item.get("priceRanges") else None)
        or _to_float(item.get("sale_price"))
        or _to_float(item.get("price_text"))
        or _to_float(item.get("price_value"))
    )
    if price is not None and not result.get("price"):
        result["price"] = price

    image_url = _normalize_image(
        item.get("mainImgUrl")
        or (item.get("mainImgUrlList") or [None])[0]
        or item.get("image")
        or item.get("image_url")
        or item.get("main_image")
    )
    if image_url and not result.get("image_url"):
        result["image_url"] = image_url

    extra_images = list(result.get("extra_images") or [])
    for image in item.get("mainImgUrlList") or []:
        if isinstance(image, dict):
            _append_unique(extra_images, image.get("url") or image.get("Url"))
        else:
            _append_unique(extra_images, image)
    for image in item.get("images") or item.get("image_list") or []:
        if isinstance(image, dict):
            _append_unique(extra_images, image.get("url") or image.get("Url") or image.get("image"))
        else:
            _append_unique(extra_images, image)
    for image in _extract_html_image_urls(item.get("description")):
        _append_unique(extra_images, image)
    for group in item.get("productPropList") or []:
        if not isinstance(group, dict):
            continue
        for value in group.get("valueList") or []:
            if not isinstance(value, dict):
                continue
            _append_unique(extra_images, value.get("imgUrl"))
    for sku in (item.get("productSkuInfo") or {}).values():
        if not isinstance(sku, dict):
            continue
        _append_unique(extra_images, sku.get("imgUrl"))
    if extra_images:
        result["extra_images"] = extra_images
        if not result.get("image_url"):
            result["image_url"] = extra_images[0]

    brand = item.get("originalShopName") or item.get("shopName") or item.get("brand_name") or item.get("seller_name")
    if isinstance(brand, str) and brand.strip() and not result.get("brand"):
        result["brand"] = brand.strip()

    item_id = str(
        item.get("productId")
        or item.get("item_id")
        or item.get("itemId")
        or item.get("num_iid")
        or item.get("Id")
        or ""
    ).strip()
    if item_id and not result.get("item_id"):
        result["item_id"] = item_id

    detail_url = _canonicalize_taobao_item_url(
        item.get("originalProductUrl") or item.get("detail_url") or item.get("item_url") or item.get("url"),
        result.get("item_id") or item_id,
    )
    if detail_url and not result.get("detail_url"):
        result["detail_url"] = detail_url

    prop_list = item.get("productPropList") or item.get("item_prop_list") or item.get("props") or item.get("sku_props")
    variants, sizes = _extract_variants(prop_list)
    if variants and not result.get("variants"):
        result["variants"] = variants
    if sizes and not result.get("available_sizes"):
        result["available_sizes"] = sizes

    active_variant_names = {
        str(group.get("name") or "").strip()
        for group in result.get("variants") or []
        if len(group.get("options") or []) >= 2
    }
    variant_price_map = _build_variant_price_map_from_data_item(item, active_variant_names)
    if variant_price_map and not result.get("variant_price_map"):
        result["variant_price_map"] = variant_price_map

    specs: dict[str, str] = {}
    for attr in item.get("productAttributeList") or []:
        if not isinstance(attr, dict):
            continue
        name = str(attr.get("originalAttrName") or attr.get("attrName") or attr.get("name") or "").strip()
        value = str(attr.get("originalAttrValue") or attr.get("attrValue") or attr.get("value") or "").strip()
        if name and value and name not in specs:
            specs[name] = value
    if specs and not result.get("specs"):
        result["specs"] = specs

    return result


def build_info_from_taobao_tmall_full_info(item: dict[str, Any]) -> dict[str, Any]:
    if not item or item.get("HasError"):
        return {}

    result: dict[str, Any] = {}
    title = item.get("OriginalTitle") or item.get("Title")
    if isinstance(title, str) and title.strip():
        result["name"] = title.strip()

    vendor_name = item.get("BrandName") or item.get("VendorDisplayName") or item.get("VendorName")
    if isinstance(vendor_name, str) and vendor_name.strip():
        result["brand"] = vendor_name.strip()

    image_url = _normalize_image(item.get("MainPictureUrl"))
    if image_url:
        result["image_url"] = image_url

    extra_images = []
    for image in item.get("Pictures") or []:
        if not isinstance(image, dict):
            continue
        normalized = _normalize_image(image.get("Url"))
        if normalized and normalized not in extra_images:
            extra_images.append(normalized)
    if extra_images:
        result["extra_images"] = extra_images
        if "image_url" not in result:
            result["image_url"] = extra_images[0]

    price = item.get("Price") or {}
    if isinstance(price, dict):
        price_value = _to_float(price.get("OriginalPrice")) or _to_float(price.get("MarginPrice"))
        if price_value is not None:
            result["price"] = price_value

    item_id = str(item.get("Id") or "").strip()
    if item_id:
        result["item_id"] = item_id

    detail_url = _canonicalize_taobao_item_url(
        item.get("TaobaoItemUrl") or item.get("ExternalItemUrl"),
        item_id,
    )
    if detail_url:
        result["detail_url"] = detail_url

    variants = []
    sizes = []
    variant_labels: dict[tuple[str, str], tuple[str, str]] = {}
    specs: dict[str, str] = {}

    for attr in item.get("Attributes") or []:
        if not isinstance(attr, dict):
            continue
        pid = str(attr.get("Pid") or "").strip()
        vid = str(attr.get("Vid") or "").strip()
        name = str(attr.get("OriginalPropertyName") or attr.get("PropertyName") or "").strip()
        value = str(attr.get("OriginalValue") or attr.get("Value") or "").strip()
        if not name or not value:
            continue
        if attr.get("IsConfigurator"):
            group = next((g for g in variants if g["name"] == name), None)
            if group is None:
                group = {"name": name, "options": []}
                variants.append(group)
            if value not in group["options"]:
                group["options"].append(value)
            if _looks_like_size(name) and value not in sizes:
                sizes.append(value)
            if pid and vid:
                variant_labels[(pid, vid)] = (name, value)
        elif name not in specs:
            specs[name] = value

    if not variants:
        for prop in item.get("Props") or []:
            if not isinstance(prop, dict):
                continue
            name = str(prop.get("Name") or "").strip()
            values = []
            for value in prop.get("Values") or []:
                if not isinstance(value, dict):
                    continue
                label = str(value.get("Name") or value.get("Value") or "").strip()
                if label and label not in values:
                    values.append(label)
            if name and values:
                variants.append({"name": name, "options": values})
                if _looks_like_size(name):
                    for label in values:
                        if label not in sizes:
                            sizes.append(label)

    if variants:
        result["variants"] = variants
    if sizes:
        result["available_sizes"] = sizes
    if specs:
        result["specs"] = specs

    active_variant_names = {
        str(group.get("name") or "").strip()
        for group in variants
        if len(group.get("options") or []) >= 2
    }
    variant_price_map: dict[str, float] = {}
    for configured in item.get("ConfiguredItems") or []:
        if not isinstance(configured, dict):
            continue
        config_pairs: list[tuple[str, str]] = []
        for config in configured.get("Configurators") or []:
            if not isinstance(config, dict):
                continue
            pid = str(config.get("Pid") or "").strip()
            vid = str(config.get("Vid") or "").strip()
            label_pair = variant_labels.get((pid, vid))
            if label_pair:
                if label_pair[0] in active_variant_names:
                    config_pairs.append(label_pair)
        if not config_pairs:
            continue
        price_block = configured.get("Price") or {}
        if not isinstance(price_block, dict):
            continue
        price_value = _to_float(price_block.get("OriginalPrice")) or _to_float(price_block.get("MarginPrice"))
        if price_value is None:
            continue
        variant_price_map[_variant_price_key(config_pairs)] = price_value
    if variant_price_map:
        result["variant_price_map"] = variant_price_map

    category = item.get("CategoryName")
    if isinstance(category, str) and category.strip():
        result["cn_category"] = category.strip()

    return result


def build_info_from_open_1688_detail(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}

    result: dict[str, Any] = {}
    item_id = str(item.get("offerId") or "").strip()
    title = item.get("subjectTrans") or item.get("subject")
    if isinstance(title, str) and title.strip():
        result["name"] = title.strip()

    if item_id:
        result["item_id"] = item_id

    detail_url = _canonicalize_1688_item_url(
        item.get("promotionUrl") or item.get("promotionURL"),
        item_id,
    )
    if detail_url:
        result["detail_url"] = detail_url

    images: list[str] = []
    product_image = item.get("productImage")
    if isinstance(product_image, dict):
        for image in product_image.get("images") or []:
            _append_unique(images, image)

    sku_list = item.get("productSkuInfos") if isinstance(item.get("productSkuInfos"), list) else []
    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        for attr in sku.get("skuAttributes") or []:
            if not isinstance(attr, dict):
                continue
            _append_unique(images, attr.get("skuImageUrl"))
    for image in _extract_html_image_urls(item.get("description")):
        _append_unique(images, image)

    if images:
        result["image_url"] = images[0]
        result["extra_images"] = images

    variants, sizes = _build_variant_groups_from_open_1688_skus(sku_list)
    if variants:
        result["variants"] = variants
    if sizes:
        result["available_sizes"] = sizes

    active_variant_names = {
        str(group.get("name") or "").strip()
        for group in variants
        if len(group.get("options") or []) >= 2
    }
    all_sku_prices: list[float] = []
    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        fenxiao_price = sku.get("fenxiaoPriceInfo") if isinstance(sku.get("fenxiaoPriceInfo"), dict) else {}
        sku_price, _ = _extract_price_value_and_starting(
            sku.get("promotionPrice"),
            sku.get("consignPrice"),
            sku.get("price"),
            fenxiao_price.get("offerPrice"),
        )
        if sku_price is not None:
            all_sku_prices.append(sku_price)
    variant_price_map = _build_variant_price_map_from_open_1688_skus(sku_list, active_variant_names)
    if variant_price_map:
        result["variant_price_map"] = variant_price_map

    distinct_variant_prices = sorted({price for price in all_sku_prices if price is not None})
    base_price, base_price_is_starting = _extract_price_value_and_starting(
        (item.get("priceInfo") or {}).get("promotionPrice") if isinstance(item.get("priceInfo"), dict) else None,
        (item.get("priceInfo") or {}).get("price") if isinstance(item.get("priceInfo"), dict) else None,
    )
    if base_price is None and distinct_variant_prices:
        base_price = distinct_variant_prices[0]
    if base_price is not None:
        result["price"] = base_price
    if base_price_is_starting or len(distinct_variant_prices) > 1:
        result["price_is_starting"] = True

    specs: dict[str, str] = {}
    for attr in item.get("productAttribute") or []:
        if not isinstance(attr, dict):
            continue
        name = str(attr.get("attributeNameTrans") or attr.get("attributeName") or "").strip()
        value = str(attr.get("valueTrans") or attr.get("value") or "").strip()
        _append_spec_value(specs, name, value)

        normalized_name = name.lower()
        if normalized_name in ("brand", "品牌") and value and not result.get("brand"):
            result["brand"] = value
        if normalized_name in ("product category", "category", "产品类别") and value and not result.get("cn_category"):
            result["cn_category"] = value

    if specs:
        result["specs"] = specs

    if not result.get("brand"):
        company_name = str(item.get("companyName") or "").strip()
        if company_name:
            result["brand"] = company_name

    weight = _extract_open_1688_weight(item)
    if weight is not None:
        result["weight_kg"] = weight

    return result


def build_info_from_1688_datahub(
    *,
    detail: dict[str, Any],
    simple: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if detail:
        title = detail.get("title")
        if isinstance(title, str) and title.strip():
            result["name"] = title.strip()

        item_url = detail.get("itemUrl")
        if isinstance(item_url, str) and item_url.strip():
            result["detail_url"] = f"https:{item_url}" if item_url.startswith("//") else item_url.strip()

        images = []
        for image in detail.get("images") or []:
            normalized = _normalize_image(image)
            if normalized and normalized not in images:
                images.append(normalized)
        if images:
            result["image_url"] = images[0]
            result["extra_images"] = images

        properties = detail.get("properties") or {}
        prop_list = properties.get("list") if isinstance(properties, dict) else []
        if isinstance(prop_list, list) and prop_list:
            specs: dict[str, str] = {}
            for item in prop_list:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "").strip()
                if name and value:
                    specs[name] = value
            if specs:
                result["specs"] = specs
                category = specs.get("产品类别") or specs.get("产品类目")
                if category:
                    result["cn_category"] = category

        sku = detail.get("sku") or {}
        sku_props = []
        if isinstance(sku, dict):
            sku_props = sku.get("props") or []
        if not sku_props:
            sku_props = detail.get("skuProps") or []
        variants: list[dict[str, Any]] = []
        sizes: list[str] = []
        if isinstance(sku_props, list):
            for group in sku_props:
                if not isinstance(group, dict):
                    continue
                name = str(group.get("prop") or group.get("name") or "").strip()
                if not name and isinstance(group.get("pid"), int):
                    name = str(group.get("pid")).strip()
                values = []
                for value_item in group.get("value") or group.get("values") or []:
                    if not isinstance(value_item, dict):
                        continue
                    value = str(value_item.get("name") or value_item.get("value") or "").strip()
                    if value and value not in values:
                        values.append(value)
                if name and values:
                    variants.append({"name": name, "options": values})
                    if _looks_like_size(name) or any(token in name for token in ("尺码", "码数")):
                        for value in values:
                            if value not in sizes:
                                sizes.append(value)
        if not variants:
            variants, sizes = _extract_variants_from_properties(prop_list)
        if variants:
            result["variants"] = variants
        if sizes:
            result["available_sizes"] = sizes

    if simple:
        item = simple.get("item") or {}
        if isinstance(item, dict):
            if not result.get("name"):
                title = item.get("title")
                if isinstance(title, str) and title.strip():
                    result["name"] = title.strip()
            if not result.get("price"):
                sku = item.get("sku") or {}
                if isinstance(sku, dict):
                    default_sku = sku.get("def") or {}
                    price = _to_float(default_sku.get("promotionPrice")) or _to_float(default_sku.get("price"))
                    if price is not None:
                        result["price"] = price
            if not result.get("image_url"):
                image_url = _normalize_image(item.get("image"))
                if image_url:
                    result["image_url"] = image_url

        seller = simple.get("seller") or {}
        if isinstance(seller, dict):
            store_id = seller.get("storeId")
            if isinstance(store_id, str) and store_id.strip():
                result["store_id"] = store_id.strip()

    if package:
        weight = _to_float(package.get("productWeight"))
        if weight:
            result["weight_kg"] = weight

    return result


def extract_item_id(value: str) -> str | None:
    if not value:
        return None
    match = re.search(r"[?&]id=(\d{8,15})", value)
    if match:
        return match.group(1)
    match = re.search(r"/offer/(\d{8,15})", value)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{8,15})\b", value)
    if match:
        return match.group(1)
    return None
