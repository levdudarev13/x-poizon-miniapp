"""Сравнение цен с Wildberries (парсинг страницы через Playwright)."""
import logging
import urllib.parse
from dataclasses import dataclass

log = logging.getLogger(__name__)


async def extract_search_query(product_name: str, category: str = "") -> str:
    """Извлечь из длинного маркетингового названия короткий поисковый запрос через Groq.
    Один проход: бренд+модель+точный тип товара. Категория с платформы используется как подсказка."""
    from config import GROQ_API_KEY
    if not GROQ_API_KEY or not product_name:
        words = product_name.split()
        return " ".join(words[:4])
    try:
        from groq import Groq
        import asyncio
        import httpx
        from config import PROXY
        _http = httpx.Client(proxy=PROXY) if PROXY else None
        client = Groq(api_key=GROQ_API_KEY, http_client=_http)

        category_hint = f"\nКатегория на платформе: {category}" if category else ""

        prompt = (
            "Составь короткий поисковый запрос для российского маркетплейса (WB/Ozon).\n"
            "Правила (строго):\n"
            "1. Формат: бренд + модель + точный тип товара (1-2 слова).\n"
            "2. Тип товара определяй максимально точно — не обобщённо.\n"
            "   Используй категорию с платформы как подсказку, но уточняй по названию.\n"
            "   Если категория не указана — определи тип товара самостоятельно по названию и сразу дай ответ.\n"
            "3. НЕ включай: цвет, материал, размер, год, прилагательные, маркетинговые слова.\n"
            "4. Если бренд сам является типом товара (Zippo, Lego) — добавь только тип: 'Zippo зажигалка'.\n"
            "5. Если тип уже понятен из модели — не дублируй его: 'AirPods Pro 2', не 'AirPods Pro 2 наушники'.\n"
            "6. Верни ТОЛЬКО сам запрос — одну строку, без объяснений, без вводных слов, без точек.\n\n"
            "Примеры:\n"
            "  Название: 'Nike Air Force 1 белые кожаные мужские', Категория: Sneakers / Shoes → 'Nike Air Force 1 кроссовки'\n"
            "  Название: 'Nike Sb Zoom Janoski OG+ Black White 2024', Категория: Sneakers / Shoes → 'Nike Sb Zoom Janoski кеды'\n"
            "  Название: 'ZIPPO антикварное серебро керосиновая популярная', Категория: Lighters → 'Zippo зажигалка'\n"
            "  Название: 'Apple AirPods Pro 2nd generation активное шумоподавление', Категория: Headphones → 'AirPods Pro 2'\n"
            "  Название: 'Samsung Galaxy S24 Ultra 256GB черный', Категория: Smartphones → 'Samsung Galaxy S24 Ultra'\n"
            "  Название: 'Adidas Originals Superstar белые классические', Категория: Sneakers / Shoes → 'Adidas Superstar кеды'\n"
            "  Название: 'The North Face Nuptse 700 пуховик мужской', Категория: Clothing → 'The North Face Nuptse пуховик'\n\n"
            f"Название: {product_name}{category_hint}"
        )

        def _call():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=30,
                temperature=0.0,
            )

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=12.0,
        )

        result = response.choices[0].message.content.strip().strip('"').strip("'")
        log.info(f"Groq search query: '{product_name[:40]}' (cat='{category}') → '{result}'")
        return result
    except Exception as e:
        log.warning(f"Groq extract_search_query failed: {e}")
        words = product_name.split()
        return " ".join(words[:4])

_WB_JS = """
() => {
    const cards = Array.from(
        document.querySelectorAll('article.product-card')
    ).slice(0, 10);

    return cards.map(card => {
        const link = card.querySelector('a[href*="/catalog/"]');
        const href = link ? link.getAttribute('href') : '';
        const idMatch = href.match(/\\/catalog\\/(\\d+)\\//);

        const name = link ? (link.getAttribute('aria-label') || '').trim() : '';

        const ins = card.querySelector('ins');
        const priceRaw = ins ? ins.textContent.replace(/\\D/g, '') : '';

        const ratingEl = card.querySelector('[class*="address-rate-mini"]');
        const ratingRaw = ratingEl ? ratingEl.textContent.trim() : '';

        const countEl = card.querySelector('[class*="product-card__count"]');
        const countRaw = countEl ? countEl.textContent : '';

        const imgEl = card.querySelector('img');
        const imgSrc = imgEl ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '') : '';

        return {
            id:      idMatch ? idMatch[1] : '',
            name:    name,
            price:   parseInt(priceRaw)  || 0,
            rating:  parseFloat(ratingRaw.replace(',', '.')) || 0,
            reviews: parseInt(countRaw.replace(/\\D/g, '')) || 0,
            img:     imgSrc,
        };
    });
}
"""



