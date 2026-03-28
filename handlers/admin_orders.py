"""Администраторский экран заявок — просмотр и управление."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

import database as db
from config import ADMIN_USER_ID, ADMIN_USERNAME
from services.market_compare import extract_search_query

log = logging.getLogger(__name__)


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _fmt_dt(dt_str: str) -> str:
    """Форматировать дату из SQLite: '2026-03-09 14:32:00' → '09.03.2026 в 14:32'."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        return dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        return dt_str


def _safe_md(text: str) -> str:
    """Экранировать символы, ломающие Markdown v1 в тексте ссылки."""
    return text.replace("[", "(").replace("]", ")")


async def _get_short_names(items: list[dict], ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    """Короткие Groq-названия для заявок. Кешируются в bot_data (общий кеш)."""
    cache = ctx.bot_data.setdefault("admin_order_short_names", {})
    new_ids, new_coros = [], []
    for item in items:
        cid = item["calc_id"]
        if cid not in cache:
            new_ids.append(cid)
            new_coros.append(extract_search_query(item.get("name") or "Товар"))
    if new_coros:
        results = await asyncio.gather(*new_coros, return_exceptions=True)
        items_map = {item["calc_id"]: item for item in items}
        for cid, res in zip(new_ids, results):
            if isinstance(res, Exception) or not res:
                cache[cid] = (items_map[cid].get("name") or "Товар")[:30]
            else:
                cache[cid] = str(res)[:35]
    return cache


def _contact_kb() -> Optional[InlineKeyboardMarkup]:
    """Клавиатура со ссылкой на администратора для уведомлений пользователям."""
    if not ADMIN_USERNAME:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💬 Связаться с администратором",
            url=f"https://t.me/{ADMIN_USERNAME}",
        )
    ]])


# ─── Тексты ───────────────────────────────────────────────────────────────────

def _orders_text(items: list[dict], short_names: dict) -> str:
    """Основной текст экрана заявок для администратора."""
    if not items:
        return "📋 *Нет активных заявок*"

    lines = ["📋 *Заявки на оформление*", ""]

    # Группировка по user_id с сохранением порядка появления
    seen_users: list[int] = []
    by_user: dict[int, list] = {}
    for item in items:
        uid = item["user_id"]
        if uid not in by_user:
            seen_users.append(uid)
            by_user[uid] = []
        by_user[uid].append(item)

    counter = 1
    for uid in seen_users:
        user_items = by_user[uid]
        username = user_items[0].get("username") or str(uid)
        all_paid = all(item.get("paid") for item in user_items)

        lines.append(f"👤 @{username}:")
        if not all_paid:
            lines.append("_Свяжитесь с пользователем для уточнения деталей и оплаты_")

        for item in user_items:
            cid = item["calc_id"]
            name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:30]))
            url = item.get("product_url") or ""
            dt = _fmt_dt(item.get("order_added_at") or "")
            paid = item.get("paid")

            name_part = f"[{name}]({url})" if url else name
            status = "✅ Товар оплачен" if paid else "❌ Товар ещё не оплачен"

            lines.append(f"{counter}. {name_part}")
            lines.append(f"   📅 {dt}")
            lines.append(f"   {status}")
            if item.get("arrived"):
                lines.append("   📦 Доставлен")
            elif item.get("shipped"):
                lines.append("   🚚 Отправлен")
            counter += 1

        lines.append("")

    return "\n".join(lines).strip()


def _action_text(title: str, filtered: list[dict], short_names: dict) -> str:
    """Текст для экранов выбора действия (отметить/снять/удалить)."""
    lines = [title, ""]
    for i, item in enumerate(filtered, 1):
        cid = item["calc_id"]
        name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:30]))
        username = item.get("username") or str(item["user_id"])
        lines.append(f"{i}. {name} (@{username})")
    return "\n".join(lines)


# ─── Клавиатуры ───────────────────────────────────────────────────────────────

def _kb_main(has_items: bool) -> InlineKeyboardMarkup:
    if not has_items:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Обновить", callback_data="aord:show"),
        ]])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Просмотр товаров",  callback_data="aord:items_menu"),
        ],
        [
            InlineKeyboardButton("✅ Отметить оплаченные", callback_data="aord:mark_paid_menu"),
            InlineKeyboardButton("❌ Удалить оплату",      callback_data="aord:remove_pay_menu"),
        ],
        [
            InlineKeyboardButton("🚚 Уведомить об отправке", callback_data="aord:notify_ship"),
            InlineKeyboardButton("📦 Уведомить о прибытии",  callback_data="aord:notify_arrival"),
        ],
        [
            InlineKeyboardButton("◀️ Назад",             callback_data="aord:back"),
            InlineKeyboardButton("🗑 Удалить из заявки", callback_data="aord:delete_menu"),
        ],
    ])


