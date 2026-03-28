"""Настройки: курс валюты + панель расценок для администратора."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters,
)
from telegram.constants import ParseMode

import database as db
from services import exchange_rate as er
from utils.formatters import fmt_rate_info
from auth import is_admin

log = logging.getLogger(__name__)

# ─── Поля расценок ────────────────────────────────────────────────────────────

PRICING_FIELDS = [
    ("commission_pct",     "Комиссия (%)",          "10.0"),
    ("min_commission_rub", "Мин. комиссия (₽)",     "300"),
    ("logistics_rub",      "Логистика (₽)",          "500"),
    ("insurance_rub",      "Страховка (₽)",          "200"),
    ("price_per_kg",       "Цена за 1 кг (₽)",      "250"),
    ("delivery_time",      "Срок доставки",           "до 2 недель"),
    ("next_shipment_date", "Дата ближайшей отправки", "00.00.0000"),
    ("rate_override",      "Ручной курс ¥→₽",         ""),
]

FIELD_LABELS = {f[0]: f[1] for f in PRICING_FIELDS}


def _is_admin(user_id: int) -> bool:
    return is_admin(user_id)


# ─── /settings — курс + кнопка расценок для админа ───────────────────────────

async def show_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = (
        update.callback_query.from_user.id
        if update.callback_query
        else update.message.from_user.id
    )
    rate = await er.get_rate()
    rate_text = fmt_rate_info(rate) if rate else "_Курс недоступен_"

    buttons = [
        [InlineKeyboardButton("🔄 Обновить курс", callback_data="settings:rate")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="settings:close")],
    ]
    if _is_admin(user_id):
        buttons.insert(0, [InlineKeyboardButton("⚙️ Расценки", callback_data="pricing:show")])

    reply = (
        update.callback_query.message.reply_text
        if update.callback_query
        else update.message.reply_text
    )
    await reply(rate_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_settings_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "settings:close":
        await query.message.delete()
        return

    if data == "settings:rate":
        await query.message.reply_text("⏳ Обновляю курс…")
        rate = await er.get_rate(force_refresh=True)
        if rate:
            await query.message.reply_text(fmt_rate_info(rate), parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text("❌ Не удалось обновить курс.")
        return


# ─── Панель расценок (только для админа) ──────────────────────────────────────

async def _pricing_text(settings: dict) -> str:
    from services.calculator import get_effective_rate
    rate = await get_effective_rate()
    lines = ["⚙️ *Расценки*", ""]
    lines.append(f"Комиссия: *{settings.get('commission_pct', '10.0')}%* (мин. *{settings.get('min_commission_rub', '300')} ₽*)")
    lines.append(f"Логистика: *{settings.get('logistics_rub', '500')} ₽*")
    lines.append(f"Страховка: *{settings.get('insurance_rub', '200')} ₽*")
    lines.append(f"Цена за 1 кг: *{settings.get('price_per_kg', '250')} ₽*")
    lines.append(f"Срок доставки: *{settings.get('delivery_time', 'до 2 недель')}*")
    lines.append(f"Дата ближайшей отправки: *{settings.get('next_shipment_date', '00.00.0000')}*")

    rate_override = settings.get("rate_override", "")
    import time as _time
    until = float(settings.get("rate_override_until", "0") or "0")
    if rate_override and _time.time() < until:
        import datetime
        exp = datetime.datetime.fromtimestamp(until).strftime("%d.%m %H:%M")
        lines.append(f"Курс ¥→₽: *{rate_override}* (до {exp})")
    else:
        lines.append(f"Курс ¥→₽: *{rate:.2f}* (авто ЦБ)")

    return "\n".join(lines)


def _pricing_kb() -> InlineKeyboardMarkup:
    buttons = []
    edit_fields = [
        ("commission_pct",     "Комиссию"),
        ("min_commission_rub", "Мин. комиссию"),
        ("logistics_rub",      "Логистику"),
        ("insurance_rub",      "Страховку"),
        ("price_per_kg",       "Цену/кг"),
        ("delivery_time",      "Срок доставки"),
        ("next_shipment_date", "Дату отправки"),
        ("rate_override",      "Ручной курс"),
    ]
    row = []
    for field, label in edit_fields:
        row.append(InlineKeyboardButton(f"✏️ {label}", callback_data=f"pricing:edit:{field}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔄 Сбросить всё", callback_data="pricing:reset")])
    buttons.append([InlineKeyboardButton("❌ Закрыть", callback_data="pricing:close")])
    return InlineKeyboardMarkup(buttons)


async def show_pricing_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать панель расценок (только для админа)."""
    user_id = (
        update.callback_query.from_user.id
        if update.callback_query
        else update.message.from_user.id
    )
    if not _is_admin(user_id):
        return

    settings = await db.get_admin_settings()
    text = await _pricing_text(settings)

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_pricing_kb()
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_pricing_kb()
        )