@dataclass
class MarketItem:
    name: str
    price_rub: int
    rating: float
    reviews: int
    url: str
    image_url: str = ""


def _pick_top3(items: list) -> list:
    """Топ-3 из первых 10 результатов по количеству отзывов. Без доп. фильтров."""
    return sorted(items, key=lambda x: x.reviews, reverse=True)[:3]


# Ключевые слова для фильтрации явных аксессуаров на уровне кода (страховка после Groq)
_ACCESSORY_KEYWORDS = [
    "чехол", "топлив", "кремн", "кремень", "фитил", "расходник", "запчаст",
    "набор для", "аксессуар", "кабель", "зарядк", "адаптер",
    "для зажигалк", "для зажигалок", "2406ng", "flint",
]


def _is_clearly_accessory(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _ACCESSORY_KEYWORDS)


def _filter_by_word_overlap(query: str, items: list) -> list:
    """Оставляет только товары, в названии которых есть хотя бы 1 слово из запроса (>= 3 букв).
    Страховка от нерелевантных результатов, когда название товара нестандартное."""
    query_words = [w.lower() for w in query.split() if len(w) >= 3]
    if not query_words:
        return items
    threshold = min(2, len(query_words))
    result = [it for it in items if sum(w in it.name.lower() for w in query_words) >= threshold]
    if not result and len(query_words) >= 2:
        result = [it for it in items if sum(w in it.name.lower() for w in query_words) >= 1]
    if len(result) < len(items):
        log.info(
            "Word overlap filter: %d → %d items (query words: %s)",
            len(items), len(result), query_words,
        )
    return result


async def _groq_filter_relevant(query: str, items: list) -> list:
    """Отфильтровать через Groq только те товары, которые соответствуют запросу.
    Возвращает отфильтрованный список (топ-3 по отзывам из подходящих).
    При ошибке — возвращает исходный _pick_top3."""
    from config import GROQ_API_KEY
    if not GROQ_API_KEY or not items:
        return _pick_top3(items)

    try:
        from groq import Groq
        import asyncio
        import httpx
        from config import PROXY
        _http = httpx.Client(proxy=PROXY) if PROXY else None

        numbered = "\n".join(
            f"{i}. {item.name}" for i, item in enumerate(items)
        )
        log.info("Groq input items:\n%s", numbered)
        prompt = (
            f"Поисковый запрос: «{query}»\n\n"
            f"Твоя задача: выбрать ТОЛЬКО те товары, которые являются самим товаром «{query}».\n"
            f"Разные модели и варианты одного и того же товара — подходят.\n\n"
            f"СТРОГО НЕ ВЫБИРАЙ: чехлы, топливо, кремни, фитили, расходники, запчасти, "
            f"наборы аксессуаров, сопутствующие товары, любые товары «для» чего-либо.\n"
            f"Примеры НЕПРАВИЛЬНОГО выбора (если ищем зажигалку Zippo):\n"
            f"  ✗ «Кремни для зажигалок Zippo» — это расходник, НЕ зажигалка\n"
            f"  ✗ «Топливо Zippo 125 мл» — это расходник, НЕ зажигалка\n"
            f"  ✗ «Набор для зажигалок Zippo 2+1» — это набор аксессуаров, НЕ зажигалка\n"
            f"  ✗ «Чехол для зажигалки» — это чехол, НЕ зажигалка\n"
            f"Правило: если название содержит слово «для» — это НЕ сам товар.\n\n"
            f"Результаты поиска ({len(items)} шт.):\n{numbered}\n\n"
            f"Верни ТОЛЬКО номера подходящих товаров через запятую, например: 4,17,28. "
            f"Без объяснений. Если ни один не подходит, верни пустую строку."
        )

        client = Groq(api_key=GROQ_API_KEY, http_client=_http)

        def _call():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=60,
                temperature=0.0,
            )

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=15.0,
        )
        raw = response.choices[0].message.content.strip()
        log.info("Groq filter result for '%s': %s", query, raw)

        if not raw:
            return _pick_top3(items)

        indices = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(items):
                    indices.append(idx)

        if not indices:
            return _pick_top3(items)

        filtered = [items[i] for i in indices]

        # Страховочный фильтр: всегда убираем явные аксессуары (даже если Groq их пропустил)
        before = len(filtered)
        filtered = [it for it in filtered if not _is_clearly_accessory(it.name)]
        if len(filtered) < before:
            log.info("Code filter removed %d accessory items from Groq result", before - len(filtered))

        if not filtered:
            return []  # ничего не нашли — вызовет relaxed фильтр

        return sorted(filtered, key=lambda x: x.reviews, reverse=True)[:3]

    except Exception as e:
        log.warning("Groq filter failed: %s", e)
        return _pick_top3(items)


