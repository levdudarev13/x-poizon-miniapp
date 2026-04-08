"""Сообщения пользователей администратору."""

import asyncio
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db
from config import ADMIN_USER_IDS

log = logging.getLogger(__name__)

AWAIT_USER_MSG = 0
PAGE_SIZE = 10

_TYPE_LABEL = {
    "contact": "Диалог с оператором",
    "problem": "Сообщение о проблеме",
    "calc_request": "Заявка на расчёт товара",
    "operator_request": "Запрос связи с оператором",
}


def _is_admin(user_id: int) -> bool:
    return int(user_id or 0) in ADMIN_USER_IDS


def _user_label(user) -> str:
    if getattr(user, "username", None):
        return f"@{user.username}"
    full_name = " ".join(
        part for part in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if part
    ).strip()
    return full_name or f"id:{user.id}"


def _admin_reply_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ответить пользователю", callback_data=f"msg:admin_reply:{user_id}")],
        [InlineKeyboardButton("Открыть сообщения", callback_data="msg:admin_list:0")],
    ])


def _user_chat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Завершить диалог", callback_data="msg:chat_close")],
    ])


def _admin_chat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Завершить диалог", callback_data="msg:admin_reply_cancel")],
    ])


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("В меню", callback_data="msg:to_menu")],
    ])


