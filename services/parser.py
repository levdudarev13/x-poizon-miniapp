"""Парсинг ссылок Poizon / Taobao / 1688.

Что извлекаем: название, цена, бренд, категория, изображение.
Цены на Dewu/Taobao/1688 грузятся через авторизованный JS-API —
без браузера получается только из встроенного JSON (работает для Dewu fast.dewu.com).
"""

import re
import json
import asyncio
import hashlib
import os
import httpx
import logging
from urllib.parse import urlparse, parse_qs

from config import PLATFORM_POIZON, PLATFORM_TAOBAO, PLATFORM_1688, PLATFORM_UNKNOWN, PLATFORM_URL_PATTERNS, DEWU_TOKEN, PROXY
from models import ProductDraft
from services.poizon_api import fetch_product_detail
from services.taobao_1688_api import (
    build_info_from_1688_datahub,
    build_info_from_open_1688_detail,
    build_info_from_taobao_1688_item,
    build_info_from_taobao_data_item,
    build_info_from_taobao_tmall_full_info,
    extract_item_id,
    fetch_1688_datahub_detail,
    fetch_1688_datahub_package,
    fetch_1688_datahub_simple,
    fetch_open_1688_product_detail,
    fetch_taobao_1688_item_by_url,
    fetch_taobao_1688_item_detail,
    fetch_taobao_data_item_detail,
    fetch_taobao_tmall_full_info,
)

log = logging.getLogger(__name__)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)
HEADERS = {
    "User-Agent": MOBILE_UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _variant_price_key_from_dict(selected: dict[str, str]) -> str:
    normalized = sorted(
        (str(name).strip(), str(value).strip())
        for name, value in selected.items()
        if str(name).strip() and str(value).strip()
    )
    return json.dumps(normalized, ensure_ascii=False)


def _merge_preferred_fields(preferred: dict, fallback: dict) -> dict:
    merged = dict(preferred)
    for key, value in fallback.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def _has_taobao_core_fields(info: dict) -> bool:
    return bool(
        info.get("price")
        and info.get("name")
        and (info.get("variants") or info.get("available_sizes") or info.get("specs"))
    )


def _has_1688_core_fields(info: dict) -> bool:
    return bool(info.get("price") and info.get("name"))

# ── Категории ──────────────────────────────────────────────────────────────────
# Ключевые слова для определения категории из названия/китайской категории
# Китайские категории → наши ключи (надёжные данные прямо со страницы)
CN_CATEGORY_MAP = {
    "鞋": "sneakers", "运动鞋": "sneakers", "板鞋": "sneakers",
    "服装": "clothing", "上衣": "clothing", "裤子": "clothing", "外套": "clothing",
    "包": "bag", "背包": "bag", "斜挎包": "bag", "手提包": "bag", "腰包": "bag",
    "帽子": "accessories", "配件": "accessories", "首饰": "accessories",
    "数码": "electronics", "手机": "electronics", "手表": "electronics",
}


def infer_category(name: str, cn_category: str = "") -> str:
    """Определить категорию по китайской категории со страницы."""
    for cn, key in CN_CATEGORY_MAP.items():
        if cn in cn_category:
            return key
    en_category = cn_category.strip().lower()
    if "shoes" in en_category or "slippers" in en_category:
        return "sneakers"
    if any(word in en_category for word in ("jackets", "coats", "hoodies", "pants", "t-shirts")):
        return "clothing"
    if any(word in en_category for word in ("bags", "backpacks")):
        return "bag"
    if any(word in en_category for word in ("wallets", "caps", "accessories")):
        return "accessories"
    return ""


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    for platform, patterns in PLATFORM_URL_PATTERNS.items():
        if any(p in url_lower for p in patterns):
            return platform
    return PLATFORM_UNKNOWN


def is_valid_url(text: str) -> bool:
    text = text.strip()
    if not text.startswith(("http://", "https://")):
        return False
    try:
        return bool(urlparse(text).netloc)
    except Exception:
        return False


def extract_url(text: str) -> str | None:
    """Извлечь первую http(s)-ссылку из текста (даже если текст — шаринг из приложения)."""
    m = re.search(r"https?://[^\s\u4e00-\u9fff\u0400-\u04FF\"'<>]+", text)
    if m:
        url = m.group(0).rstrip(".,;:!?)")
        if urlparse(url).netloc:
            return url
    return None


# ── Вспомогательные извлечения ────────────────────────────────────────────────

BLACKLIST = {
    "productDetail", "先鉴别后发货", "购物须知", "历史图文",
    "实物对比", "退货", "Loading", "loading", "undefined",
    "null", "得物App", "Page",
    # Taobao/Tmall маркетинговые слоганы (не товар!)
    "天猫淘宝海外", "天貓淘寶海外", "花更少", "买到寶", "買到寶",
    "淘宝 - 淘！我喜欢", "淘宝网", "天猫", "tmall.com",
}


def _is_product_name(s: str) -> bool:
    if len(s) < 6:
        return False
    has_cn = bool(re.search(r"[\u4e00-\u9fff]", s))
    has_latin = bool(re.search(r"[A-Za-z]", s))
    if not has_cn and not has_latin:
        return False
    return not any(b.lower() in s.lower() for b in BLACKLIST)


def _find_name(html: str) -> str | None:
    # 1. Dewu SSR: <div class="_title_XXXXX">название</div> — самый надёжный источник
    # Минимум 20 символов — иначе ловим короткий бренд вместо полного названия
    m = re.search(r'class="_title_[^"]*">([^<]{20,200})<', html)
    if m and _is_product_name(m.group(1)):
        return m.group(1).strip()
    # 2. JSON-поля с конкретными ключами (не "title"/"name" — слишком общие)
    hits = re.findall(
        r'"(?:spuName|goodsName|productName|articleTitle|structureTitle|originalTitle)"'
        r':"([^"]{6,120})"',
        html,
    )
    for h in hits:
        if _is_product_name(h):
            return h.strip()
    # 3. og:title
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:title["\'][^>]+content=["\']([^"\']{6,120})["\']',
        html, re.I,
    )
    if m and _is_product_name(m.group(1)):
        return m.group(1).strip()
    # 4. <title>
    m = re.search(r"<title[^>]*>([^<]{6,150})</title>", html, re.I)
    if m:
        t = m.group(1).strip()
        for sep in [" - 得物", " - Poizon", " - 淘宝", " - 1688", " | ", " – "]:
            if sep in t:
                t = t.split(sep)[0].strip()
                break
        if _is_product_name(t):
            return t
    return None


# ── Dewu API: подпись и получение реальной цены ──────────────────────────────

_DEWU_SALT = "048a9c4943398714b356a696503d2d36"
_DEWU_API_BASE = "https://app.dewu.com"


def _dewu_serialize(v) -> str:
    """Сериализация значения по правилам Dewu JS."""
    if v is None or v == "":
        return ""
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(json.dumps(item, separators=(",", ":"), ensure_ascii=False))
            elif item is None:
                parts.append("null")
            else:
                parts.append(str(item))
        return ",".join(parts)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _dewu_sign(params: dict) -> str:
    """MD5-подпись запроса: sorted(key+value) + salt."""
    token = "".join(
        k + _dewu_serialize(params[k])
        for k in sorted(params.keys())
        if params[k] is not None
    )
    return hashlib.md5((token + _DEWU_SALT).encode("utf-8")).hexdigest()


async def _dewu_api_price(client: httpx.AsyncClient, spu_id: str, sku_id: str | None) -> float | None:
    """Получить реальную цену через Dewu detailV5 API."""
    payload = {
        "extDatas": [{"name": "source", "value": "h5"}],
        "abTests": [{"name": "536_Labelgeneration", "value": "3"}],
        "params": {
            "spuId": int(spu_id),
            "skuId": int(sku_id) if sku_id else 0,
            "propertyValueId": 0,
            "sourceName": "shareDetail",
        },
    }
    sign = _dewu_sign(payload)
    url = f"{_DEWU_API_BASE}/api/v1/h5/index/fire/flow/product/detailV5?sign={sign}"
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appVersion": "4.4.0",
        "appId": "h5",
        "platform": "h5",
        "Referer": "https://fast.dewu.com/",
        "Origin": "https://fast.dewu.com",
    }
    if DEWU_TOKEN:
        headers["x-auth-token"] = DEWU_TOKEN
    try:
        r = await client.post(url, json=payload, headers=headers, timeout=10.0)
        log.info(f"dewu api: status={r.status_code}")
        if r.status_code != 200:
            return None
        data = r.json()
        log.info(f"dewu api: code={data.get('code')} msg={data.get('msg')!r}")
        # code=7999 = нет авторизации, но ответ может содержать частичные данные с ценой
        if data.get("code") not in (200, 7999):
            return None
        body = json.dumps(data, ensure_ascii=False)
        # Убираем 发售价格 из ответа перед поиском цены
        body = re.sub(r'发售价格[^¥￥\d]{0,20}[¥￥]?\s*\d+', '', body)
        price = _find_price(body)
        log.info(f"dewu api price found: {price}")
        return price
    except Exception as e:
        log.info(f"dewu api price error: {e}")
        return None


DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _taobao_headers(cookie_str: str = "", referer: str = "https://www.taobao.com/") -> dict:
    """Полные браузерные заголовки для запросов к Taobao/Tmall.

    Без Referer и sec-fetch-* Taobao видит запрос как бота.
    Эти заголовки имитируют переход пользователя внутри сайта.
    """
    h = {
        "User-Agent": MOBILE_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-site",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }
    if cookie_str:
        h["Cookie"] = cookie_str
    return h


def _playwright_sync_run(target_url: str, cookie_str: str = "", cookie_domain: str = "", extra_domains: list | None = None) -> tuple:
    """
    Playwright в отдельном потоке с ProactorEventLoop.
    cookie_str     — строка куков (формат: "name=val; name2=val2")
    cookie_domain  — основной домен для куков (например ".taobao.com")
    extra_domains  — дополнительные домены (например [".tmall.com"]) — те же куки
    Возвращает (price, name).
    """
    import asyncio as _asyncio

    async def _inner() -> tuple:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.info("playwright not installed")
            return (None, None)

        price_found: list[float] = []
        name_found: list[str] = []

        async def on_response(response):
            if price_found:
                return
            url = response.url
            if not any(k in url for k in (
                "detailV5", "productDetail", "sku", "price", "product/detail",
                "spuPrice", "skuPrice", "offerDetail", "detail", "item",
                "h5api-intl", "h5api.m.taobao", "getdetail", "pcdetail",
            )):
                return
            try:
                data = await response.json()
                body = json.dumps(data, ensure_ascii=False)
                body = re.sub(r'发售价格[^¥￥\d]{0,20}[¥￥]?\s*\d+', '', body)
                for pat in [
                    r'"(?:lowestPrice|currentPrice|showPrice|salePrice|sellPrice|skuPrice)":\s*"?(\d{2,6}(?:\.\d{1,2})?)"?',
                    r'"(?:minPrice|startPrice|tradePrice|priceText|defaultItemPrice)":\s*"?(\d{2,6}(?:\.\d{1,2})?)"?',
                    r'"price"\s*:\s*"(\d{2,6}(?:\.\d{1,2})?)"',
                    r'[¥￥]\s*(\d{3,6}(?:\.\d{1,2})?)\s*起',
                ]:
                    hits = [float(m) for m in re.findall(pat, body) if 10 <= float(m) <= 50000]
                    if hits:
                        log.info(f"playwright API price: {hits[0]} from {url[:80]}")
                        price_found.append(hits[0])
                        return
            except Exception as e:
                log.debug(f"playwright response parse: {e}")

        try:
            async with async_playwright() as pw:
                pw_proxy = None
                if PROXY:
                    from urllib.parse import urlparse as _urlparse
                    _p = _urlparse(PROXY)
                    pw_proxy = {"server": f"{_p.scheme}://{_p.hostname}:{_p.port}"}
                    if _p.username:
                        pw_proxy["username"] = _p.username
                    if _p.password:
                        pw_proxy["password"] = _p.password

                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    proxy=pw_proxy,
                )
                ctx = await browser.new_context(
                    user_agent=DESKTOP_UA,
                    locale="zh-CN",
                    viewport={"width": 1280, "height": 800},
                )
                # Инжектируем cookies если есть (на основной + дополнительные домены)
                if cookie_str and cookie_domain:
                    try:
                        domains_to_inject = [cookie_domain] + (extra_domains or [])
                        pw_cookies = []
                        for domain in domains_to_inject:
                            for part in cookie_str.split(";"):
                                part = part.strip()
                                if "=" in part:
                                    name, _, value = part.partition("=")
                                    pw_cookies.append({
                                        "name": name.strip(),
                                        "value": value.strip(),
                                        "domain": domain,
                                        "path": "/",
                                    })
                        await ctx.add_cookies(pw_cookies)
                        log.info(f"playwright: injected cookies for {domains_to_inject}")
                    except Exception as e:
                        log.info(f"playwright: cookie inject error: {e}")
                await ctx.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = await ctx.new_page()
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except ImportError:
                    pass
                page.on("response", on_response)
                log.info(f"playwright opening: {target_url}")
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=35000)
                except Exception:
                    pass

                # Логируем финальный URL после всех JS-редиректов
                final_page_url = page.url
                log.info(f"playwright final URL: {final_page_url}")

                if not price_found or "dewu.com" in target_url:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                if not price_found:
                    try:
                        price_el = await page.wait_for_selector('[class*="price"]', timeout=12000)
                        if price_el and "dewu.com" in target_url:
                            price_text = (await price_el.inner_text()).strip()
                            pm = re.search(r'(\d{2,6}(?:\.\d{1,2})?)', price_text)
                            if pm:
                                val = float(pm.group(1))
                                if 10 <= val <= 50000:
                                    log.info(f"playwright price_el text: {val!r} from {price_text!r}")
                                    price_found.append(val)
                    except Exception:
                        pass

                # Извлечь название из DOM для Dewu через CSS-селектор
                if not name_found and "dewu.com" in target_url:
                    for sel in ['[class*="title unfold"]', '[class*="title"]']:
                        try:
                            title_el = await page.wait_for_selector(sel, timeout=3000)
                            if title_el:
                                candidate = (await title_el.inner_text()).strip()
                                candidate = candidate.split('\n')[0].strip()
                                if candidate and len(candidate) > 8:
                                    name_found.append(candidate)
                                    log.info(f"playwright CSS name ({sel}): {candidate[:80]}")
                                    break
                        except Exception:
                            pass
                    # Fallback: regex по body_text
                    if not name_found:
                        try:
                            body_text_for_name = await page.inner_text("body", timeout=8000)
                            nm = re.search(r'([^\n]{15,200})\n[¥￥\xa5][\s\d,.]+起', body_text_for_name)
                            if nm:
                                candidate = nm.group(1).strip()
                                if _is_product_name(candidate):
                                    name_found.append(candidate)
                                    log.info(f"playwright body_text name: {candidate[:60]}")
                        except Exception as e:
                            log.info(f"playwright name extraction error: {e}")

                if not price_found:
                    try:
                        body_text = await page.inner_text("body", timeout=3000)
                        body_clean = re.sub(r'发售价格[\s\S]{0,30}?\d+', '', body_text)
                        # Убираем рекламные тексты с ценами (подарки новым пользователям и т.п.)
                        body_clean = re.sub(r'[¥￥\xa5]\s*\d+\s*(?:专属礼物|礼品|优惠券|红包|满减)', '', body_clean)
                        for pat in [
                            r"[¥￥\xa5]\s*(\d{2,6}(?:\.\d{1,2})?)\s*起",  # ¥589 起
                            r"(\d{3,6}(?:\.\d{1,2})?)\s*起",               # 589 起
                            r"[¥￥\xa5]\s*(\d{2,6}(?:\.\d{1,2})?)\b",     # ¥589 (без 起, конкретный вариант)
                        ]:
                            m = re.search(pat, body_clean)
                            if m:
                                val = float(m.group(1))
                                if 10 <= val <= 50000:
                                    log.info(f"playwright DOM price: {val} (pat={pat[:30]})")
                                    price_found.append(val)
                                    break
                    except Exception as e:
                        log.info(f"playwright body_text error: {e}")

                # Извлекаем группы вариантов (цвет, размер, ёмкость и т.д.)
                variants_found: list = []
                if "dewu.com" in target_url:
                    try:
                        # Раскрываем скрытые группы кнопкой "展开所有规格▼" если она есть
                        expanded = await page.evaluate("""
                            () => {
                                const btn = Array.from(
                                    document.querySelectorAll('span[role="button"]')
                                ).find(el => el.textContent.includes('展开所有规格'));
                                if (btn) { btn.click(); return true; }
                                return false;
                            }
                        """)
                        if expanded:
                            log.info("playwright: clicked '展开所有规格' button")
                            await _asyncio.sleep(0.6)

                        raw_groups = await page.evaluate("""
                            () => {
                                const groups = [];
                                const containers = document.querySelectorAll('[class*="2601963492"]');
                                containers.forEach(container => {
                                    const titleEl = container.querySelector('[class*="title"]');
                                    if (!titleEl) return;
                                    const name = titleEl.textContent.trim();
                                    if (!name || name.length > 20) return;
                                    const options = [];
                                    container.querySelectorAll('[title]').forEach(el => {
                                        const t = el.getAttribute('title').trim();
                                        if (t && t.length < 40 && !options.includes(t)) options.push(t);
                                    });
                                    if (options.length >= 1) groups.push({name, options});
                                });
                                return groups;
                            }
                        """)
                        if raw_groups:
                            variants_found.extend(raw_groups)
                            log.info(f"playwright variants: {[g['name'] for g in raw_groups]}")
                    except Exception as e:
                        log.info(f"playwright variants extract error: {e}")

                await browser.close()
        except Exception as e:
            log.info(f"playwright launch error: {e}")
            return None

        return (
            price_found[0] if price_found else None,
            name_found[0] if name_found else None,
            variants_found,
        )

    import sys as _sys
    loop = _asyncio.ProactorEventLoop() if _sys.platform == "win32" else _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    except Exception as e:
        log.info(f"playwright proactor error: {e}")
        return (None, None)
    finally:
        loop.close()