async def _groq_filter_relaxed(query: str, items: list, exclude_urls: set) -> list:
    """Смягчённый фильтр: ищем аналоги того же типа товара, игнорируя бренд.
    Используется когда строгий фильтр нашёл меньше 3 товаров.
    exclude_urls — URL уже найденных товаров (чтобы не дублировать)."""
    from config import GROQ_API_KEY

    # Оставляем только товары которых ещё нет в результатах
    candidates = [it for it in items if it.url not in exclude_urls]
    # И убираем очевидные аксессуары ещё до Groq
    candidates = [it for it in candidates if not _is_clearly_accessory(it.name)]

    if not candidates:
        return []

    if not GROQ_API_KEY:
        return sorted(candidates, key=lambda x: x.reviews, reverse=True)[:3]

    try:
        from groq import Groq
        import asyncio
        import httpx
        from config import PROXY
        _http = httpx.Client(proxy=PROXY) if PROXY else None

        numbered = "\n".join(
            f"{i}. {it.name}" for i, it in enumerate(candidates)
        )
        log.info("Groq relaxed filter candidates:\n%s", numbered)

        prompt = (
            f"Исходный запрос: «{query}».\n\n"
            f"Строгий поиск по бренду дал мало результатов. "
            f"Теперь найди среди товаров ниже аналоги — товары того же ТИПА (любого бренда), "
            f"которые покупатель мог бы рассмотреть как альтернативу.\n"
            f"НЕ выбирай: чехлы, топливо, расходники, кремни, фитили, запчасти, "
            f"наборы аксессуаров, товары «для» чего-либо.\n"
            f"Выбирай только сам товар — разные бренды и модели подходят.\n\n"
            f"Товары ({len(candidates)} шт.):\n{numbered}\n\n"
            f"Верни ТОЛЬКО номера подходящих товаров через запятую, например: 2,5. "
            f"Без объяснений. Если ни один не подходит, верни пустую строку."
        )

        client = Groq(api_key=GROQ_API_KEY, http_client=_http)

        def _call():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=40,
                temperature=0.0,
            )

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=15.0,
        )
        raw = response.choices[0].message.content.strip()
        log.info("Groq relaxed filter result: %s", raw)

        if not raw:
            return []

        indices = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(candidates):
                    indices.append(idx)

        if not indices:
            return []

        found = [candidates[i] for i in indices]
        return sorted(found, key=lambda x: x.reviews, reverse=True)

    except Exception as e:
        log.warning("Groq relaxed filter failed: %s", e)
        return sorted(candidates, key=lambda x: x.reviews, reverse=True)


def _wb_search_sync(query: str) -> list:
    """Синхронная версия — запускается в отдельном потоке с собственным event loop."""
    import asyncio
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    encoded = urllib.parse.quote(query)
    url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}&sort=popular"

    async def _inner():
        async with async_playwright() as pw:
            _args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
            try:
                browser = await pw.chromium.launch(headless=True, channel="chrome", args=_args)
            except Exception:
                browser = await pw.chromium.launch(headless=True, args=_args)

            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                viewport={"width": 1280, "height": 800},
                extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)
            await page.goto(url, wait_until="networkidle", timeout=45000)
            try:
                await page.wait_for_selector("article.product-card", timeout=30000)
            except Exception:
                # Selector не появился — WB не показал карточки (пустая выдача или anti-bot)
                await browser.close()
                return []
            raw = await page.evaluate(_WB_JS)
            await browser.close()
            return raw

    import sys
    loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


