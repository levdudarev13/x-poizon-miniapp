"""Обработчики истории расчётов."""
import asyncio
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

import database as db
from utils.keyboards import kb_history_numbered
from utils.formatters import fmt_history_list
from services.market_compare import extract_search_query

log = logging.getLogger(__name__)

_HIST_NAMES_KEY = "hist_short_names"
_STICKER_HIST = "CAACAgIAAxkBAAFEF2FprB-04zbubwK96NZLKQABqQePHlQAAg0AA8A2TxOk-eH01HiNUzoE"


async def _get_history_short_names(items: list[dict], ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    """Groq-сокращения для истории (кешируются в user_data)."""
    cache = ctx.user_data.setdefault(_HIST_NAMES_KEY, {})
    new_ids, new_coros = [], []
    for item in items:
        cid = item["id"]
        if cid not in cache:
            new_ids.append(cid)
            new_coros.append(extract_search_query(item.get("name") or "Товар"))
    if new_coros:
        results = await asyncio.gather(*new_coros, return_exceptions=True)
        items_map = {item["id"]: item for item in items}
        for cid, res in zip(new_ids, results):
            if isinstance(res, Exception) or not res:
                cache[cid] = (items_map[cid].get("name") or "Товар")[:35]
            else:
                cache[cid] = str(res)[:35]
    return cache


async def show_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать список последних расчётов."""
    is_callback = bool(update.callback_query)
    if is_callback:
        await update.callback_query.answer()
        user_id = update.callback_query.from_user.id
        msg = update.callback_query.message
    else:
        user_id = update.message.from_user.id
        msg = update.message

    items = await db.get_history(user_id, limit=15)

    if not items:
        text = "📭 *История расчётов пуста*\n\nПришли ссылку на товар, чтобы сделать первый расчёт."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="hist:back")]])
        if is_callback:
            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        else:
            await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return

    # Анимация загрузки пока Groq обрабатывает имена
    sticker_msg = await msg.reply_sticker(_STICKER_HIST)
    loading_msg = await msg.reply_text("⏳ Загружаю историю…")

    short_names = await _get_history_short_names(items, ctx)

    try:
        await sticker_msg.delete()
        await loading_msg.delete()
    except Exception:
        pass

    text = fmt_history_list(items, short_names)
    kb = kb_history_numbered(items)

    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                         disable_web_page_preview=True)


async def handle_history_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "hist:open":
        await show_history(update, ctx)
        return

    if data == "hist:back":
        from handlers.commands import send_start_photo
        try:
            await query.message.delete()
        except Exception:
            pass
        await send_start_photo(ctx.bot, query.message.chat_id, query.from_user, ctx)
        return

    if data == "hist:back_card":
        # Удаляем карточку товара
        try:
            await query.message.delete()
        except Exception:
            pass
        # Восстанавливаем кнопки на сообщении истории
        hist_msg_id = ctx.user_data.pop("_hist_msg_id", None)
        hist_chat_id = ctx.user_data.pop("_hist_chat_id", None)
        if hist_msg_id and hist_chat_id:
            user_id = query.from_user.id
            items = await db.get_history(user_id, limit=15)
            if items:
                kb = kb_history_numbered(items)
                try:
                    await ctx.bot.edit_message_reply_markup(
                        chat_id=hist_chat_id,
                        message_id=hist_msg_id,
                        reply_markup=kb,
                    )
                except Exception:
                    pass
        return


def build_history_handlers():
    return [
        CommandHandler("history", show_history),
        CallbackQueryHandler(handle_history_callback, pattern=r"^hist:(open|back|back_card)$"),
    ]