def _kb_action(filtered: list[dict], action: str) -> InlineKeyboardMarkup:
    """Кнопки-цифры для выбора товара (5 в ряд) + кнопка Назад."""
    rows = []
    btn_row = []
    for i, item in enumerate(filtered, 1):
        uid = item["user_id"]
        cid = item["calc_id"]
        btn_row.append(InlineKeyboardButton(
            str(i),
            callback_data=f"aord:{action}:{uid}:{cid}",
        ))
        if len(btn_row) == 5:
            rows.append(btn_row)
            btn_row = []
    if btn_row:
        rows.append(btn_row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="aord:show")])
    return InlineKeyboardMarkup(rows)


# ─── Уведомления: вспомогательные функции ─────────────────────────────────────

def _notify_full_list_text(items: list[dict], short_names: dict, header: str) -> str:
    """Нумерованный список всех заявок для выбора товаров."""
    lines = [header, ""]
    seen_users: list[int] = []
    by_user: dict[int, list] = {}
    for item in items:
        uid = item["user_id"]
        if uid not in by_user:
            seen_users.append(uid)
            by_user[uid] = []
        by_user[uid].append(item)
    counter = 1
    for uid in seen_users:
        user_items = by_user[uid]
        username = user_items[0].get("username") or str(uid)
        lines.append(f"👤 @{username}:")
        for item in user_items:
            cid = item["calc_id"]
            name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:35]))
            paid_icon = "✅" if item.get("paid") else "❌"
            if item.get("arrived"):
                delivery_icon = " 📦"
            elif item.get("shipped"):
                delivery_icon = " 🚚"
            else:
                delivery_icon = ""
            lines.append(f"{counter}. {name}{delivery_icon} {paid_icon}")
            counter += 1
        lines.append("")
    return "\n".join(lines).strip()


def _notify_selected_text(items: list[dict], short_names: dict) -> str:
    """Список выбранных товаров буллетами."""
    lines = []
    for item in items:
        cid = item["calc_id"]
        name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:35]))
        username = item.get("username") or str(item["user_id"])
        lines.append(f"• {name} (@{username})")
    return "\n".join(lines)


def _kb_notify_waiting(back_cb: str = "aord:notify_back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data=back_cb),
    ]])


def _kb_notify_ship_confirm(sent: bool = False) -> InlineKeyboardMarkup:
    send_btn = (
        InlineKeyboardButton("✅ Отправлено", callback_data="aord:noop")
        if sent else
        InlineKeyboardButton("📤 Отправить уведомление", callback_data="aord:notify_ship_send")
    )
    return InlineKeyboardMarkup([[
        send_btn,
        InlineKeyboardButton("◀️ Назад", callback_data="aord:notify_back"),
    ]])


