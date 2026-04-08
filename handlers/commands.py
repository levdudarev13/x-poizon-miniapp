"""/start, /help и обработка deep-link share_XXXXXX."""

import json
import logging
import os as _os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import database as db
from auth import is_admin as is_admin_user
from config import (
    ADMIN_CONTACT_USER_ID,
    ADMIN_CONTACT_USERNAME,
    ADMIN_USERNAME,
    ADMIN_USER_ID,
    ADMIN_USER_IDS,
    MINI_APP_URL,
)
from services import exchange_rate as er
from utils.formatters import fmt_rate_info, fmt_result

log = logging.getLogger(__name__)

START_IMAGE_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(__file__)),
    "miniapp",
    "public",
    "123.jpg",
)
REVIEWS_URL = "https://vk.ru/topic-214425199_48948017"
BUYER_BTN_CALC = "🎰 Рассчитать стоимость"
BUYER_BTN_ORDER = "📦 Сделать заказ"
BUYER_BTN_FAQ = "❓ FAQ"
BUYER_BTN_REVIEWS = "⭐ Отзывы"
BUYER_BTN_SUPPORT = "💬 Поддержка"
BUYER_BTN_RATE = "💱 Текущий курс"
BUYER_RATE_CALLBACK = "buyer:rate"


def _admin_contact_target_user_id() -> int:
    if ADMIN_CONTACT_USER_ID > 0:
        return int(ADMIN_CONTACT_USER_ID)
    if ADMIN_USER_IDS:
        return int(ADMIN_USER_IDS[-1])
    try:
        user_id = int(ADMIN_USER_ID or 0)
    except (TypeError, ValueError):
        return 0
    return user_id if user_id > 0 else 0


def _admin_contact_username() -> str:
    explicit_contact_username = str(ADMIN_CONTACT_USERNAME or "").strip().lstrip("@")
    if explicit_contact_username:
        return explicit_contact_username
    if _admin_contact_target_user_id() != int(ADMIN_USER_ID or 0):
        return ""
    return str(ADMIN_USERNAME or "").strip().lstrip("@")


def _admin_contact_url() -> str:
    username = _admin_contact_username()
    if username:
        return f"https://t.me/{username}"
    contact_user_id = _admin_contact_target_user_id()
    return f"tg://user?id={contact_user_id}" if contact_user_id > 0 else ""


def _build_mini_app_url(*, tab: str | None = None, view: str | None = None) -> str:
    base_url = str(MINI_APP_URL or "").strip()
    if not base_url:
        return ""

    parts = urlsplit(base_url)
    query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    if tab:
        query_params["tab"] = tab
    if view:
        query_params["view"] = view

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query_params),
        parts.fragment,
    ))


def _build_buyer_inline_kb(*, buyer_mode: bool = False) -> InlineKeyboardMarkup:
    calc_url = _build_mini_app_url()
    cart_url = _build_mini_app_url(tab="cart")
    faq_url = _build_mini_app_url(tab="profile", view="faq")
    contact_url = _admin_contact_url()

    rows = []
    if calc_url or MINI_APP_URL:
        rows.append([InlineKeyboardButton(BUYER_BTN_CALC, web_app=WebAppInfo(url=calc_url or MINI_APP_URL))])
    if cart_url or MINI_APP_URL or faq_url:
        rows.append([
            InlineKeyboardButton(BUYER_BTN_ORDER, web_app=WebAppInfo(url=cart_url or MINI_APP_URL)),
            InlineKeyboardButton(BUYER_BTN_FAQ, web_app=WebAppInfo(url=faq_url or MINI_APP_URL)),
        ])

    review_support_row = [InlineKeyboardButton(BUYER_BTN_REVIEWS, url=REVIEWS_URL)]
    if contact_url:
        review_support_row.append(InlineKeyboardButton(BUYER_BTN_SUPPORT, url=contact_url))
    rows.append(review_support_row)
    rows.append([InlineKeyboardButton(BUYER_BTN_RATE, callback_data=BUYER_RATE_CALLBACK)])

    if buyer_mode:
        rows.append([InlineKeyboardButton("Вернуться в режим админа", callback_data="mode:back_to_admin")])

    return InlineKeyboardMarkup(rows)


def _build_buyer_reply_kb() -> ReplyKeyboardMarkup:
    calc_url = _build_mini_app_url()
    cart_url = _build_mini_app_url(tab="cart")
    faq_url = _build_mini_app_url(tab="profile", view="faq")

    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BUYER_BTN_CALC, web_app=WebAppInfo(url=calc_url or MINI_APP_URL))],
            [
                KeyboardButton(BUYER_BTN_ORDER, web_app=WebAppInfo(url=cart_url or MINI_APP_URL)),
                KeyboardButton(BUYER_BTN_FAQ, web_app=WebAppInfo(url=faq_url or MINI_APP_URL)),
            ],
            [
                KeyboardButton(BUYER_BTN_REVIEWS),
                KeyboardButton(BUYER_BTN_SUPPORT),
            ],
            [KeyboardButton(BUYER_BTN_RATE)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )


def _is_buyer_view(user_id: int, ctx) -> bool:
    admin_viewer = is_admin_user(user_id)
    buyer_mode = admin_viewer and ctx is not None and ctx.user_data.get("admin_buyer_mode", False)
    return (not admin_viewer) or buyer_mode