async def handle_pricing_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not _is_admin(user_id):
        await query.answer("Нет доступа.")
        return
    await query.answer()
    data = query.data

    if data == "pricing:show":
        await show_pricing_panel(update, ctx)
        return

    if data == "pricing:close":
        await query.message.delete()
        return

    if data == "pricing:reset":
        from database import DEFAULT_ADMIN_SETTINGS
        for key, val in DEFAULT_ADMIN_SETTINGS.items():
            await db.set_admin_setting(key, str(val))
        settings = await db.get_admin_settings()
        text = await _pricing_text(settings)
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=_pricing_kb())
        except Exception:
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=_pricing_kb())
        return

    if data.startswith("pricing:edit:"):
        field = data.split("pricing:edit:")[1]
        label = FIELD_LABELS.get(field, field)
        ctx.user_data["editing_pricing_field"] = field
        ctx.user_data["editing_pricing_msg_id"] = query.message.message_id

        hints = {
            "commission_pct":     "Введи число, например: `12` (это 12%)",
            "min_commission_rub": "Введи минимальную комиссию в рублях, например: `300`\nЕсли % от цены товара меньше этой суммы — берём минимум.",
            "logistics_rub":      "Введи сумму в рублях, например: `600`",
            "insurance_rub":      "Введи сумму в рублях, например: `150`",
            "price_per_kg":       "Введи сумму за 1 кг, например: `300`",
            "delivery_time":      "Введи текст срока, например: `до 3 недель`",
            "next_shipment_date": "Введи дату ближайшей отправки в формате ДД.ММ.ГГГГ, например: `15.03.2026`",
            "rate_override":      "Введи курс ¥→₽, например: `12.5`\nКурс будет действовать 24 часа, потом сбросится на ЦБ.\nОтправь `0` чтобы использовать курс ЦБ.",
        }
        hint = hints.get(field, "Введи новое значение:")
        await query.message.reply_text(
            f"✏️ *{label}*\n\n{hint}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return


async def handle_pricing_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Получить новое значение поля расценок от администратора."""
    if not _is_admin(update.message.from_user.id):
        return
    field = ctx.user_data.get("editing_pricing_field")
    if not field:
        return

    ctx.user_data.pop("editing_pricing_field", None)
    text = (update.message.text or "").strip()

    # Валидация
    if field in ("delivery_time", "next_shipment_date"):
        value = text[:100]
    elif field == "rate_override":
        try:
            val = float(text.replace(",", "."))
            if val <= 0:
                await db.set_admin_setting("rate_override", "")
                await db.set_admin_setting("rate_override_until", "0")
                await update.message.reply_text("✅ Ручной курс сброшен — буду использовать курс ЦБ.")
                return
            import time as _time
            value = str(val)
            await db.set_admin_setting("rate_override", value)
            await db.set_admin_setting("rate_override_until", str(_time.time() + 86400))
            await update.message.reply_text(
                f"✅ Ручной курс установлен: *{val} ₽/¥* на 24 часа.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        except ValueError:
            await update.message.reply_text("Введи число, например: `12.5`", parse_mode=ParseMode.MARKDOWN)
            ctx.user_data["editing_pricing_field"] = field
            return
    else:
        try:
            val = float(text.replace(",", ".").replace(" ", ""))
            if val < 0:
                raise ValueError
            value = str(val)
        except ValueError:
            await update.message.reply_text("Введи корректное число.", parse_mode=ParseMode.MARKDOWN)
            ctx.user_data["editing_pricing_field"] = field
            return

    await db.set_admin_setting(field, value)
    label = FIELD_LABELS.get(field, field)
    await update.message.reply_text(
        f"✅ *{label}* обновлено: `{value}`",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Обновить панель
    settings = await db.get_admin_settings()
    text_panel = await _pricing_text(settings)
    await update.message.reply_text(
        text_panel, parse_mode=ParseMode.MARKDOWN, reply_markup=_pricing_kb()
    )


def build_settings_handlers():
    return [
        CommandHandler("settings", show_settings),
        CallbackQueryHandler(handle_settings_callback, pattern="^settings:"),
        CallbackQueryHandler(handle_pricing_callback, pattern="^pricing:"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pricing_input),
    ]