async def _playwright_price(url: str, cookie_str: str = "", cookie_domain: str = "", extra_domains: list | None = None) -> float | None:
    """Универсальный Playwright в ProactorEventLoop-потоке (совместимо с Windows SelectorEventLoop)."""
    import concurrent.futures
    import functools
    loop = asyncio.get_event_loop()
    fn = functools.partial(_playwright_sync_run, url, cookie_str, cookie_domain, extra_domains)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(executor, fn)
        try:
            result = await asyncio.wait_for(future, timeout=35.0)
            return result[0] if isinstance(result, tuple) else result
        except asyncio.TimeoutError:
            log.info("playwright timeout")
            return None


async def _dewu_price_playwright(url: str) -> tuple:
    """Возвращает (price, name, variants) из Playwright для Dewu."""
    import concurrent.futures
    import functools
    loop = asyncio.get_event_loop()
    fn = functools.partial(_playwright_sync_run, url, "", "", None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(executor, fn)
        try:
            result = await asyncio.wait_for(future, timeout=70.0)
            if isinstance(result, tuple) and len(result) == 3:
                return result
            if isinstance(result, tuple) and len(result) == 2:
                return (result[0], result[1], [])
            return (result, None, [])
        except asyncio.TimeoutError:
            log.info("playwright timeout")
            return (None, None, [])


def _find_price(html: str) -> float | None:
    # NOTE: authPrice на Dewu — MSRP/цена релиза, НЕ текущая цена продажи.
    # "value":"¥X" — поле спецификаций (发售价格), тоже НЕ цена продажи.
    # Реальная цена Dewu загружается через JS и недоступна в статическом HTML.

    # Убираем блок 发售价格 (MSRP/цена релиза), чтобы не путать с ценой продажи
    html = re.sub(r'发售价格[^¥￥\d]{0,20}[¥￥]?\s*\d+', '', html)

    patterns = [
        r'"(?:lowestPrice|currentPrice|salePrice|tradePrice|skuPrice|defaultPrice)"'
        r':\s*"?(\d{2,6}(?:\.\d{1,2})?)"?',
        r'"(?:priceText|priceStr)"\s*:\s*"(\d{2,6}(?:\.\d{1,2})?)"',
        r'"wantPrice"\s*:\s*"(\d{2,6}(?:\.\d{1,2})?)"',
        r'[¥￥]\s*(\d{3,6}(?:\.\d{1,2})?)',  # минимум 3 цифры — отсечь мелкие сборы
    ]
    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            try:
                val = float(m.group(1))
                if val > 10000:
                    val /= 100
                if 10 <= val <= 50000:
                    candidates.append(round(val, 2))
            except Exception:
                pass
    if not candidates:
        return None
    from collections import Counter
    return Counter(candidates).most_common(1)[0][0]


def _find_specs(html: str) -> dict:
    """Извлечь характеристики товара из HTML Poizon, включая rich params."""
    patterns = [
        (
            r'"(?:attrKey|propName|label|key)"\s*:\s*"([^"]{1,60})"\s*,'
            r'\s*"(?:attrValue|propValue|value)"\s*:\s*"([^"]{1,200})"'
        ),
        r'"key"\s*:\s*"([^"]{1,60})"\s*,\s*"value"\s*:\s*"([^"]{1,200})"',
    ]
    pairs: list[tuple[str, str]] = []
    for pattern in patterns:
        pairs.extend(re.findall(pattern, html))

    skip_keys = {
        "source",
        "function",
        "window.",
        "propertyValueId",
        "definitionId",
        "tagType",
        "paramGroupName",
        "windowPkButtonText",
    }
    skip_fragments = ("http://", "https://", "function", "window.", "{", "}", "[", "]", "<", ">")
    seen: dict[str, str] = {}
    for key, value in pairs:
        key = str(key).strip()
        value = str(value).strip()
        if not key or not value:
            continue
        if key in skip_keys:
            continue
        if len(key) > 40 or len(value) > 160:
            continue
        if any(fragment in key for fragment in skip_fragments):
            continue
        if any(fragment in value for fragment in skip_fragments):
            continue
        if key.lower() == value.lower():
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z]", key):
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value):
            continue
        seen.setdefault(key, value)
    return seen