def build_start_kb(user_id: int, ctx) -> InlineKeyboardMarkup:
    """Построить клавиатуру стартового сообщения с учетом режима."""
    admin_viewer = is_admin_user(user_id)
    buyer_mode = admin_viewer and ctx is not None and ctx.user_data.get("admin_buyer_mode", False)

    if admin_viewer and not buyer_mode:
        rows = [
            [InlineKeyboardButton("Открыть mini app", web_app=WebAppInfo(url=MINI_APP_URL))],
            [InlineKeyboardButton("Статистика", callback_data="adm:stats")],
            [InlineKeyboardButton("Рассылки", callback_data="adm:broadcast")],
        ]
        return InlineKeyboardMarkup(rows)

    return _build_buyer_inline_kb(buyer_mode=buyer_mode)


BUYER_TEXT = """
LOGISTICS X STORE
Быстро и надежно
Самые выгодные цены только у нас

🤝 Минимальный курс юаня на рынке

🤝 Минимальная комиссия

🤝 Быстрые сроки доставки

🤝 Оплата доставки при получении по самому выгодному тарифу!

🤝 Делаем подарки к КАЖДОМУ ЗАКАЗУ

Работаем 4 года , привезли свыше 100.000 заказов для 30.000 клиентов
""".strip()

ADMIN_TEXT = """
China_Helper — Админ-режим

Открыть mini app
Статистика
Рассылки
""".strip()

HELP_TEXT = BUYER_TEXT


def get_start_text(user_id: int, ctx) -> str:
    """Вернуть стартовый текст для пользователя или администратора."""
    admin_viewer = is_admin_user(user_id)
    buyer_mode = admin_viewer and ctx is not None and ctx.user_data.get("admin_buyer_mode", False)
    return ADMIN_TEXT if (admin_viewer and not buyer_mode) else BUYER_TEXT


async def send_start_photo(bot, chat_id: int, user, ctx) -> None:
    """Отправить стартовое сообщение с фото и клавиатурой."""
    caption = get_start_text(user.id, ctx)
    kb = build_start_kb(user.id, ctx)
    file_id = ctx.bot_data.get("start_photo_file_id") if ctx else None

    if file_id:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                reply_markup=kb,
            )
            return
        except Exception:
            if ctx:
                ctx.bot_data.pop("start_photo_file_id", None)

    try:
        with open(START_IMAGE_PATH, "rb") as photo_stream:
            sent_message = await bot.send_photo(
                chat_id=chat_id,
                photo=photo_stream,
                caption=caption,
                reply_markup=kb,
            )
        if ctx and getattr(sent_message, "photo", None):
            ctx.bot_data["start_photo_file_id"] = sent_message.photo[-1].file_id
        return
    except Exception:
        log.exception("Failed to send start photo, falling back to text")

    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=kb,
    )


async def send_buyer_reply_keyboard(bot, chat_id: int, user_id: int, ctx) -> None:
    if not _is_buyer_view(user_id, ctx):
        return

    await bot.send_message(
        chat_id=chat_id,
        text="Быстрые действия доступны в клавиатуре ниже.",
        reply_markup=_build_buyer_reply_kb(),
        disable_notification=True,
    )


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(
        user.id,
        user.username or "",
        user.first_name or "",
        user.last_name or "",
    )

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
    await send_buyer_reply_keyboard(ctx.bot, update.effective_chat.id, user.id, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def handle_buyer_shortcuts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == BUYER_BTN_REVIEWS:
        await update.message.reply_text(
            "Отзывы о работе можно посмотреть здесь:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Открыть отзывы", url=REVIEWS_URL)],
            ]),
            disable_web_page_preview=True,
        )
        return

    if text == BUYER_BTN_SUPPORT:
        contact_url = _admin_contact_url()
        if contact_url:
            await update.message.reply_text(
                "Напишите оператору напрямую:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Открыть поддержку", url=contact_url)],
                ]),
                disable_web_page_preview=True,
            )
            return

        await update.message.reply_text("Ссылка на поддержку пока не настроена.")
        return

    if text == BUYER_BTN_RATE:
        rate = await er.get_rate()
        if not rate:
            await update.message.reply_text("Не удалось получить актуальный курс. Попробуйте чуть позже.")
            return

        await update.message.reply_text(
            fmt_rate_info(rate),
            parse_mode=ParseMode.MARKDOWN,
        )


async def handle_buyer_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    rate = await er.get_rate()
    if not rate:
        await query.message.reply_text("Не удалось получить актуальный курс. Попробуйте чуть позже.")
        return

    await query.message.reply_text(
        fmt_rate_info(rate),
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_unexpected_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Любое сообщение вне диалога — показываем стартовое меню."""
    user = update.effective_user
    await db.get_or_create_user(
        user.id,
        user.username or "",
        user.first_name or "",
        user.last_name or "",
    )
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
    buyer_shortcuts_pattern = rf"^({re.escape(BUYER_BTN_REVIEWS)}|{re.escape(BUYER_BTN_SUPPORT)}|{re.escape(BUYER_BTN_RATE)})$"
    return [
        CommandHandler("start", cmd_start),
        CommandHandler("help", cmd_help),
        CallbackQueryHandler(handle_buyer_rate, pattern=f"^{BUYER_RATE_CALLBACK}$"),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.User(user_id=list(ADMIN_USER_IDS)) & filters.Regex(buyer_shortcuts_pattern),
            handle_buyer_shortcuts,
        ),
    ]
