"""Расчёт стоимости под ключ."""
import math
from models import ProductDraft, CalculationResult, BreakdownLine, ExchangeRate, UserSettings
from config import (
    PLATFORM_COMMISSIONS, CHINA_DOMESTIC_SHIPPING_CNY,
    DELIVERY_RATE_RUB_PER_KG, DELIVERY_MIN_WEIGHT_KG,
    WAREHOUSE_FEE_RUB,
    INSURANCE_THRESHOLD_RUB, INSURANCE_RATE,
    CITY_SURCHARGE_RUB,
    CATEGORIES, PRICE_RANGES_CNY,
)


def get_typical_weight(category: str) -> float:
    return CATEGORIES.get(category, ("", 0.5))[1]


def _map_groq_category(text: str) -> str:
    """Смапить свободный ответ Groq на наш внутренний ключ категории."""
    t = text.lower()
    if any(w in t for w in ("обувь", "кроссовк", "sneaker", "shoe", "ботинк", "сланц", "сандал", "тапочк")):
        return "sneakers"
    if any(w in t for w in ("одежд", "футболк", "худи", "свитшот", "куртк", "пальто", "рубашк", "брюк", "шорт", "платье", "clothing", "shirt", "hoodie", "jacket", "pants", "dress", "tee", "coat")):
        return "clothing"
    if any(w in t for w in ("сумк", "рюкзак", "кошелёк", "кошелек", "bag", "backpack", "wallet", "purse")):
        return "bag"
    # Электроника проверяется ДО аксессуаров — смартфоны не должны попасть в "аксессуары"
    if any(w in t for w in ("электроник", "телефон", "смартфон", "iphone", "сотов", "наушник", "планшет", "ноутбук", "часы", "зарядк", "electronics", "phone", "smartphone", "headphone", "tablet", "laptop", "watch", "charger")):
        return "electronics"
    if any(w in t for w in ("аксессуар", "шапк", "носк", "очки", "ремень", "перчатк", "шарф", "украшен", "accessories", "hat", "cap", "sock", "belt", "scarf")):
        return "accessories"
    return "other"


async def groq_detect(name: str) -> dict:
    """Определить категорию и вес товара через Groq одним запросом.
    Возвращает {"category": key_or_empty, "weight_kg": float_or_0}.
    Fallback — пустые значения (caller решает что делать).
    """
    import asyncio
    import re
    import logging
    log = logging.getLogger(__name__)

    try:
        from config import GROQ_API_KEY
        if not GROQ_API_KEY:
            return {"category": "", "weight_kg": 0.0}
        from groq import Groq
        import httpx
        from config import PROXY
        _http = httpx.Client(proxy=PROXY) if PROXY else None
        client = Groq(api_key=GROQ_API_KEY, http_client=_http)

        def _call():
            return client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Товар: {name}\n\n"
                        "Ответь на два вопроса:\n"
                        "1. К какой категории относится этот товар?\n"
                        "2. Сколько примерно весит этот товар в кг (с упаковкой)?\n\n"
                        "Формат ответа:\n"
                        "CATEGORY: <категория>\n"
                        "WEIGHT: <число>"
                    ),
                }],
                max_tokens=40,
                temperature=0.1,
            )

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=10.0,
        )
        text = response.choices[0].message.content.strip()
        log.info("groq_detect '%s': %s", name[:40], text.replace('\n', ' '))

        result: dict = {"category": "", "weight_kg": 0.0}

        cat_m = re.search(r'CATEGORY:\s*(.+)', text)
        if cat_m:
            result["category"] = _map_groq_category(cat_m.group(1).strip().lower())

        wt_m = re.search(r'WEIGHT:\s*(\d+[.,]\d+|\d+)', text)
        if wt_m:
            w = float(wt_m.group(1).replace(',', '.'))
            if 0.05 <= w <= 50:
                result["weight_kg"] = w

        return result
    except Exception as e:
        log.warning("groq_detect failed: %s", e)
        return {"category": "", "weight_kg": 0.0}


async def get_effective_rate() -> float:
    """Вернуть курс ¥→₽: ручной (если не истёк 24ч) или авто с ЦБ."""
    import time as _time
    import database as _db
    settings = await _db.get_admin_settings()
    override = settings.get("rate_override", "")
    until = float(settings.get("rate_override_until", "0") or "0")
    if override and _time.time() < until:
        try:
            return float(override)
        except ValueError:
            pass
    from services import exchange_rate as _er
    rate = await _er.get_rate()
    return rate.cny_rub if rate else 11.5


def calculate_simple(price_cny: float, weight_kg: float, admin: dict) -> int:
    """Простой расчёт по формуле (синхронный, принимает уже полученный словарь admin).
    Возвращает итог в рублях (int).
    Вес округляется вверх до целого кг, минимум 1 кг.
    Комиссия не меньше min_commission_rub.
    """
    commission_pct    = float(admin.get("commission_pct",    10.0))
    min_commission    = float(admin.get("min_commission_rub", 300.0))
    logistics_rub     = float(admin.get("logistics_rub",     500.0))
    insurance_rub     = float(admin.get("insurance_rub",     200.0))
    price_per_kg      = float(admin.get("price_per_kg",      250.0))
    rate              = float(admin.get("_effective_rate",   11.5))

    goods_rub        = price_cny * rate
    commission       = max(goods_rub * commission_pct / 100, min_commission)
    weight_rounded   = math.ceil(max(weight_kg or 1.0, 1.0))  # мин. 1 кг, округл. вверх
    weight_fee       = weight_rounded * price_per_kg
    total = goods_rub + commission + logistics_rub + insurance_rub + weight_fee
    return int(round(total))