async def search_wildberries(query: str) -> tuple:
    """Парсит первые 10 товаров WB, возвращает (топ-3 по отзывам, все до 10 без фильтров)."""
    import asyncio
    import concurrent.futures
    import functools

    try:
        loop = asyncio.get_event_loop()
        fn = functools.partial(_wb_search_sync, query)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            raw = await asyncio.wait_for(
                loop.run_in_executor(executor, fn),
                timeout=60.0,
            )

        log.info(
            "WB raw %d items: %s",
            len(raw),
            [(p.get("name", "")[:20], p.get("reviews", 0)) for p in raw],
        )

        items = []
        for p in raw:
            if not p.get("id") or p.get("price", 0) <= 0:
                continue
            img = p.get("img", "")
            if img and img.startswith("//"):
                img = "https:" + img
            items.append(MarketItem(
                name=(p["name"] or "—")[:80],
                price_rub=p["price"],
                rating=round(float(p.get("rating", 0.0)), 1),
                reviews=int(p.get("reviews", 0)),
                url=f"https://www.wildberries.ru/catalog/{p['id']}/detail.aspx",
                image_url=img,
            ))

        raw_items = items[:10]  # первые 10 без фильтров
        filtered = _filter_by_word_overlap(query, items)
        return _pick_top3(filtered), raw_items

    except Exception as e:
        log.warning("WB search failed: %s", e)
        return [], []


def _ozon_search_playwright(query: str, max_pages: int = 3) -> list:
    """Playwright + реальный Chrome. Перехватывает BFF-ответы Ozon."""
    import asyncio
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth
    import urllib.parse

    encoded = urllib.parse.quote(query)
    from config import OZON_PROXY as _OZON_PROXY
    pw_proxy = None
    # Пробуем без прокси — реальный Chrome + xvfb может пройти antibot напрямую
    log.info("Ozon PW: no proxy (direct server IP)")

    async def _inner():
        async with async_playwright() as pw:
            import os as _os
            has_display = bool(_os.environ.get("DISPLAY"))
            use_headless = not has_display
            log.info("Ozon PW: DISPLAY=%s headless=%s", _os.environ.get("DISPLAY"), use_headless)

            try:
                browser = await pw.chromium.launch(
                    headless=use_headless,
                    channel="chrome",
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    proxy=pw_proxy,
                )
                log.info("Ozon PW: launched real Chrome (headless=%s)", use_headless)
            except Exception as e:
                log.warning("Ozon PW: Chrome not available (%s), using Chromium", e)
                browser = await pw.chromium.launch(
                    headless=use_headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                    proxy=pw_proxy,
                )

            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/145.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                viewport={"width": 1280, "height": 900},
                extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)
            all_bff, pending = [], []

            async def _on_response(response):
                url = response.url
                if "ozon.ru" in url and response.status != 200:
                    log.info("Ozon PW response: status=%d url=%s", response.status, url[:100])
                if "entrypoint-api.bx" in url or "composer-api" in url or "page/json" in url:
                    log.info("Ozon PW BFF candidate: status=%d url=%s", response.status, url[:120])
                if ("entrypoint-api.bx" in url and "page/json" in url
                        and "searchSuggestions" not in url and response.status == 200):
                    try:
                        data = await response.json()
                        if any(isinstance(v, str) and "mainState" in v
                               for v in data.get("widgetStates", {}).values()):
                            pending.append(data)
                    except Exception:
                        pass

            page.on("response", _on_response)

            async def _wait_for_real_page(label: str, max_wait: int = 25):
                for i in range(max_wait):
                    try:
                        title = await page.title()
                    except Exception:
                        break
                    if "antibot" not in title.lower() and "доступ" not in title.lower():
                        log.info("Ozon PW %s: page ready after %ds, title=%r", label, i, title)
                        return True
                    await asyncio.sleep(1)
                title = ""
                try:
                    title = await page.title()
                except Exception:
                    pass
                log.warning("Ozon PW %s: not ready after %ds, title=%r", label, max_wait, title)
                return False

            # Warmup
            try:
                await page.goto("https://www.ozon.ru/", wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                log.info("Ozon PW warmup title=%r", title)
                if "antibot" in title.lower() or "доступ" in title.lower():
                    await page.mouse.move(400, 300)
                    await asyncio.sleep(0.5)
                    await page.evaluate("window.scrollTo(0, 200)")
                    await _wait_for_real_page("warmup")
            except Exception as e:
                log.info("Ozon PW warmup error: %s", e)
            await asyncio.sleep(2)

            for page_num in range(1, max_pages + 1):
                url = f"https://www.ozon.ru/search/?text={encoded}&from_global=true"
                if page_num > 1:
                    url += f"&page={page_num}"
                pending.clear()
                log.info("Ozon PW: loading page %d", page_num)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                except Exception:
                    pass

                title = ""
                try:
                    title = await page.title()
                except Exception:
                    pass
                current_url = page.url
                log.info("Ozon PW: page %d title=%r url=%s", page_num, title, current_url[:100])
                if "antibot" in title.lower() or "доступ" in title.lower():
                    await page.mouse.move(400, 300)
                    await asyncio.sleep(0.5)
                    await page.evaluate("window.scrollTo(0, 100)")
                    await _wait_for_real_page(f"page{page_num}")

                # Ждём BFF активно — до 30 секунд
                for _w in range(30):
                    if pending:
                        break
                    await asyncio.sleep(1)
                log.info("Ozon PW: page %d waited %ds for BFF", page_num, _w + 1)

                if pending:
                    all_bff.append(pending[0])
                    log.info("Ozon PW: page %d BFF captured", page_num)
                else:
                    log.warning("Ozon PW: page %d BFF not captured after 30s", page_num)
                    break

            await browser.close()
            return all_bff

    import sys as _sys
    loop = asyncio.ProactorEventLoop() if _sys.platform == "win32" else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_inner())
    finally:
        loop.close()


