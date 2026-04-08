"""Admin bot shortcuts for statistics and segmented broadcasts."""

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes

import database as db
from auth import is_admin

log = logging.getLogger(__name__)

ADMIN_STATS_OPEN = "adm:stats"
ADMIN_STATS_REFRESH = "adm:stats:refresh"
ADMIN_BROADCAST_OPEN = "adm:broadcast"
ADMIN_BROADCAST_BACK = "adm:broadcast:back"
ADMIN_BROADCAST_CANCEL = "adm:broadcast:cancel"
ADMIN_CLOSE = "adm:close"


def _is_admin_user(update: Update) -> bool:
    user = update.effective_user
    return bool(user and is_admin(int(user.id or 0)))


def clear_admin_broadcast_state(user_data) -> None:
    if not user_data:
        return
    user_data.pop("admin_broadcast_segment_key", None)
    user_data.pop("admin_broadcast_segment_label", None)


def _format_int(value: object) -> str:
    return f"{int(round(float(value or 0))):,}".replace(",", " ")


def _format_rub(value: object) -> str:
    return f"{_format_int(value)} ₽"


def _format_percent(value: object) -> str:
    return f"{float(value or 0):.1f}".replace(".", ",")


def _stats_text(payload: dict) -> str:
    users = payload.get("users") or {}
    cart = payload.get("cart") or {}
    orders = payload.get("orders") or {}
    segments = payload.get("segments") or []
    lines = [
        "Статистика",
        f"Сегодня: {payload.get('today_label') or '—'} ({payload.get('timezone_label') or 'МСК'})",
        "",
        "Пользователи",
        f"• Всего пользователей: {_format_int(users.get('total'))}",
        f"• Активных сегодня: {_format_int(users.get('active_today'))}",
        f"• Новых сегодня: {_format_int(users.get('new_today'))}",
        "",
        "Товары",
        (
            "• В корзине: "
            f"{_format_int(cart.get('items_total'))} / {_format_rub(cart.get('amount_total_rub'))}"
        ),
        (
            "• Новых в корзине сегодня: "
            f"{_format_int(cart.get('items_new_today'))} / {_format_rub(cart.get('amount_new_today_rub'))}"
        ),
        (
            "• В заявках: "
            f"{_format_int(orders.get('items_total'))} / {_format_rub(orders.get('amount_total_rub'))}"
        ),
        (
            "• Новых в заявках сегодня: "
            f"{_format_int(orders.get('items_new_today'))} / {_format_rub(orders.get('amount_new_today_rub'))}"
        ),
        "",
        "Сегменты",
    ]
    for segment in segments:
        lines.append(
            f"• {segment.get('label')}: {_format_int(segment.get('count'))} "
            f"({_format_percent(segment.get('percent'))}%)"
        )
    return "\n".join(lines)


def _stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Обновить", callback_data=ADMIN_STATS_REFRESH),
            InlineKeyboardButton("Закрыть", callback_data=ADMIN_CLOSE),
        ],
    ])


def _broadcast_segment_keyboard(counts: dict[str, int]) -> InlineKeyboardMarkup:
    rows = []
    for key, label in db.ADMIN_BROADCAST_SEGMENT_LABELS.items():
        count = int((counts or {}).get(key, 0) or 0)
        rows.append([InlineKeyboardButton(f"{label} • {_format_int(count)}", callback_data=f"adm:broadcast:segment:{key}")])
    rows.append([InlineKeyboardButton("Закрыть", callback_data=ADMIN_CLOSE)])
    return InlineKeyboardMarkup(rows)


def _broadcast_menu_text(counts: dict[str, int]) -> str:
    total_users = int((counts or {}).get("all_users", 0) or 0)
    return (
        "Рассылки\n"
        "Выберите сегмент для сообщения.\n\n"
        f"База получателей сейчас: {_format_int(total_users)} пользователей.\n"
        "Бот может отправить рассылку только тем, кто уже запускал его раньше."
    )


def _broadcast_compose_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сменить сегмент", callback_data=ADMIN_BROADCAST_BACK),
            InlineKeyboardButton("Отмена", callback_data=ADMIN_BROADCAST_CANCEL),
        ],
    ])


def _broadcast_compose_text(segment_label: str, recipients_count: int) -> str:
    return (
        "Рассылки\n"
        f"Сегмент: {segment_label}\n"
        f"Получателей сейчас: {_format_int(recipients_count)}\n\n"
        "Отправьте следующее сообщение, и бот разошлёт его выбранному сегменту.\n"
        "Поддерживаются обычные сообщения Telegram: текст, фото, видео, документы и другие вложения."
    )


async def _copy_broadcast_message(
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    source_chat_id: int,
    source_message_id: int,
    target_user_id: int,
) -> bool:
    for attempt in range(3):
        try:
            await ctx.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            return True
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1.0)
        except (Forbidden, BadRequest):
            return False
        except Exception:
            if attempt == 2:
                log.warning("Broadcast copy failed for user_id=%s", target_user_id, exc_info=True)
                return False
            await asyncio.sleep(1.0 + attempt)
    return False


async def _send_or_edit_text(message, text: str, reply_markup: InlineKeyboardMarkup, *, edit: bool) -> None:
    if edit:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.reply_text(text, reply_markup=reply_markup)


