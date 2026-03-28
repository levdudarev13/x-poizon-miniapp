"""Форматирование сообщений."""
from models import CalculationResult, ExchangeRate
from config import (
    PLATFORM_DISPLAY, DELIVERY_DISPLAY, DELIVERY_DAYS,
    CITIES, EXCHANGE_RATE_STALE_SECONDS, CLIENT_MSG_TEMPLATES,
)


def fmt_product_card(draft, rate=None, total_rub: int = None, delivery_time: str = None, has_active_variants: bool = False) -> str:
    """Карточка товара после парсинга ссылки."""
    from config import PLATFORM_DISPLAY, CATEGORIES

    lines = ["✅ *Вот что нашёл:*", ""]

    platform = PLATFORM_DISPLAY.get(draft.platform, draft.platform)
    lines.append(f"🏪 {platform}")

    if draft.name:
        lines.append(f"📦 {draft.name}")
    if draft.brand and draft.brand not in (draft.name or ""):
        lines.append(f"🔖 Бренд: {draft.brand}")

    if draft.price_cny:
        if rate:
            price_rub = round(draft.price_cny * rate.cny_rub)
            lines.append(f"💰 Цена: *{draft.price_cny:.0f} ¥* (~{fmt_rub(price_rub)})")
        else:
            lines.append(f"💰 Цена: *{draft.price_cny:.0f} ¥*")
    else:
        lines.append("💰 Цена: введи вручную")

    if rate:
        lines.append(f"💱 Курс: {rate.cny_rub:.2f} ₽/¥")

    if draft.category and draft.category in CATEGORIES:
        cat_name = CATEGORIES[draft.category][0]
        lines.append(f"📂 Категория: {cat_name}")
    else:
        lines.append("📂 Категория: *не определена* — выберу при расчёте")

    if draft.weight_kg:
        if draft.weight_estimated:
            lines.append(f"⚖️ Вес: ~{draft.weight_kg:.2g} кг")
        else:
            lines.append(f"⚖️ Вес: {draft.weight_kg:.2g} кг")

    if draft.size:
        lines.append(f"🎯 Вариант: {draft.size}")

    if getattr(draft, "notes", ""):
        lines.append(f"💬 Заметка: _{draft.notes}_")

    # Итоговая цена или подсказка про варианты
    lines.append("")
    if has_active_variants:
        lines.append("ℹ️ У товара есть разновидности — уточните детали, чтобы получить итоговую цену ↓")
    elif total_rub:
        lines.append(f"*Итого: {fmt_rub(total_rub)}*")
        dt = delivery_time or "до 2 недель"
        lines.append(f"Сроки доставки: Владивосток {dt}")

    return "\n".join(lines)


def fmt_rub(amount: float) -> str:
    """12500.5 → '12 500 ₽'"""
    return f"{int(amount):,} ₽".replace(",", "\u202f")


