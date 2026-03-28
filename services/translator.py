"""Перевод китайского текста на русский через Google Translate (без API-ключа)."""
import asyncio
import logging
import re

log = logging.getLogger(__name__)

_CN_RE = re.compile(r"[\u4e00-\u9fff]")
TRANSLATE_TIMEOUT = 15.0
_cache: dict[str, str] = {}

# Встроенный словарь частых китайских слов — переводятся мгновенно без сети
_BUILTIN: dict[str, str] = {
    # Цвета
    "黑色": "Черный", "白色": "Белый", "红色": "Красный", "蓝色": "Синий",
    "绿色": "Зеленый", "黄色": "Желтый", "灰色": "Серый", "粉色": "Розовый",
    "紫色": "Фиолетовый", "橙色": "Оранжевый", "棕色": "Коричневый",
    "米色": "Бежевый", "深蓝": "Темно-синий", "深灰": "Темно-серый",
    "浅灰": "Светло-серый", "卡其": "Хаки", "军绿": "Оливковый",
    "黑": "Черный", "白": "Белый", "红": "Красный", "蓝": "Синий",
    # Материалы
    "皮革": "Кожа", "真皮": "Натуральная кожа", "牛皮": "Воловья кожа",
    "棉": "Хлопок", "纯棉": "100% хлопок", "涤纶": "Полиэстер",
    "聚酯纤维": "Полиэстер", "尼龙": "Нейлон", "帆布": "Парусина/Канвас",
    "麂皮": "Замша", "绒面": "Велюр", "网布": "Сетка", "橡胶": "Резина",
    # Пол/возраст
    "男": "Мужской", "女": "Женский", "男女": "Унисекс", "儿童": "Детский",
    "男款": "Мужской", "女款": "Женский", "男女同款": "Унисекс",
    # Общие
    "是": "Да", "否": "Нет", "中国": "Китай", "进口": "Импорт",
    # Ключи характеристик (названия полей)
    "面料": "Материал", "成分含量": "Состав", "材质": "Материал",
    "版型": "Крой", "款式": "Фасон", "风格": "Стиль",
    "适用季节": "Сезон", "季节": "Сезон",
    "衣长": "Длина", "裤长": "Длина брюк",
    "袖长": "Длина рукава", "袖型": "Тип рукава",
    "领型": "Тип воротника", "领子": "Воротник",
    "厚度": "Плотность", "厚薄": "Плотность",
    "图案": "Принт", "花型": "Узор",
    "颜色": "Цвет", "颜色分类": "Цвет",
    "主货号": "Артикул", "辅助货号": "Доп. артикул", "货号": "Артикул",
    "发售价格": "Цена выпуска", "发售日期": "Дата выпуска",
    "尺码": "Размер", "尺寸": "Размер",
    "适用人群": "Для кого", "性别": "Пол",
    "品牌": "Бренд", "品名": "Название",
    "鞋面材质": "Материал верха", "鞋底材质": "Материал подошвы",
    "闭合方式": "Застёжка", "鞋跟高度": "Высота каблука",
    "内里材质": "Подкладка", "鞋垫材质": "Стелька",
    "重量": "Вес", "净重": "Вес нетто",
    "产地": "Страна производства", "上市年份": "Год выпуска",
    "洗涤建议": "Уход", "洗涤方式": "Стирка",
}


def has_chinese(text: str) -> bool:
    return bool(_CN_RE.search(text))


def _translate_sync(text: str) -> str:
    from deep_translator import GoogleTranslator
    for attempt in range(2):
        try:
            result = GoogleTranslator(source="auto", target="ru").translate(text[:500])
            if result:
                return result
        except Exception as e:
            log.debug(f"translate attempt {attempt+1} error '{text[:30]}': {e}")
    return text


def _translate_batch_sync(texts: list) -> list:
    from deep_translator import GoogleTranslator
    for attempt in range(2):
        try:
            results = GoogleTranslator(source="auto", target="ru").translate_batch(texts)
            if results:
                return [r or t for r, t in zip(results, texts)]
        except Exception as e:
            log.debug(f"translate_batch attempt {attempt+1} error: {e}")
    return texts