def _find_weight_from_specs(specs: dict) -> float | None:
    """Извлечь вес из атрибутов если он явно указан."""
    weight_keys = {"重量", "净重", "毛重", "商品重量", "参考重量", "weight", "net weight"}
    for k, v in specs.items():
        if k.lower() in weight_keys or "重量" in k:
            # Парсим число из значения: "200g", "0.5kg", "500 克"
            m = re.search(r"([\d.]+)\s*(kg|g|克|千克)", v, re.I)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                if unit in ("g", "克"):
                    val /= 1000
                if 0.05 <= val <= 50:
                    return round(val, 3)
    return None


def _find_weight_from_dimensions(specs: dict) -> float | None:
    """Оценить вес по габаритам (Д×Ш×В в см) — для сумок/коробок."""
    dim_keys = {"尺寸", "外形尺寸", "规格", "产品尺寸", "dimensions", "size"}
    for k, v in specs.items():
        if k in dim_keys or "尺寸" in k:
            # "20×30×10 cm" или "20*30*10"
            m = re.search(r"([\d.]+)\s*[×xX*×]\s*([\d.]+)\s*[×xX*×]\s*([\d.]+)\s*(cm|mm)?", v)
            if m:
                a, b, c = float(m.group(1)), float(m.group(2)), float(m.group(3))
                unit = (m.group(4) or "cm").lower()
                if unit == "mm":
                    a, b, c = a/10, b/10, c/10
                # Плотность ~0.15 г/см³ для мягких товаров (одежда, сумки)
                volume_cm3 = a * b * c
                estimated_kg = round(volume_cm3 * 0.00015 + 0.2, 2)  # + 0.2 кг упаковка
                if 0.1 <= estimated_kg <= 5.0:
                    return estimated_kg
    return None


def _find_available_sizes(html: str) -> list:
    """Извлечь доступные размеры (обувь: 36–50, одежда: XS/S/M/L/XL)."""
    sizes = []
    # Числовые размеры обуви (EU: 35–50, US: 4–15)
    num_sizes = re.findall(r'"propertyValueName"\s*:\s*"(\d{2,3}(?:[./]\d{1,2})?)"', html)
    # Буквенные размеры одежды
    letter_sizes = re.findall(r'"propertyValueName"\s*:\s*"((?:XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL))"', html)
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    for s in num_sizes + letter_sizes:
        if s not in seen:
            seen.add(s)
            sizes.append(s)
    return sizes[:20]  # максимум 20 размеров


def _extract_json_array_after_pattern(html: str, pattern: str) -> list | None:
    match = re.search(pattern, html)
    if not match:
        return None

    start = match.end()
    while start < len(html) and html[start].isspace():
        start += 1
    if start >= len(html) or html[start] != "[":
        return None

    depth = 0
    in_string = False
    escape = False
    for end in range(start, len(html)):
        char = html[end]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : end + 1])
                except Exception:
                    return None
    return None


