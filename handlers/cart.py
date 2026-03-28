"""Корзина — полный UX: просмотр, навигация, заявка."""
import json
import logging
import math
import time as _time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

import database as db
from auth import is_admin
from models import CalculationResult, BreakdownLine
from services.market_compare import extract_search_query
from services.calculator import get_effective_rate
from services import exchange_rate as er
from utils.formatters import fmt_result


def _rebuild_breakdown(result: CalculationResult, admin: dict, eff_rate: float) -> list:
    """Перестроить разбивку по текущим настройкам админа.
    Используется при показе карточки из корзины, чтобы данные были актуальны.
    """
    p = result.product
    goods_rub      = p.price_cny * eff_rate
    comm_pct       = float(admin.get("commission_pct", 10.0))
    min_commission = float(admin.get("min_commission_rub", 300.0))
    commission     = max(goods_rub * comm_pct / 100, min_commission)
    logistics      = float(admin.get("logistics_rub", 500.0))
    insurance      = float(admin.get("insurance_rub", 200.0))
    price_per_kg   = float(admin.get("price_per_kg", 250.0))
    weight_rounded = math.ceil(max(p.weight_kg or 1.0, 1.0))
    weight_fee     = weight_rounded * price_per_kg
    return [
        BreakdownLine("Товар", goods_rub, f"{p.price_cny:.0f} ¥ × {eff_rate:.2f}"),
        BreakdownLine(f"Комиссия ({comm_pct:.0f}%)", commission, ""),
        BreakdownLine("Логистика и страховка", logistics + insurance + weight_fee, ""),
    ]

log = logging.getLogger(__name__)

# Стикер загрузки корзины (из чата пользователя)
_STICKER_CART = "CAACAgIAAxkBAAFEF2FprB-04zbubwK96NZLKQABqQePHlQAAg0AA8A2TxOk-eH01HiNUzoE"

# ─── Бан-система ──────────────────────────────────────────────────────────────

# level → (секунд до окончания бана, текст для сообщения)
_BAN_LEVELS = {
    1: (86400,          "24 часа"),
    2: (7  * 86400,     "1 неделю"),
    3: (30 * 86400,     "1 месяц"),
    4: (90 * 86400,     "3 месяца"),
    5: (-1,             "навсегда"),
}
_BAN_SPAM_THRESHOLD = 5  # кол-во удалений из заявки за день до бана


async def _check_ban(user_id: int, bot, chat_id: int) -> bool:
    if is_admin(user_id):
        return False
    """Проверить, забанен ли пользователь.
    Если да и прошёл час с последнего уведомления — отправить сообщение.
    Возвращает True, если пользователь забанен (действие нужно заблокировать).
    """
    ban = await db.get_ban_info(user_id)
    level = int(ban.get("ban_level", 0))
    if level == 0:
        return False
    until = float(ban.get("ban_until", 0))
    if until != -1 and _time.time() > until:
        return False  # бан истёк
    # Throttle уведомлений: не чаще раза в час
    last_notified = float(ban.get("ban_last_notified", 0))
    if _time.time() - last_notified >= 3600:
        await db.update_ban_notified(user_id)
        _, duration_label = _BAN_LEVELS.get(level, (-1, "некоторое время"))
        await bot.send_message(
            chat_id,
            f"🚫 *Доступ ограничен*\n\n"
            f"Вы удалили товар из заявки более {_BAN_SPAM_THRESHOLD} раз за сутки — "
            f"мы расцениваем это как спам.\n\n"
            f"Возможность взаимодействия с ботом вернётся к вам через *{duration_label}*. "
            f"При повторном нарушении время бана увеличивается.",
            parse_mode=ParseMode.MARKDOWN,
        )
    return True