async def _groq_translate_text(text: str) -> str:
    """Перевести текст через Groq (фолбэк)."""
    from config import GROQ_API_KEY
    if not GROQ_API_KEY:
        return text
    try:
        from groq import Groq
        import httpx
        from config import PROXY
        _http = httpx.Client(proxy=PROXY) if PROXY else None
        client = Groq(api_key=GROQ_API_KEY, http_client=_http)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": (
                    f"Переведи на русский язык. Верни ТОЛЬКО перевод, без пояснений:\n{text}"
                ),
            }],
            max_tokens=200,
            temperature=0.1,
        )
        translated = resp.choices[0].message.content.strip()
        if translated:
            _cache[text] = translated
            return translated
    except Exception as e:
        log.debug(f"groq fallback translate failed: {e}")
    return text


async def translate_to_english(text: str) -> str:
    """Translate Russian/Chinese text to English via Groq for API search queries."""
    if not text:
        return text
    # If text is already in English/Latin, return as-is
    if not re.search(r'[а-яА-ЯёЁ\u4e00-\u9fff]', text):
        return text

    from config import GROQ_API_KEY
    if not GROQ_API_KEY:
        return text

    try:
        from groq import Groq
        import httpx as _httpx
        from config import PROXY
        _http = _httpx.Client(proxy=PROXY) if PROXY else None
        client = Groq(api_key=GROQ_API_KEY, http_client=_http)

        def _call():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": (
                        "Translate to English. Return ONLY the translation, "
                        "no quotes, no explanation:\n" + text
                    ),
                }],
                max_tokens=100,
                temperature=0.1,
            )

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=10.0,
        )
        translated = response.choices[0].message.content.strip()
        if translated:
            return translated
    except Exception as e:
        log.debug(f"translate_to_english failed: {e}")
    return text


async def translate_market_text(text: str) -> str:
    """Перевести короткие рыночные label/value через Groq, даже если они не китайские."""
    if not text:
        return text
    if text in _cache:
        return _cache[text]

    normalized = str(text).strip()
    if not normalized:
        return text

    looks_short_label = len(normalized) <= 60 and bool(re.search(r"[A-Za-z\u4e00-\u9fff]", normalized))
    if not looks_short_label:
        return text

    translated = await _groq_translate_text(normalized)
    if translated:
        _cache[normalized] = translated
        return translated
    return text


async def translate_if_cn(text: str) -> str:
    """Перевести текст если содержит китайские символы, иначе вернуть как есть."""
    if text in _BUILTIN:
        return _BUILTIN[text]
    if not text or not has_chinese(text):
        return text
    if text in _cache:
        return _cache[text]
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _translate_sync, text),
            timeout=TRANSLATE_TIMEOUT,
        )
        # Если Google вернул пустоту или не смог — фолбэк на Groq
        if result and has_chinese(result):
            raise ValueError("google returned untranslated")
        _cache[text] = result
        return result
    except (asyncio.TimeoutError, ValueError, Exception) as e:
        log.debug(f"google translate failed '{text[:30]}': {e}, trying groq")
        return await _groq_translate_text(text)


async def translate_specs_values(specs: dict) -> dict:
    """Перевести значения спецификаций на русский."""
    if not specs:
        return specs

    keys_to_translate = []
    result = dict(specs)
    for k, v in specs.items():
        sv = str(v)
        if not has_chinese(sv):
            continue
        if sv in _BUILTIN:
            result[k] = _BUILTIN[sv]
        elif sv in _cache:
            result[k] = _cache[sv]
        else:
            keys_to_translate.append(k)

    if not keys_to_translate:
        return result

    values = [specs[k] for k in keys_to_translate]
    loop = asyncio.get_event_loop()
    google_ok = False
    try:
        translated = await asyncio.wait_for(
            loop.run_in_executor(None, _translate_batch_sync, values),
            timeout=TRANSLATE_TIMEOUT,
        )
        google_ok = True
    except asyncio.TimeoutError:
        log.debug("translate_batch timeout, falling back to groq")
        translated = list(values)

    # Применяем результаты Google; те что остались китайскими — в Groq
    still_cn = []
    still_cn_keys = []
    for k, orig, trans in zip(keys_to_translate, values, translated):
        if google_ok and trans and not has_chinese(trans):
            result[k] = trans
            _cache[orig] = trans
        else:
            still_cn_keys.append(k)
            still_cn.append(orig)

    # Groq-фолбэк для непереведённых значений
    if still_cn:
        log.debug(f"groq fallback for {len(still_cn)} spec values")
        for k, orig in zip(still_cn_keys, still_cn):
            translated_val = await _groq_translate_text(orig)
            result[k] = translated_val

    return result


