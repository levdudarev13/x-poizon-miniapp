"""Сообщения пользователей администратору."""
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode

import database as db
from config import ADMIN_USER_IDS

log = logging.getLogger(__name__)

AWAIT_USER_MSG = 0
PAGE_SIZE = 10

_TYPE_LABEL = {
    "contact":      "Просто сообщение",
    "problem":      "Сообщение о проблеме",
    "calc_request": "Заявка на расчёт товара",
}


async def _send_new_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отправить новое стартовое сообщение пользователю."""
    from handlers.commands import send_start_photo
    user = update.effective_user
    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


# ─── Пользовательский поток ────────────────────────────────────────────────────

async def handle_msg_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data["msg_type"] = "contact"
    ctx.user_data["_in_msg_flow"] = True
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="msg:back")]])
    await query.message.reply_text(
        "✉️ *Напишите ваше сообщение*\n\n"
        "Введите текст — он автоматически отправится администратору. "
        "Он свяжется с вами при необходимости.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )
    return AWAIT_USER_MSG


async def handle_msg_problem(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data["msg_type"] = "problem"
    ctx.user_data["_in_msg_flow"] = True
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="msg:back")]])
    await query.message.reply_text(
        "🚨 *Сообщить о проблеме*\n\n"
        "Опишите возникшую проблему — сообщение автоматически отправится администратору. "
        "Он свяжется с вами при необходимости.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )
    return AWAIT_USER_MSG


async def handle_calc_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data["msg_type"] = "calc_request"
    ctx.user_data["_in_msg_flow"] = True
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="msg:back")]])
    await query.message.reply_text(
        "🔢 *Расчёт товара с 1688 / Taobao*\n\n"
        "К сожалению, мы пока не можем рассчитывать товары с этих платформ автоматически.\n\n"
        "Но вы можете отправить заявку администратору — напишите сообщение с ссылкой на товар, "
        "и он свяжется с вами в ближайшее время.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )
    return AWAIT_USER_MSG


async def handle_msg_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data.pop("_in_msg_flow", None)
    ctx.user_data.pop("msg_type", None)
    await _send_new_start(update, ctx)
    return ConversationHandler.END


async def handle_msg_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        return AWAIT_USER_MSG

    user = update.effective_user
    msg_type = ctx.user_data.pop("msg_type", "contact")
    ctx.user_data.pop("_in_msg_flow", None)

    await db.msg_save(user.id, user.username or "", msg_type, text)

    if ADMIN_USER_IDS:
        uname_display = f"@{user.username}" if user.username else f"{user.first_name} (id: {user.id})"
        type_label = _TYPE_LABEL.get(msg_type, "Message")
        notify_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open messages", callback_data="msg:admin_list:0")],
        ])
        preview = text[:300] + ("..." if len(text) > 300 else "")
        notify_text = (
            f"New user message\n\n"
            f"From: {uname_display}\n"
            f"Type: {type_label}\n\n"
            f"{preview}"
        )
        for admin_user_id in ADMIN_USER_IDS:
            try:
                await ctx.bot.send_message(
                    chat_id=admin_user_id,
                    text=notify_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=notify_kb,
                )
            except Exception as e:
                log.warning("Failed to notify admin %s about message: %s", admin_user_id, e)

    if msg_type == "problem":
        reply_text = "✅ Ваше сообщение отправлено — проблема решится в ближайшее время."
        btn_text = "🏠 Перейти в меню"
    elif msg_type == "calc_request":
        reply_text = "✅ Ваша заявка на расчёт товара отправлена администратору — ожидайте."
        btn_text = "◀️ Назад"
    else:
        reply_text = "✅ Ваше сообщение отправлено, ожидайте ответа от администратора."
        btn_text = "🏠 Перейти в меню"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text, callback_data="msg:to_menu")],
    ])
    await update.message.reply_text(reply_text, reply_markup=kb)
    return ConversationHandler.END


async def handle_msg_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_new_start(update, ctx)


# ─── Админ: список сообщений ───────────────────────────────────────────────────

def _fmt_dt(dt_str: str) -> str:
    if not dt_str:
        return "—"
    try:
        dt = datetime.strptime(dt_str[:16], "%Y-%m-%d %H:%M")
        return dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        return dt_str


async def handle_admin_msgs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    msgs = await db.msg_get_all()
    total = len(msgs)

    if total == 0:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="msg:admin_back")],
        ])
        try:
            await query.message.edit_text(
                "📨 *Сообщения*\n\nСообщений пока нет.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
        except Exception:
            await ctx.bot.send_message(
                chat_id=query.message.chat_id,
                text="📨 *Сообщения*\n\nСообщений пока нет.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
        return

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    page_msgs = msgs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [f"📨 *Сообщения* (стр. {page + 1}/{total_pages}):\n"]
    for m in page_msgs:
        uname = f"@{m['username']}" if m.get("username") else f"id:{m['user_id']}"
        type_label = _TYPE_LABEL.get(m["msg_type"], m["msg_type"])
        sent = _fmt_dt(m["sent_at"])
        # Экранируем Markdown v1 в тексте сообщения
        safe_text = (
            m["text"]
            .replace("_", "\\_")
            .replace("*", "\\*")
            .replace("`", "\\`")
            .replace("[", "\\[")
        )
        lines.append(f"{uname} — {type_label} — {sent}\n_\"{safe_text}\"_\n")

    body = "\n".join(lines)
    if len(body) > 3800:
        body = body[:3800] + "\n…"

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"msg:admin_list:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"msg:admin_list:{page + 1}"))

    rows = []
    if nav_row:
        rows.append(nav_row)
    rows.append([
        InlineKeyboardButton("◀️ Назад",      callback_data="msg:admin_back"),
        InlineKeyboardButton("🗑 Удалить все", callback_data="msg:admin_delete_confirm"),
    ])

    kb = InlineKeyboardMarkup(rows)
    try:
        await query.message.edit_text(
            body,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )
    except Exception:
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=body,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb,
        )


async def handle_admin_msgs_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass


async def handle_admin_delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить все", callback_data="msg:admin_delete_do"),
            InlineKeyboardButton("❌ Отмена",          callback_data="msg:admin_list:0"),
        ],
    ])
    await query.message.edit_text(
        "⚠️ *Удалить все сообщения?*\n\nЭто действие нельзя отменить.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def handle_admin_delete_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await db.msg_delete_all()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="msg:admin_back")],
    ])
    await query.message.edit_text(
        "✅ Все сообщения удалены.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


# ─── Регистрация ───────────────────────────────────────────────────────────────

def build_messages_conv_handler() -> ConversationHandler:
    """ConversationHandler для потока ввода сообщения пользователем."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_msg_contact,     pattern="^msg:contact$"),
            CallbackQueryHandler(handle_msg_problem,     pattern="^msg:problem$"),
            CallbackQueryHandler(handle_calc_request,    pattern="^msg:calc_request$"),
        ],
        per_message=False,
        allow_reentry=True,
        states={
            AWAIT_USER_MSG: [
                CallbackQueryHandler(handle_msg_back, pattern="^msg:back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handle_msg_back, pattern="^msg:back$"),
        ],
        name="msg_conv",
        persistent=False,
    )


def build_messages_handlers() -> list:
    """Независимые callback-хендлеры (просмотр сообщений у админа + кнопка 'В меню')."""
    return [
        CallbackQueryHandler(handle_admin_msgs,           pattern=r"^msg:admin_list:\d+$"),
        CallbackQueryHandler(handle_admin_msgs_back,      pattern="^msg:admin_back$"),
        CallbackQueryHandler(handle_admin_delete_confirm, pattern="^msg:admin_delete_confirm$"),
        CallbackQueryHandler(handle_admin_delete_do,      pattern="^msg:admin_delete_do$"),
        CallbackQueryHandler(handle_msg_to_menu,          pattern="^msg:to_menu$"),
    ]
