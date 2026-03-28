"""Переключение режима работы для администратора (Админ / Покупатель)."""
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

from config import ADMIN_USER_ID

log = logging.getLogger(__name__)


async def handle_mode_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать экран выбора режима."""
    query = update.callback_query
    await query.answer()

    in_buyer_mode = ctx.user_data.get("admin_buyer_mode", False)
    mode_label = "Покупатель" if in_buyer_mode else "Администратор"

    if in_buyer_mode:
        switch_btn = InlineKeyboardButton(
            "👔 Перейти в режим администратора",
            callback_data="mode:back_to_admin",
        )
    else:
        switch_btn = InlineKeyboardButton(
            "🛒 Перейти в режим покупателя",
            callback_data="mode:to_buyer",
        )

    kb = InlineKeyboardMarkup([
        [switch_btn],
        [InlineKeyboardButton("◀️ Назад", callback_data="mode:select_back")],
    ])

    await query.message.reply_text(
        f"🔄 *Выбор режима*\n\n"
        f"В режиме *покупателя* вы видите бота глазами обычного пользователя — "
        f"все функции расчёта, корзина и история работают как обычно.\n\n"
        f"В режиме *администратора* доступны заявки, корзины клиентов, расценки и сообщения.\n\n"
        f"Сейчас вы находитесь в режиме: *{mode_label}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def handle_mode_to_buyer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Переключить в режим покупателя."""
    query = update.callback_query
    await query.answer()
    ctx.user_data["admin_buyer_mode"] = True

    from handlers.commands import send_start_photo
    user = update.effective_user
    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


async def handle_mode_back_to_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Переключить обратно в режим администратора."""
    query = update.callback_query
    await query.answer()
    ctx.user_data["admin_buyer_mode"] = False

    from handlers.commands import send_start_photo
    user = update.effective_user
    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


async def handle_mode_select_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Назад из экрана выбора режима — новое стартовое сообщение."""
    query = update.callback_query
    await query.answer()

    from handlers.commands import send_start_photo
    user = update.effective_user
    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


def build_mode_handlers() -> list:
    return [
        CallbackQueryHandler(handle_mode_select,        pattern="^mode:select$"),
        CallbackQueryHandler(handle_mode_to_buyer,      pattern="^mode:to_buyer$"),
        CallbackQueryHandler(handle_mode_back_to_admin, pattern="^mode:back_to_admin$"),
        CallbackQueryHandler(handle_mode_select_back,   pattern="^mode:select_back$"),
    ]