def validate_price(price_cny: float, category: str) -> tuple[bool, str]:
    """True = OK; иначе предупреждение."""
    lo, hi = PRICE_RANGES_CNY.get(category, (10, 100000))
    if price_cny < lo:
        return False, f"Цена {price_cny:.0f} ¥ кажется слишком низкой для категории «{CATEGORIES.get(category, ('?',))[0]}» (обычно от {lo} ¥)"
    if price_cny > hi:
        return False, f"Цена {price_cny:.0f} ¥ кажется очень высокой (обычно до {hi} ¥). Перепроверьте."
    return True, ""


def calculate(
    product: ProductDraft,
    rate: ExchangeRate,
    settings: UserSettings,
    min_commission_rub: float = 300.0,
) -> CalculationResult:
    """Посчитать стоимость под ключ и вернуть полный CalculationResult.
    Вес округляется вверх до целого кг, минимум 1 кг.
    Комиссия не меньше min_commission_rub.
    """
    cny = rate.cny_rub
    breakdown: list[BreakdownLine] = []

    # 1. Стоимость товара
    goods_rub = product.price_cny * cny
    breakdown.append(BreakdownLine(
        label="Товар",
        amount_rub=goods_rub,
        note=f"{product.price_cny:.0f} ¥ × {cny:.2f}",
    ))

    # 2. Комиссия площадки / байера (не меньше минимальной)
    comm_rate = PLATFORM_COMMISSIONS.get(product.platform, 0.05)
    comm_rub = max(goods_rub * comm_rate, min_commission_rub)
    breakdown.append(BreakdownLine(
        label=f"Комиссия ({int(comm_rate * 100)}%)",
        amount_rub=comm_rub,
        note=product.platform,
    ))

    # 3. Доставка внутри Китая
    china_ship_cny = CHINA_DOMESTIC_SHIPPING_CNY.get(product.platform, 55.0)
    if china_ship_cny > 0:
        china_ship_rub = china_ship_cny * cny
        breakdown.append(BreakdownLine(
            label="Доставка внутри Китая",
            amount_rub=china_ship_rub,
            note=f"{china_ship_cny:.0f} ¥",
        ))
    else:
        china_ship_rub = 0.0

    # 4. Международная доставка (вес округляется вверх, минимум 1 кг)
    weight = max(math.ceil(max(product.weight_kg, DELIVERY_MIN_WEIGHT_KG)), 1)
    ship_rate = DELIVERY_RATE_RUB_PER_KG.get(product.delivery_type, 1300.0)
    intl_ship_rub = weight * ship_rate
    weight_note = f"~{weight} кг (оценка)" if product.weight_estimated else f"{weight} кг"
    breakdown.append(BreakdownLine(
        label="Доставка Китай → РФ",
        amount_rub=intl_ship_rub,
        note=weight_note,
    ))

    # 5. Складская обработка
    breakdown.append(BreakdownLine(
        label="Складская обработка",
        amount_rub=WAREHOUSE_FEE_RUB,
    ))

    # 6. Надбавка по городу
    city_surcharge = CITY_SURCHARGE_RUB.get(product.city, 500.0)
    if city_surcharge > 0:
        breakdown.append(BreakdownLine(
            label="Доставка по РФ",
            amount_rub=city_surcharge,
            note="от московского хаба",
        ))

    # 7. Страховка (если товар дорогой)
    if goods_rub >= INSURANCE_THRESHOLD_RUB:
        ins_rub = goods_rub * INSURANCE_RATE
        breakdown.append(BreakdownLine(
            label=f"Страховка ({int(INSURANCE_RATE * 100)}%)",
            amount_rub=ins_rub,
            note="оценка",
        ))
    else:
        ins_rub = 0.0

    subtotal = sum(b.amount_rub for b in breakdown)

    # 8. Маржа байера
    margin_rub = settings.calc_margin(subtotal)
    margin_percent = settings.get_margin_percent(subtotal)

    return CalculationResult(
        product=product,
        breakdown=breakdown,
        subtotal_rub=subtotal,
        margin_rub=margin_rub,
        total_with_margin_rub=subtotal + margin_rub,
        margin_percent=margin_percent,
        exchange_rate=rate,
    )


def calculate_cart(
    items: list[ProductDraft],
    rates: list,  # CalculationResult per item
) -> dict:
    """Суммарный расчёт по корзине + скидка при совмещении доставки."""
    total_client = sum(r.subtotal_rub for r in rates)
    total_buyer = sum(r.total_with_margin_rub for r in rates)
    total_weight = sum(r.product.weight_kg for r in rates)

    # Если объединить в одну посылку — выгоднее одна доставка
    # (но пока просто суммируем — отдельная посылка = отдельная доставка)
    return {
        "item_count": len(rates),
        "total_weight_kg": total_weight,
        "total_client_rub": total_client,
        "total_buyer_rub": total_buyer,
        "total_margin_rub": total_buyer - total_client,
    }