def fmt_result(result: CalculationResult, mode: str = "client", delivery_time: str = None, next_shipment_date: str = None, in_order: bool = False) -> str:
    """Полное сообщение с расчётом."""
    p = result.product
    rate = result.exchange_rate

    name = p.name or "Товар без названия"
    platform = PLATFORM_DISPLAY.get(p.platform, p.platform)
    delivery_days = DELIVERY_DAYS.get(p.delivery_type, "—")
    city_label = CITIES.get(p.city, p.city)

    lines = []

    # ── 1. Платформа ────────────────────────────────────────────────────────
    lines.append(f"🏪 {platform}")
    lines.append("")

    # ── 2. Название товара ──────────────────────────────────────────────────
    lines.append(f"📦 *{name}*")
    if p.url:
        lines.append(f"[Ссылка на товар]({p.url})")
    lines.append("")

    # ── 3. Уточнения и комментарий ──────────────────────────────────────────
    clarifications = []
    if p.size:
        clarifications.append(f"  • {p.size}")
    if getattr(p, "notes", ""):
        clarifications.append(f"  💬 {p.notes}")
    if clarifications:
        for c in clarifications:
            lines.append(c)
        lines.append("")

    if mode == "buyer":
        # ── Режим байера ───────────────────────────────────────────────────
        lines.append("━━ МОЙ РАСЧЁТ ━━━━━━━━━━━━")
        lines.append(f"Стоимость клиенту:  *{fmt_rub(result.subtotal_rub)}*")
        lines.append(f"Моя маржа ({result.margin_percent:.0f}%):  +{fmt_rub(result.margin_rub)}")
        recommended = round(result.total_with_margin_rub / 50) * 50
        lines.append(f"Цена клиенту:  *{fmt_rub(recommended)}* (рекоменд.)")
        lines.append(f"Чистая прибыль:  *{fmt_rub(result.margin_rub)}*")
        lines.append("")
    else:
        # ── Режим клиента ──────────────────────────────────────────────────
        lines.append(f"💰 *Итого: {fmt_rub(result.subtotal_rub)}*")
        lines.append("")

    # ── Разбивка ───────────────────────────────────────────────────────────
    import re
    lines.append("📊 Состав цены:")
    for item in result.breakdown:
        label = re.sub(r"\s*\(\d+%\)", "", item.label)
        suffix = ""
        if label == "Товар" and p.price_cny:
            suffix = f" ({p.price_cny:.0f} ¥)"
        lines.append(f"  • {label}: {fmt_rub(item.amount_rub)}{suffix}")

    lines.append("")

    # ── Доставка ───────────────────────────────────────────────────────────
    if city_label and delivery_days != "—":
        lines.append(f"🚚 Доставка до {city_label} займёт {delivery_days}")
    elif city_label:
        lines.append(f"📍 Город получения: {city_label}")

    # ── Доставка и ближайшая отправка (только для клиента) ─────────────────
    if mode == "client":
        dt = delivery_time or "до 2 недель"
        nsd = next_shipment_date or "00.00.0000"
        lines.append(f"🚚 Время доставки до Владивостока — {dt}")
        lines.append(f"📅 Ближайшая отправка товаров — {nsd}")
        if not in_order:
            lines.append("_(успейте добавить товар в заявку)_")

    # ── Курс ───────────────────────────────────────────────────────────────
    lines.append("")
    stale = rate.age_seconds > EXCHANGE_RATE_STALE_SECONDS
    stale_warn = " ⚠️ устарел" if stale else ""
    lines.append(f"💱 Курс: {rate.cny_rub:.2f} ₽/¥ • {rate.age_human}{stale_warn}")

    if stale:
        lines.append("_Рекомендую обновить курс (/settings → Обновить курс)_")

    # ── Предупреждение (только для клиента) ────────────────────────────────
    if mode == "client":
        lines.append("")
        lines.append("*⚠️ Внимание: это предварительная цена.*")
        if in_order:
            lines.append("_Администратор свяжется с вами в ближайшее время для согласования всех необходимых деталей._")
        else:
            lines.append("_После добавления товара в заявку администратор свяжется с вами для согласования всех необходимых деталей._")

    return "\n".join(lines)


def fmt_cart(items: list[dict], results: list[CalculationResult]) -> str:
    """Сводка по корзине."""
    lines = ["🛒 *Корзина*", ""]

    total_client = 0.0
    total_buyer = 0.0
    total_weight = 0.0

    for i, (item, res) in enumerate(zip(items, results), 1):
        name = (item["name"] or "Без названия")[:30]
        lines.append(f"{i}. {name}")
        lines.append(f"   {fmt_rub(res.subtotal_rub)} (клиент) / {fmt_rub(res.total_with_margin_rub)} (с маржой)")
        if item["weight_estimated"]:
            lines.append(f"   ~{item['weight_kg']:.1f} кг (оценка)")
        else:
            lines.append(f"   {item['weight_kg']:.1f} кг")
        lines.append("")
        total_client += res.subtotal_rub
        total_buyer += res.total_with_margin_rub
        total_weight += item["weight_kg"]

    lines.append("─" * 28)
    lines.append(f"Позиций: {len(items)}")
    lines.append(f"Общий вес: ~{total_weight:.1f} кг")
    lines.append(f"Итого клиенту: *{fmt_rub(total_client)}*")
    lines.append(f"Итого с маржой: *{fmt_rub(total_buyer)}*")
    lines.append(f"Прибыль: *{fmt_rub(total_buyer - total_client)}*")

    return "\n".join(lines)


def fmt_history_list(items: list[dict], short_names: dict = None) -> str:
    if not items:
        return "📭 *История расчётов пуста*\n\nПришли ссылку на товар, чтобы сделать первый расчёт."
    lines = ["📋 *История ваших расчётов:*", ""]
    for i, item in enumerate(items, 1):
        name = (short_names or {}).get(item["id"]) or (item.get("name") or "Товар")[:35]
        url = item.get("product_url", "")
        if url:
            lines.append(f"{i}. [{name}]({url})")
        else:
            lines.append(f"{i}. {name}")
    lines.append("")
    lines.append("_Нажмите на цифру, чтобы вернуться к расчёту_")
    return "\n".join(lines)