def _build_variant_groups(variant_rows: list[dict]) -> list:
    skip_names = {"非金刚位渠道", "source", "type", "status"}
    groups: dict[str, dict] = {}

    for index, row in enumerate(variant_rows):
        if not isinstance(row, dict):
            continue

        name = str(
            row.get("name")
            or row.get("propertyName")
            or row.get("label")
            or ""
        ).strip()
        value = str(
            row.get("value")
            or row.get("propertyValueName")
            or row.get("showValue")
            or row.get("optionName")
            or ""
        ).strip()
        if not name or not value:
            continue
        if name in skip_names or len(name) > 40 or len(value) > 80:
            continue

        try:
            level = int(str(row.get("level") or "").strip())
        except Exception:
            level = index + 1
        try:
            sort = int(str(row.get("sort") or "").strip())
        except Exception:
            sort = index + 1

        group = groups.setdefault(
            name,
            {"name": name, "options": [], "level": level, "sort": sort},
        )
        group["level"] = min(int(group.get("level", level)), level)
        group["sort"] = min(int(group.get("sort", sort)), sort)
        if value not in group["options"]:
            group["options"].append(value)

    return [
        {"name": group["name"], "options": group["options"]}
        for group in sorted(
            groups.values(),
            key=lambda item: (item["level"], item["sort"], item["name"]),
        )
        if group.get("options")
    ]


def _find_variants_from_html(html: str) -> list:
    """Извлечь группы вариантов из fast.dewu.com HTML."""
    sale_properties = _extract_json_array_after_pattern(
        html,
        r'"saleProperties"\s*:\s*\{\s*"list"\s*:\s*',
    )
    if sale_properties:
        result = _build_variant_groups(sale_properties)
        if result:
            log.info(f"dewu HTML saleProperties variants: {[g['name'] for g in result]}")
            return result

    pairs = re.findall(
        r'"name"\s*:\s*"([^"]{1,30})"\s*,\s*"value"\s*:\s*"([^"]{1,80})"',
        html,
    )
    result = _build_variant_groups(
        [{"name": name, "value": value, "level": index + 1, "sort": index + 1} for index, (name, value) in enumerate(pairs)]
    )
    log.info(f"dewu HTML variants: {[g['name'] for g in result]}")
    return result


def _find_brand(html: str) -> str | None:
    m = re.search(r'"brandName"\s*:\s*"([^"]{2,50})"', html)
    if m:
        v = m.group(1).strip()
        if _is_product_name(v):
            return v
    return None


def _find_cn_category(html: str) -> str:
    hits = re.findall(r'"(?:categoryName|catName)"\s*:\s*"([^"]{2,30})"', html)
    return hits[0] if hits else ""


def _find_image(html: str) -> str | None:
    """Лучший CDN-URL с изображением товара."""
    # Приоритет: pro-img (оригинальные фото товара)
    imgs = re.findall(r"https://cdn[.](?:poizon|dewu)[.]com/[^\"]{10,200}", html)
    prod_imgs = [u for u in imgs if "pro-img" in u and any(
        u.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")
    )]
    if prod_imgs:
        return prod_imgs[0]
    # node-common обычно иконки, но если нет ничего лучше — берём
    all_imgs = [u for u in imgs if any(
        u.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")
    )]
    return all_imgs[0] if all_imgs else None


def _find_extra_images(html: str) -> list:
    """Все фото товара (кроме первого) из CDN Dewu."""
    imgs = re.findall(r"https://cdn[.](?:poizon|dewu)[.]com/[^\"]{10,200}", html)
    prod_imgs = [u for u in imgs if any(
        seg in u for seg in ("pro-img", "materialPicPath")
    ) and any(
        u.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp")
    )]
    seen = set()
    unique = []
    for u in prod_imgs:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[1:]


# ── Taobao / 1688 вспомогательные функции ────────────────────────────────────

def _find_taobao_price(html: str) -> float | None:
    """Цена из JSON-структуры Taobao/Tmall."""
    patterns = [
        r'"priceText"\s*:\s*"(\d+(?:\.\d{1,2})?)"',
        r'"defaultItemPrice"\s*:\s*"(\d+(?:\.\d{1,2})?)"',
        r'"promotionPrice"\s*:\s*"(\d+(?:\.\d{1,2})?)"',
        r'"originalPrice"\s*:\s*"(\d+(?:\.\d{1,2})?)"',
        r'"price"\s*:\s*"(\d+(?:\.\d{1,2})?)"',
    ]
    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            try:
                val = float(m.group(1))
                if 5 <= val <= 50000:
                    candidates.append(round(val, 2))
            except Exception:
                pass
    if candidates:
        from collections import Counter
        return Counter(candidates).most_common(1)[0][0]
    return _find_price(html)


def _find_1688_price(html: str) -> float | None:
    """Цена из JSON-структуры 1688. Часто диапазон X~Y — берём минимум."""
    patterns = [
        # priceInfo/offerPrice: {"price":"X.XX"}
        r'"(?:priceInfo|offerPrice)"\s*:\s*\{[^}]{0,200}"price"\s*:\s*"([\d.]+)"',
        r'"price"\s*:\s*"([\d.~]+)"',  # может быть "10.5~20.0"
    ]
    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            try:
                val_str = m.group(1).split("~")[0]  # берём нижнюю границу диапазона
                val = float(val_str)
                if 1 <= val <= 50000:
                    candidates.append(round(val, 2))
            except Exception:
                pass
    if candidates:
        from collections import Counter
        return Counter(candidates).most_common(1)[0][0]
    return _find_price(html)


def _find_alibaba_image(html: str) -> str | None:
    """Главное изображение товара из Taobao/Tmall/1688 (alicdn.com CDN)."""
    # picUrl / mainPic / imageUrl в JSON
    imgs = re.findall(
        r'"(?:picUrl|mainPic|imageUrl|img|coverUrl)"\s*:\s*"((?:https?:)?//[^"]{10,200}(?:jpg|jpeg|png|webp)[^"]*)"',
        html, re.I,
    )
    if imgs:
        url = imgs[0]
        if url.startswith("//"):
            url = "https:" + url
        return url.split("_")[0] + ".jpg" if "_" in url and ".jpg" not in url.split("_")[-1] else url
    # og:image fallback
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I,
    )
    if m:
        return m.group(1)
    return None


# ── Платформо-специфичный парсинг ─────────────────────────────────────────────

async def _fetch(client: httpx.AsyncClient, url: str, max_chars: int = 800_000, cookie_str: str = "", extra_headers: dict | None = None) -> str:
    try:
        headers = {}
        if cookie_str:
            headers["Cookie"] = cookie_str
        if extra_headers:
            headers.update(extra_headers)  # extra_headers может переопределить Cookie
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return r.text[:max_chars]
        log.debug(f"fetch {url} → HTTP {r.status_code}")
    except Exception as e:
        log.debug(f"fetch {url} → {e}")
    return ""