def _relay_store(ctx: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    return ctx.bot_data.setdefault("operator_relay_targets", {})


def _relay_key(chat_id: int, message_id: int) -> str:
    return f"{int(chat_id)}:{int(message_id)}"


def _remember_relay_target(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, user_id: int) -> None:
    _relay_store(ctx)[_relay_key(chat_id, message_id)] = int(user_id)


def _resolve_relay_target(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> int:
    return int(_relay_store(ctx).get(_relay_key(chat_id, message_id), 0) or 0)


def _forget_relay_targets_for_user(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    store = _relay_store(ctx)
    for key, value in list(store.items()):
        if int(value or 0) == int(user_id):
            store.pop(key, None)


def _clear_dialog_state(user_data) -> None:
    if not user_data:
        return
    user_data.pop("_in_msg_flow", None)
    user_data.pop("msg_type", None)
    user_data.pop("operator_chat_active", None)
    user_data.pop("operator_chat_first_message_pending", None)
    user_data.pop("operator_chat_closed_by_peer", None)


def _clear_admin_reply_modes(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> list[int]:
    cleared_admin_ids: list[int] = []
    for admin_user_id in ADMIN_USER_IDS:
        admin_state = ctx.application.user_data.get(int(admin_user_id))
        if not admin_state:
            continue
        if int(admin_state.get("operator_reply_user_id", 0) or 0) != int(user_id):
            continue
        admin_state.pop("operator_reply_user_id", None)
        cleared_admin_ids.append(int(admin_user_id))
    return cleared_admin_ids


def _is_user_dialog_active(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    user_state = ctx.application.user_data.get(int(user_id), {})
    return bool(user_state.get("operator_chat_active"))


async def _close_dialog_everywhere(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    *,
    closed_by: str,
) -> list[int]:
    user_state = ctx.application.user_data.get(int(user_id))
    _clear_dialog_state(user_state)
    if closed_by == "admin" and user_state is not None:
        user_state["operator_chat_closed_by_peer"] = True

    cleared_admin_ids = _clear_admin_reply_modes(ctx, user_id)
    _forget_relay_targets_for_user(ctx, user_id)
    return cleared_admin_ids


async def _safe_answer_callback(query, *args, **kwargs) -> None:
    try:
        await query.answer(*args, **kwargs)
    except Exception as exc:
        log.warning("Callback answer failed for %s: %s", getattr(query, "data", ""), exc)


async def _send_message_with_retry(bot, *, chat_id: int, text: str, reply_markup=None, parse_mode=None, retries: int = 3):
    last_error = None
    for attempt in range(retries):
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1.2 * (attempt + 1))
    raise last_error


async def _forward_message_with_retry(bot, *, chat_id: int, from_chat_id: int, message_id: int, retries: int = 3):
    last_error = None
    for attempt in range(retries):
        try:
            return await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
        except Exception as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1.2 * (attempt + 1))
    raise last_error


async def _send_new_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отправить новое стартовое сообщение пользователю."""
    from handlers.commands import send_start_photo

    user = update.effective_user
    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


async def _notify_admins_about_operator_request(ctx: ContextTypes.DEFAULT_TYPE, user) -> None:
    if not ADMIN_USER_IDS:
        return

    notify_text = (
        "Пользователь открыл диалог с оператором.\n\n"
        f"Пользователь: {_user_label(user)}\n"
        f"ID: {user.id}\n\n"
        "Нажмите кнопку ниже, чтобы ответить в этом же боте."
    )
    reply_markup = _admin_reply_kb(user.id)

    for admin_user_id in ADMIN_USER_IDS:
        try:
            sent = await _send_message_with_retry(
                ctx.bot,
                chat_id=admin_user_id,
                text=notify_text,
                reply_markup=reply_markup,
            )
            _remember_relay_target(ctx, admin_user_id, sent.message_id, user.id)
        except Exception as exc:
            log.warning("Failed to notify admin %s about operator request: %s", admin_user_id, exc)


async def _notify_admins_about_user_message(
    ctx: ContextTypes.DEFAULT_TYPE,
    user,
    msg_type: str,
    text: str,
    *,
    source_message=None,
) -> None:
    if not ADMIN_USER_IDS:
        return

    preview = text[:800] + ("..." if len(text) > 800 else "")
    notify_text = (
        f"Сообщение от пользователя {_user_label(user)}\n"
        f"ID: {user.id}\n"
        f"Тип: {_TYPE_LABEL.get(msg_type, msg_type)}\n\n"
        f"{preview}"
    )
    if msg_type == "contact" and source_message is None:
        notify_text = (
            "Пользователь начал диалог с оператором.\n\n"
            f"Пользователь: {_user_label(user)}\n"
            f"ID: {user.id}\n\n"
            f"Сообщение:\n{preview}"
        )
    reply_markup = _admin_reply_kb(user.id)

    for admin_user_id in ADMIN_USER_IDS:
        try:
            if msg_type == "contact" and source_message is not None:
                try:
                    sent = await _forward_message_with_retry(
                        ctx.bot,
                        chat_id=admin_user_id,
                        from_chat_id=source_message.chat_id,
                        message_id=source_message.message_id,
                    )
                except Exception:
                    sent = await _send_message_with_retry(
                        ctx.bot,
                        chat_id=admin_user_id,
                        text=text,
                    )
            else:
                sent = await _send_message_with_retry(
                    ctx.bot,
                    chat_id=admin_user_id,
                    text=notify_text,
                    reply_markup=reply_markup,
                )
            _remember_relay_target(ctx, admin_user_id, sent.message_id, user.id)
        except Exception as exc:
            log.warning("Failed to notify admin %s about user message: %s", admin_user_id, exc)


# --- Пользовательский поток -------------------------------------------------

async def handle_msg_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await _safe_answer_callback(query)

    user = update.effective_user
    await db.msg_save(user.id, user.username or "", "operator_request", "Пользователь открыл диалог с оператором.")
    ctx.user_data.pop("operator_chat_closed_by_peer", None)
    ctx.user_data["msg_type"] = "contact"
    ctx.user_data["operator_chat_active"] = True
    ctx.user_data["operator_chat_first_message_pending"] = True
    ctx.user_data["_in_msg_flow"] = True

    await query.message.reply_text(
        "Диалог с оператором открыт.\n\n"
        "Пишите сюда сообщения, и оператор будет отвечать вам прямо в этом боте.",
        reply_markup=_user_chat_kb(),
    )
    return AWAIT_USER_MSG


async def handle_msg_problem(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await _safe_answer_callback(query)
    ctx.user_data["msg_type"] = "problem"
    ctx.user_data["_in_msg_flow"] = True
    await query.message.reply_text(
        "Опишите проблему одним сообщением, и я передам её администратору.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="msg:back")]]),
    )
    return AWAIT_USER_MSG


async def handle_calc_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await _safe_answer_callback(query)
    ctx.user_data["msg_type"] = "calc_request"
    ctx.user_data["_in_msg_flow"] = True
    await query.message.reply_text(
        "Отправьте одним сообщением ссылку на товар, и администратор свяжется с вами для ручного расчёта.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="msg:back")]]),
    )
    return AWAIT_USER_MSG


async def handle_msg_chat_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await _safe_answer_callback(query, "Диалог завершён")
    user = update.effective_user
    cleared_admin_ids = await _close_dialog_everywhere(ctx, user.id, closed_by="user")

    for admin_user_id in cleared_admin_ids:
        try:
            await _send_message_with_retry(
                ctx.bot,
                chat_id=admin_user_id,
                text=(
                    f"Пользователь {_user_label(user)}\n"
                    f"ID: {user.id}\n\n"
                    "Завершил диалог."
                ),
            )
        except Exception as exc:
            log.warning("Failed to notify admin %s about closed dialog: %s", admin_user_id, exc)
    try:
        await query.message.edit_text(
            "Диалог с оператором завершён.",
            reply_markup=_menu_kb(),
        )
    except Exception:
        await query.message.reply_text(
            "Диалог с оператором завершён.",
            reply_markup=_menu_kb(),
        )
    return ConversationHandler.END


async def handle_msg_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await _safe_answer_callback(query)
    _clear_dialog_state(ctx.user_data)
    await _send_new_start(update, ctx)
    return ConversationHandler.END


async def handle_msg_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if ctx.user_data.pop("operator_chat_closed_by_peer", False):
        await update.message.reply_text(
            "Диалог с оператором уже завершён.",
            reply_markup=_menu_kb(),
        )
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        return AWAIT_USER_MSG

    user = update.effective_user
    msg_type = ctx.user_data.get("msg_type", "contact")

    if ctx.user_data.get("operator_chat_active"):
        await db.msg_save(user.id, user.username or "", "contact", text)
        first_message_pending = bool(ctx.user_data.pop("operator_chat_first_message_pending", False))
        await _notify_admins_about_user_message(
            ctx,
            user,
            "contact",
            text,
            source_message=None if first_message_pending else update.message,
        )
        return AWAIT_USER_MSG

    ctx.user_data.pop("msg_type", None)
    ctx.user_data.pop("_in_msg_flow", None)

    await db.msg_save(user.id, user.username or "", msg_type, text)
    await _notify_admins_about_user_message(ctx, user, msg_type, text, source_message=update.message)

    if msg_type == "problem":
        reply_text = "Сообщение о проблеме отправлено. Мы проверим и вернёмся с ответом."
    elif msg_type == "calc_request":
        reply_text = "Заявка на ручной расчёт отправлена администратору. Ожидайте ответ."
    else:
        reply_text = "Сообщение отправлено оператору."

    await update.message.reply_text(
        reply_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("В меню", callback_data="msg:to_menu")]]),
    )
    return ConversationHandler.END


async def handle_msg_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer_callback(query)
    _clear_dialog_state(ctx.user_data)
    await _send_new_start(update, ctx)


# --- Админ: диалог с пользователем -----------------------------------------

async def handle_admin_reply_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer_callback(query, "Режим ответа включён")

    if not _is_admin(query.from_user.id):
        return

    try:
        target_user_id = int(query.data.rsplit(":", 1)[-1])
    except Exception:
        await _safe_answer_callback(query, "Некорректный пользователь", show_alert=True)
        return

    if not _is_user_dialog_active(ctx, target_user_id):
        await _safe_answer_callback(query, "Диалог уже закрыт", show_alert=True)
        try:
            await query.message.edit_text("Этот диалог уже завершён.")
        except Exception:
            await query.message.reply_text("Этот диалог уже завершён.")
        return

    ctx.user_data["operator_reply_user_id"] = target_user_id
    try:
        await query.message.edit_text(
            f"Режим ответа пользователю `{target_user_id}` включён.\n\n"
            "Все ваши следующие текстовые сообщения будут отправляться ему, пока вы не нажмёте `Завершить диалог`.\n"
            "Также можно отвечать реплаем на сообщения пользователя в этом чате.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_admin_chat_kb(),
        )
    except Exception:
        await query.message.reply_text(
            f"Режим ответа пользователю `{target_user_id}` включён.\n\n"
            "Все ваши следующие текстовые сообщения будут отправляться ему, пока вы не нажмёте `Завершить диалог`.\n"
            "Также можно отвечать реплаем на сообщения пользователя в этом чате.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_admin_chat_kb(),
        )


async def handle_admin_reply_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer_callback(query, "Диалог завершён")
    target_user_id = int(ctx.user_data.get("operator_reply_user_id", 0) or 0)
    if target_user_id > 0:
        await _close_dialog_everywhere(ctx, target_user_id, closed_by="admin")
        try:
            await _send_message_with_retry(
                ctx.bot,
                chat_id=target_user_id,
                text="Диалог с оператором завершён.",
                reply_markup=_menu_kb(),
            )
        except Exception as exc:
            log.warning("Failed to notify user %s about closed dialog: %s", target_user_id, exc)
    else:
        ctx.user_data.pop("operator_reply_user_id", None)
    try:
        await query.message.edit_text("Режим ответа пользователю выключен.")
    except Exception:
        await query.message.reply_text("Режим ответа пользователю выключен.")


async def handle_admin_text_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from handlers.admin_dashboard import maybe_handle_admin_broadcast_message

    if await maybe_handle_admin_broadcast_message(update, ctx):
        raise ApplicationHandlerStop()

    reply_to = getattr(update.message, "reply_to_message", None)
    if reply_to is not None:
        target_user_id = _resolve_relay_target(ctx, update.effective_chat.id, reply_to.message_id)
        if target_user_id > 0:
            text = (update.message.text or "").strip()
            if not text:
                raise ApplicationHandlerStop()

            try:
                await ctx.bot.send_message(
                    chat_id=target_user_id,
                    text=text,
                    reply_markup=_user_chat_kb(),
                )
            except Exception as exc:
                log.warning("Failed to relay admin reply to %s: %s", target_user_id, exc)
                await update.message.reply_text(
                    "Не удалось отправить сообщение пользователю. Возможно, он не запускал бота или заблокировал его."
                )
            raise ApplicationHandlerStop()

    target_user_id = int(ctx.user_data.get("operator_reply_user_id", 0) or 0)
    if target_user_id > 0:
        text = (update.message.text or "").strip()
        if not text:
            raise ApplicationHandlerStop()

        try:
            await ctx.bot.send_message(
                chat_id=target_user_id,
                text=text,
                reply_markup=_user_chat_kb(),
            )
        except Exception as exc:
            log.warning("Failed to send operator reply to %s: %s", target_user_id, exc)
            await update.message.reply_text(
                "Не удалось отправить сообщение пользователю. Возможно, он не запускал бота или заблокировал его."
            )
        raise ApplicationHandlerStop()

    from handlers.admin_orders import handle_admin_notify_text

    await handle_admin_notify_text(update, ctx)


# --- Админ: список сообщений ------------------------------------------------

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
    await _safe_answer_callback(query)

    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    msgs = await db.msg_get_all()
    total = len(msgs)

    if total == 0:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="msg:admin_back")],
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
    for item in page_msgs:
        uname = f"@{item['username']}" if item.get("username") else f"id:{item['user_id']}"
        type_label = _TYPE_LABEL.get(item["msg_type"], item["msg_type"])
        sent = _fmt_dt(item["sent_at"])
        safe_text = (
            item["text"]
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
        InlineKeyboardButton("Назад", callback_data="msg:admin_back"),
        InlineKeyboardButton("Удалить все", callback_data="msg:admin_delete_confirm"),
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
    await _safe_answer_callback(query)
    try:
        await query.message.delete()
    except Exception:
        pass


async def handle_admin_delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer_callback(query)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да, удалить все", callback_data="msg:admin_delete_do"),
            InlineKeyboardButton("Отмена", callback_data="msg:admin_list:0"),
        ],
    ])
    await query.message.edit_text(
        "⚠️ *Удалить все сообщения?*\n\nЭто действие нельзя отменить.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def handle_admin_delete_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer_callback(query)
    await db.msg_delete_all()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад", callback_data="msg:admin_back")],
    ])
    await query.message.edit_text(
        "Все сообщения удалены.",
        reply_markup=kb,
    )


# --- Регистрация ------------------------------------------------------------

def build_messages_conv_handler() -> ConversationHandler:
    """ConversationHandler для потока ввода сообщения пользователем."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_msg_contact, pattern="^msg:contact$"),
            CallbackQueryHandler(handle_msg_problem, pattern="^msg:problem$"),
            CallbackQueryHandler(handle_calc_request, pattern="^msg:calc_request$"),
        ],
        per_message=False,
        allow_reentry=True,
        states={
            AWAIT_USER_MSG: [
                CallbackQueryHandler(handle_msg_chat_close, pattern="^msg:chat_close$"),
                CallbackQueryHandler(handle_msg_back, pattern="^msg:back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handle_msg_chat_close, pattern="^msg:chat_close$"),
            CallbackQueryHandler(handle_msg_back, pattern="^msg:back$"),
        ],
        name="msg_conv",
        persistent=False,
    )


def build_messages_handlers() -> list:
    """Независимые callback-хендлеры для сообщений и ответов оператора."""
    return [
        CallbackQueryHandler(handle_admin_reply_prompt, pattern=r"^msg:admin_reply:\d+$"),
        CallbackQueryHandler(handle_admin_reply_cancel, pattern="^msg:admin_reply_cancel$"),
        CallbackQueryHandler(handle_admin_msgs, pattern=r"^msg:admin_list:\d+$"),
        CallbackQueryHandler(handle_admin_msgs_back, pattern="^msg:admin_back$"),
        CallbackQueryHandler(handle_admin_delete_confirm, pattern="^msg:admin_delete_confirm$"),
        CallbackQueryHandler(handle_admin_delete_do, pattern="^msg:admin_delete_do$"),
        CallbackQueryHandler(handle_msg_to_menu, pattern="^msg:to_menu$"),
    ]