async def translate_specs_with_groq(specs: dict) -> dict:
    """Переводит характеристики товара на русский через Groq — качественно и полностью."""
    if not specs:
        return specs

    from config import GROQ_API_KEY

    # Сначала применяем встроенный словарь
    pre_translated: dict[str, str] = {}
    need_groq_set: set[str] = set()
    for k, v in specs.items():
        for t in (str(k), str(v)):
            if not has_chinese(t):
                pre_translated[t] = t
            elif t in _BUILTIN:
                pre_translated[t] = _BUILTIN[t]
            elif t in _cache:
                pre_translated[t] = _cache[t]
            else:
                need_groq_set.add(t)

    need_groq = list(need_groq_set)

    if need_groq and GROQ_API_KEY:
        # Отправляем в Groq батчами по 30
        chunk_size = 30
        for i in range(0, len(need_groq), chunk_size):
            chunk = need_groq[i:i + chunk_size]
            numbered = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(chunk))
            prompt = (
                "Переведи следующие китайские тексты на русский язык.\n"
                "Это технические характеристики товара (смартфон, одежда, обувь и т.д.).\n"
                "Правила:\n"
                "- Используй технические термины (напр. '屏幕尺寸' → 'Размер экрана')\n"
                "- '以官方信息为准' → 'по данным производителя'\n"
                "- '万像素' → 'Мпикс'\n"
                "- Верни ТОЛЬКО переводы с номером, без пояснений\n"
                "- Формат: 1. перевод\n2. перевод\n...\n\n"
                f"Тексты:\n{numbered}"
            )
            try:
                from groq import Groq
                import httpx
                from config import PROXY
                _http = httpx.Client(proxy=PROXY) if PROXY else None
                client = Groq(api_key=GROQ_API_KEY, http_client=_http)

                def _call(p=prompt):
                    return client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": p}],
                        max_tokens=600,
                        temperature=0.1,
                    )

                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, _call),
                    timeout=20.0,
                )
                raw = response.choices[0].message.content.strip()
                for line in raw.split("\n"):
                    m = re.match(r'^(\d+)\.\s*(.+)', line.strip())
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < len(chunk):
                            translation = m.group(2).strip()
                            pre_translated[chunk[idx]] = translation
                            _cache[chunk[idx]] = translation
            except Exception as e:
                log.warning("Groq specs translate failed: %s", e)
                # Fallback: оставляем оригинал
                for t in chunk:
                    if t not in pre_translated:
                        pre_translated[t] = t
    elif need_groq:
        # Нет Groq — пробуем Google Translate батчом
        loop = asyncio.get_event_loop()
        try:
            translated = await asyncio.wait_for(
                loop.run_in_executor(None, _translate_batch_sync, need_groq),
                timeout=30.0,
            )
            for orig, trans in zip(need_groq, translated):
                pre_translated[orig] = trans
                _cache[orig] = trans
        except Exception:
            for t in need_groq:
                pre_translated[t] = t

    result = {}
    for k, v in specs.items():
        ru_key = pre_translated.get(str(k), str(k))
        ru_val = pre_translated.get(str(v), str(v))
        result[ru_key] = ru_val
    return result