def _extract_dewu_ids(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    spu_id = (qs.get("spuId") or qs.get("productNo") or [None])[0]
    sku_id = (qs.get("skuId") or [None])[0]
    prop_id = (qs.get("propertyValueId") or [None])[0]

    if not spu_id:
        m = re.search(r"/product[s]?/(\d+)", parsed.path)
        if m:
            spu_id = m.group(1)

    if not spu_id and parsed.netloc.lower().endswith("dw4.co"):
        m = re.fullmatch(r"/t/A/(\d+)", parsed.path)
        if m:
            spu_id = m.group(1)

    return spu_id, sku_id, prop_id


def build_dewu_share_url(spu_id: str, sku_id: str | None = None) -> str:
    clean_spu_id = str(spu_id or "").strip()
    clean_sku_id = str(sku_id or "").strip()
    if not clean_spu_id:
        return ""

    share_url = f"https://fast.dewu.com/page/productDetail?spuId={clean_spu_id}"
    if clean_sku_id:
        share_url += f"&skuId={clean_sku_id}"
    share_url += "&sourceName=shareDetail"
    return share_url


def build_dewu_desktop_url(
    spu_id: str,
    sku_id: str | None = None,
    prop_id: str | None = None,
) -> str:
    clean_spu_id = str(spu_id or "").strip()
    clean_sku_id = str(sku_id or "").strip()
    clean_prop_id = str(prop_id or "").strip()
    if not clean_spu_id:
        return ""

    desktop_url = f"https://www.dewu.com/product-detail.html?sourceName=h5&spuId={clean_spu_id}"
    if clean_sku_id:
        desktop_url += f"&skuId={clean_sku_id}"
    if clean_prop_id:
        desktop_url += f"&propertyValueId={clean_prop_id}"
    return desktop_url


def _poizon_info_has_core_fields(info: dict) -> bool:
    return bool(
        str(info.get("name") or "").strip()
        and info.get("price") is not None
        and str(info.get("image_url") or "").strip()
    )


def _merge_dewu_info(target: dict, extra: dict) -> None:
    if not isinstance(extra, dict):
        return

    scalar_keys = ("name", "brand", "cn_category", "image_url", "weight_kg", "selected_variant")
    list_keys = ("extra_images", "available_sizes", "variants")
    dict_keys = ("specs", "variant_price_map")

    for key in scalar_keys:
        if extra.get(key) and not target.get(key):
            target[key] = extra[key]

    for key in list_keys:
        if extra.get(key) and not target.get(key):
            target[key] = extra[key]

    for key in dict_keys:
        if extra.get(key) and not target.get(key):
            target[key] = extra[key]


def canonicalize_dewu_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith("dw4.co"):
        return url
    if not re.fullmatch(r"/t/A/\d+", parsed.path):
        return url

    spu_id, sku_id, _prop_id = _extract_dewu_ids(url)
    share_url = build_dewu_share_url(spu_id or "", sku_id=sku_id)
    return share_url or url


async def _parse_dewu(
    client: httpx.AsyncClient, final_url: str
) -> dict:
    """RapidAPI -> fast.dewu HTML."""
    result = {}
    spu_id, sku_id, _prop_id = _extract_dewu_ids(final_url)
    log.info(f"Dewu spuId={spu_id} skuId={sku_id}")
    if not spu_id:
        return result

    share_url = build_dewu_share_url(spu_id, sku_id=sku_id)

    api_info = await fetch_product_detail(client, spu_id, sku_id=sku_id)
    if api_info:
        result.update(api_info)

    need_html_fallback = (
        not _poizon_info_has_core_fields(result)
        or not result.get("variants")
        or not result.get("specs")
        or not result.get("extra_images")
    )
    if need_html_fallback and share_url:
        html_info = await parse_poizon_html_specs(share_url)
        if html_info:
            used_html_name = bool(html_info.get("name") and not result.get("name"))
            _merge_dewu_info(result, html_info)
            if used_html_name:
                result["name_needs_shortening"] = True

    return result


async def parse_poizon_html_specs(url: str) -> dict:
    """Poizon характеристики и галерея только из HTML fast.dewu."""
    final_url = await resolve_url(url)
    spu_id, sku_id, _prop_id = _extract_dewu_ids(final_url)

    if not spu_id:
        return {}

    share_url = build_dewu_share_url(spu_id, sku_id=sku_id)

    proxy_candidates = [PROXY or None]
    if proxy_candidates[0] is not None:
        proxy_candidates.append(None)

    for proxy in proxy_candidates:
        try:
            async with httpx.AsyncClient(
                timeout=13.0,
                follow_redirects=True,
                headers=HEADERS,
                proxy=proxy,
            ) as client:
                html = await _fetch(client, share_url)
            if not html:
                continue

            specs = _find_specs(html)
            extra_images = _find_extra_images(html)
            image_url = _find_image(html)
            name = _find_name(html)
            brand = _find_brand(html)
            cn_category = _find_cn_category(html)
            available_sizes = _find_available_sizes(html)
            variants = _find_variants_from_html(html)
            weight = _find_weight_from_specs(specs)
            if not weight:
                weight = _find_weight_from_dimensions(specs)

            result = {
                "specs": specs or {},
                "extra_images": extra_images or [],
            }
            if name:
                result["name"] = name
            if brand:
                result["brand"] = brand
            if cn_category:
                result["cn_category"] = cn_category
            if image_url:
                result["image_url"] = image_url
            if available_sizes:
                result["available_sizes"] = available_sizes
            if variants:
                result["variants"] = variants
            if weight:
                result["weight_kg"] = weight
            log.info(
                "parse_poizon_html_specs: url=%s specs=%s extra_images=%s",
                share_url,
                len(result.get("specs") or {}),
                len(result.get("extra_images") or []),
            )
            return result
        except Exception as e:
            log.warning(f"parse_poizon_html_specs failed via proxy={proxy}: {e}")

    return {}


_LOGIN_DOMAINS = ("login.taobao", "login.tmall", "login.1688", "passport.taobao", "accounts.taobao")


async def _follow_redirect(client: httpx.AsyncClient, url: str, cookie_str: str = "") -> str:
    """GET-редирект чтобы раскрыть короткую ссылку.
    Если HTTP-редиректа нет (JS-страница), ищем реальный URL в HTML.
    """
    try:
        referer = "https://www.1688.com/" if "1688.com" in url else "https://www.taobao.com/"
        headers = {"Referer": referer}
        if cookie_str:
            headers["Cookie"] = cookie_str
        resp = await client.get(url, timeout=10.0, headers=headers)
        final = str(resp.url)
        if any(d in final for d in _LOGIN_DOMAINS):
            log.info(f"redirect led to login: {final[:80]}, keeping original")
            return url
        # Если URL не изменился — страница делает JS-редирект, ищем реальный URL в HTML
        if final == url and resp.status_code == 200:
            html = resp.text[:300_000]
            if "1688.com" in url:
                # 1688 QR often embeds wireless1688://...offer?id=XXX.html and offerId=XXX
                m = re.search(r'offerId=([0-9]{8,15})', html)
                if m:
                    offer_id = m.group(1)
                    log.info(f"found 1688 offerId in HTML: {offer_id}")
                    return f"https://detail.1688.com/offer/{offer_id}.html"
                m = re.search(r'offer\?id=([0-9]{8,15})\.html', html)
                if m:
                    offer_id = m.group(1)
                    log.info(f"found 1688 offer?id in HTML: {offer_id}")
                    return f"https://detail.1688.com/offer/{offer_id}.html"
                m = re.search(r'/offer/(\d{8,15})\.html', html)
                if m:
                    offer_id = m.group(1)
                    log.info(f"found 1688 offer path in HTML: {offer_id}")
                    return f"https://detail.1688.com/offer/{offer_id}.html"
            # Taobao/Tmall: ищем item_id=XXX и строим чистый URL
            m = re.search(r'[?&]id=(\d{10,15})', html)
            if m:
                item_id = m.group(1)
                log.info(f"found Taobao item_id in HTML: {item_id}")
                return f"https://item.taobao.com/item.htm?id={item_id}"
        return final
    except Exception as e:
        log.info(f"redirect follow error: {e}")
        return url


async def _parse_taobao(client: httpx.AsyncClient, url: str) -> dict:
    result = {}
    item_id = extract_item_id(url)
    if not item_id and any(d in url for d in ("e.tb.cn", "tb.cn", "s.click.taobao")):
        real_url = await _follow_redirect(client, url)
        item_id = extract_item_id(real_url)

    if item_id:
        primary_item = await fetch_taobao_data_item_detail(client, item_id)
        result = build_info_from_taobao_data_item(primary_item)
        if _has_taobao_core_fields(result):
            return result

    api_item = await fetch_taobao_1688_item_by_url(client, url)
    result = _merge_preferred_fields(result, build_info_from_taobao_1688_item(api_item))
    item_id = result.get("item_id") or extract_item_id(result.get("detail_url", "")) or item_id or extract_item_id(url)
    if item_id:
        api_detail = await fetch_taobao_1688_item_detail(client, provider="taobao", item_id=item_id)
        result = _merge_preferred_fields(result, build_info_from_taobao_1688_item(api_detail))
        result["item_id"] = result.get("item_id") or item_id
        if result.get("detail_url"):
            url = result["detail_url"]
        if _has_taobao_core_fields(result):
            return result

        tertiary_item = await fetch_taobao_tmall_full_info(client, item_id)
        result = _merge_preferred_fields(result, build_info_from_taobao_tmall_full_info(tertiary_item))
        result["item_id"] = result.get("item_id") or item_id

    if _has_taobao_core_fields(result):
        return result

    return result


async def _parse_1688(client: httpx.AsyncClient, url: str) -> dict:
    result = {}
    real_url = url
    if "qr.1688.com" in url:
        real_url = await _follow_redirect(client, url, os.getenv("ALIBABA_COOKIE", ""))
        log.info(f"1688 redirect result: {real_url[:80]}")
        if "taobao.com" in real_url or "tmall.com" in real_url:
            return await _parse_taobao(client, real_url)

    item_id = extract_item_id(real_url) or extract_item_id(url)
    api_item_info = {}

    if not item_id:
        api_item = await fetch_taobao_1688_item_by_url(client, url)
        api_item_info = build_info_from_taobao_1688_item(api_item)
        item_id = (
            api_item_info.get("item_id")
            or extract_item_id(api_item_info.get("detail_url", ""))
            or extract_item_id(url)
        )

    if item_id:
        simple = await fetch_1688_datahub_simple(client, item_id)
        detail = await fetch_1688_datahub_detail(client, item_id)
        seller = simple.get("seller") if isinstance(simple, dict) else None
        store_id = str(seller.get("storeId") or "").strip() if isinstance(seller, dict) else ""
        package = await fetch_1688_datahub_package(client, item_id=item_id, store_id=store_id) if store_id else {}
        result = build_info_from_1688_datahub(detail=detail, simple=simple, package=package)
        for key, value in api_item_info.items():
            if value and not result.get(key):
                result[key] = value
        result["item_id"] = item_id
        if _has_1688_core_fields(result):
            return result

    if not api_item_info:
        api_item = await fetch_taobao_1688_item_by_url(client, real_url)
        api_item_info = build_info_from_taobao_1688_item(api_item)

    if api_item_info:
        for key, value in api_item_info.items():
            if value and not result.get(key):
                result[key] = value
        item_id = result.get("item_id") or api_item_info.get("item_id") or item_id
        if _has_1688_core_fields(result):
            return result

    if item_id:
        open_detail = await fetch_open_1688_product_detail(client, item_id)
        open_detail_info = build_info_from_open_1688_detail(open_detail)
        result = _merge_preferred_fields(result, open_detail_info)
        if open_detail_info.get("detail_url"):
            result["detail_url"] = open_detail_info["detail_url"]
        result["item_id"] = result.get("item_id") or item_id

    return result


# ── Основная функция ───────────────────────────────────────────────────────────

async def resolve_url(url: str) -> str:
    """Следовать редиректам и вернуть финальный URL (HEAD-запрос)."""
    for proxy in (PROXY or None, None):
        try:
            async with httpx.AsyncClient(
                timeout=8.0,
                follow_redirects=True,
                headers=HEADERS,
                proxy=proxy,
            ) as client:
                head = await client.head(url)
                return str(head.url)
        except Exception:
            continue
    return url


def needs_poizon_html_fallback(draft: ProductDraft) -> bool:
    return (
        draft.platform == PLATFORM_POIZON
        and (
            not str(draft.name or "").strip()
            or draft.price_cny is None
            or not str(draft.image_url or "").strip()
        )
    )


async def parse_url(url: str) -> ProductDraft:
    draft = ProductDraft(url=url)
    auto_detected = []
    final_url = await resolve_url(url)
    draft.platform = detect_platform(final_url)
    if draft.platform == PLATFORM_UNKNOWN:
        draft.platform = detect_platform(url)
    draft.url = canonicalize_dewu_url(final_url) if draft.platform == PLATFORM_POIZON else final_url
    log.info(f"parse_url: platform={draft.platform} url={final_url[:80]}")

    info = {}
    proxy_candidates = [PROXY or None]
    if proxy_candidates[0] is not None:
        proxy_candidates.append(None)

    for proxy in proxy_candidates:
        try:
            async with httpx.AsyncClient(
                timeout=13.0,
                follow_redirects=True,
                headers=HEADERS,
                proxy=proxy,
            ) as client:
                if draft.platform == PLATFORM_POIZON:
                    info = await _parse_dewu(client, final_url)
                elif draft.platform == PLATFORM_TAOBAO:
                    info = await _parse_taobao(client, final_url)
                elif draft.platform == PLATFORM_1688:
                    info = await _parse_1688(client, final_url)
                else:
                    info = {}
            if info:
                break
        except Exception as e:
            log.exception(f"parse error: {e}")

    # Заполняем черновик
    if info.get("name"):
        draft.name = info["name"]
        auto_detected.append("name")
    if info.get("price"):
        draft.price_cny = info["price"]
        auto_detected.append("price")
    draft.price_is_starting = bool(info.get("price_is_starting", False))
    if info.get("brand"):
        draft.brand = info["brand"]
    if info.get("selected_variant") and not draft.size:
        draft.size = info["selected_variant"]
        auto_detected.append("size")
    if info.get("image_url"):
        draft.image_url = info["image_url"]
        auto_detected.append("image")
    if info.get("extra_images"):
        draft.extra_images = info["extra_images"]

    if info.get("specs"):
        draft.specs = info["specs"]
    if info.get("available_sizes"):
        draft.available_sizes = info["available_sizes"]
        auto_detected.append("sizes")
    raw_variants = info.get("variants") or []
    if raw_variants:
        from services.translator import translate_variants_with_groq
        draft.variants = await translate_variants_with_groq(raw_variants)
    if info.get("variant_price_map"):
        draft.variant_price_map = info["variant_price_map"]
    if info.get("weight_kg"):
        draft.weight_kg = info["weight_kg"]
        draft.weight_estimated = False
        auto_detected.append("weight")

    cn_cat = str(info.get("cn_category") or "").strip()

    if needs_poizon_html_fallback(draft):
        try:
            html_info = await parse_poizon_html_specs(draft.url or final_url)
        except Exception as e:
            log.debug(f"poizon html fallback skipped: {e}")
            html_info = {}

        if html_info.get("name") and not draft.name:
            draft.name = html_info["name"]
            if "name" not in auto_detected:
                auto_detected.append("name")
        if html_info.get("brand") and not draft.brand:
            draft.brand = html_info["brand"]
        if html_info.get("cn_category") and not cn_cat:
            cn_cat = str(html_info["cn_category"]).strip()
        if html_info.get("image_url") and not draft.image_url:
            draft.image_url = html_info["image_url"]
            if "image" not in auto_detected:
                auto_detected.append("image")
        if html_info.get("extra_images") and not draft.extra_images:
            draft.extra_images = html_info["extra_images"]
        if html_info.get("specs") and not draft.specs:
            draft.specs = html_info["specs"]
        if html_info.get("weight_kg") and not draft.weight_kg:
            draft.weight_kg = html_info["weight_kg"]
            draft.weight_estimated = False
            if "weight" not in auto_detected:
                auto_detected.append("weight")

    # Переводим название и значения спецификаций на русский
    try:
        from services.translator import translate_if_cn, translate_specs_values
        if draft.name:
            _cn_blocks = re.findall(r'[\u4e00-\u9fff]+', draft.name)
            if _cn_blocks:
                # Смешанный текст (бренд + китайское описание) — переводим блоки по отдельности
                # иначе Google Translate возвращает только первое слово
                _name = draft.name
                for _blk in _cn_blocks:
                    try:
                        _tr = await translate_if_cn(_blk)
                        _name = _name.replace(_blk, f' {_tr} ', 1)
                    except Exception:
                        pass
                draft.name = re.sub(r'\s{2,}', ' ', _name).strip()
            else:
                draft.name = await translate_if_cn(draft.name)
        if draft.brand:
            _cn_blocks = re.findall(r'[\u4e00-\u9fff]+', draft.brand)
            if _cn_blocks:
                _brand = draft.brand
                for _blk in _cn_blocks:
                    try:
                        _tr = await translate_if_cn(_blk)
                        _brand = _brand.replace(_blk, f' {_tr} ', 1)
                    except Exception:
                        pass
                draft.brand = re.sub(r'\s{2,}', ' ', _brand).strip()
            else:
                draft.brand = await translate_if_cn(draft.brand)
        if draft.specs:
            draft.specs = await translate_specs_values(draft.specs)
        if draft.variant_price_map:
            translated_map = {}
            group_name_map: dict[str, str] = {}
            option_value_map: dict[tuple[str, str], str] = {}
            for raw_group, translated_group in zip(raw_variants, draft.variants):
                raw_group_name = str(raw_group.get("name") or "").strip()
                translated_group_name = str(translated_group.get("name") or raw_group_name).strip()
                if raw_group_name:
                    group_name_map[raw_group_name] = translated_group_name
                for raw_option, translated_option in zip(raw_group.get("options") or [], translated_group.get("options") or []):
                    option_value_map[(raw_group_name, str(raw_option).strip())] = str(translated_option).strip()
            for raw_key, raw_price in draft.variant_price_map.items():
                try:
                    pairs = json.loads(raw_key)
                except Exception:
                    continue
                translated_pairs = []
                for name, value in pairs:
                    name = str(name).strip()
                    value = str(value).strip()
                    translated_pairs.append([
                        group_name_map.get(name) or await translate_if_cn(name),
                        option_value_map.get((name, value)) or await translate_if_cn(value),
                    ])
                translated_map[json.dumps(sorted(translated_pairs), ensure_ascii=False)] = raw_price
            draft.variant_price_map = translated_map
    except Exception as e:
        log.debug(f"translation skipped: {e}")

    # Определяем категорию
    draft.category = infer_category(draft.name, cn_cat)
    if draft.category:
        auto_detected.append("category")

    if info.get("name_needs_shortening") and draft.name:
        try:
            from services.market_compare import extract_search_query

            shortened_name = await extract_search_query(draft.name, draft.category or cn_cat)
            if shortened_name:
                draft.name = shortened_name
        except Exception as e:
            log.debug(f"dewu fallback name shorten skipped: {e}")

    draft.auto_detected = auto_detected
    log.info(
        "parse_url result: price=%s starting=%s name=%r cat=%s img=%s",
        draft.price_cny,
        draft.price_is_starting,
        draft.name,
        draft.category,
        "yes" if draft.image_url else "no",
    )
    return draft