async def _apply_ban_if_needed(user_id: int, bot, chat_id: int, removes_count: int):
    if is_admin(user_id):
        return
    """Если счётчик достиг порога — наложить следующий уровень бана."""
    if removes_count < _BAN_SPAM_THRESHOLD:
        return
    ban = await db.get_ban_info(user_id)
    current_level = int(ban.get("ban_level", 0))
    next_level = min(current_level + 1, 5)
    duration_secs, duration_label = _BAN_LEVELS[next_level]
    until = -1.0 if duration_secs == -1 else _time.time() + duration_secs
    await db.set_ban(user_id, next_level, until)
    await db.update_ban_notified(user_id)
    await bot.send_message(
        chat_id,
        f"🚫 Вы удалили товар из заявки более {_BAN_SPAM_THRESHOLD} раз за сутки — "
        f"мы расцениваем это как спам.\n\n"
        f"Возможность взаимодействия с ботом вернётся к вам через *{duration_label}*. "
        f"При повторном нарушении время бана увеличивается.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _plural_items(n: int) -> str:
    last = n % 10
    last100 = n % 100
    if 11 <= last100 <= 19:
        return f"{n} товаров"
    if last == 1:
        return f"{n} товар"
    if 2 <= last <= 4:
        return f"{n} товара"
    return f"{n} товаров"


async def _notify_admin_order(ctx: ContextTypes.DEFAULT_TYPE, user_id: int,
                              calc_id: int, username: str, added: bool):
    """Отправить администратору уведомление о добавлении/удалении товара из заявки."""
    from config import ADMIN_USER_ID
    if not ADMIN_USER_ID:
        return
    try:
        # Берём короткое имя из кеша, иначе из БД
        short_name = ctx.user_data.get("cart_short_names", {}).get(calc_id)
        if not short_name:
            row = await db.get_calculation_by_id(calc_id, user_id)
            short_name = (row.get("name") or "Товар")[:40] if row else "Товар"
        uname = f"@{username}" if username else f"id:{user_id}"
        if added:
            text = (
                f"📋 *Новый товар в заявке*\n"
                f"{uname} добавил: *{short_name}*\n"
                f"_Свяжитесь с покупателем для уточнения деталей_"
            )
        else:
            text = f"🗑 *Товар убран из заявки*\n{uname} убрал: *{short_name}*"
        await ctx.bot.send_message(ADMIN_USER_ID, text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.warning(f"admin order notify failed: {e}")


async def _get_short_names(items: list[dict], ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    """Короткие Groq-названия для кнопок. Кешируются в user_data."""
    cache = ctx.user_data.setdefault("cart_short_names", {})
    new_ids = []
    new_coros = []
    for item in items:
        cid = item["id"]
        if cid not in cache:
            name = item.get("name") or "Товар"
            new_ids.append(cid)
            new_coros.append(extract_search_query(name))
    if new_coros:
        results = await asyncio.gather(*new_coros, return_exceptions=True)
        items_map = {item["id"]: item for item in items}
        for cid, res in zip(new_ids, results):
            if isinstance(res, Exception) or not res:
                cache[cid] = (items_map[cid].get("name") or "Товар")[:30]
            else:
                cache[cid] = str(res)[:35]
    return cache


# ─── Тексты ───────────────────────────────────────────────────────────────────

def _cart_welcome_text(items: list[dict], short_names: dict, order_count: int) -> str:
    total = len(items)
    lines = [
        "🛒 *Твоя корзина*",
        "",
        "Здесь хранятся товары, которые ты сохранил для расчёта.\n"
        "Когда определишься — добавляй нужное в 📋 *Заявку* и отправляй на оформление.",
        "",
        f"*В корзине {_plural_items(total)}:*",
    ]
    for item in items:
        mark = "📋 " if item.get("in_order") else "• "
        name = short_names.get(item["id"], (item.get("name") or "Товар")[:30])
        if item.get("arrived"):
            status = " 📦"
        elif item.get("shipped"):
            status = " 🚚"
        else:
            status = ""
        lines.append(f"{mark}{name}{status}")
    if order_count:
        lines.append("")
        lines.append(f"_📋 В заявке: {order_count} из {total}_")
    return "\n".join(lines)


def _order_welcome_text(order_items: list[dict], short_names: dict) -> str:
    if not order_items:
        return (
            "📋 *Заявка пуста*\n\n"
            "Открой корзину, выбери товар и нажми «📋 В заявку» — он появится здесь."
        )
    lines = [
        "📋 *Заявка на заказ*",
        "",
        "Ниже список товаров, добавленных в заявку. Они уже переданы администратору.",
        "",
        f"*{_plural_items(len(order_items))}:*",
    ]
    for item in order_items:
        name = short_names.get(item["id"], (item.get("name") or "Товар")[:30])
        paid_mark = " ✅ Оплачен" if item.get("paid") else ""
        if item.get("arrived"):
            delivery_mark = " 📦 Доставлен"
        elif item.get("shipped"):
            delivery_mark = " 🚚 Отправлен"
        else:
            delivery_mark = ""
        lines.append(f"• {name}{paid_mark}{delivery_mark}")
    return "\n".join(lines)


# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def _kb_cart_main(item_count: int, order_count: int) -> InlineKeyboardMarkup:
    order_label = f"📋 Заявка ({order_count})" if order_count else "📋 Заявка"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Посмотреть товары", callback_data="cart:products")],
        [
            InlineKeyboardButton(order_label, callback_data="cart:order_view"),
            InlineKeyboardButton("🗑 Очистить", callback_data="cart:clear_menu"),
        ],
        [InlineKeyboardButton("🆕 Рассчитать новый товар", callback_data="cart:new_calc")],
    ])


def _kb_cart_products(items: list[dict], short_names: dict) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        cid = item["id"]
        name = short_names.get(cid, (item.get("name") or "Товар")[:30])
        mark = "📋 " if item.get("in_order") else ""
        rows.append([InlineKeyboardButton(f"{mark}{name}", callback_data=f"cart:item:{cid}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="cart:back_main")])
    return InlineKeyboardMarkup(rows)


def _kb_cart_item(calc_id: int, in_order: bool, removed: bool = False) -> InlineKeyboardMarkup:
    if removed:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Вернуть в корзину", callback_data=f"cart:restore:{calc_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="cart:item_back")],
        ])
    order_btn = (
        InlineKeyboardButton("✅ Убрать из заявки", callback_data=f"cart:order_remove:{calc_id}")
        if in_order else
        InlineKeyboardButton("📋 В заявку", callback_data=f"cart:order_add:{calc_id}")
    )
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Комментарий", callback_data=f"cart:comment:{calc_id}"),
            InlineKeyboardButton("✏️ Изменить", callback_data=f"cart:edit_calc:{calc_id}"),
        ],
        [order_btn],
        [InlineKeyboardButton("🔍 Характеристики товара", callback_data=f"cart:specs:{calc_id}")],
        [
            InlineKeyboardButton("🟣 Сравнить с WB", callback_data=f"cart:compare:wb:{calc_id}"),
            InlineKeyboardButton("🔵 Сравнить с Ozon", callback_data=f"cart:compare:ozon:{calc_id}"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="cart:item_back"),
            InlineKeyboardButton("🗑 Удалить из корзины", callback_data=f"cart:remove:{calc_id}"),
        ],
    ])


