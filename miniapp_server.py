"""Lightweight mini app server for the buyer bot."""

from __future__ import annotations

import asyncio
import base64
import binascii
from contextlib import contextmanager
import httpx
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Counter of in-flight heavy requests (parse-product, etc.)
# Watchdog reads this to avoid killing the tunnel mid-request.
active_requests = 0
active_requests_lock = threading.Lock()

import database as db
from auth import get_user_id_from_init_data, is_admin
from config import (
    ADMIN_CONTACT_USER_ID,
    ADMIN_CONTACT_USERNAME,
    ADMIN_USER_ID,
    ADMIN_USER_IDS,
    ADMIN_USERNAME,
    BOT_TOKEN,
    CATEGORIES,
    CITIES,
    DEFAULT_MARGIN_MIN_RUB,
    DEFAULT_MARGIN_STEPS,
    DELIVERY_DISPLAY,
    MINI_APP_PORT,
)
from models import ProductDraft, UserSettings
from services import exchange_rate as er
import math
from services.calculator import get_typical_weight, get_effective_rate
from services.delivery_pricing import (
    DELIVERY_INCLUDES_NOTE,
    DELIVERY_PAYMENT_NOTE,
    DELIVERY_PRICE_FIELD_KEYS,
    DELIVERY_TIMING_FIELD_KEYS,
    EXPRESS_DELIVERY_TYPE,
    STANDARD_DELIVERY_TYPE,
    calculate_pricing_components,
    get_delivery_info,
    is_moscow_city,
    normalize_delivery_type,
)
from services.parser import (
    build_dewu_share_url,
    canonicalize_dewu_url,
    extract_url,
    is_valid_url,
    needs_poizon_html_fallback,
    parse_url,
)
from models import CalculationResult, BreakdownLine, ExchangeRate
from services.taobao_1688_api import Open1688SearchUnavailableError, TaobaoSearchUnavailableError

log = logging.getLogger(__name__)

mimetypes.add_type("image/webp", ".webp")