def _ozon_search_sync(query: str, max_pages: int = 3) -> list:
    """Playwright + реальный Chrome (channel=chrome). Перехватывает BFF-ответы Ozon."""
    return _ozon_search_playwright(query, max_pages)


def _parse_ozon_bff(data: dict) -> list:
    """Парсит widgetStates из BFF-ответа Ozon (tileGridDesktop структура)."""
    import json as _json, re as _re

    items = []
    seen: set = set()
    widgets = data.get("widgetStates", {})
    # Лог ключей виджетов для диагностики
    widget_keys = list(widgets.keys())[:10]
    log.info("BFF widget keys (first 10): %s", widget_keys)
    # Лог виджетов у которых есть mainState
    for k, v in widgets.items():
        if isinstance(v, str) and "mainState" in v:
            log.info("Widget with mainState found: key=%s, len=%d", k, len(v))
            break

    for widget_data in widgets.values():
        if not isinstance(widget_data, str):
            continue
        try:
            w = _json.loads(widget_data)
        except Exception:
            continue

        items_list = w.get("items") or []
        if not isinstance(items_list, list) or not items_list:
            continue

        first = items_list[0] if items_list else {}
        # Проверяем что это плитки товаров (у них mainState)
        if not isinstance(first, dict) or "mainState" not in first:
            continue

        for item in items_list:
            if not isinstance(item, dict):
                continue

            item_id = str(item.get("sku") or item.get("id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)

            # URL товара
            link = item.get("action", {}).get("link", "")
            if link:
                url = "https://www.ozon.ru" + link.split("?")[0]
            else:
                url = f"https://www.ozon.ru/product/{item_id}/"

            # Парсим mainState — список типизированных объектов
            name = ""
            price = 0
            rating = 0.0
            reviews = 0
            img = ""

            raw_json = _json.dumps(item, ensure_ascii=False)

            # Картинка — первый jpg/webp из JSON
            img_m = _re.search(r'"(https://[^"]+\.(jpg|webp|png))"', raw_json)
            if img_m:
                img = img_m.group(1)

            for state in item.get("mainState", []):
                if not isinstance(state, dict):
                    continue
                stype = state.get("type", "")

                # Название
                if stype == "textAtom" and state.get("id") == "name":
                    name = state.get("textAtom", {}).get("text", "")

                # Цена — берём первый элемент (актуальная цена со скидкой)
                elif stype == "priceV2" and price == 0:
                    price_list = state.get("priceV2", {}).get("price", [])
                    for pl in price_list:
                        if pl.get("textStyle") == "PRICE":
                            m = _re.search(r"[\d\u2009\s]+", pl.get("text", ""))
                            if m:
                                price = int(m.group(0).replace("\u2009", "").replace(" ", ""))
                            break

                # Рейтинг и отзывы — labelList с иконками star + dialog
                elif stype == "labelList":
                    for lbl in state.get("labelList", {}).get("items", []):
                        icon = lbl.get("icon", {}).get("image", "")
                        if "star" in icon.lower():
                            rating_text = lbl.get("title", "0")
                            try:
                                rating = float(_re.search(r"[\d.]+", rating_text).group(0))
                            except Exception:
                                pass
                        elif "dialog" in icon.lower():
                            rev_text = lbl.get("title", "0")
                            m_rev = _re.search(r"\d+", rev_text)
                            if m_rev:
                                reviews = int(m_rev.group(0))

            if not name or price <= 0:
                continue

            items.append(MarketItem(
                name=name[:80],
                price_rub=price,
                rating=round(rating, 1),
                reviews=reviews,
                url=url,
                image_url=img,
            ))
            if len(items) >= 10:
                return items

    return items


async def search_ozon(query: str, max_pages: int = 3) -> tuple:
    """Ищет товары на Ozon через Playwright (перехват BFF-ответа).
    Возвращает (отфильтрованные, все до 10 без фильтров)."""
    import asyncio
    import concurrent.futures
    import functools

    log.info("Ozon search START: query='%s', max_pages=%d", query, max_pages)
    try:
        loop = asyncio.get_event_loop()
        fn = functools.partial(_ozon_search_sync, query, max_pages)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            bff_pages = await asyncio.wait_for(
                loop.run_in_executor(executor, fn),
                timeout=120.0,
            )

        if not bff_pages:
            log.warning("Ozon: BFF не перехвачен, повторная попытка...")
            fn2 = functools.partial(_ozon_search_sync, query, 2)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor2:
                bff_pages = await asyncio.wait_for(
                    loop.run_in_executor(executor2, fn2),
                    timeout=90.0,
                )
            if not bff_pages:
                log.warning("Ozon: BFF не перехвачен даже после ретрая")
                return None, None  # None = антибот

            log.info("Ozon: ретрай успешен, страниц: %d", len(bff_pages))

        # Собираем все товары со всех страниц, дедуплицируем по URL
        all_items: list = []
        seen_urls: set = set()
        for page_num, bff_data in enumerate(bff_pages, start=1):
            page_items = _parse_ozon_bff(bff_data)
            new_items = [it for it in page_items if it.url not in seen_urls]
            for it in new_items:
                seen_urls.add(it.url)
            log.info("Ozon page %d: %d items (%d new)", page_num, len(page_items), len(new_items))
            all_items.extend(new_items)

        log.info("Ozon total items collected: %d", len(all_items))
        if not all_items:
            log.warning("Ozon: _parse_ozon_bff вернул 0 товаров")
            return [], []

        raw_items = all_items[:10]  # первые 10 без фильтров

        result = await _groq_filter_relevant(query, all_items)
        log.info("Ozon after strict Groq filter: %d items", len(result))

        if len(result) < 3:
            log.info("Ozon: strict filter gave %d items, running relaxed filter", len(result))
            exclude = {it.url for it in result}
            relaxed = await _groq_filter_relaxed(query, all_items, exclude)
            needed = 3 - len(result)
            result = result + relaxed[:needed]
            log.info("Ozon after relaxed filter: %d items total", len(result))

        result = _filter_by_word_overlap(query, result)
        log.info("Ozon after word overlap filter: %d items", len(result))
        return result, raw_items

    except asyncio.TimeoutError:
        log.warning("Ozon search TIMEOUT (>120s)")
        return [], []
    except Exception as e:
        log.warning("Ozon search FAILED: %s", e, exc_info=True)
        return [], []


async def compare_on_markets(query: str) -> tuple:
    """Возвращает (wb_items, []). Используй search_wildberries/search_ozon напрямую."""
    wb_items, _ = await search_wildberries(query)
    return wb_items, []