def _kb_cart_clear(items: list[dict], short_names: dict) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        cid = item["id"]
        name = short_names.get(cid, (item.get("name") or "Товар")[:30])
        rows.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"cart:remove_one:{cid}")])
    rows.append([
        InlineKeyboardButton("⚠️ Удалить всё", callback_data="cart:clear_confirm"),
        InlineKeyboardButton("◀️ Назад", callback_data="cart:back_main"),
    ])
    return InlineKeyboardMarkup(rows)


def _kb_order_list(has_items: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_items:
        rows.append([InlineKeyboardButton("📦 Товары заявки", callback_data="cart:order_products")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="cart:back_main")])
    return InlineKeyboardMarkup(rows)


def _kb_order_products(items: list[dict], short_names: dict) -> InlineKeyboardMarkup:
    """Список товаров в заявке — ведёт в карточку order_item."""
    rows = []
    for item in items:
        cid = item["id"]
        name = short_names.get(cid, (item.get("name") or "Товар")[:30])
        rows.append([InlineKeyboardButton(f"• {name}", callback_data=f"cart:order_item:{cid}")])
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="cart:order_view")])
    return InlineKeyboardMarkup(rows)


def _kb_order_item(calc_id: int) -> InlineKeyboardMarkup:
    """Карточка товара из раздела Заявки — только 2 кнопки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Убрать из заявки", callback_data=f"cart:order_item_remove:{calc_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="cart:order_item_back")],
    ])


def _kb_order_item_removed(calc_id: int) -> InlineKeyboardMarkup:
    """Карточка товара из Заявки после удаления из заявки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 В заявку", callback_data=f"cart:order_item_add:{calc_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="cart:order_item_back")],
    ])


# ─── Основные хэндлеры ────────────────────────────────────────────────────────

