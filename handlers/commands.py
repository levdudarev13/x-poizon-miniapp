"""/start, /help и обработка deep-link share_XXXXXX."""

import json
import logging
import os as _os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

import database as db
from auth import is_admin as is_admin_user
from config import MINI_APP_URL
from services import exchange_rate as er
from utils.formatters import fmt_result

log = logging.getLogger(__name__)

START_IMAGE_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "Image.png")


def build_start_kb(user_id: int, ctx) -> InlineKeyboardMarkup:
    """Построить клавиатуру стартового сообщения с учетом режима."""
    admin_viewer = is_admin_user(user_id)
    buyer_mode = admin_viewer and ctx is not None and ctx.user_data.get("admin_buyer_mode", False)

    if admin_viewer and not buyer_mode:
        rows = [
            [InlineKeyboardButton("📱 Открыть mini app", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton("📋 Заявки", callback_data="aord:open")],
            [InlineKeyboardButton("👁 Просмотр корзин", callback_data="acart:open")],
            [InlineKeyboardButton("⚙️ Расценки", callback_data="pricing:show")],
            [InlineKeyboardButton("💬 Сообщения", callback_data="msg:admin_list:0")],
            [InlineKeyboardButton("🔄 Выбрать режим", callback_data="mode:select")],
        ]
    else:
        rows = []
        if MINI_APP_URL:
            rows.append(
                [InlineKeyboardButton("📱 Открыть mini app", web_app=WebAppInfo(url=MINI_APP_URL))]
            )
        rows.extend(
            [
                [InlineKeyboardButton("🛒 Моя корзина", callback_data="cart:open")],
                [InlineKeyboardButton("📋 История расчётов", callback_data="hist:open")],
                [
                    InlineKeyboardButton("✉️ Написать админу", callback_data="msg:contact"),
                    InlineKeyboardButton("🚨 Сообщить о проблеме", callback_data="msg:problem"),
                ],
            ]
        )
        if buyer_mode:
            rows.append([InlineKeyboardButton("↩️ Вернуться в режим админа", callback_data="mode:back_to_admin")])

    return InlineKeyboardMarkup(rows)


BUYER_TEXT = """
🇨🇳 *China_Helper — цены из Китая без сюрпризов*

Пришли ссылку с *Poizon*, *Taobao* или *1688* — за 30–60 сек получишь:

💰 Полную стоимость с доставкой и комиссией
📊 Сравнение с ценами на WB и Ozon
📋 Характеристики, варианты и фото

Если товар понравился — уточни вариант, добавь в корзину и оформи заявку 🛒
""".strip()

ADMIN_TEXT = """
🇨🇳 *China_Helper — Панель администратора*

📋 *Заявки* — клиентские заявки и статусы оплат
👁 *Корзины* — просмотр корзин пользователей
⚙️ *Расценки* — комиссия, доставка, курс юаня
💬 *Сообщения* — обращения клиентов
🔄 *Режим покупателя* — протестировать бота как клиент
""".strip()

HELP_TEXT = BUYER_TEXT


def get_start_text(user_id: int, ctx) -> str:
    """Вернуть стартовый текст для пользователя или администратора."""
    admin_viewer = is_admin_user(user_id)
    buyer_mode = admin_viewer and ctx is not None and ctx.user_data.get("admin_buyer_mode", False)
    return ADMIN_TEXT if (admin_viewer and not buyer_mode) else BUYER_TEXT


async def send_start_photo(bot, chat_id: int, user, ctx) -> None:
    """Отправить стартовое сообщение с фото и клавиатурой."""
    caption = f"Привет, {user.first_name}! 👋\n\n{get_start_text(user.id, ctx)}"
    kb = build_start_kb(user.id, ctx)
    file_id = ctx.bot_data.get("start_photo_file_id") if ctx else None

    import os

    # NOTE: фото временно отключено — таймауты при отправке 6МБ Image.png
    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username or "")

    args = ctx.args
    if args and args[0].startswith("share_"):
        share_code = args[0][6:]
        row = await db.get_calculation_by_share(share_code)
        if row:
            rate = await er.get_rate()
            try:
                from models import CalculationResult

                result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
                text = fmt_result(result, "client")
                await update.message.reply_text(
                    f"📋 *Расчёт от байера*\n\n{text}",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
            except Exception as exc:
                log.exception(exc)
        await update.message.reply_text("Расчёт не найден или устарел.")
        return

    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def handle_unexpected_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Любое сообщение вне диалога — показываем стартовое меню."""
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username or "")
    ban = await db.get_ban_info(user.id)

    import time as _t

    level = int(ban.get("ban_level", 0))
    until = float(ban.get("ban_until", 0))
    if level > 0 and (until == -1 or _t.time() < until):
        last = float(ban.get("ban_last_notified", 0))
        if _t.time() - last >= 3600:
            await db.update_ban_notified(user.id)
            from handlers.cart import _BAN_LEVELS

            _, label = _BAN_LEVELS.get(level, (-1, "некоторое время"))
            await update.message.reply_text(
                "🚫 *Доступ ограничен*\n\n"
                "Вы удалили товар из заявки более 5 раз за сутки — "
                "мы расцениваем это как спам.\n\n"
                f"Возможность взаимодействия с ботом вернётся к вам через *{label}*. "
                "При повторном нарушении время бана увеличивается.",
                parse_mode="Markdown",
            )
        return

    await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)


def build_command_handlers():
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("help", cmd_help),
    ]