def fmt_share_info(share_code: str, bot_username: str) -> str:
    link = f"https://t.me/{bot_username}?start=share_{share_code}"
    return (
        f"🔗 *Код расчёта:* `{share_code}`\n\n"
        f"Скопируй ссылку и отправь клиенту:\n"
        f"`{link}`\n\n"
        "_Клиент увидит расчёт без вашей маржи._"
    )


def fmt_client_message(result: CalculationResult, template_key: str = "standard") -> str:
    """Готовый текст для пересылки клиенту."""
    p = result.product
    rate = result.exchange_rate
    city_label = CITIES.get(p.city, p.city)
    delivery_days = DELIVERY_DAYS.get(p.delivery_type, "—")
    total_recommended = round(result.subtotal_rub / 50) * 50

    tpl = CLIENT_MSG_TEMPLATES.get(template_key, CLIENT_MSG_TEMPLATES["standard"])
    return tpl.format(
        product_name=p.name or "Товар",
        total_rub=fmt_rub(total_recommended),
        delivery_days=delivery_days,
        city=city_label,
        cny_rate=f"{rate.cny_rub:.2f}",
        tracking="{tracking}",  # заменить отдельно при трекинге
    )


def _plural_reviews(n: int) -> str:
    n_str = f"{n:,}".replace(",", "\u202f")
    last100 = n % 100
    last10 = n % 10
    if 11 <= last100 <= 19:
        return f"{n_str} отзывов"
    if last10 == 1:
        return f"{n_str} отзыв"
    if 2 <= last10 <= 4:
        return f"{n_str} отзыва"
    return f"{n_str} отзывов"


def fmt_comparison_result(
    query: str,
    items: list,
    _ozon_items: list,
    our_price_rub: float,
    market: str = "wb",
) -> str:
    """Сравнение цен: WB или Ozon vs наша цена."""
    if market == "ozon":
        market_name = "Ozon"
        link_label = "Открыть на Ozon"
        icon = "🟠"
    else:
        market_name = "Wildberries"
        link_label = "Открыть на WB"
        icon = "🛒"

    lines = [f"🔍 *Сравниваем «{query}»*", ""]

    if not items:
        lines.append(f"😔 _Не нашёл подходящих товаров на {market_name}_")
        return "\n".join(lines)

    nums = ["1️⃣", "2️⃣", "3️⃣"]
    lines.append(f"{icon} *{market_name} — топ по отзывам*")
    lines.append("")
    for i, item in enumerate(items):
        n = nums[i] if i < len(nums) else f"{i+1}."
        stars = f"★ {item.rating:.1f}" if item.rating else ""
        rev = _plural_reviews(item.reviews)
        meta = " · ".join(filter(None, [stars, rev]))
        price_str = f"{item.price_rub:,}".replace(",", "\u202f")
        lines.append(f"{n} {item.name}")
        lines.append(f"   💰 {price_str} ₽  {meta}")
        lines.append(f"   🔗 [{link_label}]({item.url})")
        lines.append("")

    lines.append("─" * 28)

    avg_price = sum(i.price_rub for i in items) / len(items)
    avg_str = f"{int(avg_price):,}".replace(",", "\u202f")
    our_str = f"{int(our_price_rub):,}".replace(",", "\u202f")
    lines.append(f"📊 Средняя цена на {market_name}: *{avg_str} ₽*")
    lines.append(f"🛍 Ваша цена у нас: *{our_str} ₽*")
    lines.append("")
    if avg_price <= our_price_rub:
        lines.append("⚠️ _паленое говно (на свой страх и риск)_")
    else:
        lines.append("💎 _паленое говно стоит дороже чем качественный оригинал ахах (выбор очевиден)_")

    return "\n".join(lines)


def fmt_rate_info(rate: ExchangeRate) -> str:
    stale = rate.age_seconds > EXCHANGE_RATE_STALE_SECONDS
    lines = [
        "💱 *Текущий курс (ЦБ РФ)*",
        "",
        f"  1 ¥ (CNY) = {rate.cny_rub:.4f} ₽",
        f"  1 $ (USD) = {rate.usd_rub:.2f} ₽",
        f"  1 € (EUR) = {rate.eur_rub:.2f} ₽",
        "",
        f"Обновлён: {rate.age_human}",
    ]
    if stale:
        lines.append("⚠️ *Курс устарел* — рекомендую обновить")
    return "\n".join(lines)