async def show_cart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Открыть корзину — всегда новое сообщение."""
    if update.callback_query:
        await update.callback_query.answer()
        user_id = update.callback_query.from_user.id
        chat = update.callback_query.message.chat
    else:
        user_id = update.message.from_user.id
        chat = update.message.chat

    if await _check_ban(user_id, ctx.bot, chat.id):
        return

    items = await db.cart_get_items(user_id)
    if not items:
        await chat.send_message(
            "🛒 *Корзина пуста*\n\n"
            "Добавляй товары кнопкой «🛒 Добавить в корзину» после расчёта — "
            "и они появятся здесь.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Анимация загрузки пока Groq обрабатывает названия
    sticker_msg = await chat.send_sticker(_STICKER_CART)
    loading_msg = await chat.send_message("⏳ Формирую корзину…")

    short_names = await _get_short_names(items, ctx)

    try:
        await sticker_msg.delete()
        await loading_msg.delete()
    except Exception:
        pass

    order_count = sum(1 for item in items if item.get("in_order"))
    text = _cart_welcome_text(items, short_names, order_count)
    await chat.send_message(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_kb_cart_main(len(items), order_count),
    )


async def handle_cart_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # Бан-проверка (кроме dismiss предупреждения)
    if data != "cart:warning_dismiss":
        if await _check_ban(user_id, ctx.bot, query.message.chat_id):
            return

    # ── Открыть корзину из кнопки "Перейти в корзину" (новое сообщение) ────────
    if data == "cart:open":
        items = await db.cart_get_items(user_id)
        if not items:
            await query.message.reply_text(
                "🛒 *Корзина пуста*\n\nДобавляй товары кнопкой «🛒 Добавить в корзину».",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        sticker_msg = await query.message.reply_sticker(_STICKER_CART)
        loading_msg = await query.message.reply_text("⏳ Формирую корзину…")
        short_names = await _get_short_names(items, ctx)
        try:
            await sticker_msg.delete()
            await loading_msg.delete()
        except Exception:
            pass
        order_count = sum(1 for item in items if item.get("in_order"))
        text = _cart_welcome_text(items, short_names, order_count)
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_cart_main(len(items), order_count),
        )
        return

    # ── Назад к главной корзине (редактирование текущего сообщения) ───────────
    if data == "cart:back_main":
        items = await db.cart_get_items(user_id)
        if not items:
            await query.message.edit_text(
                "🛒 *Корзина пуста*\n\nДобавляй товары кнопкой «🛒 Добавить в корзину».",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        short_names = await _get_short_names(items, ctx)
        order_count = sum(1 for item in items if item.get("in_order"))
        text = _cart_welcome_text(items, short_names, order_count)
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_cart_main(len(items), order_count),
        )
        return

    # ── Рассчитать новый товар ────────────────────────────────────────────────
    if data == "cart:new_calc":
        from handlers.commands import send_start_photo
        await send_start_photo(ctx.bot, query.message.chat_id, query.from_user, ctx)
        return

    # ── Список товаров ────────────────────────────────────────────────────────
    if data in ("cart:products", "cart:item_back"):
        items = await db.cart_get_items(user_id)
        if not items:
            if query.message.photo:
                await query.message.delete()
                await ctx.bot.send_message(query.message.chat_id, "🛒 *Корзина пуста*", parse_mode=ParseMode.MARKDOWN)
            else:
                await query.message.edit_text("🛒 *Корзина пуста*", parse_mode=ParseMode.MARKDOWN)
            return
        short_names = await _get_short_names(items, ctx)
        list_text = "Выбери товар, чтобы посмотреть расчёт:"
        kb = _kb_cart_products(items, short_names)
        if query.message.photo:
            await query.message.delete()
            await ctx.bot.send_message(query.message.chat_id, list_text, reply_markup=kb)
        else:
            await query.message.edit_text(list_text, reply_markup=kb)
        return

    # ── Детали товара ─────────────────────────────────────────────────────────
    if data.startswith("cart:item:"):
        calc_id = int(data.split(":")[-1])
        row = await db.get_calculation_by_id(calc_id, user_id)
        if not row:
            await query.answer("Товар не найден", show_alert=True)
            return
        rate = await er.get_rate()
        settings = await db.get_admin_settings()
        try:
            result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
            result.calc_id = calc_id
            eff_rate = await get_effective_rate()
            result.breakdown = _rebuild_breakdown(result, settings, eff_rate)
        except Exception as e:
            log.warning(f"cart item load failed: {e}")
            await query.answer("Не удалось загрузить расчёт", show_alert=True)
            return

        text = fmt_result(
            result, "client",
            delivery_time=settings.get("delivery_time"),
            next_shipment_date=settings.get("next_shipment_date"),
        )

        items = await db.cart_get_items(user_id)
        in_order = next((bool(item.get("in_order")) for item in items if item["id"] == calc_id), False)
        kb = _kb_cart_item(calc_id, in_order)
        image_url = result.product.image_url

        if image_url:
            try:
                await query.message.delete()
                await ctx.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=image_url,
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=kb,
                )
                return
            except Exception as e:
                log.warning(f"cart item send_photo failed: {e}")

        try:
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            log.warning(f"cart item edit_text failed: {e}")
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb, disable_web_page_preview=True)
        return

    # ── Вернуть в заявку из карточки заявки (order item view) ─────────────────
    if data.startswith("cart:order_item_add:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_set_order(user_id, calc_id, True)
        await _notify_admin_order(ctx, user_id, calc_id, query.from_user.username or "", True)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_order_item(calc_id))
        except Exception:
            pass
        await query.message.reply_text(
            "✅ Товар добавлен в заявку!\n\n"
            "Администратор получил уведомление и свяжется с вами в ближайшее время.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="cart:warning_dismiss")]
            ]),
        )
        return

    # ── Добавить в заявку ─────────────────────────────────────────────────────
    if data.startswith("cart:order_add:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_set_order(user_id, calc_id, True)
        await _notify_admin_order(ctx, user_id, calc_id, query.from_user.username or "", True)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_cart_item(calc_id, True))
        except Exception:
            pass
        await query.message.reply_text(
            "✅ Товар добавлен в заявку!\n\n"
            "Администратор получил уведомление и свяжется с вами в ближайшее время.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="cart:warning_dismiss")]
            ]),
        )
        return

    # ── Убрать из заявки (из обычной карточки корзины) ───────────────────────
    if data.startswith("cart:order_remove:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_set_order(user_id, calc_id, False)
        await _notify_admin_order(ctx, user_id, calc_id, query.from_user.username or "", False)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_cart_item(calc_id, False))
        except Exception:
            pass
        # Предупреждение о спаме
        await query.message.reply_text(
            "⚠️ *Внимание!*\n"
            "При добавлении и удалении товаров из заявки администратор получает уведомление.\n"
            "Спам удалением товара из заявки приведёт к временному бану!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="cart:warning_dismiss")]
            ]),
        )
        # Счётчик и бан
        count = await db.increment_order_removes(user_id)
        await _apply_ban_if_needed(user_id, ctx.bot, query.message.chat_id, count)
        return

    # ── Удалить из корзины ────────────────────────────────────────────────────
    if data.startswith("cart:remove:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_remove(user_id, calc_id)
        ctx.user_data.get("cart_short_names", {}).pop(calc_id, None)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_cart_item(calc_id, False, removed=True))
        except Exception:
            pass
        return

    # ── Вернуть в корзину ─────────────────────────────────────────────────────
    if data.startswith("cart:restore:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_add(user_id, calc_id)
        items = await db.cart_get_items(user_id)
        in_order = next((bool(i.get("in_order")) for i in items if i["id"] == calc_id), False)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_cart_item(calc_id, in_order, removed=False))
        except Exception:
            pass
        return

    # ── Меню очистки ──────────────────────────────────────────────────────────
    if data == "cart:clear_menu":
        items = await db.cart_get_items(user_id)
        if not items:
            await query.answer("Корзина уже пуста")
            return
        short_names = await _get_short_names(items, ctx)
        await query.message.edit_text(
            "Выбери товар для удаления:\n\n_Нажми на название — он будет удалён._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_cart_clear(items, short_names),
        )
        return

    # ── Удалить один (из меню очистки) ────────────────────────────────────────
    if data.startswith("cart:remove_one:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_remove(user_id, calc_id)
        ctx.user_data.get("cart_short_names", {}).pop(calc_id, None)
        items = await db.cart_get_items(user_id)
        if not items:
            await query.message.edit_text(
                "🛒 *Корзина пуста*\n\nВсе товары удалены.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Вернуться в корзину", callback_data="cart:open")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="cart:back_main")],
                ]),
            )
            return
        short_names = await _get_short_names(items, ctx)
        await query.message.edit_text(
            "Выбери товар для удаления:\n\n_Нажми на название — он будет удалён._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_cart_clear(items, short_names),
        )
        return

    # ── Подтверждение удаления всего ────────────────────────────────────────
    if data == "cart:clear_confirm":
        await query.message.edit_text(
            "⚠️ *Вы уверены?*\n\nВсе товары из корзины будут удалены безвозвратно.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, удалить всё", callback_data="cart:clear_all")],
                [InlineKeyboardButton("◀️ Назад", callback_data="cart:clear_menu")],
            ]),
        )
        return

    # ── Удалить всё ───────────────────────────────────────────────────────────
    if data == "cart:clear_all":
        await db.cart_clear(user_id)
        ctx.user_data.pop("cart_short_names", None)
        await query.message.edit_text(
            "🗑 *Корзина очищена*\n\nВсе товары удалены.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Вернуться в корзину", callback_data="cart:open")],
                [InlineKeyboardButton("🆕 Новый расчёт", callback_data="cart:new_calc")],
            ]),
        )
        return

    # ── Закрыть предупреждение о спаме ───────────────────────────────────────
    if data == "cart:warning_dismiss":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Назад из карточки товара заявки ──────────────────────────────────────
    if data == "cart:order_item_back":
        items = await db.cart_get_items(user_id)
        order_items = [i for i in items if i.get("in_order")]
        short_names = await _get_short_names(items, ctx)
        if order_items:
            list_text = "Товары в заявке:"
            kb = _kb_order_products(order_items, short_names)
        else:
            list_text = _order_welcome_text([], short_names)
            kb = _kb_order_list(False)
        if query.message.photo:
            await query.message.delete()
            await ctx.bot.send_message(query.message.chat_id, list_text,
                                       parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        else:
            await query.message.edit_text(list_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return

    # ── Карточка товара из раздела Заявки (только 2 кнопки) ──────────────────
    if data.startswith("cart:order_item:"):
        calc_id = int(data.split(":")[-1])
        row = await db.get_calculation_by_id(calc_id, user_id)
        if not row:
            await query.answer("Товар не найден", show_alert=True)
            return
        rate = await er.get_rate()
        settings = await db.get_admin_settings()
        try:
            result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
            result.calc_id = calc_id
            eff_rate = await get_effective_rate()
            result.breakdown = _rebuild_breakdown(result, settings, eff_rate)
        except Exception as e:
            log.warning(f"order item load failed: {e}")
            await query.answer("Не удалось загрузить расчёт", show_alert=True)
            return
        text = fmt_result(
            result, "client",
            delivery_time=settings.get("delivery_time"),
            next_shipment_date=settings.get("next_shipment_date"),
            in_order=True,
        )
        kb = _kb_order_item(calc_id)
        image_url = result.product.image_url
        if image_url:
            try:
                await query.message.delete()
                await ctx.bot.send_photo(chat_id=query.message.chat_id, photo=image_url,
                                         caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                return
            except Exception as e:
                log.warning(f"order item send_photo failed: {e}")
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                          reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            log.warning(f"order item edit_text failed: {e}")
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                           reply_markup=kb, disable_web_page_preview=True)
        return

    # ── Убрать из заявки (из карточки Заявки) ────────────────────────────────
    if data.startswith("cart:order_item_remove:"):
        calc_id = int(data.split(":")[-1])
        await db.cart_set_order(user_id, calc_id, False)
        await _notify_admin_order(ctx, user_id, calc_id, query.from_user.username or "", False)
        try:
            await query.message.edit_reply_markup(reply_markup=_kb_order_item_removed(calc_id))
        except Exception:
            pass
        # Предупреждение о спаме
        await query.message.reply_text(
            "⚠️ *Внимание!*\n"
            "При добавлении и удалении товаров из заявки администратор получает уведомление.\n"
            "Спам удалением товара из заявки приведёт к временному бану!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="cart:warning_dismiss")]
            ]),
        )
        # Счётчик и бан
        count = await db.increment_order_removes(user_id)
        await _apply_ban_if_needed(user_id, ctx.bot, query.message.chat_id, count)
        return

    # ── Заявка ────────────────────────────────────────────────────────────────
    if data == "cart:order_view":
        items = await db.cart_get_items(user_id)
        order_items = [i for i in items if i.get("in_order")]
        short_names = await _get_short_names(items, ctx)
        text = _order_welcome_text(order_items, short_names)
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_order_list(bool(order_items)),
        )
        return

    # ── Назад из характеристик — удалить все сообщения (фото + текст) ─────────
    if data == "cart:specs_back":
        msg_ids = ctx.user_data.pop("cart_specs_msg_ids", [])
        chat_id = query.message.chat_id
        for mid in msg_ids:
            try:
                await ctx.bot.delete_message(chat_id, mid)
            except Exception:
                pass
        if not msg_ids:
            try:
                await query.message.delete()
            except Exception:
                pass
        return

    # ── Характеристики товара ─────────────────────────────────────────────────
    if data.startswith("cart:specs:"):
        calc_id = int(data.split(":")[-1])
        row = await db.get_calculation_by_id(calc_id, user_id)
        if not row:
            await query.answer("Товар не найден", show_alert=True)
            return
        from services import exchange_rate as _er
        rate = await _er.get_rate()
        try:
            result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
        except Exception as e:
            log.warning(f"cart specs load failed: {e}")
            await query.answer("Не удалось загрузить товар", show_alert=True)
            return
        draft = result.product
        _SPECS_STICKER = "CAACAgIAAxkBAAFED75pq5go0D9gmpBWWMBRJQ8Oo07P4QACGAADwDZPE9b6J7-cahj4OgQ"
        sticker_msg = await query.message.reply_sticker(_SPECS_STICKER)
        loading_msg = await query.message.reply_text("🔍 Загружаю характеристики...")
        specs = draft.specs or {}
        try:
            from services.translator import translate_specs_with_groq
            specs = await translate_specs_with_groq(specs)
        except Exception:
            pass
        try:
            await sticker_msg.delete()
            await loading_msg.delete()
        except Exception:
            pass
        lines = ["📋 *Характеристики товара*\n"]
        if specs:
            for key, val in specs.items():
                lines.append(f"• *{key}:* {val}")
        else:
            lines.append("_Спецификации не найдены_")
        if draft.available_sizes:
            lines.append(f"\n📏 *Размеры:* {', '.join(draft.available_sizes)}")
        if draft.weight_kg:
            lines.append(f"⚖️ *Вес:* {draft.weight_kg:.1f} кг")
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="cart:specs_back")]])
        msg_ids = []
        # Отправляем фото (extra_images) как медиагруппу
        photos = draft.extra_images if draft.extra_images else []
        if photos:
            from telegram import InputMediaPhoto
            try:
                media = [InputMediaPhoto(media=url) for url in photos[:10]]
                photo_msgs = await query.message.reply_media_group(media=media)
                msg_ids.extend(m.message_id for m in photo_msgs)
            except Exception as e:
                log.warning(f"cart specs photos send failed: {e}")
        text_msg = await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb)
        msg_ids.append(text_msg.message_id)
        ctx.user_data["cart_specs_msg_ids"] = msg_ids
        return

    # ── Комментарий к товару ─────────────────────────────────────────────────
    if data.startswith("cart:comment:"):
        calc_id = int(data.split(":")[-1])
        ctx.user_data["cart_comment_calc_id"] = calc_id
        ctx.user_data["cart_comment_msg_id"] = query.message.message_id
        ctx.user_data["cart_comment_chat_id"] = query.message.chat_id
        ctx.user_data["cart_comment_is_photo"] = bool(query.message.photo)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="cart:comment_cancel")]])
        prompt = await query.message.reply_text(
            "💬 Введите комментарий или уточнение о товаре.\n\n"
            "_Он будет виден на карточке товара._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )
        ctx.user_data["cart_comment_prompt_msg_id"] = prompt.message_id
        return

    # ── Отмена комментария ────────────────────────────────────────────────────
    if data == "cart:comment_cancel":
        ctx.user_data.pop("cart_comment_calc_id", None)
        ctx.user_data.pop("cart_comment_msg_id", None)
        ctx.user_data.pop("cart_comment_chat_id", None)
        ctx.user_data.pop("cart_comment_is_photo", None)
        ctx.user_data.pop("cart_comment_prompt_msg_id", None)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Сравнение с WB / Ozon ─────────────────────────────────────────────────
    if data.startswith("cart:compare:"):
        parts = data.split(":")
        market = parts[2]  # "wb" или "ozon"
        calc_id = int(parts[3])
        row = await db.get_calculation_by_id(calc_id, user_id)
        if not row:
            await query.answer("Товар не найден", show_alert=True)
            return
        rate = await er.get_rate()
        try:
            result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
        except Exception as e:
            log.warning(f"cart compare load failed: {e}")
            await query.answer("Не удалось загрузить расчёт", show_alert=True)
            return
        ctx.user_data["_compare_from_cart_name"] = result.product.name
        ctx.user_data["_compare_from_cart_price"] = result.subtotal_rub
        from handlers.conversation import _run_comparison
        await _run_comparison(query.message, ctx, result.product.name, result.subtotal_rub, market, cart_mode=True)
        return

    # ── "Сравнить ещё" из результата сравнения в корзине ─────────────────────
    if data.startswith("cart:cross:"):
        market = data.split(":")[-1]  # "wb" или "ozon"
        name = ctx.user_data.get("_compare_from_cart_name", "")
        our_price = ctx.user_data.get("_compare_from_cart_price", 0.0)
        if not name:
            await query.answer("Не найдено название товара", show_alert=True)
            return
        from handlers.conversation import _run_comparison
        await _run_comparison(query.message, ctx, name, our_price, market, cart_mode=True)
        return

    # ── Товары заявки ─────────────────────────────────────────────────────────
    if data == "cart:order_products":
        items = await db.cart_get_items(user_id)
        order_items = [i for i in items if i.get("in_order")]
        if not order_items:
            await query.answer("Заявка пуста")
            return
        short_names = await _get_short_names(items, ctx)
        await query.message.edit_text(
            "Товары в заявке:",
            reply_markup=_kb_order_products(order_items, short_names),
        )
        return


async def handle_cart_comment_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Пользователь ввёл текст комментария к товару в корзине."""
    calc_id = ctx.user_data.get("cart_comment_calc_id")
    if not calc_id:
        return
    if await _check_ban(update.effective_user.id, ctx.bot, update.effective_chat.id):
        return
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        return

    # Удаляем сообщение пользователя и prompt
    for msg_id in [
        update.message.message_id,
        ctx.user_data.pop("cart_comment_prompt_msg_id", None),
    ]:
        if msg_id:
            try:
                await ctx.bot.delete_message(update.effective_chat.id, msg_id)
            except Exception:
                pass

    # Загружаем расчёт, обновляем notes, пересохраняем
    row = await db.get_calculation_by_id(calc_id, user_id)
    if not row:
        ctx.user_data.pop("cart_comment_calc_id", None)
        return

    rate = await er.get_rate()
    try:
        result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
    except Exception as e:
        log.warning(f"cart comment load failed: {e}")
        ctx.user_data.pop("cart_comment_calc_id", None)
        return

    result.product.notes = text
    new_calc_id, _ = await db.save_calculation(user_id, result)
    await db.cart_update_item(user_id, calc_id, new_calc_id)
    ctx.user_data.get("cart_short_names", {}).pop(calc_id, None)

    # Очищаем флаги; ставим маркер чтобы group=2 ConversationHandler не перехватил
    card_msg_id = ctx.user_data.pop("cart_comment_msg_id", None)
    card_chat_id = ctx.user_data.pop("cart_comment_chat_id", None)
    ctx.user_data.pop("cart_comment_is_photo", None)
    ctx.user_data.pop("cart_comment_calc_id", None)
    ctx.user_data["_cart_comment_done"] = True

    # Обновляем карточку товара
    if not card_msg_id or not card_chat_id:
        return

    result.calc_id = new_calc_id
    items = await db.cart_get_items(user_id)
    in_order = next((bool(i.get("in_order")) for i in items if i["id"] == new_calc_id), False)
    kb = _kb_cart_item(new_calc_id, in_order)
    from utils.formatters import fmt_result
    _settings = await db.get_admin_settings()
    new_text = fmt_result(
        result, "client",
        delivery_time=_settings.get("delivery_time"),
        next_shipment_date=_settings.get("next_shipment_date"),
    )

    image_url = result.product.image_url
    if image_url:
        try:
            await ctx.bot.delete_message(card_chat_id, card_msg_id)
            await ctx.bot.send_photo(
                chat_id=card_chat_id,
                photo=image_url,
                caption=new_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
        except Exception as e:
            log.warning(f"cart comment send_photo failed: {e}")
    else:
        try:
            await ctx.bot.edit_message_text(
                chat_id=card_chat_id,
                message_id=card_msg_id,
                text=new_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"cart comment update text failed: {e}")


def build_cart_handlers():
    from telegram.ext import MessageHandler, filters as tg_filters
    return [
        CommandHandler("cart", show_cart),
        MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_cart_comment_text),
        # cart:edit_calc: исключён — перехватывается ConversationHandler (group=2)
        CallbackQueryHandler(handle_cart_callback, pattern=r"^cart:(?!edit_calc:)"),
    ]