async def translate_variants_with_groq(variants: list) -> list:
    """Переводит названия групп вариантов и их опции на русский через Groq.
    variants: [{"name": "套装", "options": ["国行标配...", ...]}, ...]"""
    if not variants:
        return variants

    from config import GROQ_API_KEY

    # Собираем все уникальные строки для перевода
    all_texts: list[str] = []
    for g in variants:
        all_texts.append(g["name"])
        all_texts.extend(g["options"])

    # Проверяем кэш и встроенный словарь
    translations: dict[str, str] = {}
    need_groq: list[str] = []
    for t in all_texts:
        if not has_chinese(t):
            translations[t] = t
        elif t in _BUILTIN:
            translations[t] = _BUILTIN[t]
        elif t in _cache:
            translations[t] = _cache[t]
        else:
            need_groq.append(t)

    # Дедупликация
    need_groq = list(dict.fromkeys(need_groq))

    if need_groq and GROQ_API_KEY:
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(need_groq))
        prompt = (
            "Переведи следующие китайские тексты на русский язык.\n"
            "Это названия вариантов товара (цвет, комплектация, объём и т.д.).\n"
            "Правила:\n"
            "- Переводи точно, сохраняй скобки и разделители (например 【原封|未激活】 → 【Запечатан|Не активирован】)\n"
            "- Верни ТОЛЬКО переводы с номером, без пояснений\n"
            "- Формат: 1. перевод\n2. перевод\n...\n\n"
            f"Тексты:\n{numbered}"
        )
        try:
            from groq import Groq
            import httpx
            from config import PROXY
            _http = httpx.Client(proxy=PROXY) if PROXY else None
            client = Groq(api_key=GROQ_API_KEY, http_client=_http)

            def _call():
                return client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=800,
                    temperature=0.1,
                )

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _call),
                timeout=20.0,
            )
            raw = response.choices[0].message.content.strip()
            for line in raw.split("\n"):
                m = re.match(r'^(\d+)\.\s*(.+)', line.strip())
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(need_groq):
                        translation = m.group(2).strip()
                        translations[need_groq[idx]] = translation
                        _cache[need_groq[idx]] = translation
        except Exception as e:
            log.warning("Groq variants translate failed: %s", e)

    # Заполняем непереведённые оригиналами
    for t in need_groq:
        if t not in translations:
            translations[t] = t

    # Реконструируем структуру
    result = []
    for g in variants:
        result.append({
            "name": translations.get(g["name"], g["name"]),
            "options": [translations.get(o, o) for o in g["options"]],
        })
    return result


async def translate_specs_full(specs: dict) -> dict:
    """Перевести и ключи, и значения спецификаций на русский (батчами по 20)."""
    if not specs:
        return specs

    # Собираем все тексты (ключи + значения) требующие перевода
    all_texts = []
    for k, v in specs.items():
        all_texts.append(str(k))
        all_texts.append(str(v))

    need_translate = []
    cache_result = {}
    for t in all_texts:
        if not has_chinese(t):
            cache_result[t] = t
        elif t in _BUILTIN:
            cache_result[t] = _BUILTIN[t]
        elif t in _cache:
            cache_result[t] = _cache[t]
        else:
            need_translate.append(t)

    if need_translate:
        loop = asyncio.get_event_loop()
        # Делим на батчи по 20 — Google Translate надёжнее с небольшими порциями
        chunk_size = 20
        chunks = [need_translate[i:i + chunk_size] for i in range(0, len(need_translate), chunk_size)]
        try:
            for chunk in chunks:
                translated = await asyncio.wait_for(
                    loop.run_in_executor(None, _translate_batch_sync, chunk),
                    timeout=30.0,
                )
                for orig, trans in zip(chunk, translated):
                    _cache[orig] = trans
                    cache_result[orig] = trans
        except asyncio.TimeoutError:
            log.debug("translate_specs_full timeout")
            for t in need_translate:
                if t not in cache_result:
                    cache_result[t] = t

    result = {}
    for k, v in specs.items():
        ru_key = cache_result.get(str(k), str(k))
        ru_val = cache_result.get(str(v), str(v))
        result[ru_key] = ru_val
    return result