BASE_DIR = Path(__file__).resolve().parent
MINIAPP_DIR = BASE_DIR / "miniapp" / "dist"
UPLOADS_DIR = BASE_DIR / "uploads"
PROMO_BANNER_UPLOADS_DIR = UPLOADS_DIR / "promo-banners"
_ADMIN_AVATAR_CACHE_TTL_SECONDS = 6 * 60 * 60
_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS = 15 * 60
_admin_avatar_cache: dict[int, tuple[float, str | None, bytes | None]] = {}
_admin_avatar_cache_lock = threading.Lock()
DELIVERY_PROFILE_FIELDS = db.DELIVERY_PROFILE_FIELDS
DELIVERY_REQUIRED_FIELDS = ("city", "street", "house")
_PROMO_BANNER_UPLOAD_RE = re.compile(
    r"^data:(?P<mime>image/(?:webp|png|jpeg|jpg));base64,(?P<body>[A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)
_ABOUT_DETAILS_IMAGE_FORMAT = "2:3"
_PUBLIC_UPLOAD_BASE_URL = str(
    os.getenv("MINI_APP_API_PUBLIC_URL", "").strip() or "https://api.x-poizon.ru"
).rstrip("/")


def _resolve_static_file_path(request_path: str) -> Path:
    normalized_path = str(request_path or "/").split("?", 1)[0]
    if normalized_path == "/" or normalized_path.startswith("/launch/"):
        return MINIAPP_DIR / "index.html"

    relative_path = normalized_path.lstrip("/")
    candidate = MINIAPP_DIR / relative_path
    if candidate.exists() and candidate.is_file():
        return candidate

    # Keep asset 404s intact, but allow extensionless SPA routes to render the app shell.
    if "." not in Path(relative_path).name:
        return MINIAPP_DIR / "index.html"

    return candidate


@contextmanager
def _track_active_request():
    """Mark long-running work so the tunnel watchdog does not recycle mid-request."""
    global active_requests

    with active_requests_lock:
        active_requests += 1

    try:
        yield
    finally:
        with active_requests_lock:
            active_requests -= 1


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _repair_mojibake_text(value: str) -> str:
    text = str(value or "")
    if not text or not any(ord(char) > 127 for char in text):
        return text

    raw_bytes = bytearray()
    for char in text:
        code_point = ord(char)
        if code_point <= 0xFF:
            raw_bytes.append(code_point)
            continue

        try:
            raw_bytes.extend(char.encode("cp1251"))
        except UnicodeEncodeError:
            return text

    try:
        repaired = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return text

    return repaired if repaired != text else text


def _repair_mojibake_deep(value: object):
    if isinstance(value, str):
        return _repair_mojibake_text(value)
    if isinstance(value, list):
        return [_repair_mojibake_deep(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_repair_mojibake_deep(item) for item in value)
    if isinstance(value, dict):
        repaired: dict[object, object] = {}
        for key, item in value.items():
            repaired_key = _repair_mojibake_text(key) if isinstance(key, str) else key
            repaired[repaired_key] = _repair_mojibake_deep(item)
        return repaired
    return value


_IMAGE_PROXY_ALLOWED_HOST_SUFFIXES = ("alicdn.com", "alicdn.com.cn")
_IMAGE_PROXY_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _build_search_pagination(
    platform: str,
    *,
    start_id: int,
    count: int,
    loaded_count: int,
    total_count: int,
    provider_cursor: int | None = None,
) -> tuple[int, bool]:
    safe_start_id = max(0, int(start_id or 0))
    safe_count = max(1, int(count or 1))
    safe_loaded_count = max(0, int(loaded_count or 0))
    safe_total_count = max(0, int(total_count or 0))
    normalized_platform = str(platform or "").strip().lower()

    if normalized_platform == "poizon":
        next_start_id = max(0, int(provider_cursor or 0))
        has_more = safe_loaded_count >= safe_count and next_start_id > safe_start_id
        return next_start_id, has_more

    next_start_id = safe_start_id + safe_count if safe_loaded_count > 0 else safe_start_id

    if normalized_platform == "taobao":
        if safe_total_count > 0:
            return next_start_id, next_start_id < safe_total_count
        return next_start_id, safe_loaded_count >= safe_count

    if normalized_platform == "1688":
        # This provider reports a cumulative page ceiling instead of the true total.
        return next_start_id, safe_loaded_count >= safe_count

    return next_start_id, safe_loaded_count >= safe_count


def _is_allowed_image_proxy_url(url: str) -> bool:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return False
    if normalized_url.startswith("//"):
        normalized_url = f"https:{normalized_url}"

    parsed = urlparse(normalized_url)
    host = str(parsed.hostname or "").strip().lower()
    if parsed.scheme not in ("http", "https") or not host:
        return False
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _IMAGE_PROXY_ALLOWED_HOST_SUFFIXES
    )


async def _fetch_image_proxy(url: str) -> tuple[bytes, str, str]:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("url is required")
    if normalized_url.startswith("//"):
        normalized_url = f"https:{normalized_url}"
    if not _is_allowed_image_proxy_url(normalized_url):
        raise ValueError("image host not allowed")

    headers = {
        "User-Agent": _IMAGE_PROXY_USER_AGENT,
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(normalized_url, headers=headers)
        response.raise_for_status()

    content_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
    if not content_type.startswith("image/"):
        raise RuntimeError("upstream did not return an image")

    cache_control = str(response.headers.get("Cache-Control") or "").strip() or "public, max-age=86400"
    return response.content, content_type, cache_control


def _resolve_upload_path(request_path: str) -> Path | None:
    normalized_path = str(request_path or "").split("?", 1)[0].split("#", 1)[0]
    if not normalized_path.startswith("/uploads/"):
        return None

    relative_path = Path(normalized_path[len("/uploads/"):])
    if not relative_path.parts or any(part in ("", ".", "..") for part in relative_path.parts):
        return None

    uploads_root = UPLOADS_DIR.resolve()
    candidate = (uploads_root / relative_path).resolve()
    try:
        candidate.relative_to(uploads_root)
    except ValueError:
        return None
    return candidate


def _public_media_url(value: object) -> str:
    normalized_url = str(value or "").strip()
    if not normalized_url.startswith("/uploads/"):
        return normalized_url
    if not _PUBLIC_UPLOAD_BASE_URL:
        return normalized_url
    return f"{_PUBLIC_UPLOAD_BASE_URL}{normalized_url}"


def _save_promo_banner_image(data_url: object, *, prefix: str = "banner") -> dict:
    data_url_text = str(data_url or "").strip()
    if not data_url_text:
        raise ValueError("image_data is required")

    match = _PROMO_BANNER_UPLOAD_RE.match(data_url_text)
    if not match:
        raise ValueError("unsupported_image_format")

    mime_type = str(match.group("mime") or "").strip().lower()
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    try:
        image_bytes = base64.b64decode(match.group("body"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid_image_data") from exc

    if not image_bytes:
        raise ValueError("invalid_image_data")
    if len(image_bytes) > 4 * 1024 * 1024:
        raise ValueError("image_too_large")

    PROMO_BANNER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_extension = {
        "image/webp": ".webp",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }.get(mime_type)
    if not file_extension:
        raise ValueError("unsupported_image_format")

    filename = f"{prefix}-{secrets.token_hex(10)}{file_extension}"
    output_path = PROMO_BANNER_UPLOADS_DIR / filename
    output_path.write_bytes(image_bytes)

    relative_url = f"/uploads/promo-banners/{filename}"

    return {
        "url": _public_media_url(relative_url),
        "path": relative_url,
        "mime_type": mime_type,
        "byte_size": len(image_bytes),
    }


def _manual_rate_state(settings: dict | None, now: float | None = None) -> tuple[bool, float | None]:
    current_time = time.time() if now is None else now
    override_raw = str((settings or {}).get("rate_override", "") or "").strip()
    override_until_raw = (settings or {}).get("rate_override_until", "0")
    try:
        override_until = float(override_until_raw or "0")
    except (TypeError, ValueError):
        override_until = 0.0

    if not override_raw or current_time >= override_until:
        return False, None

    try:
        return True, float(override_raw)
    except ValueError:
        return False, None


def _display_rate_payload(
    rate,
    *,
    settings: dict | None = None,
    effective_rate: float | None = None,
    now: float | None = None,
) -> dict | None:
    if not rate and effective_rate is None:
        return None

    manual_override_active, manual_rate_value = _manual_rate_state(settings, now=now)
    display_rate = effective_rate
    if display_rate is None:
        display_rate = manual_rate_value if manual_override_active else (rate.cny_rub if rate else None)

    source = "manual" if manual_override_active else "cbr"

    return {
        "cny_rub": display_rate,
        "usd_rub": rate.usd_rub if rate else None,
        "eur_rub": rate.eur_rub if rate else None,
        "updated_at": rate.updated_at.isoformat() if rate else None,
        "age_seconds": 0 if manual_override_active else (rate.age_seconds if rate else None),
        "age_human": "\u0420\u0443\u0447\u043d\u043e\u0439 \u043a\u0443\u0440\u0441" if manual_override_active else (rate.age_human if rate else None),
        "source": source,
    }


def _build_delivery_info_payload(settings: dict | None = None) -> dict:
    return get_delivery_info(settings)


def _ensure_product_weight(draft: ProductDraft) -> ProductDraft:
    if not draft.weight_kg:
        draft.weight_kg = get_typical_weight(draft.category or "other")
        draft.weight_estimated = True
    return draft


def _pricing_components_for_draft(
    draft: ProductDraft,
    settings: dict,
    effective_rate: float,
    *,
    delivery_type: str | None = None,
    include_cdek: bool = False,
) -> dict:
    _ensure_product_weight(draft)
    draft.delivery_type = normalize_delivery_type(
        delivery_type or draft.delivery_type or STANDARD_DELIVERY_TYPE
    )
    return calculate_pricing_components(
        settings,
        price_cny=draft.price_cny,
        effective_rate=effective_rate,
        weight_kg=draft.weight_kg,
        weight_estimated=bool(draft.weight_estimated),
        delivery_type=draft.delivery_type,
        include_cdek=include_cdek,
    )


def _build_pricing_breakdown_payload(
    *,
    price_cny: float,
    effective_rate: float,
    pricing: dict,
) -> list[dict]:
    delivery = pricing["delivery"]
    rows = [
        {
            "label": "Товар",
            "amount_rub": pricing["goods_rub"],
            "note": f"{price_cny:.0f} ¥ × {effective_rate:.2f}",
        },
        {
            "label": f"Комиссия ({pricing['commission_pct']:.0f}%)",
            "amount_rub": pricing["commission_rub"],
            "note": (
                f"мин. {pricing['min_commission_rub']:.0f} ₽"
                if pricing["commission_rub"] <= pricing["min_commission_rub"]
                else ""
            ),
        },
        {
            "label": "Доставка до Москвы",
            "amount_rub": delivery["to_moscow_rub"],
            "note": f"{delivery['route_label']} • {delivery['units_note']}",
        },
    ]

    if delivery["cdek_rub"] > 0:
        rows.append(
            {
                "label": "СДЭК по России",
                "amount_rub": delivery["cdek_rub"],
                "note": delivery["units_note"],
            }
        )

    return rows


def _build_pricing_breakdown_lines(
    *,
    price_cny: float,
    effective_rate: float,
    pricing: dict,
) -> list[BreakdownLine]:
    return [
        BreakdownLine(item["label"], item["amount_rub"], item["note"])
        for item in _build_pricing_breakdown_payload(
            price_cny=price_cny,
            effective_rate=effective_rate,
            pricing=pricing,
        )
    ]


def _build_result_from_pricing(
    draft: ProductDraft,
    *,
    rate_snapshot: ExchangeRate,
    effective_rate: float,
    pricing: dict,
) -> CalculationResult:
    subtotal = pricing["subtotal_rub"]
    return CalculationResult(
        product=draft,
        breakdown=_build_pricing_breakdown_lines(
            price_cny=float(draft.price_cny or 0),
            effective_rate=effective_rate,
            pricing=pricing,
        ),
        subtotal_rub=subtotal,
        margin_rub=0,
        total_with_margin_rub=subtotal,
        margin_percent=0,
        exchange_rate=rate_snapshot,
    )


def _draft_from_calc_row(row: dict) -> ProductDraft:
    raw_calc_json = row.get("calc_json")
    draft: ProductDraft | None = None

    if raw_calc_json:
        try:
            parsed = json.loads(raw_calc_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        product_payload = (
            parsed.get("product")
            if isinstance(parsed, dict) and isinstance(parsed.get("product"), dict)
            else parsed
        )
        if isinstance(product_payload, dict):
            draft = _draft_from_payload(product_payload)

    if draft is None:
        draft = ProductDraft()

    if draft.price_cny is None and row.get("price_cny") is not None:
        draft.price_cny = float(row["price_cny"])
    if draft.weight_kg is None and row.get("weight_kg") is not None:
        draft.weight_kg = float(row["weight_kg"])
    if not draft.name:
        draft.name = str(row.get("name") or "")
    if not draft.platform:
        draft.platform = str(row.get("platform") or "unknown")
    if not draft.size:
        draft.size = str(row.get("size") or "")
    if not draft.url:
        draft.url = str(row.get("product_url") or "")
    if not draft.city:
        draft.city = str(row.get("city") or "")
    if not draft.delivery_type:
        draft.delivery_type = str(row.get("delivery_type") or "")
    draft.weight_estimated = bool(draft.weight_estimated or row.get("weight_estimated"))
    return draft


def _draft_to_dict(draft: ProductDraft) -> dict:
    return {
        "url": draft.url,
        "platform": draft.platform,
        "name": draft.name,
        "brand": draft.brand,
        "price_cny": draft.price_cny,
        "price_is_starting": draft.price_is_starting,
        "size": draft.size,
        "category": draft.category,
        "weight_kg": draft.weight_kg,
        "weight_estimated": draft.weight_estimated,
        "city": draft.city,
        "delivery_type": draft.delivery_type,
        "image_url": draft.image_url,
        "extra_images": draft.extra_images,
        "specs": draft.specs,
        "available_sizes": draft.available_sizes,
        "variants": draft.variants,
        "variant_price_map": draft.variant_price_map,
        "original_variants": draft.original_variants,
        "notes": draft.notes,
        "auto_detected": draft.auto_detected,
    }


def _draft_from_payload(payload: dict) -> ProductDraft:
    platform = payload.get("platform", "unknown")
    raw_url = payload.get("url", "")
    normalized_url = canonicalize_dewu_url(raw_url) if platform == "poizon" else raw_url
    return ProductDraft(
        url=normalized_url,
        platform=platform,
        name=payload.get("name", ""),
        brand=payload.get("brand", ""),
        price_cny=float(payload["price_cny"]) if payload.get("price_cny") is not None else None,
        price_is_starting=bool(payload.get("price_is_starting", False)),
        size=payload.get("size", ""),
        category=payload.get("category", ""),
        weight_kg=float(payload["weight_kg"]) if payload.get("weight_kg") is not None else None,
        weight_estimated=bool(payload.get("weight_estimated", False)),
        city=payload.get("city", ""),
        delivery_type=payload.get("delivery_type", ""),
        image_url=payload.get("image_url", ""),
        extra_images=payload.get("extra_images") or [],
        specs=payload.get("specs") or {},
        available_sizes=payload.get("available_sizes") or [],
        variants=payload.get("variants") or [],
        variant_price_map=payload.get("variant_price_map") or {},
        original_variants=payload.get("original_variants") or [],
        notes=payload.get("notes", ""),
    )


def _extract_product_input_url(raw_value: object) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    if is_valid_url(text):
        return text
    return extract_url(text) or ""


async def _build_calculation_result(payload: dict):
    """Miniapp calculator — uses admin settings (same formula as bot's calculate_simple)."""
    draft = _draft_from_payload(payload.get("product") or {})
    draft.city = payload.get("city") or draft.city or "moscow"
    draft.delivery_type = normalize_delivery_type(
        payload.get("delivery_type") or draft.delivery_type or STANDARD_DELIVERY_TYPE
    )
    _ensure_product_weight(draft)

    if draft.price_cny is None:
        raise RuntimeError("price_cny is required")
    if draft.price_is_starting:
        raise RuntimeError("exact price is required")

    rate = await er.get_rate()
    if not rate:
        raise RuntimeError("Exchange rate unavailable")

    admin = await db.get_admin_settings()
    eff_rate = await get_effective_rate()
    pricing = _pricing_components_for_draft(
        draft,
        admin,
        eff_rate,
        delivery_type=draft.delivery_type,
        include_cdek=False,
    )
    return _build_result_from_pricing(
        draft,
        rate_snapshot=rate,
        effective_rate=eff_rate,
        pricing=pricing,
    )


def _calculate_showcase_subtotal(draft: ProductDraft, settings: dict, effective_rate: float) -> float:
    pricing = _pricing_components_for_draft(
        draft,
        settings,
        effective_rate,
        delivery_type=STANDARD_DELIVERY_TYPE,
        include_cdek=False,
    )
    return pricing["subtotal_rub"]


def _showcase_product_payload_is_incomplete(product_payload: object) -> bool:
    if not isinstance(product_payload, dict):
        return True

    name = str(product_payload.get("name") or "").strip()
    return not name


def _deserialize_showcase_product_payload(product_json: object) -> dict | None:
    product_json_text = str(product_json or "").strip()
    if not product_json_text:
        return None

    try:
        parsed_payload = json.loads(product_json_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    return parsed_payload if isinstance(parsed_payload, dict) else None


async def _refresh_incomplete_showcase_slots(slots: list[dict]) -> list[dict]:
    refreshed_slots = [dict(slot_row) for slot_row in slots]

    for index, slot_row in enumerate(refreshed_slots):
        slot = int(slot_row.get("slot") or 0)
        url = str(slot_row.get("url") or "").strip()
        product_json = str(slot_row.get("product_json") or "").strip()

        if not url:
            continue

        cached_payload = _deserialize_showcase_product_payload(product_json)

        if not _showcase_product_payload_is_incomplete(cached_payload):
            continue

        try:
            repaired_payload = await _parse_product(url)
        except Exception:
            continue

        if not isinstance(repaired_payload, dict):
            continue

        repaired_json = json.dumps(repaired_payload, ensure_ascii=False)
        refreshed_slots[index]["product_json"] = repaired_json

        if slot > 0:
            try:
                await db.set_admin_showcase_slot(slot, url, repaired_json)
            except Exception:
                pass

    return refreshed_slots


def _showcase_item_from_product_payload(
    slot: int,
    url: str,
    product_payload: dict,
    settings: dict,
    effective_rate: float,
) -> dict | None:
    if not isinstance(product_payload, dict):
        return None

    draft = _draft_from_payload(product_payload)
    if not draft.url:
        draft.url = url
    if not draft.name:
        return None

    subtotal_rub = (
        _calculate_showcase_subtotal(draft, settings, effective_rate)
        if draft.price_cny is not None and not draft.price_is_starting
        else None
    )

    return {
        "slot": slot,
        "url": url or draft.url,
        "product": _draft_to_dict(draft),
        "subtotal_rub": subtotal_rub,
    }


def _showcase_payload_from_slots(
    slots: list[dict],
    settings: dict,
    effective_rate: float,
    *,
    include_links: bool = False,
) -> dict:
    links: list[str] = []
    items: list[dict] = []

    for slot_row in slots:
        slot = int(slot_row.get("slot") or 0)
        url = str(slot_row.get("url") or "").strip()
        product_json = str(slot_row.get("product_json") or "").strip()

        if include_links:
            links.append(url)

        if not url or not product_json:
            continue

        try:
            product_payload = json.loads(product_json)
        except (TypeError, ValueError):
            continue

        showcase_item = _showcase_item_from_product_payload(
            slot,
            url,
            product_payload,
            settings,
            effective_rate,
        )
        if showcase_item:
            items.append(showcase_item)

    items.sort(key=lambda item: item["slot"])

    payload = {
        "items": items,
        "configured_count": sum(1 for link in links if link.strip()) if include_links else sum(1 for row in slots if str(row.get("url") or "").strip()),
    }

    if include_links:
        payload["links"] = links

    return payload


async def _showcase_payload(
    *,
    settings: dict | None = None,
    effective_rate: float | None = None,
    include_links: bool = False,
) -> dict:
    showcase_slots = await db.get_admin_showcase_slots()
    showcase_slots = await _refresh_incomplete_showcase_slots(showcase_slots)
    resolved_settings = settings or await db.get_admin_settings()
    resolved_effective_rate = effective_rate if effective_rate is not None else await get_effective_rate()
    return _showcase_payload_from_slots(
        showcase_slots,
        resolved_settings,
        resolved_effective_rate,
        include_links=include_links,
    )


def _result_to_payload(
    result,
    *,
    settings: dict | None = None,
    effective_rate: float | None = None,
) -> dict:
    return {
        "product": _draft_to_dict(result.product),
        "subtotal_rub": result.subtotal_rub,
        "total_with_margin_rub": result.total_with_margin_rub,
        "margin_rub": result.margin_rub,
        "margin_percent": result.margin_percent,
        "exchange_rate": _display_rate_payload(
            result.exchange_rate,
            settings=settings,
            effective_rate=effective_rate,
        ),
        "breakdown": [
            {"label": item.label, "amount_rub": item.amount_rub, "note": item.note}
            for item in result.breakdown
        ],
        "delivery_info": _build_delivery_info_payload(settings),
    }


def _admin_contact_target_user_id() -> int:
    if ADMIN_CONTACT_USER_ID > 0:
        return int(ADMIN_CONTACT_USER_ID)
    if ADMIN_USER_IDS:
        return int(ADMIN_USER_IDS[-1])
    try:
        user_id = int(ADMIN_USER_ID or 0)
    except (TypeError, ValueError):
        return 0
    return user_id if user_id > 0 else 0


def _admin_contact_url() -> str:
    username = _admin_contact_username()
    if not username:
        contact_user_id = _admin_contact_target_user_id()
        return f"tg://user?id={contact_user_id}" if contact_user_id > 0 else ""
    return f"https://t.me/{username}"


def _admin_contact_username() -> str:
    explicit_contact_username = str(ADMIN_CONTACT_USERNAME or "").strip().lstrip("@")
    if explicit_contact_username:
        return explicit_contact_username
    if _admin_contact_target_user_id() != int(ADMIN_USER_ID or 0):
        return ""
    return str(ADMIN_USERNAME or "").strip().lstrip("@")


def _admin_contact_user_id() -> int:
    return _admin_contact_target_user_id()


async def _track_miniapp_activity(user_id: int | None) -> None:
    safe_user_id = int(user_id or 0)
    if safe_user_id <= 0:
        return
    try:
        await db.record_miniapp_activity(safe_user_id)
    except Exception as exc:
        if "no such table: miniapp_activity_daily" in str(exc):
            log.debug("Miniapp activity table is not available yet for user_id=%s", safe_user_id)
            return
        log.warning("Failed to record miniapp activity for user_id=%s", safe_user_id, exc_info=True)


async def _bootstrap_payload(user_id: int | None, is_admin_user: bool = False) -> dict:
    rate = await er.get_rate()
    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    showcase_payload = await _showcase_payload(
        settings=admin,
        effective_rate=effective_rate,
    )
    about_details_payload = await _about_details_payload()
    promo_banners_payload = await _promo_banners_payload()
    user_settings = None
    if user_id:
        await _track_miniapp_activity(user_id)
        user = await db.get_or_create_user(user_id)
        user_settings = {
            "margin_steps": json.loads(user.get("margin_steps", "[]") or "[]"),
            "margin_min_rub": float(user.get("margin_min_rub", DEFAULT_MARGIN_MIN_RUB)),
        }

    return {
        "rate": _display_rate_payload(
            rate,
            settings=admin,
            effective_rate=effective_rate,
        ),
        "admin_settings": admin,
        "delivery_info": _build_delivery_info_payload(admin),
        "user_settings": user_settings or {
            "margin_steps": DEFAULT_MARGIN_STEPS,
            "margin_min_rub": DEFAULT_MARGIN_MIN_RUB,
        },
        "cities": [{"key": key, "label": label} for key, label in CITIES.items()],
        "delivery_options": [
            {"key": key, "label": label}
            for key, label in DELIVERY_DISPLAY.items()
        ],
        "categories": [
            {"key": key, "label": label, "weight_kg": weight}
            for key, (label, weight) in CATEGORIES.items()
        ],
        "admin_contact_url": _admin_contact_url(),
        "admin_contact_username": _admin_contact_username(),
        "admin_contact_user_id": _admin_contact_user_id(),
        "showcase_items": showcase_payload["items"],
        "showcase_configured_count": showcase_payload["configured_count"],
        "about_details_slides": about_details_payload["items"],
        "promo_banners": promo_banners_payload["items"],
        "promo_entry_banner_id": promo_banners_payload["entry_banner_id"],
        "is_admin": is_admin_user,
    }


def _resolve_bootstrap_identity(
    user_id: int | None,
    init_data_raw: str | None,
    bot_token: str | None = None,
) -> tuple[int | None, bool]:
    if isinstance(init_data_raw, str) and init_data_raw:
        trusted_user_id = get_user_id_from_init_data(init_data_raw, bot_token=bot_token)
        return trusted_user_id, is_admin(trusted_user_id)
    if user_id is not None and user_id > 0:
        return user_id, False
    return None, False


def _normalize_delivery_payload(delivery_payload: dict | None) -> dict:
    payload = delivery_payload if isinstance(delivery_payload, dict) else {}
    return {
        field: str(payload.get(field) or "").strip()
        for field in DELIVERY_PROFILE_FIELDS
    }


def _delivery_missing_required(delivery_payload: dict | None) -> list[str]:
    normalized_payload = _normalize_delivery_payload(delivery_payload)
    return [
        field for field in DELIVERY_REQUIRED_FIELDS
        if not normalized_payload[field]
    ]


async def _delivery_profile_payload(user_id: int) -> dict:
    await _track_miniapp_activity(user_id)
    delivery_record = await db.get_delivery_profile(user_id)
    delivery_data = _normalize_delivery_payload(delivery_record)
    missing_required = _delivery_missing_required(delivery_data)
    return {
        "delivery_data": delivery_data,
        "is_complete": not missing_required,
        "updated_at": str(delivery_record.get("updated_at") or ""),
    }


async def _save_delivery_profile_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    if user_id <= 0:
        raise RuntimeError("user_id is required")

    await _track_miniapp_activity(user_id)
    delivery_data = _normalize_delivery_payload(payload.get("delivery_data"))
    saved_delivery = await db.save_delivery_profile(user_id, delivery_data)
    saved_payload = _normalize_delivery_payload(saved_delivery)
    missing_required = _delivery_missing_required(saved_payload)
    return {
        "delivery_data": saved_payload,
        "is_complete": not missing_required,
        "updated_at": str(saved_delivery.get("updated_at") or ""),
    }


_ADMIN_PRICING_FIELDS = {
    "commission_pct",
    "min_commission_rub",
    *DELIVERY_PRICE_FIELD_KEYS,
    *DELIVERY_TIMING_FIELD_KEYS,
    "rate_override",
}

_ADMIN_MESSAGE_TYPE_LABELS = {
    "contact": "Просто сообщение",
    "problem": "Сообщение о проблеме",
    "calc_request": "Заявка на расчёт товара",
}


_SHOWCASE_SLOT_COUNT = db.SHOWCASE_SLOT_COUNT
_SHOWCASE_ROW_SIZE = 5
_SHOWCASE_FIELD_MAX_LENGTH = 2048
_PROMO_BANNER_EDITOR_IMAGE_FORMAT = "WEBP"
_PROMO_BANNER_EDITOR_COVER_SIZE = "1320 x 480"
_PROMO_BANNER_EDITOR_INLINE_SIZE = "1200 x 1200"


class ShowcaseValidationError(ValueError):
    def __init__(self, message: str, slot_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.slot_errors = slot_errors or {}


def _format_admin_message_datetime(value: str) -> str:
    if not value:
        return "—"

    try:
        parsed = datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
        return parsed.strftime("%d.%m.%Y в %H:%M")
    except ValueError:
        return value


def _normalize_admin_page(raw_value: object, default: int = 1) -> int:
    try:
        value = int(raw_value or default)
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def _format_admin_timestamp(value: object) -> str:
    try:
        timestamp = float(value or 0)
    except (TypeError, ValueError):
        timestamp = 0.0

    if timestamp <= 0:
        return "—"

    try:
        return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y в %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


def _serialize_promo_banner_block(block: dict | None) -> dict:
    banner_block = block if isinstance(block, dict) else {}
    block_type = str(banner_block.get("type") or "").strip().lower()
    block_id = str(banner_block.get("id") or "").strip()

    payload = {
        "id": block_id,
        "type": block_type,
    }

    if block_type == "list":
        payload["items"] = [
            str(item).strip()
            for item in banner_block.get("items") or []
            if str(item).strip()
        ]
        return payload

    if block_type == "image":
        payload["image_url"] = _public_media_url(banner_block.get("image_url"))
        payload["alt_text"] = str(banner_block.get("alt_text") or "").strip()
        payload["caption"] = str(banner_block.get("caption") or "").strip()
        return payload

    if block_type == "button":
        payload["button_label"] = str(banner_block.get("button_label") or "").strip()
        payload["button_url"] = str(banner_block.get("button_url") or "").strip()
        payload["button_color"] = str(banner_block.get("button_color") or "").strip()
        return payload

    payload["text"] = str(banner_block.get("text") or "").strip()
    return payload


def _serialize_promo_banner_item(item: dict | None) -> dict:
    banner_item = item if isinstance(item, dict) else {}
    updated_at = float(banner_item.get("updated_at") or 0)
    blocks = [
        _serialize_promo_banner_block(block)
        for block in banner_item.get("blocks") or []
    ]

    return {
        "id": int(banner_item.get("id") or 0),
        "label": str(banner_item.get("label") or "").strip(),
        "title": str(banner_item.get("title") or "").strip(),
        "subtitle": str(banner_item.get("subtitle") or "").strip(),
        "button_label": str(banner_item.get("button_label") or "").strip(),
        "button_url": str(banner_item.get("button_url") or "").strip(),
        "button_color": str(banner_item.get("button_color") or "").strip(),
        "image_url": _public_media_url(banner_item.get("image_url")),
        "image_alt": str(banner_item.get("image_alt") or "").strip(),
        "story_image_url": _public_media_url(banner_item.get("story_image_url")),
        "story_image_alt": str(banner_item.get("story_image_alt") or "").strip(),
        "blocks": blocks,
        "position": int(banner_item.get("position") or 0),
        "show_on_entry": bool(banner_item.get("show_on_entry")),
        "created_at": float(banner_item.get("created_at") or 0),
        "updated_at": updated_at,
        "updated_at_label": _format_admin_timestamp(updated_at),
    }


async def _promo_banners_payload() -> dict:
    items = [_serialize_promo_banner_item(item) for item in await db.get_admin_banners()]
    entry_banner = next((item for item in items if item.get("show_on_entry")), None)
    return {
        "items": items,
        "entry_banner_id": int(entry_banner.get("id") or 0) if entry_banner else 0,
    }


def _serialize_about_slide_item(item: dict | None) -> dict:
    slide_item = item if isinstance(item, dict) else {}
    slot = int(slide_item.get("slot") or 0)
    updated_at = float(slide_item.get("updated_at") or 0)
    image_alt = str(slide_item.get("image_alt") or "").strip() or f"Слайд {slot}"

    return {
        "slot": slot,
        "image_url": _public_media_url(slide_item.get("image_url")),
        "image_alt": image_alt,
        "updated_at": updated_at,
        "updated_at_label": _format_admin_timestamp(updated_at),
    }


async def _about_details_payload() -> dict:
    items = [_serialize_about_slide_item(item) for item in await db.get_admin_about_slides()]
    return {
        "items": items,
    }


async def _admin_about_details_payload() -> dict:
    items = [_serialize_about_slide_item(item) for item in await db.get_admin_about_slides()]
    latest_updated_at = max((float(item.get("updated_at") or 0) for item in items), default=0.0)
    return {
        "items": items,
        "stats": {
            "total": len(items),
            "latest_updated_at": latest_updated_at,
            "latest_updated_at_label": _format_admin_timestamp(latest_updated_at),
        },
        "upload": {
            "format": _ABOUT_DETAILS_IMAGE_FORMAT,
            "required_size": _ABOUT_DETAILS_IMAGE_FORMAT,
        },
    }


async def _admin_about_details_upload_payload(payload: dict) -> dict:
    try:
        slot = int(payload.get("slot") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid slide slot") from exc

    insert_mode = bool(payload.get("insert"))
    if slot < 1:
        raise ValueError("Invalid slide slot")

    upload_payload = _save_promo_banner_image(
        payload.get("image_data"),
        prefix=f"about-slide-{slot:02d}",
    )
    await db.set_admin_about_slide(
        slot,
        str(upload_payload.get("url") or ""),
        str(payload.get("image_alt") or f"Слайд {slot}"),
    )

    response_payload = await _admin_about_details_payload()
    response_payload["updated_slot"] = slot
    response_payload["uploaded_image"] = {
        **upload_payload,
        "slot": slot,
    }
    return response_payload


async def _admin_about_details_delete_payload(payload: dict) -> dict:
    try:
        slot = int(payload.get("slot") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid slide slot") from exc

    await db.delete_admin_about_slide(slot)
    response_payload = await _admin_about_details_payload()
    response_payload["deleted_slot"] = slot
    return response_payload


async def _admin_promo_banners_payload() -> dict:
    items = [_serialize_promo_banner_item(item) for item in await db.get_admin_banners()]
    latest_updated_at = max((float(item.get("updated_at") or 0) for item in items), default=0.0)
    return {
        "items": items,
        "stats": {
            "total": len(items),
            "auto_open_count": sum(1 for item in items if item.get("show_on_entry")),
            "latest_updated_at": latest_updated_at,
            "latest_updated_at_label": _format_admin_timestamp(latest_updated_at),
        },
        "limits": {
            "max_banners": db.PROMO_BANNER_MAX_COUNT,
            "max_blocks": db.PROMO_BANNER_BLOCK_MAX_COUNT,
        },
        "upload": {
            "format": _PROMO_BANNER_EDITOR_IMAGE_FORMAT,
            "cover_size": _PROMO_BANNER_EDITOR_COVER_SIZE,
            "inline_size": _PROMO_BANNER_EDITOR_INLINE_SIZE,
        },
    }


async def _admin_promo_banner_save_payload(payload: dict) -> dict:
    try:
        banner_id = int(payload.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid banner id") from exc

    saved_banner = await db.save_admin_banner(
        banner_id,
        str(payload.get("label") or ""),
        str(payload.get("title") or ""),
        str(payload.get("subtitle") or ""),
        str(payload.get("button_label") or ""),
        str(payload.get("button_url") or ""),
        str(payload.get("button_color") or ""),
        str(payload.get("image_url") or ""),
        str(payload.get("image_alt") or ""),
        str(payload.get("story_image_url") or ""),
        str(payload.get("story_image_alt") or ""),
        bool(payload.get("show_on_entry")),
        payload.get("blocks") if isinstance(payload.get("blocks"), list) else [],
    )
    response_payload = await _admin_promo_banners_payload()
    response_payload["saved_banner_id"] = int(saved_banner.get("id") or 0)
    return response_payload


async def _admin_promo_banner_delete_payload(payload: dict) -> dict:
    try:
        banner_id = int(payload.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid banner id") from exc

    await db.delete_admin_banner(banner_id)
    return await _admin_promo_banners_payload()


async def _admin_promo_banner_upload_payload(payload: dict) -> dict:
    asset_kind = str(payload.get("asset_kind") or "cover").strip().lower()
    if asset_kind not in {"cover", "block"}:
        asset_kind = "cover"

    upload_payload = _save_promo_banner_image(
        payload.get("image_data"),
        prefix=f"promo-{asset_kind}",
    )
    return {
        **upload_payload,
        "asset_kind": asset_kind,
    }


def _serialize_faq_item(item: dict | None) -> dict:
    faq_item = item if isinstance(item, dict) else {}
    updated_at = float(faq_item.get("updated_at") or 0)
    answer = str(faq_item.get("answer") or "").strip()
    link_url = str(faq_item.get("link_url") or "").strip()
    button_label = str(faq_item.get("button_label") or "").strip()
    preview_limit = 180

    return {
        "id": int(faq_item.get("id") or 0),
        "question": str(faq_item.get("question") or "").strip(),
        "answer": answer,
        "link_url": link_url,
        "button_label": button_label,
        "position": int(faq_item.get("position") or 0),
        "updated_at": updated_at,
        "updated_at_label": _format_admin_timestamp(updated_at),
        "answer_preview": (
            answer[:preview_limit].rstrip() + "…"
            if len(answer) > preview_limit
            else answer
        ),
    }


async def _faq_payload() -> dict:
    items = [_serialize_faq_item(item) for item in await db.get_faq_entries()]
    return {
        "items": items,
        "contact": {
            "url": _admin_contact_url(),
            "username": _admin_contact_username(),
            "user_id": _admin_contact_user_id(),
        },
    }


async def _admin_faq_payload() -> dict:
    items = [_serialize_faq_item(item) for item in await db.get_faq_entries()]
    latest_updated_at = max((item["updated_at"] for item in items), default=0.0)

    return {
        "items": items,
        "stats": {
            "total": len(items),
            "latest_updated_at": latest_updated_at,
            "latest_updated_at_label": _format_admin_timestamp(latest_updated_at),
        },
    }


async def _admin_faq_save_payload(payload: dict) -> dict:
    try:
        entry_id = int(payload.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid faq entry id") from exc

    await db.save_faq_entry(
        entry_id,
        str(payload.get("question") or ""),
        str(payload.get("answer") or ""),
        str(payload.get("link_url") or ""),
        str(payload.get("button_label") or ""),
    )
    return await _admin_faq_payload()


async def _admin_faq_delete_payload(payload: dict) -> dict:
    try:
        entry_id = int(payload.get("id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid faq entry id") from exc

    await db.delete_faq_entry(entry_id)
    return await _admin_faq_payload()


def _build_admin_settings_updates(field: str, raw_value: object, now: float | None = None) -> dict[str, str]:
    if field not in _ADMIN_PRICING_FIELDS:
        raise ValueError("Unknown admin setting")

    value = str(raw_value or "").strip()

    if field in set(DELIVERY_TIMING_FIELD_KEYS):
        return {field: value[:100]}

    if field == "rate_override":
        if not value:
            return {"rate_override": "", "rate_override_until": "0"}
        try:
            numeric_value = float(value.replace(",", ".").replace(" ", ""))
        except ValueError as exc:
            raise ValueError("Value must be a number") from exc
        if numeric_value <= 0:
            return {"rate_override": "", "rate_override_until": "0"}
        expires_at = (now if now is not None else time.time()) + 86400
        return {
            "rate_override": str(numeric_value),
            "rate_override_until": str(expires_at),
        }

    try:
        numeric_value = float(value.replace(",", ".").replace(" ", ""))
    except ValueError as exc:
        raise ValueError("Value must be a number") from exc

    if numeric_value < 0:
        raise ValueError("Value must be non-negative")

    return {field: str(numeric_value)}


async def _admin_settings_payload() -> dict:
    settings = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    override_until = float(settings.get("rate_override_until", "0") or "0")
    now = time.time()
    override_value = settings.get("rate_override", "")
    manual_override_active = bool(override_value and now < override_until)

    normalized_settings = {
        key: settings.get(key, default_value)
        for key, default_value in db.DEFAULT_ADMIN_SETTINGS.items()
    }

    return {
        "settings": normalized_settings,
        "effective_rate": effective_rate,
        "rate_source": "manual" if manual_override_active else "cbr",
        "rate_override_active": manual_override_active,
        "rate_override_expires_at": (
            datetime.fromtimestamp(override_until).isoformat()
            if manual_override_active
            else None
        ),
    }


async def _admin_settings_update_payload(payload: dict) -> dict:
    field = str(payload.get("field") or "").strip()
    updates = _build_admin_settings_updates(field, payload.get("value"))

    for key, value in updates.items():
        await db.set_admin_setting(key, value)

    return await _admin_settings_payload()


async def _admin_settings_reset_payload() -> dict:
    for key, value in db.DEFAULT_ADMIN_SETTINGS.items():
        await db.set_admin_setting(key, str(value))
    return await _admin_settings_payload()


def _normalize_showcase_links(raw_links: object) -> list[str]:
    links = raw_links if isinstance(raw_links, list) else []
    normalized_links: list[str] = []

    for index in range(_SHOWCASE_SLOT_COUNT):
        raw_value = links[index] if index < len(links) else ""
        normalized_links.append(str(raw_value or "").strip()[:_SHOWCASE_FIELD_MAX_LENGTH])

    return normalized_links


async def _admin_showcase_payload() -> dict:
    payload = await _showcase_payload(include_links=True)
    return {
        "links": payload["links"],
        "items": payload["items"],
        "configured_count": payload["configured_count"],
        "row_size": _SHOWCASE_ROW_SIZE,
    }


async def _admin_showcase_update_payload(payload: dict) -> dict:
    links = _normalize_showcase_links(payload.get("links"))
    invalid_slot_errors: dict[str, str] = {}
    duplicate_slot_errors: dict[str, str] = {}
    parsed_products: list[dict | None] = [None] * _SHOWCASE_SLOT_COUNT
    current_slots = await db.get_admin_showcase_slots()
    seen_links: dict[str, int] = {}

    for index, raw_link in enumerate(links):
        if not raw_link:
            continue

        normalized_url = _extract_product_input_url(raw_link)
        if not normalized_url:
            invalid_slot_errors[str(index + 1)] = "Вставьте корректную ссылку на товар."
            continue

        links[index] = normalized_url
        first_slot = seen_links.get(normalized_url)
        if first_slot is not None:
            duplicate_slot_errors[str(index + 1)] = f"Этот товар уже закреплен в слоте {first_slot}."
            continue

        seen_links[normalized_url] = index + 1

    if invalid_slot_errors:
        raise ShowcaseValidationError("invalid_showcase_links", slot_errors=invalid_slot_errors)

    if duplicate_slot_errors:
        raise ShowcaseValidationError("duplicate_showcase_links", slot_errors=duplicate_slot_errors)

    for index, normalized_url in enumerate(links):
        if not normalized_url:
            continue

        current_slot = current_slots[index] if index < len(current_slots) else {}
        current_url = str(current_slot.get("url") or "").strip()
        cached_payload = _deserialize_showcase_product_payload(current_slot.get("product_json"))
        if current_url == normalized_url and not _showcase_product_payload_is_incomplete(cached_payload):
            parsed_products[index] = cached_payload
            continue

        try:
            parsed_products[index] = await _parse_product(normalized_url)
        except Exception:
            invalid_slot_errors[str(index + 1)] = "Не удалось загрузить товар по этой ссылке."

    if invalid_slot_errors:
        raise ShowcaseValidationError("showcase_products_unavailable", slot_errors=invalid_slot_errors)

    updated_slots: list[dict] = []
    for index, normalized_url in enumerate(links, start=1):
        product_payload = parsed_products[index - 1]
        product_json = json.dumps(product_payload, ensure_ascii=False) if product_payload else ""
        await db.set_admin_showcase_slot(index, normalized_url, product_json)
        updated_slots.append(
            {
                "slot": index,
                "url": normalized_url,
                "product_json": product_json,
                "updated_at": time.time(),
            }
        )

    settings = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    response_payload = _showcase_payload_from_slots(
        updated_slots,
        settings,
        effective_rate,
        include_links=True,
    )
    return {
        "links": response_payload["links"],
        "items": response_payload["items"],
        "configured_count": response_payload["configured_count"],
        "row_size": _SHOWCASE_ROW_SIZE,
    }

async def _admin_messages_payload(payload: dict | None = None) -> dict:
    request_payload = payload or {}
    page = _normalize_admin_page(request_payload.get("page"), default=1)
    page_size = min(50, _normalize_admin_page(request_payload.get("page_size"), default=10))

    rows = list(reversed(await db.msg_get_all()))

    stats_by_type = {
        key: 0
        for key in _ADMIN_MESSAGE_TYPE_LABELS
    }
    for row in rows:
        msg_type = str(row.get("msg_type") or "").strip()
        if msg_type in stats_by_type:
            stats_by_type[msg_type] += 1

    total_items = len(rows)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(page, total_pages)
    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    items = []
    for row in rows[start_index:end_index]:
        username = str(row.get("username") or "").strip()
        user_id = int(row.get("user_id") or 0)
        sent_at = str(row.get("sent_at") or "")
        msg_type = str(row.get("msg_type") or "").strip()

        items.append({
            "id": int(row.get("id") or 0),
            "user_id": user_id,
            "username": username,
            "contact_label": f"@{username}" if username else f"id:{user_id}",
            "msg_type": msg_type,
            "type_label": _ADMIN_MESSAGE_TYPE_LABELS.get(msg_type, msg_type or "Сообщение"),
            "text": str(row.get("text") or ""),
            "sent_at": sent_at,
            "sent_at_label": _format_admin_message_datetime(sent_at),
        })

    latest_sent_at = str(rows[0].get("sent_at") or "") if rows else ""

    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_prev": page > 1 and total_items > 0,
            "has_next": page < total_pages,
        },
        "stats": {
            "total": total_items,
            "by_type": stats_by_type,
            "latest_sent_at": latest_sent_at,
            "latest_sent_at_label": _format_admin_message_datetime(latest_sent_at),
        },
    }


async def _admin_messages_clear_payload() -> dict:
    await db.msg_delete_all()
    return await _admin_messages_payload({"page": 1, "page_size": 10})


def _build_admin_user_identity(user_id: int, username: str) -> dict[str, str | int]:
    clean_username = str(username or "").strip()
    return {
        "user_id": user_id,
        "username": clean_username,
        "contact_label": f"@{clean_username}" if clean_username else f"id:{user_id}",
        "display_name": f"@{clean_username}" if clean_username else f"Пользователь #{user_id}",
    }


def _extract_admin_calc_snapshot(row: dict) -> tuple[str, float | None]:
    image_url = ""
    goods_rub = None
    calc_json_raw = row.get("calc_json")

    if not calc_json_raw:
        return image_url, goods_rub

    try:
        calc_payload = json.loads(calc_json_raw)
        product_payload = calc_payload.get("product") or {}
        image_url = str(
            product_payload.get("image_url")
            or calc_payload.get("image_url")
            or ""
        )

        breakdown = calc_payload.get("breakdown") or []
        goods_line = next(
            (
                line
                for line in breakdown
                if str(line.get("label") or "").strip().lower().startswith("товар")
            ),
            None,
        )
        if goods_line and goods_line.get("amount_rub") is not None:
            goods_rub = float(goods_line["amount_rub"])
        else:
            exchange_rate_payload = calc_payload.get("exchange_rate") or {}
            cny_rub = exchange_rate_payload.get("cny_rub")
            if cny_rub is not None and row.get("price_cny") is not None:
                goods_rub = float(row["price_cny"]) * float(cny_rub)
    except Exception:
        image_url = ""
        goods_rub = None

    return image_url, goods_rub


def _normalize_item_number(value: object) -> str:
    return str(value or "").strip().lstrip("#").strip()


def _normalize_admin_selected_variants_value(raw_value: object) -> list[dict[str, str]]:
    selected_variants: list[dict[str, str]] = []

    if isinstance(raw_value, dict):
        iterable = raw_value.items()
        for index, (raw_label, raw_selected_value) in enumerate(iterable):
            label = str(raw_label or "").strip() or f"Вариант {index + 1}"
            selected_value = str(raw_selected_value or "").strip()
            if not selected_value:
                continue
            selected_variants.append({
                "label": label,
                "value": selected_value,
            })
        return selected_variants

    if not isinstance(raw_value, list):
        return selected_variants

    for index, entry in enumerate(raw_value):
        label = ""
        selected_value = ""

        if isinstance(entry, dict):
            label = str(
                entry.get("label")
                or entry.get("name")
                or entry.get("group")
                or entry.get("key")
                or ""
            ).strip()
            selected_value = str(
                entry.get("value")
                or entry.get("option")
                or entry.get("selected")
                or entry.get("choice")
                or ""
            ).strip()
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            label = str(entry[0] or "").strip()
            selected_value = str(entry[1] or "").strip()
        else:
            selected_value = str(entry or "").strip()

        if not selected_value:
            continue

        selected_variants.append({
            "label": label or f"Вариант {index + 1}",
            "value": selected_value,
        })

    return selected_variants


def _extract_admin_selected_variants(row: dict) -> list[dict[str, str]]:
    size_text = str(row.get("size") or "").strip()
    calc_payload = {}
    product_payload = {}
    variant_groups = []
    calc_json_raw = row.get("calc_json")

    if calc_json_raw:
        try:
            calc_payload = json.loads(calc_json_raw)
            if not isinstance(calc_payload, dict):
                calc_payload = {}
            product_payload = calc_payload.get("product")
            if not isinstance(product_payload, dict):
                product_payload = calc_payload
            if not size_text:
                size_text = str(
                    product_payload.get("size")
                    or calc_payload.get("size")
                    or ""
                ).strip()
            variant_groups = (
                product_payload.get("variants")
                or calc_payload.get("variants")
                or []
            )
        except Exception:
            variant_groups = []

    explicit_selected_variants = (
        _normalize_admin_selected_variants_value(product_payload.get("selected_variants"))
        or _normalize_admin_selected_variants_value(calc_payload.get("selected_variants"))
        or _normalize_admin_selected_variants_value(product_payload.get("selected_options"))
        or _normalize_admin_selected_variants_value(calc_payload.get("selected_options"))
    )
    if explicit_selected_variants:
        return explicit_selected_variants

    if not size_text:
        return []

    parts = [part.strip() for part in size_text.split("/") if part.strip()]
    if not parts:
        return []

    remaining_parts = parts.copy()
    selected_variants: list[dict[str, str]] = []

    for group in variant_groups:
        if not isinstance(group, dict):
            continue

        label = str(group.get("name") or "").strip()
        options = [
            str(option.get("name") if isinstance(option, dict) else option).strip()
            for option in (group.get("options") or [])
        ]
        match = next((part for part in remaining_parts if part in options), "")
        if not match:
            continue

        selected_variants.append({
            "label": label or f"Вариант {len(selected_variants) + 1}",
            "value": match,
        })
        remaining_parts.remove(match)

    if not selected_variants:
        return [{"label": "Выбранный вариант", "value": size_text}]

    if remaining_parts:
        selected_variants.append({
            "label": "Дополнительно",
            "value": " / ".join(remaining_parts),
        })

    return selected_variants


def _extract_admin_delivery_snapshot(row: dict) -> tuple[dict, bool, str, str]:
    delivery_data = _normalize_delivery_payload(None)
    delivery_snapshot_raw = row.get("delivery_snapshot_json")
    submission_batch_id = str(row.get("submission_batch_id") or "")
    submitted_at = str(row.get("submitted_at") or "")

    if delivery_snapshot_raw:
        try:
            delivery_snapshot = json.loads(delivery_snapshot_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            delivery_snapshot = {}
        delivery_data = _normalize_delivery_payload(delivery_snapshot)

    delivery_complete = not _delivery_missing_required(delivery_data)
    return delivery_data, delivery_complete, submission_batch_id, submitted_at


def _admin_order_status_payload(row: dict) -> dict[str, str]:
    if row.get("arrived"):
        return {
            "key": "arrived",
            "label": "Доставлено",
            "description": "Пользователь уже получил уведомление о прибытии.",
        }

    if row.get("shipped"):
        return {
            "key": "shipped",
            "label": "Отправлен",
            "description": "Товар в пути к клиенту.",
        }

    if row.get("paid"):
        return {
            "key": "paid",
            "label": "Оплачен",
            "description": "Оплата подтверждена, можно отмечать отправку.",
        }

    if row.get("order_submitted"):
        return {
            "key": "submitted",
            "label": "На рассмотрении",
            "description": "Пользователь уже отправил заявку на оформление.",
        }

    return {
        "key": "in_order",
        "label": "В заявке",
        "description": "Товар уже добавлен в заявку, но ещё не отправлен на оформление.",
    }


def _admin_contact_reply_markup() -> dict | None:
    contact_url = _admin_contact_url()
    if not contact_url:
        return None

    return {
        "inline_keyboard": [[
            {
                "text": "Связаться с администратором",
                "url": contact_url,
            },
        ]],
    }


def _admin_order_display_name(item: dict) -> str:
    return str(
        item.get("short_name")
        or item.get("name")
        or f"Товар #{int(item.get('calc_id') or 0)}"
    ).strip()[:80]


async def _send_telegram_message(
    user_id: int,
    text: str,
    *,
    reply_markup: dict | None = None,
) -> bool:
    if user_id <= 0 or not BOT_TOKEN or not text:
        return False

    payload = {
        "chat_id": user_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                raise RuntimeError(result.get("description") or "sendMessage failed")
    except Exception:
        log.warning("Failed to send Telegram notification to user_id=%s", user_id, exc_info=True)
        return False

    return True


async def _notify_admin_order_action(action: str, item: dict) -> None:
    user_id = int(item.get("user_id") or 0)
    if user_id <= 0:
        return

    product_name = _admin_order_display_name(item)
    contact_markup = _admin_contact_reply_markup()

    if action == "mark_paid":
        await _send_telegram_message(
            user_id,
            f"✅ Ваш товар «{product_name}» оплачен.\n\nСкоро выкупим и отправим.",
        )
        return

    if action == "remove_paid":
        await _send_telegram_message(
            user_id,
            f"❌ Оплата по товару «{product_name}» была отменена.\n\nСвяжитесь с администратором для уточнений.",
            reply_markup=contact_markup,
        )
        return

    if action == "mark_shipped":
        await _send_telegram_message(
            user_id,
            f"🚚 Ваш товар отправлен.\n\n• {product_name}\n\nОжидайте прибытия.",
        )
        return

    if action == "set_tracking":
        tracking_number = str(item.get("tracking_number") or "").strip()
        if not tracking_number:
            return

        await _send_telegram_message(
            user_id,
            "🚚 Для вашего товара добавлен трек-номер.\n\n"
            f"• {product_name}\n"
            f"• Трек-номер: {tracking_number}\n\n"
            "Он также доступен в miniapp в разделе «Мои заказы».",
            reply_markup=contact_markup,
        )
        return

    if action == "mark_arrived":
        await _send_telegram_message(
            user_id,
            f"📦 Ваш товар прибыл.\n\n• {product_name}\n\nСвяжитесь с администратором для согласования получения.",
            reply_markup=contact_markup,
        )
        return

    if action == "remove_order":
        await _send_telegram_message(
            user_id,
            f"🗑 Ваш товар «{product_name}» был удалён из заявки администратором.\n\nЕсли это ошибка, свяжитесь с нами.",
            reply_markup=contact_markup,
        )


async def _admin_orders_payload() -> dict:
    rows = [
        row
        for row in await db.cart_get_all_orders()
        if bool(row.get("order_submitted"))
    ]

    stats = {
        "users_total": 0,
        "items_total": len(rows),
        "pending_items": 0,
        "submitted_items": 0,
        "paid_items": 0,
        "shipped_items": 0,
        "arrived_items": 0,
        "total_with_margin_rub": 0.0,
        "latest_order_added_at": "",
        "latest_order_added_at_label": "—",
    }

    users: list[dict] = []
    users_map: dict[int, dict] = {}

    for row in rows:
        user_id = int(row.get("user_id") or 0)
        username = str(row.get("username") or "").strip()

        user_payload = users_map.get(user_id)
        if user_payload is None:
            user_payload = {
                **_build_admin_user_identity(user_id, username),
                "total_items": 0,
                "pending_items": 0,
                "submitted_items": 0,
                "paid_items": 0,
                "shipped_items": 0,
                "arrived_items": 0,
                "total_with_margin_rub": 0.0,
                "latest_order_added_at": "",
                "latest_order_added_at_label": "—",
                "items": [],
            }
            users_map[user_id] = user_payload
            users.append(user_payload)

        order_added_at = str(row.get("order_added_at") or "")
        tracking_number = str(row.get("tracking_number") or "").strip()
        item_number = _normalize_item_number(row.get("item_number"))
        total_with_margin_rub = float(row.get("total_with_margin_rub") or 0)
        image_url, goods_rub = _extract_admin_calc_snapshot(row)
        selected_variants = _extract_admin_selected_variants(row)
        delivery_data, delivery_complete, submission_batch_id, submitted_at = _extract_admin_delivery_snapshot(row)
        status = _admin_order_status_payload(row)

        item_payload = {
            "user_id": user_id,
            "calc_id": int(row.get("calc_id") or 0),
            "name": str(row.get("name") or ""),
            "short_name": str(row.get("short_name") or ""),
            "product_url": str(row.get("product_url") or ""),
            "price_cny": row.get("price_cny"),
            "goods_rub": goods_rub,
            "subtotal_rub": float(row.get("subtotal_rub") or 0),
            "total_with_margin_rub": total_with_margin_rub,
            "platform": str(row.get("platform") or ""),
            "image_url": image_url,
            "size_text": str(row.get("size") or "").strip(),
            "paid": bool(row.get("paid")),
            "shipped": bool(row.get("shipped")),
            "arrived": bool(row.get("arrived")),
            "order_submitted": bool(row.get("order_submitted")),
            "order_added_at": order_added_at,
            "order_added_at_label": _format_admin_message_datetime(order_added_at),
            "tracking_number": tracking_number,
            "item_number": item_number,
            "selected_variants": selected_variants,
            "status_key": status["key"],
            "status_label": status["label"],
            "status_description": status["description"],
            "delivery_data": delivery_data,
            "delivery_complete": delivery_complete,
            "submission_batch_id": submission_batch_id,
            "submitted_at": submitted_at,
        }

        user_payload["total_items"] += 1
        user_payload["pending_items"] += int(item_payload["status_key"] == "submitted")
        user_payload["submitted_items"] += int(item_payload["order_submitted"])
        user_payload["paid_items"] += int(item_payload["paid"])
        user_payload["shipped_items"] += int(item_payload["shipped"])
        user_payload["arrived_items"] += int(item_payload["arrived"])
        user_payload["total_with_margin_rub"] += total_with_margin_rub
        user_payload["items"].append(item_payload)

        if order_added_at and order_added_at > str(user_payload["latest_order_added_at"] or ""):
            user_payload["latest_order_added_at"] = order_added_at
            user_payload["latest_order_added_at_label"] = _format_admin_message_datetime(order_added_at)

        stats["pending_items"] += int(item_payload["status_key"] == "submitted")
        stats["submitted_items"] += int(item_payload["order_submitted"])
        stats["paid_items"] += int(item_payload["paid"])
        stats["shipped_items"] += int(item_payload["shipped"])
        stats["arrived_items"] += int(item_payload["arrived"])
        stats["total_with_margin_rub"] += total_with_margin_rub

        if order_added_at and order_added_at > str(stats["latest_order_added_at"] or ""):
            stats["latest_order_added_at"] = order_added_at
            stats["latest_order_added_at_label"] = _format_admin_message_datetime(order_added_at)

    for user_payload in users:
        user_payload["items"].sort(
            key=lambda item: (
                str(item.get("order_added_at") or ""),
                int(item.get("calc_id") or 0),
            ),
            reverse=True,
        )

    users.sort(
        key=lambda user: (
            str(user.get("latest_order_added_at") or ""),
            int(user.get("total_items") or 0),
            int(user.get("user_id") or 0),
        ),
        reverse=True,
    )

    stats["users_total"] = len(users)

    return {
        "users": users,
        "stats": stats,
    }


async def _admin_orders_update_payload(payload: dict) -> dict:
    action = str(payload.get("action") or "").strip()
    tracking_number = str(payload.get("tracking_number") or "").strip()
    item_number = _normalize_item_number(payload.get("item_number"))

    try:
        user_id = int(payload.get("user_id") or 0)
        calc_id = int(payload.get("calc_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid user_id or calc_id") from exc

    if user_id <= 0 or calc_id <= 0:
        raise ValueError("user_id and calc_id are required")

    rows = [
        row
        for row in await db.cart_get_all_orders()
        if bool(row.get("order_submitted"))
    ]
    item = next(
        (
            row
            for row in rows
            if int(row.get("user_id") or 0) == user_id and int(row.get("calc_id") or 0) == calc_id
        ),
        None,
    )
    if item is None:
        raise ValueError("Order item not found")

    if action == "mark_paid":
        if not bool(item.get("paid")):
            await db.cart_set_paid(user_id, calc_id, True)
            await _notify_admin_order_action(action, item)
        return await _admin_orders_payload()

    if action == "remove_paid":
        if bool(item.get("paid")):
            await db.cart_set_paid(user_id, calc_id, False)
            await _notify_admin_order_action(action, item)
        return await _admin_orders_payload()

    if action == "mark_shipped":
        if not bool(item.get("arrived")) and not bool(item.get("shipped")):
            await db.cart_set_shipped([calc_id])
            await _notify_admin_order_action(action, item)
        return await _admin_orders_payload()

    if action == "mark_arrived":
        if not bool(item.get("arrived")):
            await db.cart_set_arrived([calc_id])
            await _notify_admin_order_action(action, item)
        return await _admin_orders_payload()

    if action == "set_tracking":
        if not tracking_number:
            raise ValueError("tracking_number is required")
        if len(tracking_number) > 120:
            raise ValueError("tracking_number is too long")

        updated_item = {
            **item,
            "tracking_number": tracking_number,
        }
        await db.cart_set_tracking_number(user_id, calc_id, tracking_number)
        await _notify_admin_order_action(action, updated_item)
        return await _admin_orders_payload()

    if action == "set_item_number":
        if not item_number:
            raise ValueError("item_number is required")
        if len(item_number) > 60:
            raise ValueError("item_number is too long")

        await db.cart_set_item_number(user_id, calc_id, item_number)
        return await _admin_orders_payload()

    if action == "remove_order":
        await db.cart_set_order(user_id, calc_id, False)
        await _notify_admin_order_action(action, item)
        return await _admin_orders_payload()

    raise ValueError("Unknown admin order action")


async def _admin_carts_payload() -> dict:
    rows = await db.cart_get_all_carts()

    stats = {
        "users_total": 0,
        "items_total": len(rows),
        "items_in_order": 0,
        "subtotal_rub": 0.0,
        "total_with_margin_rub": 0.0,
    }

    users: list[dict] = []
    users_map: dict[int, dict] = {}

    for row in rows:
        user_id = int(row.get("user_id") or 0)
        username = str(row.get("username") or "").strip()

        user_payload = users_map.get(user_id)
        if user_payload is None:
            user_payload = {
                "user_id": user_id,
                "username": username,
                "contact_label": f"@{username}" if username else f"id:{user_id}",
                "display_name": f"@{username}" if username else f"Пользователь #{user_id}",
                "total_items": 0,
                "items_in_order": 0,
                "subtotal_rub": 0.0,
                "total_with_margin_rub": 0.0,
                "items": [],
            }
            users_map[user_id] = user_payload
            users.append(user_payload)

        subtotal_rub = float(row.get("subtotal_rub") or 0)
        total_with_margin_rub = float(row.get("total_with_margin_rub") or 0)
        in_order = bool(row.get("in_order"))
        image_url = ""
        goods_rub = None
        selected_variants = _extract_admin_selected_variants(row)

        calc_json_raw = row.get("calc_json")
        if calc_json_raw:
            try:
                calc_payload = json.loads(calc_json_raw)
                product_payload = calc_payload.get("product") or {}
                image_url = str(
                    product_payload.get("image_url")
                    or calc_payload.get("image_url")
                    or ""
                )

                breakdown = calc_payload.get("breakdown") or []
                goods_line = next(
                    (
                        line
                        for line in breakdown
                        if str(line.get("label") or "").strip().lower().startswith("товар")
                    ),
                    None,
                )
                if goods_line and goods_line.get("amount_rub") is not None:
                    goods_rub = float(goods_line["amount_rub"])
                else:
                    exchange_rate_payload = calc_payload.get("exchange_rate") or {}
                    cny_rub = exchange_rate_payload.get("cny_rub")
                    if cny_rub is not None and row.get("price_cny") is not None:
                        goods_rub = float(row["price_cny"]) * float(cny_rub)
            except Exception:
                image_url = ""
                goods_rub = None

        user_payload["total_items"] += 1
        user_payload["items_in_order"] += int(in_order)
        user_payload["subtotal_rub"] += subtotal_rub
        user_payload["total_with_margin_rub"] += total_with_margin_rub
        user_payload["items"].append({
            "calc_id": int(row.get("calc_id") or 0),
            "name": str(row.get("name") or ""),
            "short_name": str(row.get("short_name") or ""),
            "product_url": str(row.get("product_url") or ""),
            "price_cny": row.get("price_cny"),
            "goods_rub": goods_rub,
            "subtotal_rub": subtotal_rub,
            "total_with_margin_rub": total_with_margin_rub,
            "platform": str(row.get("platform") or ""),
            "image_url": image_url,
            "selected_variants": selected_variants,
            "in_order": in_order,
        })

        stats["items_in_order"] += int(in_order)
        stats["subtotal_rub"] += subtotal_rub
        stats["total_with_margin_rub"] += total_with_margin_rub

    stats["users_total"] = len(users)

    return {
        "users": users,
        "stats": stats,
    }


def _get_cached_admin_avatar(user_id: int) -> tuple[str | None, bytes | None] | None:
    with _admin_avatar_cache_lock:
        cached = _admin_avatar_cache.get(user_id)
        if not cached:
            return None

        expires_at, content_type, body = cached
        if time.time() >= expires_at:
            _admin_avatar_cache.pop(user_id, None)
            return None

        return content_type, body


def _store_cached_admin_avatar(
    user_id: int,
    content_type: str | None,
    body: bytes | None,
    *,
    ttl_seconds: int,
) -> None:
    with _admin_avatar_cache_lock:
        _admin_avatar_cache[user_id] = (
            time.time() + ttl_seconds,
            content_type,
            body,
        )


async def _admin_avatar_bytes(user_id: int) -> tuple[str, bytes] | None:
    if user_id <= 0 or not BOT_TOKEN:
        return None

    cached = _get_cached_admin_avatar(user_id)
    if cached is not None:
        content_type, body = cached
        if content_type and body:
            return content_type, body
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            photos_response = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
            )
            photos_response.raise_for_status()
            photos_payload = photos_response.json()
            photos = ((photos_payload.get("result") or {}).get("photos") or [])
            if not photos or not photos[0]:
                _store_cached_admin_avatar(
                    user_id,
                    None,
                    None,
                    ttl_seconds=_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS,
                )
                return None

            file_id = str((photos[0][-1] or {}).get("file_id") or "").strip()
            if not file_id:
                _store_cached_admin_avatar(
                    user_id,
                    None,
                    None,
                    ttl_seconds=_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS,
                )
                return None

            file_response = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            file_response.raise_for_status()
            file_payload = file_response.json()
            file_path = str((file_payload.get("result") or {}).get("file_path") or "").strip()
            if not file_path:
                _store_cached_admin_avatar(
                    user_id,
                    None,
                    None,
                    ttl_seconds=_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS,
                )
                return None

            if file_path.startswith(("https://", "http://")):
                file_url = file_path
            else:
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path.lstrip('/')}"

            image_response = await client.get(file_url)
            image_response.raise_for_status()
            body = image_response.content
            if not body:
                _store_cached_admin_avatar(
                    user_id,
                    None,
                    None,
                    ttl_seconds=_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS,
                )
                return None

            content_type = str(image_response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if not content_type or content_type == "application/octet-stream":
                lower_file_url = file_url.lower()
                if lower_file_url.endswith(".png"):
                    content_type = "image/png"
                elif lower_file_url.endswith(".webp"):
                    content_type = "image/webp"
                else:
                    content_type = "image/jpeg"
            _store_cached_admin_avatar(
                user_id,
                content_type,
                body,
                ttl_seconds=_ADMIN_AVATAR_CACHE_TTL_SECONDS,
            )
            return content_type, body
    except Exception:
        log.warning("Failed to fetch admin avatar for user_id=%s", user_id, exc_info=True)
        _store_cached_admin_avatar(
            user_id,
            None,
            None,
            ttl_seconds=_ADMIN_AVATAR_CACHE_MISS_TTL_SECONDS,
        )
        return None


async def _parse_product(url: str) -> dict:
    normalized_url = _extract_product_input_url(url)
    if not normalized_url:
        raise RuntimeError("url is required")

    draft = await parse_url(normalized_url)

    # Translate Chinese specs to Russian via Groq
    if draft.specs:
        try:
            from services.translator import translate_specs_with_groq
            draft.specs = await translate_specs_with_groq(draft.specs)
        except Exception:
            pass  # keep original specs if translation fails

    return _draft_to_dict(draft)


async def _product_by_spu(spu_id: str) -> dict:
    """Fetch product by Poizon spu_id — directly via RapidAPI, no URL resolution."""
    import httpx
    from services.poizon_api import fetch_product_detail
    from services.parser import infer_category, parse_poizon_html_specs

    draft = ProductDraft(
        url=build_dewu_share_url(spu_id),
        platform="poizon",
    )

    # 1. Fetch product detail directly by spu_id
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        info = await fetch_product_detail(client, spu_id)

    if not info:
        raise RuntimeError(f"Product not found: {spu_id}")

    # 2. Fill draft from API response
    if info.get("name"):
        draft.name = info["name"]
    if info.get("price"):
        draft.price_cny = info["price"]
        draft.price_is_starting = bool(info.get("price_is_starting", False))
    if info.get("brand"):
        draft.brand = info["brand"]
    if info.get("image_url"):
        draft.image_url = info["image_url"]
    if info.get("extra_images"):
        draft.extra_images = info["extra_images"]
    if info.get("specs"):
        draft.specs = info["specs"]
    if info.get("available_sizes"):
        draft.available_sizes = info["available_sizes"]
    if info.get("weight_kg"):
        draft.weight_kg = info["weight_kg"]
        draft.weight_estimated = False
    if info.get("variant_price_map"):
        draft.variant_price_map = info["variant_price_map"]

    # Translate variants
    raw_variants = info.get("variants") or []
    if raw_variants:
        try:
            from services.translator import translate_variants_with_groq
            draft.variants = await translate_variants_with_groq(raw_variants)
        except Exception:
            draft.variants = raw_variants

    # Infer category
    draft.category = infer_category(draft.name or "", info.get("category", ""))

    # Translate name
    try:
        import re as _re
        from services.translator import translate_if_cn
        if draft.name:
            cn_blocks = _re.findall(r'[\u4e00-\u9fff]+', draft.name)
            if cn_blocks:
                _name = draft.name
                for blk in cn_blocks:
                    try:
                        tr = await translate_if_cn(blk)
                        _name = _name.replace(blk, f' {tr} ', 1)
                    except Exception:
                        pass
                draft.name = _re.sub(r'\s{2,}', ' ', _name).strip()
            else:
                draft.name = await translate_if_cn(draft.name)
    except Exception:
        pass

    # 3. Fallback to HTML only when API still lacks core card data.
    if needs_poizon_html_fallback(draft):
        try:
            share_url = f"https://fast.dewu.com/page/productDetail?spuId={spu_id}&sourceName=shareDetail"
            html_info = await parse_poizon_html_specs(share_url)
            if html_info.get("name") and not draft.name:
                draft.name = html_info["name"]
            if html_info.get("brand") and not draft.brand:
                draft.brand = html_info["brand"]
            if html_info.get("image_url") and not draft.image_url:
                draft.image_url = html_info["image_url"]
            if html_info.get("extra_images") and not draft.extra_images:
                draft.extra_images = html_info["extra_images"]
            if html_info.get("specs") and not draft.specs:
                draft.specs = html_info["specs"]
            if html_info.get("weight_kg") and not draft.weight_kg:
                draft.weight_kg = html_info["weight_kg"]
        except Exception:
            pass

    # 4. Translate specs
    if draft.specs:
        try:
            from services.translator import translate_specs_with_groq
            draft.specs = await translate_specs_with_groq(draft.specs)
        except Exception:
            pass

    return _draft_to_dict(draft)


async def _calculate_payload(payload: dict) -> dict:
    result = await _build_calculation_result(payload)
    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    resp = _result_to_payload(
        result,
        settings=admin,
        effective_rate=effective_rate,
    )

    # Auto-save to history
    user_id = int(payload.get("user_id") or 0)
    calc_id = payload.get("calc_id")
    if user_id:
        await _track_miniapp_activity(user_id)
        try:
            if calc_id:
                await db.update_calculation(int(calc_id), user_id, result)
                resp["calc_id"] = int(calc_id)
            else:
                new_id, share_code = await db.save_calculation(user_id, result)
                resp["calc_id"] = new_id
                resp["share_code"] = share_code
        except Exception as e:
            log.warning("auto-save calculation failed: %s", e)

    return resp


async def _save_calculation_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    if not user_id:
        raise RuntimeError("user_id is required")

    await _track_miniapp_activity(user_id)
    result = await _build_calculation_result(payload)
    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    calc_payload = _result_to_payload(
        result,
        settings=admin,
        effective_rate=effective_rate,
    )
    calc_id, share_code = await db.save_calculation(user_id, result)
    return {"calc_id": calc_id, "share_code": share_code, "result": calc_payload}


async def _history_payload(user_id: int) -> list[dict]:
    await _track_miniapp_activity(user_id)
    rows = await db.get_history(user_id, limit=20)
    # Enrich rows with image_url parsed from calc_json
    for row in rows:
        cj = row.get("calc_json")
        if cj:
            try:
                parsed = json.loads(cj)
                row["url"] = parsed.get("url", "")
                row["price_is_starting"] = bool(parsed.get("price_is_starting", False))
                row["size"] = parsed.get("size", "")
                row["weight_kg"] = parsed.get("weight_kg")
                row["weight_estimated"] = bool(parsed.get("weight_estimated", False))
                row["notes"] = parsed.get("notes", "")
                row["image_url"] = parsed.get("image_url", "")
                row["extra_images"] = parsed.get("extra_images", [])
                row["variants"] = parsed.get("variants", [])
                row["original_variants"] = parsed.get("original_variants", [])
                row["variant_price_map"] = parsed.get("variant_price_map", {})
                row["specs"] = parsed.get("specs", {})
                row["available_sizes"] = parsed.get("available_sizes", [])
                row["brand"] = parsed.get("brand", "")
                row["category"] = parsed.get("category", "")
                row["breakdown"] = parsed.get("breakdown", [])
            except Exception:
                pass
        # Remove raw calc_json to reduce payload size
        row.pop("calc_json", None)
    return rows


async def _cart_payload(user_id: int) -> list[dict]:
    await _track_miniapp_activity(user_id)
    rows = await db.cart_get_items(user_id)
    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()

    # Backfill short_name for items that don't have one yet
    from services.market_compare import extract_search_query
    for row in rows:
        row["tracking_number"] = str(row.get("tracking_number") or "").strip()
        row["item_number"] = _normalize_item_number(row.get("item_number"))
        if row.get("price_cny") is not None:
            try:
                draft = _draft_from_calc_row(row)
                pricing = _pricing_components_for_draft(
                    draft,
                    admin,
                    effective_rate,
                    delivery_type=STANDARD_DELIVERY_TYPE,
                    include_cdek=False,
                )
                row["subtotal_rub"] = pricing["subtotal_rub"]
                row["total_with_margin_rub"] = pricing["subtotal_rub"]
            except Exception:
                pass
        if not row.get("short_name") and row.get("name"):
            try:
                category = ""
                if row.get("calc_json"):
                    import json as _json
                    try:
                        cj = _json.loads(row["calc_json"])
                        category = cj.get("category") or cj.get("product", {}).get("category", "")
                    except Exception:
                        pass
                short = await extract_search_query(row["name"], category)
                if short:
                    row["short_name"] = short
                    await db.update_short_name(row["id"], short)
            except Exception as e:
                log.warning("backfill short_name failed for calc %s: %s", row.get("id"), e)

    return rows


async def _add_to_cart_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    calc_id = int(payload.get("calc_id") or 0)
    if user_id <= 0 or calc_id <= 0:
        raise RuntimeError("user_id and calc_id are required")
    await _track_miniapp_activity(user_id)
    log.info("cart_add: user=%s calc=%s", user_id, calc_id)
    await db.cart_add(user_id, calc_id)
    return {"ok": True}


async def _save_and_add_to_cart(payload: dict) -> dict:
    """Save calculation + add to cart in a single request."""
    user_id = int(payload.get("user_id") or 0)
    if not user_id:
        raise RuntimeError("user_id is required")
    await _track_miniapp_activity(user_id)
    result = await _build_calculation_result(payload)
    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    calc_payload = _result_to_payload(
        result,
        settings=admin,
        effective_rate=effective_rate,
    )
    calc_id, share_code = await db.save_calculation(user_id, result)
    log.info("save_and_add_to_cart: user=%s calc=%s", user_id, calc_id)
    await db.cart_add(user_id, calc_id)

    # Generate short name via Groq (non-blocking — don't fail if it errors)
    try:
        from services.market_compare import extract_search_query
        name = result.product.name or ""
        category = result.product.category or ""
        if name:
            short = await extract_search_query(name, category)
            if short:
                await db.update_short_name(calc_id, short)
    except Exception as e:
        log.warning("short_name generation failed: %s", e)

    return {"ok": True, "calc_id": calc_id}


async def _remove_from_cart_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    calc_id = int(payload.get("calc_id") or 0)
    if user_id <= 0 or calc_id <= 0:
        raise RuntimeError("user_id and calc_id are required")
    await _track_miniapp_activity(user_id)
    await db.cart_remove(user_id, calc_id)
    return {"ok": True}


async def _clear_cart_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    if user_id <= 0:
        raise RuntimeError("user_id is required")
    await _track_miniapp_activity(user_id)
    await db.cart_clear(user_id)
    return {"ok": True}


async def _apply_order_delivery_pricing(
    user_id: int,
    delivery_data: dict,
    *,
    delivery_type: str,
) -> None:
    rows = await db.cart_get_pending_order_items(user_id)
    if not rows:
        return

    admin = await db.get_admin_settings()
    effective_rate = await get_effective_rate()
    rate_snapshot = await er.get_rate()
    if not rate_snapshot:
        rate_snapshot = ExchangeRate(
            cny_rub=effective_rate,
            usd_rub=0.0,
            eur_rub=0.0,
            updated_at=datetime.utcnow(),
        )

    include_cdek = not is_moscow_city(delivery_data.get("city"))
    normalized_delivery_type = normalize_delivery_type(delivery_type)

    for row in rows:
        calc_id = int(row.get("id") or 0)
        if calc_id <= 0:
            continue

        draft = _draft_from_calc_row(row)
        draft.city = str(delivery_data.get("city") or draft.city or "")
        pricing = _pricing_components_for_draft(
            draft,
            admin,
            effective_rate,
            delivery_type=normalized_delivery_type,
            include_cdek=include_cdek,
        )
        result = _build_result_from_pricing(
            draft,
            rate_snapshot=rate_snapshot,
            effective_rate=effective_rate,
            pricing=pricing,
        )
        await db.update_calculation(calc_id, user_id, result)


async def _submit_order_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    if user_id <= 0:
        raise RuntimeError("user_id is required")
    await _track_miniapp_activity(user_id)
    delivery_record = await db.get_delivery_profile(user_id)
    delivery_data = _normalize_delivery_payload(delivery_record)
    missing_required = _delivery_missing_required(delivery_data)
    if missing_required:
        error = ValueError("delivery_data_incomplete")
        setattr(error, "missing_required", missing_required)
        raise error

    delivery_type = normalize_delivery_type(payload.get("delivery_type"))
    await _apply_order_delivery_pricing(
        user_id,
        delivery_data,
        delivery_type=delivery_type,
    )

    submission_batch_id = f"sub-{user_id}-{int(time.time() * 1000)}"
    submitted_at = datetime.utcnow().isoformat()
    await db.cart_apply_delivery_snapshot(
        user_id,
        delivery_data,
        submission_batch_id,
        submitted_at,
    )
    await db.cart_submit_order(user_id)
    return {
        "ok": True,
        "submission_batch_id": submission_batch_id,
        "submitted_at": submitted_at,
    }


async def _set_order_payload(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    calc_id = int(payload.get("calc_id") or 0)
    value = bool(payload.get("value", False))
    if user_id <= 0 or calc_id <= 0:
        raise RuntimeError("user_id and calc_id are required")
    await _track_miniapp_activity(user_id)
    await db.cart_set_order(user_id, calc_id, value)
    return {"ok": True}


async def _cart_item_detail(payload: dict) -> dict:
    user_id = int(payload.get("user_id") or 0)
    calc_id = int(payload.get("calc_id") or 0)
    if user_id <= 0 or calc_id <= 0:
        raise RuntimeError("user_id and calc_id are required")
    await _track_miniapp_activity(user_id)
    row = await db.get_calculation_by_id(calc_id, user_id)
    if not row:
        raise RuntimeError("Item not found")
    rate = await er.get_rate()
    if not rate:
        raise RuntimeError("Exchange rate unavailable")
    result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
    # Translate variants, variant_price_map keys, and specs if they contain Chinese
    from services.translator import translate_variants_with_groq, translate_specs_with_groq, has_chinese, translate_if_cn
    raw_variants = result.product.variants or []
    if raw_variants and any(has_chinese(g.get("name", "")) or any(has_chinese(str(o)) for o in g.get("options", [])) for g in raw_variants):
        try:
            translated_variants = await translate_variants_with_groq(raw_variants)
            # Remap variant_price_map keys to match translated names
            if result.product.variant_price_map:
                group_name_map = {}
                option_value_map = {}
                for raw_g, trans_g in zip(raw_variants, translated_variants):
                    rn = str(raw_g.get("name", "")).strip()
                    tn = str(trans_g.get("name", rn)).strip()
                    if rn:
                        group_name_map[rn] = tn
                    for ro, to in zip(raw_g.get("options", []), trans_g.get("options", [])):
                        option_value_map[(rn, str(ro).strip())] = str(to).strip()
                new_map = {}
                for raw_key, price in result.product.variant_price_map.items():
                    try:
                        pairs = json.loads(raw_key)
                    except Exception:
                        continue
                    translated_pairs = []
                    for name, value in pairs:
                        name, value = str(name).strip(), str(value).strip()
                        translated_pairs.append([
                            group_name_map.get(name, name),
                            option_value_map.get((name, value), value),
                        ])
                    new_map[json.dumps(sorted(translated_pairs), ensure_ascii=False)] = price
                result.product.variant_price_map = new_map
            result.product.variants = translated_variants
        except Exception:
            pass
    if result.product.specs and any(has_chinese(str(k)) or has_chinese(str(v)) for k, v in result.product.specs.items()):
        try:
            result.product.specs = await translate_specs_with_groq(result.product.specs)
        except Exception:
            pass
    admin = await db.get_admin_settings()
    eff_rate = await get_effective_rate()
    pricing = _pricing_components_for_draft(
        result.product,
        admin,
        eff_rate,
        delivery_type=STANDARD_DELIVERY_TYPE,
        include_cdek=False,
    )
    breakdown = _build_pricing_breakdown_payload(
        price_cny=float(result.product.price_cny or 0),
        effective_rate=eff_rate,
        pricing=pricing,
    )
    subtotal = pricing["subtotal_rub"]
    return {
        "product": _draft_to_dict(result.product),
        "breakdown": breakdown,
        "subtotal_rub": subtotal,
        "exchange_rate": _display_rate_payload(
            rate,
            settings=admin,
            effective_rate=eff_rate,
        ),
        "delivery_info": _build_delivery_info_payload(admin),
    }


async def _cart_update_variant(payload: dict) -> dict:
    """Recalculate cart item after variant/size change and persist."""
    user_id = int(payload.get("user_id") or 0)
    calc_id = int(payload.get("calc_id") or 0)
    new_price_cny = float(payload.get("price_cny") or 0)
    new_size = str(payload.get("size", ""))
    if user_id <= 0 or calc_id <= 0 or new_price_cny <= 0:
        raise RuntimeError("user_id, calc_id, price_cny are required")
    await _track_miniapp_activity(user_id)
    row = await db.get_calculation_by_id(calc_id, user_id)
    if not row:
        raise RuntimeError("Item not found")
    rate = await er.get_rate()
    if not rate:
        raise RuntimeError("Exchange rate unavailable")
    result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
    # Apply new variant selection
    result.product.price_cny = new_price_cny
    result.product.price_is_starting = False
    result.product.size = new_size
    admin = await db.get_admin_settings()
    eff_rate = await get_effective_rate()
    pricing = _pricing_components_for_draft(
        result.product,
        admin,
        eff_rate,
        delivery_type=STANDARD_DELIVERY_TYPE,
        include_cdek=False,
    )
    subtotal = pricing["subtotal_rub"]
    result.breakdown = _build_pricing_breakdown_lines(
        price_cny=float(new_price_cny or 0),
        effective_rate=eff_rate,
        pricing=pricing,
    )
    result.subtotal_rub = subtotal
    result.total_with_margin_rub = subtotal
    result.margin_rub = 0
    result.margin_percent = 0
    await db.update_calculation(calc_id, user_id, result)
    breakdown = _build_pricing_breakdown_payload(
        price_cny=float(new_price_cny or 0),
        effective_rate=eff_rate,
        pricing=pricing,
    )
    return {
        "breakdown": breakdown,
        "subtotal_rub": subtotal,
        "size": new_size,
        "exchange_rate": _display_rate_payload(
            rate,
            settings=admin,
            effective_rate=eff_rate,
        ),
        "delivery_info": _build_delivery_info_payload(admin),
    }


async def _compare_market(payload: dict) -> dict:
    """Compare product price with WB or Ozon marketplace."""
    product_name = str(payload.get("product_name", "")).strip()
    category = str(payload.get("category", "")).strip()
    market = str(payload.get("market", "wb")).strip().lower()
    our_price_rub = float(payload.get("our_price_rub", 0))

    if not product_name:
        raise RuntimeError("product_name is required")
    if market not in ("wb", "ozon"):
        raise RuntimeError("market must be 'wb' or 'ozon'")

    from services.market_compare import extract_search_query, search_wildberries, search_ozon

    search_query = await extract_search_query(product_name, category)

    if market == "wb":
        items, raw_items = await search_wildberries(search_query)
    else:
        items, raw_items = await search_ozon(search_query)

    if items is None:
        return {"status": "antibot", "query": search_query, "items": [], "raw_items": [], "avg_price": 0}

    if not items:
        return {"status": "empty", "query": search_query, "items": [], "raw_items": [], "avg_price": 0}

    avg_price = sum(it.price_rub for it in items) / len(items)

    def _serialize(it_list):
        return [
            {
                "name": it.name,
                "price_rub": it.price_rub,
                "rating": it.rating,
                "reviews": it.reviews,
                "url": it.url,
                "image_url": it.image_url,
            }
            for it in it_list
        ]

    return {
        "status": "ok",
        "query": search_query,
        "items": _serialize(items),
        "raw_items": _serialize(raw_items or []),
        "avg_price": int(avg_price),
        "our_price_rub": int(our_price_rub),
        "market": market,
    }


async def _search_products(payload: dict) -> dict:
    query = str(payload.get("query", "")).strip()
    count = int(payload.get("count", 50))
    count = max(10, min(100, count))
    start_id = int(payload.get("start_id", 0))
    platform = str(payload.get("platform", "poizon") or "poizon").strip().lower()

    if not query:
        raise RuntimeError("query is required")
    if platform not in ("poizon", "taobao", "1688"):
        raise RuntimeError("platform must be 'poizon', 'taobao' or '1688'")

    log.info(
        "search_products: platform=%s query=%s start_id=%s count=%s",
        platform,
        query,
        start_id,
        count,
    )

    from services.translator import translate_to_english
    english_query = await translate_to_english(query)
    total_count = 0
    provider_cursor: int | None = None

    import httpx
    from config import PROXY

    client_kwargs: dict[str, object] = {"timeout": 20.0}
    if PROXY:
        client_kwargs["proxy"] = PROXY

    async with httpx.AsyncClient(**client_kwargs) as client:
        if platform == "poizon":
            from services.poizon_api import fetch_keyword_search

            results, _last_id = await fetch_keyword_search(client, english_query, page_size=count, start_id=start_id)
            total_count = len(results)
            provider_cursor = int(_last_id or 0)

            # Translate variants, specs and names for each product
            from services.translator import translate_variants_with_groq, translate_if_cn, translate_specs_with_groq
            import re as _re
            from services.parser import infer_category

            for product in results:
                product["platform"] = "poizon"

                raw_variants = product.get("variants") or []
                if raw_variants:
                    try:
                        product["variants"] = await translate_variants_with_groq(raw_variants)
                    except Exception:
                        pass

                if product.get("specs"):
                    try:
                        product["specs"] = await translate_specs_with_groq(product["specs"])
                    except Exception:
                        pass

                product["category"] = infer_category(
                    product.get("title", ""), product.get("category", "")
                )

                name = product.get("title", "")
                if name:
                    cn_blocks = _re.findall(r'[\u4e00-\u9fff]+', name)
                    if cn_blocks:
                        for blk in cn_blocks:
                            try:
                                tr = await translate_if_cn(blk)
                                name = name.replace(blk, f' {tr} ', 1)
                            except Exception:
                                pass
                        product["title"] = _re.sub(r'\s{2,}', ' ', name).strip()
        else:
            if platform == "taobao":
                from services.taobao_1688_api import fetch_taobao_tmall_keyword_search

                results, total_count = await fetch_taobao_tmall_keyword_search(
                    client,
                    english_query,
                    frame_size=count,
                    frame_position=start_id,
                )
            else:
                from services.taobao_1688_api import (
                    build_open_1688_keyword_search_query,
                    fetch_open_1688_keyword_search,
                )

                provider_query = build_open_1688_keyword_search_query(query, english_query)
                results, total_count = await fetch_open_1688_keyword_search(
                    client,
                    provider_query,
                    page_size=count,
                    start_id=start_id,
                )
                english_query = provider_query

    admin = await db.get_admin_settings()
    rate_value = await get_effective_rate()
    next_start_id, has_more = _build_search_pagination(
        platform,
        start_id=start_id,
        count=count,
        loaded_count=len(results),
        total_count=total_count,
        provider_cursor=provider_cursor,
    )

    return {
        "products": results,
        "query_en": english_query,
        "total": total_count,
        "platform": platform,
        "has_more": has_more,
        "next_start_id": next_start_id,
        "rate_cny_rub": rate_value,
        "rate_source": "manual" if _manual_rate_state(admin)[0] else "cbr",
    }


class MiniAppHandler(BaseHTTPRequestHandler):
    server_version = "BuyerMiniApp/0.1"

    def _send_json(self, payload: object, status: int = 200) -> None:
        repaired_payload = _repair_mojibake_deep(payload)
        body = json.dumps(repaired_payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        body = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        cache_control = "no-store" if path.name == "index.html" else None
        self._send_bytes(body, content_type=mime, cache_control=cache_control)

    def _send_bytes(
        self,
        body: bytes,
        *,
        content_type: str,
        status: int = 200,
        cache_control: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        return _repair_mojibake_deep(payload)

    def _require_user(self, payload: dict | None = None) -> int | None:
        """Validate initData from payload and return trusted user id."""
        if payload is None:
            payload = self._json_body()
        init_data_raw = payload.get("init_data", "")
        if not init_data_raw:
            self._send_json({"error": "Missing init_data"}, status=403)
            return None
        try:
            user_id = get_user_id_from_init_data(init_data_raw)
        except ValueError:
            self._send_json({"error": "Invalid init_data"}, status=403)
            return None
        return user_id

    def _require_admin(self, payload: dict | None = None) -> int | None:
        """Validate initData from payload and check admin access."""
        user_id = self._require_user(payload)
        if user_id is None:
            return None
        if not is_admin(user_id):
            self._send_json({"error": "Forbidden"}, status=403)
            return None
        return user_id

    def _run(self, coro):
        return asyncio.run(coro)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "active_requests": active_requests})
            return
        if parsed.path.startswith("/uploads/"):
            upload_path = _resolve_upload_path(parsed.path)
            if not upload_path:
                self._send_json({"error": "Invalid upload path"}, status=400)
                return
            self._send_file(upload_path)
            return
        if parsed.path == "/api/image-proxy":
            query = parse_qs(parsed.query)
            target_url = str((query.get("url") or [""])[0] or "").strip()
            if not target_url:
                self._send_bytes(
                    b"url is required",
                    content_type="text/plain; charset=utf-8",
                    status=400,
                    cache_control="no-store",
                )
                return
            try:
                body, content_type, cache_control = self._run(_fetch_image_proxy(target_url))
                self._send_bytes(body, content_type=content_type, cache_control=cache_control)
            except ValueError as e:
                self._send_bytes(
                    str(e).encode("utf-8"),
                    content_type="text/plain; charset=utf-8",
                    status=400,
                    cache_control="no-store",
                )
            except Exception as e:
                log.warning("image proxy failed for %s: %s", target_url, e)
                self._send_bytes(
                    b"image proxy failed",
                    content_type="text/plain; charset=utf-8",
                    status=502,
                    cache_control="no-store",
                )
            return
        if parsed.path == "/api/bootstrap":
            query = parse_qs(parsed.query)
            query_user_id = int((query.get("user_id") or ["0"])[0] or "0")
            try:
                trusted_user_id, is_admin_user = _resolve_bootstrap_identity(
                    query_user_id if query_user_id > 0 else None,
                    "",
                )
                payload = self._run(_bootstrap_payload(trusted_user_id, is_admin_user))
                self._send_json(payload)
            except Exception as e:
                log.exception("bootstrap error")
                self._send_json({"error": str(e)}, status=500)
            return

        if parsed.path == "/api/faq":
            try:
                payload = self._run(_faq_payload())
                self._send_json(payload)
            except Exception as e:
                log.exception("faq error")
                self._send_json({"error": str(e)}, status=500)
            return

        if parsed.path == "/api/history":
            query = parse_qs(parsed.query)
            user_id = int((query.get("user_id") or ["0"])[0] or "0")
            if user_id <= 0:
                self._send_json({"error": "user_id is required"}, status=400)
                return
            try:
                payload = self._run(_history_payload(user_id))
                self._send_json(payload)
            except Exception as e:
                log.exception("history error")
                self._send_json({"error": str(e)}, status=500)
            return

        if parsed.path == "/api/cart":
            query = parse_qs(parsed.query)
            user_id = int((query.get("user_id") or ["0"])[0] or "0")
            if user_id <= 0:
                self._send_json({"error": "user_id is required"}, status=400)
                return
            try:
                payload = self._run(_cart_payload(user_id))
                self._send_json(payload)
            except Exception as e:
                log.exception("cart error")
                self._send_json({"error": str(e)}, status=500)
            return

        if parsed.path == "/api/profile/delivery":
            query = parse_qs(parsed.query)
            user_id = int((query.get("user_id") or ["0"])[0] or "0")
            if user_id <= 0:
                self._send_json({"error": "user_id is required"}, status=400)
                return
            try:
                payload = self._run(_delivery_profile_payload(user_id))
                self._send_json(payload)
            except Exception as e:
                log.exception("delivery profile error")
                self._send_json({"error": str(e)}, status=500)
            return

        file_path = _resolve_static_file_path(parsed.path)
        self._send_file(file_path)

    def do_POST(self) -> None:
        try:
            payload = self._json_body()
        except Exception:
            self._send_json({"error": "Invalid JSON"}, status=400)
            return

        try:
            if self.path == "/api/bootstrap":
                try:
                    trusted_user_id, is_admin_user = _resolve_bootstrap_identity(
                        int(payload.get("user_id") or 0),
                        payload.get("init_data", ""),
                    )
                except ValueError:
                    self._send_json({"error": "Invalid init_data"}, status=403)
                    return
                result = self._run(_bootstrap_payload(trusted_user_id, is_admin_user))
                self._send_json(result)
                return
            if self.path == "/api/parse-product":
                with _track_active_request():
                    result = self._run(_parse_product(payload.get("url", "")))
                    self._send_json(result)
                return
            if self.path == "/api/calculate":
                result = self._run(_calculate_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/save-calculation":
                result = self._run(_save_calculation_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/compare":
                result = self._run(_compare_market(payload))
                self._send_json(result)
                return
            if self.path == "/api/search-products":
                try:
                    result = self._run(_search_products(payload))
                except TaobaoSearchUnavailableError:
                    self._send_json(
                        {
                            "error": "Поиск по Taobao временно недоступен. Попробуйте чуть позже.",
                            "code": "taobao_search_unavailable",
                        },
                        status=503,
                    )
                    return
                except Open1688SearchUnavailableError:
                    self._send_json(
                        {
                            "error": "РџРѕРёСЃРє РїРѕ 1688 РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРµРЅ. РџРѕРїСЂРѕР±СѓР№С‚Рµ С‡СѓС‚СЊ РїРѕР·Р¶Рµ.",
                            "code": "1688_search_unavailable",
                        },
                        status=503,
                    )
                    return
                self._send_json(result)
                return
            if self.path == "/api/product-by-spu":
                result = self._run(_product_by_spu(payload.get("spu_id", "")))
                self._send_json(result)
                return
            if self.path == "/api/cart/save-and-add":
                result = self._run(_save_and_add_to_cart(payload))
                self._send_json(result)
                return
            if self.path == "/api/cart/add":
                result = self._run(_add_to_cart_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/cart/remove":
                result = self._run(_remove_from_cart_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/cart/clear":
                result = self._run(_clear_cart_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/profile/delivery/save":
                result = self._run(_save_delivery_profile_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/cart/set-order":
                result = self._run(_set_order_payload(payload))
                self._send_json(result)
                return
            if self.path == "/api/cart/submit-order":
                try:
                    result = self._run(_submit_order_payload(payload))
                except ValueError as exc:
                    if str(exc) != "delivery_data_incomplete":
                        raise
                    missing_required = [
                        field
                        for field in getattr(exc, "missing_required", DELIVERY_REQUIRED_FIELDS)
                        if field in DELIVERY_REQUIRED_FIELDS
                    ]
                    self._send_json(
                        {
                            "error": "delivery_data_incomplete",
                            "missing_required": missing_required,
                        },
                        status=400,
                    )
                    return
                self._send_json(result)
                return
            if self.path == "/api/cart/item-detail":
                result = self._run(_cart_item_detail(payload))
                self._send_json(result)
                return

            if self.path == "/api/cart/update-variant":
                result = self._run(_cart_update_variant(payload))
                self._send_json(result)
                return
            if self.path == "/api/avatar":
                user_id = self._require_user(payload)
                if user_id is None:
                    return
                avatar_payload = self._run(_admin_avatar_bytes(user_id))
                if avatar_payload is None:
                    self._send_json({"error": "Avatar not found"}, status=404)
                    return
                content_type, body = avatar_payload
                self._send_bytes(
                    body,
                    content_type=content_type,
                    cache_control="private, max-age=3600",
                )
                return
            if self.path == "/api/admin/settings":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_settings_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/settings/update":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_settings_update_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/settings/reset":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_settings_reset_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/showcase":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                with _track_active_request():
                    result = self._run(_admin_showcase_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/showcase/update":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    with _track_active_request():
                        result = self._run(_admin_showcase_update_payload(payload))
                except ShowcaseValidationError as exc:
                    self._send_json(
                        {
                            "error": str(exc),
                            "slot_errors": getattr(exc, "slot_errors", {}),
                        },
                        status=400,
                    )
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/about-carousel":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_about_details_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/about-carousel/upload":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_about_details_upload_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/about-carousel/delete":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_about_details_delete_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/banners":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_promo_banners_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/banners/save":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_promo_banner_save_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/banners/delete":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_promo_banner_delete_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/banners/upload":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_promo_banner_upload_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/faq":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_faq_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/faq/save":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_faq_save_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/faq/delete":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_faq_delete_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/messages":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_messages_payload(payload))
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/messages/clear":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_messages_clear_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/orders":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_orders_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/orders/update":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    result = self._run(_admin_orders_update_payload(payload))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/carts":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                result = self._run(_admin_carts_payload())
                self._send_json({"ok": True, "admin_id": admin_id, **result})
                return
            if self.path == "/api/admin/avatar":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                try:
                    user_id = int(payload.get("user_id") or 0)
                except (TypeError, ValueError):
                    self._send_json({"error": "Invalid user_id"}, status=400)
                    return
                if user_id <= 0:
                    self._send_json({"error": "Invalid user_id"}, status=400)
                    return
                avatar_payload = self._run(_admin_avatar_bytes(user_id))
                if avatar_payload is None:
                    self._send_json({"error": "Avatar not found"}, status=404)
                    return
                content_type, body = avatar_payload
                self._send_bytes(
                    body,
                    content_type=content_type,
                    cache_control="private, max-age=3600",
                )
                return
            if self.path == "/api/admin/ping":
                admin_id = self._require_admin(payload)
                if admin_id is None:
                    return
                self._send_json({"ok": True, "admin_id": admin_id})
                return
        except Exception as e:
            log.exception("mini app POST error")
            self._send_json({"error": str(e)}, status=500)
            return

        self._send_json({"error": "Not found"}, status=404)


def run_server() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    asyncio.run(db.init_db())
    server = ThreadingHTTPServer(("127.0.0.1", MINI_APP_PORT), MiniAppHandler)
    log.info("Mini app server listening on http://127.0.0.1:%s", MINI_APP_PORT)
    server.serve_forever()


if __name__ == "__main__":
    run_server()