def _kb_notify_arrival(sent: bool = False, has_items: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if has_items:
        rows.append([InlineKeyboardButton("➕ Добавить товар", callback_data="aord:notify_arrival_add")])
        send_btn = (
            InlineKeyboardButton("✅ Отправлено", callback_data="aord:noop")
            if sent else
            InlineKeyboardButton("📤 Отправить уведомление", callback_data="aord:notify_arrival_send")
        )
        rows.append([send_btn, InlineKeyboardButton("◀️ Назад", callback_data="aord:notify_back")])
    else:
        rows.append([InlineKeyboardButton("◀️ Назад", callback_data="aord:notify_back")])
    return InlineKeyboardMarkup(rows)


# ─── Общая функция отрисовки главного экрана ──────────────────────────────────

async def _render_orders(message, ctx: ContextTypes.DEFAULT_TYPE, edit: bool = True):
    items = await db.cart_get_all_orders()
    short_names = await _get_short_names(items, ctx)
    text = _orders_text(items, short_names)
    kb = _kb_main(bool(items))
    kwargs = dict(
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    if edit:
        await message.edit_text(**kwargs)
    else:
        await message.reply_text(**kwargs)


# ─── Основной хендлер ─────────────────────────────────────────────────────────

async def handle_admin_orders_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
        return

    # ── Открыть заявки (из стартового меню) — не трогаем текущее сообщение ──────
    if data == "aord:open":
        _LOADING_STICKER = "CAACAgIAAxkBAAFEF2FprB-04zbubwK96NZLKQABqQePHlQAAg0AA8A2TxOk-eH01HiNUzoE"
        sticker_msg = await query.message.reply_sticker(_LOADING_STICKER)
        loading_msg = await query.message.reply_text("📋 Собираем все заявки...")
        items = await db.cart_get_all_orders()
        short_names = await _get_short_names(items, ctx)
        text = _orders_text(items, short_names)
        kb = _kb_main(bool(items))
        try:
            await sticker_msg.delete()
            await loading_msg.delete()
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return

    # ── Обновить заявки (внутри экрана заявок) ─────────────────────────────────
    if data == "aord:show":
        await _render_orders(query.message, ctx, edit=True)
        return

    # ── Назад к стартовому меню ────────────────────────────────────────────────
    if data == "aord:back":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Меню "Отметить оплаченные" ─────────────────────────────────────────────
    if data == "aord:mark_paid_menu":
        items = await db.cart_get_all_orders()
        unpaid = [i for i in items if not i.get("paid")]
        if not unpaid:
            await query.answer("Все товары уже оплачены", show_alert=True)
            return
        short_names = await _get_short_names(items, ctx)
        text = _action_text("✅ Выберите оплаченный товар:", unpaid, short_names)
        await query.message.edit_text(
            text,
            reply_markup=_kb_action(unpaid, "pay"),
        )
        return

    # ── Меню "Удалить оплату" ──────────────────────────────────────────────────
    if data == "aord:remove_pay_menu":
        items = await db.cart_get_all_orders()
        paid_items = [i for i in items if i.get("paid")]
        if not paid_items:
            await query.answer("Нет оплаченных товаров", show_alert=True)
            return
        short_names = await _get_short_names(items, ctx)
        text = _action_text("❌ Выберите товар для снятия оплаты:", paid_items, short_names)
        await query.message.edit_text(
            text,
            reply_markup=_kb_action(paid_items, "unpay"),
        )
        return

    # ── Меню "Удалить из заявки" ───────────────────────────────────────────────
    if data == "aord:delete_menu":
        items = await db.cart_get_all_orders()
        if not items:
            await query.answer("Заявок нет", show_alert=True)
            return
        short_names = await _get_short_names(items, ctx)
        text = _action_text("🗑 Выберите товар для удаления из заявки:", items, short_names)
        await query.message.edit_text(
            text,
            reply_markup=_kb_action(items, "del"),
        )
        return

    # ── Отметить оплаченным: aord:pay:{user_id}:{calc_id} ─────────────────────
    if data.startswith("aord:pay:"):
        parts = data.split(":")
        target_uid, calc_id = int(parts[2]), int(parts[3])

        items = await db.cart_get_all_orders()
        short_names = await _get_short_names(items, ctx)
        item = next(
            (i for i in items if i["user_id"] == target_uid and i["calc_id"] == calc_id),
            None,
        )
        if not item:
            await query.answer("Товар не найден", show_alert=True)
            return

        await db.cart_set_paid(target_uid, calc_id, True)

        product_name = short_names.get(calc_id, item.get("name") or "Товар")
        try:
            await ctx.bot.send_message(
                target_uid,
                f"✅ Ваш товар *{product_name}* оплачен! Скоро выкупим и отправим.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.warning(f"Не удалось уведомить пользователя {target_uid}: {e}")

        await _render_orders(query.message, ctx, edit=True)
        return

    # ── Снять оплату: aord:unpay:{user_id}:{calc_id} ──────────────────────────
    if data.startswith("aord:unpay:"):
        parts = data.split(":")
        target_uid, calc_id = int(parts[2]), int(parts[3])

        items = await db.cart_get_all_orders()
        short_names = await _get_short_names(items, ctx)
        item = next(
            (i for i in items if i["user_id"] == target_uid and i["calc_id"] == calc_id),
            None,
        )
        if not item:
            await query.answer("Товар не найден", show_alert=True)
            return

        await db.cart_set_paid(target_uid, calc_id, False)

        product_name = short_names.get(calc_id, item.get("name") or "Товар")
        try:
            await ctx.bot.send_message(
                target_uid,
                f"❌ Оплата по товару *{product_name}* была отменена. "
                f"Свяжитесь с администратором для уточнений.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_contact_kb(),
            )
        except Exception as e:
            log.warning(f"Не удалось уведомить пользователя {target_uid}: {e}")

        await _render_orders(query.message, ctx, edit=True)
        return

    # ── Удалить из заявки: aord:del:{user_id}:{calc_id} ───────────────────────
    if data.startswith("aord:del:"):
        parts = data.split(":")
        target_uid, calc_id = int(parts[2]), int(parts[3])

        items = await db.cart_get_all_orders()
        short_names = await _get_short_names(items, ctx)
        item = next(
            (i for i in items if i["user_id"] == target_uid and i["calc_id"] == calc_id),
            None,
        )
        if not item:
            await query.answer("Товар не найден", show_alert=True)
            return

        await db.cart_set_order(target_uid, calc_id, False)

        product_name = short_names.get(calc_id, item.get("name") or "Товар")
        # Сбрасываем кеш для этого товара — он больше не в заявке
        ctx.bot_data.get("admin_order_short_names", {}).pop(calc_id, None)

        try:
            await ctx.bot.send_message(
                target_uid,
                f"🗑 Ваш товар *{product_name}* был удалён из заявки администратором. "
                f"Если это ошибка — свяжитесь с нами.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_contact_kb(),
            )
        except Exception as e:
            log.warning(f"Не удалось уведомить пользователя {target_uid}: {e}")

        await _render_orders(query.message, ctx, edit=True)
        return

    # ── Уведомить об отправке ─────────────────────────────────────────────────
    if data == "aord:notify_ship":
        items = await db.cart_get_all_orders()
        if not items:
            await query.answer("Нет активных заявок", show_alert=True)
            return
        short_names = await _get_short_names(items, ctx)
        ctx.bot_data["admin_notify_mode"] = "ship"
        ctx.bot_data["admin_notify_items_snapshot"] = items
        ctx.bot_data["admin_notify_short_names"] = short_names
        ctx.bot_data.pop("admin_notify_ship_pending", None)
        header = (
            "🚚 *Уведомить об отправке*\n\n"
            "Выберите товары, которые уже отправлены — пользователи получат уведомление.\n"
            "✅ — оплачено, ❌ — не оплачено, 🚚 — отправлен, 📦 — доставлен\n"
            "Введите номера через запятую, например: 1,5,13"
        )
        text = _notify_full_list_text(items, short_names, header)
        await query.message.edit_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_notify_waiting("aord:notify_back"),
            disable_web_page_preview=True,
        )
        return

    # ── Уведомить о прибытии ──────────────────────────────────────────────────
    if data == "aord:notify_arrival":
        shipped_ids = set(await db.get_shipped_calc_ids())
        items = await db.cart_get_all_orders()
        short_names = await _get_short_names(items, ctx)
        ctx.bot_data["admin_notify_items_snapshot"] = items
        ctx.bot_data["admin_notify_short_names"] = short_names
        ctx.bot_data["admin_notify_mode"] = None
        ctx.bot_data["admin_notify_arrival_msg_id"] = query.message.message_id
        ctx.bot_data["admin_notify_arrival_chat_id"] = query.message.chat_id
        arrival_items = [i for i in items if i["calc_id"] in shipped_ids]
        ctx.bot_data["admin_notify_arrival_pending"] = arrival_items
        if not arrival_items:
            text = (
                "📦 *Уведомить о прибытии*\n\n"
                "Нет товаров, отмеченных как отправленные.\n"
                "Сначала воспользуйтесь «Уведомить об отправке»."
            )
            await query.message.edit_text(
                text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=_kb_notify_arrival(has_items=False),
            )
        else:
            selected_text = _notify_selected_text(arrival_items, short_names)
            text = (
                "📦 *Уведомить о прибытии*\n\n"
                "Товары, которые получат уведомление о прибытии:\n"
                + selected_text + "\n\n"
                "Пользователи получат уведомление о прибытии товаров."
            )
            await query.message.edit_text(
                text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=_kb_notify_arrival(has_items=True),
                disable_web_page_preview=True,
            )
        return

    # ── Добавить товар в прибытие ─────────────────────────────────────────────
    if data == "aord:notify_arrival_add":
        items = ctx.bot_data.get("admin_notify_items_snapshot") or []
        short_names = ctx.bot_data.get("admin_notify_short_names") or {}
        if not items:
            items = await db.cart_get_all_orders()
            short_names = await _get_short_names(items, ctx)
            ctx.bot_data["admin_notify_items_snapshot"] = items
            ctx.bot_data["admin_notify_short_names"] = short_names
        ctx.bot_data["admin_notify_mode"] = "arrival_add"
        ctx.bot_data["admin_notify_arrival_msg_id"] = query.message.message_id
        ctx.bot_data["admin_notify_arrival_chat_id"] = query.message.chat_id
        header = (
            "📦 *Добавить товары для уведомления о прибытии*\n\n"
            "✅ — оплачено, ❌ — не оплачено, 🚚 — отправлен, 📦 — доставлен\n"
            "Введите номера через запятую, например: 1,5,13"
        )
        text = _notify_full_list_text(items, short_names, header)
        await query.message.edit_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_notify_waiting("aord:notify_arrival_back"),
            disable_web_page_preview=True,
        )
        return

    # ── Назад к экрану прибытия (из добавления) ──────────────────────────────
    if data == "aord:notify_arrival_back":
        ctx.bot_data["admin_notify_mode"] = None
        arrival_items = ctx.bot_data.get("admin_notify_arrival_pending") or []
        short_names = ctx.bot_data.get("admin_notify_short_names") or {}
        if arrival_items:
            selected_text = _notify_selected_text(arrival_items, short_names)
            text = (
                "📦 *Уведомить о прибытии*\n\n"
                "Товары, которые получат уведомление о прибытии:\n"
                + selected_text + "\n\n"
                "Пользователи получат уведомление о прибытии товаров."
            )
            await query.message.edit_text(
                text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=_kb_notify_arrival(has_items=True),
                disable_web_page_preview=True,
            )
        else:
            text = (
                "📦 *Уведомить о прибытии*\n\n"
                "Нет выбранных товаров.\n"
                "Нажмите «Добавить товар» для выбора."
            )
            await query.message.edit_text(
                text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=_kb_notify_arrival(has_items=False),
            )
        return

    # ── Назад к заявкам (из notify-экранов) ──────────────────────────────────
    if data == "aord:notify_back":
        ctx.bot_data.pop("admin_notify_mode", None)
        ctx.bot_data.pop("admin_notify_items_snapshot", None)
        ctx.bot_data.pop("admin_notify_short_names", None)
        ctx.bot_data.pop("admin_notify_ship_pending", None)
        ctx.bot_data.pop("admin_notify_arrival_pending", None)
        ctx.bot_data.pop("admin_notify_arrival_msg_id", None)
        ctx.bot_data.pop("admin_notify_arrival_chat_id", None)
        await _render_orders(query.message, ctx, edit=True)
        return

    # ── Отправить уведомление об отправке ─────────────────────────────────────
    if data == "aord:notify_ship_send":
        pending = ctx.bot_data.get("admin_notify_ship_pending") or []
        short_names = ctx.bot_data.get("admin_notify_short_names") or {}
        if not pending:
            await query.answer("Не выбраны товары", show_alert=True)
            return
        settings = await db.get_admin_settings()
        delivery_time = settings.get("delivery_time", "")
        by_user_s: dict[int, list] = {}
        for item in pending:
            by_user_s.setdefault(item["user_id"], []).append(item)
        for uid, user_items in by_user_s.items():
            names_text = "\n".join(
                f"• {_safe_md(short_names.get(i['calc_id'], (i.get('name') or 'Товар')[:35]))}"
                for i in user_items
            )
            delivery_line = f"\n\n⏱ Примерное время доставки: {delivery_time}" if delivery_time else ""
            try:
                await ctx.bot.send_message(
                    uid,
                    f"🚚 *Ваши товары отправлены!*\n\n{names_text}\n\nОжидайте прибытия.{delivery_line}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                log.warning(f"Не удалось уведомить пользователя {uid}: {e}")
        shipped_ids = [i["calc_id"] for i in pending]
        await db.cart_set_shipped(shipped_ids)
        ctx.bot_data.pop("admin_notify_mode", None)
        selected_text = _notify_selected_text(pending, short_names)
        text = (
            "🚚 *Уведомить об отправке*\n\n"
            "Выбранные товары:\n" + selected_text + "\n\n"
            "✅ Уведомления об отправке отправлены."
        )
        await query.message.edit_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_notify_ship_confirm(sent=True),
            disable_web_page_preview=True,
        )
        return

    # ── Отправить уведомление о прибытии ─────────────────────────────────────
    if data == "aord:notify_arrival_send":
        pending = ctx.bot_data.get("admin_notify_arrival_pending") or []
        short_names = ctx.bot_data.get("admin_notify_short_names") or {}
        if not pending:
            await query.answer("Не выбраны товары", show_alert=True)
            return
        by_user_a: dict[int, list] = {}
        for item in pending:
            by_user_a.setdefault(item["user_id"], []).append(item)
        for uid, user_items in by_user_a.items():
            names_text = "\n".join(
                f"• {_safe_md(short_names.get(i['calc_id'], (i.get('name') or 'Товар')[:35]))}"
                for i in user_items
            )
            try:
                await ctx.bot.send_message(
                    uid,
                    f"📦 *Ваши товары прибыли!*\n\n{names_text}\n\n"
                    f"Свяжитесь с администратором для согласования способов получения.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=_contact_kb(),
                )
            except Exception as e:
                log.warning(f"Не удалось уведомить пользователя {uid}: {e}")
        arrived_ids = [i["calc_id"] for i in pending]
        await db.cart_set_arrived(arrived_ids)
        ctx.bot_data.pop("admin_notify_mode", None)
        ctx.bot_data.pop("admin_notify_arrival_pending", None)
        selected_text = _notify_selected_text(pending, short_names)
        text = (
            "📦 *Уведомить о прибытии*\n\n"
            "Товары:\n" + selected_text + "\n\n"
            "✅ Уведомления о прибытии отправлены."
        )
        await query.message.edit_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_notify_arrival(sent=True, has_items=True),
            disable_web_page_preview=True,
        )
        return

    # ── Noop (визуальная кнопка «Отправлено») ─────────────────────────────────
    if data == "aord:noop":
        await query.answer("Уже отправлено")
        return

    # ── Список товаров ─────────────────────────────────────────────────────────
    if data == "aord:items_menu":
        await _render_items_menu(query.message, ctx, edit=True)
        return

    # ── Карточка конкретного товара ────────────────────────────────────────────
    if data.startswith("aord:view_item:"):
        parts = data.split(":")
        target_uid, calc_id = int(parts[2]), int(parts[3])
        ok = await _send_admin_item_card(
            ctx.bot, query.message.chat_id, query.message, target_uid, calc_id,
        )
        if not ok:
            await query.answer("Товар не найден", show_alert=True)
        return

    # ── Характеристики товара ──────────────────────────────────────────────────
    if data.startswith("aord:item_specs:"):
        import json
        from models import CalculationResult
        from services import exchange_rate as _er
        parts = data.split(":")
        target_uid, calc_id = int(parts[2]), int(parts[3])

        row = await db.get_calculation_admin(calc_id)
        if not row:
            await query.answer("Товар не найден", show_alert=True)
            return

        rate = await _er.get_rate()
        try:
            result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
        except Exception:
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

        back_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data=f"aord:item_specs_back:{target_uid}:{calc_id}"),
        ]])
        msg_ids = []
        photos = draft.extra_images if draft.extra_images else []
        if photos:
            from telegram import InputMediaPhoto
            try:
                media = [InputMediaPhoto(media=url) for url in photos[:10]]
                photo_msgs = await query.message.reply_media_group(media=media)
                msg_ids.extend(m.message_id for m in photo_msgs)
            except Exception as e:
                log.warning(f"admin specs photos send failed: {e}")
        text_msg = await query.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb,
        )
        msg_ids.append(text_msg.message_id)
        ctx.user_data["aord_specs_msg_ids"] = msg_ids
        return

    # ── Назад из характеристик ─────────────────────────────────────────────────
    if data.startswith("aord:item_specs_back:"):
        msg_ids = ctx.user_data.pop("aord_specs_msg_ids", [])
        for mid in msg_ids:
            try:
                await ctx.bot.delete_message(query.message.chat_id, mid)
            except Exception:
                pass
        if not msg_ids:
            try:
                await query.message.delete()
            except Exception:
                pass
        return