async def handle_admin_stats_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _is_admin_user(update):
        return

    stats = await db.get_admin_stats()
    await _send_or_edit_text(
        query.message,
        _stats_text(stats),
        _stats_keyboard(),
        edit=False,
    )


async def handle_admin_stats_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Обновляю")
    if not _is_admin_user(update):
        return

    stats = await db.get_admin_stats()
    await _send_or_edit_text(
        query.message,
        _stats_text(stats),
        _stats_keyboard(),
        edit=True,
    )


async def handle_admin_broadcast_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _is_admin_user(update):
        return

    clear_admin_broadcast_state(ctx.user_data)
    counts = await db.get_admin_broadcast_segment_counts()
    await _send_or_edit_text(
        query.message,
        _broadcast_menu_text(counts),
        _broadcast_segment_keyboard(counts),
        edit=False,
    )


async def handle_admin_broadcast_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _is_admin_user(update):
        return

    clear_admin_broadcast_state(ctx.user_data)
    counts = await db.get_admin_broadcast_segment_counts()
    await _send_or_edit_text(
        query.message,
        _broadcast_menu_text(counts),
        _broadcast_segment_keyboard(counts),
        edit=True,
    )


async def handle_admin_broadcast_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Рассылка отменена")
    if not _is_admin_user(update):
        return

    clear_admin_broadcast_state(ctx.user_data)
    await query.message.edit_text(
        "Рассылка отменена.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Закрыть", callback_data=ADMIN_CLOSE)]]),
    )


async def handle_admin_broadcast_segment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _is_admin_user(update):
        return

    segment_key = str(query.data or "").split(":")[-1]
    counts = await db.get_admin_broadcast_segment_counts()
    recipients_count = int((counts or {}).get(segment_key, 0) or 0)
    if recipients_count <= 0:
        await query.answer("В этом сегменте пока нет получателей.", show_alert=True)
        return

    label = db.ADMIN_BROADCAST_SEGMENT_LABELS.get(segment_key, segment_key)
    ctx.user_data["admin_broadcast_segment_key"] = segment_key
    ctx.user_data["admin_broadcast_segment_label"] = label
    await query.message.edit_text(
        _broadcast_compose_text(label, recipients_count),
        reply_markup=_broadcast_compose_keyboard(),
    )


async def handle_admin_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass


async def maybe_handle_admin_broadcast_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if not _is_admin_user(update):
        return False

    message = update.effective_message
    if message is None:
        return False

    segment_key = str(ctx.user_data.get("admin_broadcast_segment_key") or "").strip()
    if not segment_key:
        return False

    segment_label = str(
        ctx.user_data.get("admin_broadcast_segment_label")
        or db.ADMIN_BROADCAST_SEGMENT_LABELS.get(segment_key, segment_key)
    )
    clear_admin_broadcast_state(ctx.user_data)

    recipient_ids = await db.get_admin_broadcast_recipient_ids(segment_key)
    if not recipient_ids:
        await message.reply_text("В выбранном сегменте больше нет получателей.")
        return True

    progress_message = await message.reply_text(
        f"Запускаю рассылку по сегменту «{segment_label}» для {_format_int(len(recipient_ids))} пользователей."
    )

    delivered = 0
    failed = 0
    for index, target_user_id in enumerate(recipient_ids, start=1):
        sent = await _copy_broadcast_message(
            ctx,
            source_chat_id=message.chat_id,
            source_message_id=message.message_id,
            target_user_id=target_user_id,
        )
        if sent:
            delivered += 1
        else:
            failed += 1

        if index % 25 == 0:
            await asyncio.sleep(0.08)

    summary = (
        "Рассылка завершена.\n"
        f"Сегмент: {segment_label}\n"
        f"Получателей: {_format_int(len(recipient_ids))}\n"
        f"Доставлено: {_format_int(delivered)}\n"
        f"Недоступно или пропущено: {_format_int(failed)}"
    )
    try:
        await progress_message.edit_text(summary)
    except Exception:
        await message.reply_text(summary)
    return True


async def handle_admin_attachment_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    handled = await maybe_handle_admin_broadcast_message(update, ctx)
    if handled:
        raise ApplicationHandlerStop()


def build_admin_dashboard_handlers() -> list:
    return [
        CallbackQueryHandler(handle_admin_stats_open, pattern=f"^{ADMIN_STATS_OPEN}$"),
        CallbackQueryHandler(handle_admin_stats_refresh, pattern=f"^{ADMIN_STATS_REFRESH}$"),
        CallbackQueryHandler(handle_admin_broadcast_open, pattern=f"^{ADMIN_BROADCAST_OPEN}$"),
        CallbackQueryHandler(handle_admin_broadcast_back, pattern=f"^{ADMIN_BROADCAST_BACK}$"),
        CallbackQueryHandler(handle_admin_broadcast_cancel, pattern=f"^{ADMIN_BROADCAST_CANCEL}$"),
        CallbackQueryHandler(handle_admin_broadcast_segment, pattern=r"^adm:broadcast:segment:[a-z0-9_]+$"),
        CallbackQueryHandler(handle_admin_close, pattern=f"^{ADMIN_CLOSE}$"),
    ]