async def handle_admin_notify_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Перехватывает текстовый ввод от администратора в режиме выбора товаров."""
    from telegram.ext import ApplicationHandlerStop
    import re as _re

    mode = ctx.bot_data.get("admin_notify_mode")
    if not mode:
        return  # не в режиме ввода — пропускаем, ConversationHandler обработает

    text = (update.message.text or "").strip()
    raw_nums = _re.split(r"[,\s;]+", text)
    try:
        nums = {int(x) for x in raw_nums if x.isdigit()}
    except Exception:
        raise ApplicationHandlerStop()

    if not nums:
        raise ApplicationHandlerStop()

    items = ctx.bot_data.get("admin_notify_items_snapshot") or []
    short_names = ctx.bot_data.get("admin_notify_short_names") or {}
    selected = [items[i - 1] for i in sorted(nums) if 1 <= i <= len(items)]

    if not selected:
        raise ApplicationHandlerStop()

    if mode == "ship":
        ctx.bot_data["admin_notify_ship_pending"] = selected
        selected_text = _notify_selected_text(selected, short_names)
        confirm_text = (
            "🚚 *Уведомить об отправке*\n\n"
            "Выбранные товары:\n" + selected_text + "\n\n"
            "Нажмите «Отправить уведомление» для подтверждения."
        )
        await update.message.reply_text(
            confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_notify_ship_confirm(sent=False),
            disable_web_page_preview=True,
        )

    elif mode == "arrival_add":
        existing = ctx.bot_data.get("admin_notify_arrival_pending") or []
        existing_ids = {i["calc_id"] for i in existing}
        for item in selected:
            if item["calc_id"] not in existing_ids:
                existing.append(item)
                existing_ids.add(item["calc_id"])
        ctx.bot_data["admin_notify_arrival_pending"] = existing

        chat_id = ctx.bot_data.get("admin_notify_arrival_chat_id")
        msg_id = ctx.bot_data.get("admin_notify_arrival_msg_id")
        selected_text = _notify_selected_text(existing, short_names)
        arrival_text = (
            "📦 *Уведомить о прибытии*\n\n"
            "Товары, которые получат уведомление о прибытии:\n"
            + selected_text + "\n\n"
            "Пользователи получат уведомление о прибытии товаров."
        )
        try:
            await ctx.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=arrival_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_kb_notify_arrival(has_items=True),
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning(f"Не удалось обновить сообщение прибытия: {e}")

    raise ApplicationHandlerStop()


# ─── Просмотр товаров в заявках (aord:items_menu / aord:view_item) ────────────

def _fmt_result_admin(result) -> str:
    """fmt_result без раздела доставки, курса и предупреждений."""
    from utils.formatters import fmt_result
    text = fmt_result(result, "client")
    for marker in ["🚚 Время доставки", "🚚 Доставка до", "📍 Город получения", "💱 Курс:"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].rstrip()
            break
    return text


def _items_list_text(seen_users: list, by_user: dict, short_names: dict) -> str:
    """Текст списка товаров в заявках, сгруппированный по пользователю."""
    if not seen_users:
        return "📦 *Нет товаров в заявках*"
    lines = ["📦 *Товары в заявках*", ""]
    counter = 1
    for uid in seen_users:
        user_items = by_user[uid]
        username = user_items[0].get("username") or str(uid)
        lines.append(f"👤 @{username}:")
        for item in user_items:
            cid = item["calc_id"]
            name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:35]))
            lines.append(f"{counter}. {name}")
            counter += 1
        lines.append("")
    return "\n".join(lines).strip()


def _kb_items_list(items: list) -> InlineKeyboardMarkup:
    """Кнопки-цифры для всех товаров (5 в ряд) + Назад."""
    rows = []
    btn_row = []
    for i, item in enumerate(items, 1):
        uid = item["user_id"]
        cid = item["calc_id"]
        btn_row.append(InlineKeyboardButton(
            str(i), callback_data=f"aord:view_item:{uid}:{cid}",
        ))
        if len(btn_row) == 5:
            rows.append(btn_row)
            btn_row = []
    if btn_row:
        rows.append(btn_row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="aord:show")])
    return InlineKeyboardMarkup(rows)


def _kb_admin_item(uid: int, calc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Характеристики товара", callback_data=f"aord:item_specs:{uid}:{calc_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="aord:items_menu")],
    ])


async def _render_items_menu(message, ctx: ContextTypes.DEFAULT_TYPE, edit: bool = True):
    items = await db.cart_get_all_orders()
    short_names = await _get_short_names(items, ctx)

    seen_users: list[int] = []
    by_user: dict[int, list] = {}
    for item in items:
        uid = item["user_id"]
        if uid not in by_user:
            seen_users.append(uid)
            by_user[uid] = []
        by_user[uid].append(item)

    text = _items_list_text(seen_users, by_user, short_names)
    kb = _kb_items_list(items)
    kwargs = dict(text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    if edit:
        try:
            await message.edit_text(**kwargs)
        except Exception:
            # Сообщение может быть фото (caption) — шлём новым сообщением, карточку не трогаем
            await ctx.bot.send_message(chat_id=message.chat_id, **kwargs)
    else:
        await message.reply_text(**kwargs)


async def _send_admin_item_card(bot, chat_id: int, message, uid: int, calc_id: int):
    """Удалить текущее сообщение и показать карточку товара с фото (или без)."""
    import json
    from models import CalculationResult
    from services import exchange_rate as _er

    row = await db.get_calculation_admin(calc_id)
    if not row:
        return False

    rate = await _er.get_rate()
    try:
        result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
    except Exception:
        return False

    text = _fmt_result_admin(result)
    kb = _kb_admin_item(uid, calc_id)
    image_url = result.product.image_url

    if image_url:
        try:
            await message.delete()
            await bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
            return True
        except Exception as e:
            log.warning(f"admin view_item send_photo failed: {e}")

    try:
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                 reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=kb, disable_web_page_preview=True)
    return True


def build_admin_orders_handlers():
    return [
        CallbackQueryHandler(handle_admin_orders_callback, pattern=r"^aord:"),
    ]


# ─── Просмотр корзин пользователей (acart:) ───────────────────────────────────

async def _get_cart_short_names(items: list[dict], ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    """Короткие Groq-названия для корзин. Кешируются в bot_data."""
    cache = ctx.bot_data.setdefault("admin_cart_short_names", {})
    new_ids, new_coros = [], []
    for item in items:
        cid = item["calc_id"]
        if cid not in cache:
            new_ids.append(cid)
            new_coros.append(extract_search_query(item.get("name") or "Товар"))
    if new_coros:
        results = await asyncio.gather(*new_coros, return_exceptions=True)
        items_map = {item["calc_id"]: item for item in items}
        for cid, res in zip(new_ids, results):
            if isinstance(res, Exception) or not res:
                cache[cid] = (items_map[cid].get("name") or "Товар")[:30]
            else:
                cache[cid] = str(res)[:35]
    return cache


def _fmt_rub(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(float(v)):,}".replace(",", "\u00a0") + "\u00a0₽"
    except Exception:
        return "—"


def _fmt_cny(v) -> str:
    if v is None:
        return "—"
    try:
        return f"¥{int(float(v))}"
    except Exception:
        return "—"


def _plural_goods(n: int) -> str:
    last = n % 10
    last100 = n % 100
    if 11 <= last100 <= 19:
        return f"{n} товаров"
    if last == 1:
        return f"{n} товар"
    if 2 <= last <= 4:
        return f"{n} товара"
    return f"{n} товаров"


def _carts_users_text(seen_users: list, by_user: dict) -> str:
    if not seen_users:
        return "🛒 *Корзины пусты*\n\nНи у одного пользователя нет товаров в корзине."
    lines = ["🛒 *Корзины пользователей*", ""]
    for i, uid in enumerate(seen_users, 1):
        items = by_user[uid]
        username = (items[0].get("username") or str(uid)).replace("_", "\\_")
        lines.append(f"{i}. @{username} ({_plural_goods(len(items))})")
    return "\n".join(lines)


def _cart_user_items_text(username: str, user_items: list, short_names: dict) -> str:
    lines = [f"🛒 *Корзина @{username}*", ""]
    for i, item in enumerate(user_items, 1):
        cid = item["calc_id"]
        name = _safe_md(short_names.get(cid, (item.get("name") or "Товар")[:35]))
        url = item.get("product_url") or ""
        price_cny = item.get("price_cny")
        subtotal_rub = item.get("subtotal_rub")
        total_rub = item.get("total_with_margin_rub")
        in_order = item.get("in_order")

        order_label = " _(в заявке)_" if in_order else ""
        name_part = f"[{name}]({url})" if url else name

        lines.append(f"{i}. {name_part}{order_label}")
        lines.append(f"   Цена товара — {_fmt_rub(subtotal_rub)} ({_fmt_cny(price_cny)})")
        lines.append(f"   Итоговая цена — {_fmt_rub(total_rub)}")
        lines.append("")
    return "\n".join(lines).strip()


def _kb_cart_users(seen_users: list) -> InlineKeyboardMarkup:
    rows = []
    btn_row = []
    for i, uid in enumerate(seen_users, 1):
        btn_row.append(InlineKeyboardButton(str(i), callback_data=f"acart:user:{uid}"))
        if len(btn_row) == 5:
            rows.append(btn_row)
            btn_row = []
    if btn_row:
        rows.append(btn_row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="acart:main")])
    return InlineKeyboardMarkup(rows)


def _kb_cart_user_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data="acart:open"),
    ]])


async def _render_carts(message, edit: bool = True):
    all_items = await db.cart_get_all_carts()
    seen_users: list[int] = []
    by_user: dict[int, list] = {}
    for item in all_items:
        uid = item["user_id"]
        if uid not in by_user:
            seen_users.append(uid)
            by_user[uid] = []
        by_user[uid].append(item)
    text = _carts_users_text(seen_users, by_user)
    kb = _kb_cart_users(seen_users)
    kwargs = dict(
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    if edit:
        try:
            await message.edit_text(**kwargs)
        except Exception:
            await message.reply_text(**kwargs)
    else:
        await message.reply_text(**kwargs)


async def handle_admin_carts_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if not ADMIN_USER_ID or user_id != ADMIN_USER_ID:
        return

    # ── Открыть список корзин (из стартового фото-меню) ──────────────────────
    if data == "acart:open":
        all_items = await db.cart_get_all_carts()
        seen_users: list[int] = []
        by_user: dict[int, list] = {}
        for item in all_items:
            uid = item["user_id"]
            if uid not in by_user:
                seen_users.append(uid)
                by_user[uid] = []
            by_user[uid].append(item)
        text = _carts_users_text(seen_users, by_user)
        kb = _kb_cart_users(seen_users)
        try:
            await ctx.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        except Exception:
            await ctx.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=kb,
            )
        return

    # ── Обновить список корзин (внутри экрана корзин) ─────────────────────────
    if data == "acart:show":
        await _render_carts(query.message, edit=True)
        return

    # ── Назад к стартовому меню ────────────────────────────────────────────────
    if data == "acart:main":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Корзина конкретного пользователя ───────────────────────────────────────
    if data.startswith("acart:user:"):
        target_uid = int(data.split(":")[-1])
        all_items = await db.cart_get_all_carts()
        user_items = [i for i in all_items if i["user_id"] == target_uid]
        if not user_items:
            await query.answer("У пользователя нет товаров в корзине", show_alert=True)
            return
        username = user_items[0].get("username") or str(target_uid)
        short_names = await _get_cart_short_names(user_items, ctx)
        text = _cart_user_items_text(username, user_items, short_names)
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_kb_cart_user_back(),
            disable_web_page_preview=True,
        )
        return


def build_admin_carts_handlers():
    return [
        CallbackQueryHandler(handle_admin_carts_callback, pattern=r"^acart:"),
    ]
