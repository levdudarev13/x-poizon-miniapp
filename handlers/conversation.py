"""Главный ConversationHandler — весь диалоговый поток бота."""
import asyncio
import json
import math
import re
import logging
from telegram import Update, Message
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CallbackQueryHandler, CommandHandler,
    filters,
)
from telegram.constants import ParseMode

from auth import is_admin
from models import ProductDraft, UserSettings, CalculationResult, BreakdownLine
import database as db
from services.parser import parse_url, is_valid_url, extract_url, resolve_url, _variant_price_key_from_dict
from services.calculator import calculate, validate_price, get_typical_weight, groq_detect, calculate_simple, get_effective_rate
from services import exchange_rate as er
from utils.keyboards import (
    kb_categories, kb_result,
    kb_result_saved, kb_client_msg_templates, kb_cancel,
    kb_confirm_product, kb_add_back,
)
from utils.formatters import fmt_result, fmt_client_message, fmt_share_info, fmt_rate_info, fmt_product_card
from config import CATEGORIES, EXCHANGE_RATE_STALE_SECONDS, PLATFORM_TAOBAO, PLATFORM_1688, PLATFORM_POIZON, ADMIN_USER_IDS

log = logging.getLogger(__name__)

# ─── States ───────────────────────────────────────────────────────────────────
(
    AWAIT_LINK,
    CONFIRM_PRODUCT,
    AWAIT_PRICE,
    AWAIT_NAME,
    AWAIT_SIZE,
    AWAIT_CATEGORY,
    AWAIT_WEIGHT,
    SHOW_RESULT,
    AWAIT_COMPARE_NAME,
    AWAIT_VARIANT_SELECTION,
    AWAIT_VARIANT_PRICE,
) = range(11)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_draft(ctx: ContextTypes.DEFAULT_TYPE) -> ProductDraft:
    if "draft" not in ctx.user_data:
        ctx.user_data["draft"] = ProductDraft()
    return ctx.user_data["draft"]


def _set_draft(ctx: ContextTypes.DEFAULT_TYPE, draft: ProductDraft):
    ctx.user_data["draft"] = draft


async def _get_settings(user_id: int) -> UserSettings:
    user = await db.get_or_create_user(user_id)
    steps = json.loads(user.get("margin_steps", "[]") or "[]")
    return UserSettings(
        user_id=user_id,
        margin_steps=steps,
        margin_min_rub=user.get("margin_min_rub", 500.0),
    )


async def _do_calculate(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> "CalculationResult | None":
    draft = _get_draft(ctx)
    rate = await er.get_rate()
    if not rate:
        return None
    settings = await _get_settings(user_id)
    admin = await db.get_admin_settings()
    min_commission_rub = float(admin.get("min_commission_rub", 300.0))
    return calculate(draft, rate, settings, min_commission_rub=min_commission_rub)


async def _calc_for_cart(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> "CalculationResult | None":
    """Расчёт для корзины — та же формула что при первом добавлении (calculate_simple)."""
    draft = _get_draft(ctx)
    if not draft.price_cny:
        return None
    admin = await db.get_admin_settings()
    eff_rate = await get_effective_rate()
    admin["_effective_rate"] = eff_rate
    rate = await er.get_rate()
    if not rate:
        return None
    settings = await _get_settings(user_id)
    total_rub = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)
    goods_rub       = draft.price_cny * eff_rate
    comm_pct        = float(admin.get("commission_pct", 10.0))
    min_commission  = float(admin.get("min_commission_rub", 300.0))
    commission      = max(goods_rub * comm_pct / 100, min_commission)
    logistics       = float(admin.get("logistics_rub", 500.0))
    insurance       = float(admin.get("insurance_rub", 200.0))
    price_per_kg    = float(admin.get("price_per_kg", 250.0))
    weight_rounded  = math.ceil(max(draft.weight_kg or 1.0, 1.0))
    weight_fee      = weight_rounded * price_per_kg
    breakdown = [
        BreakdownLine("Товар", goods_rub, f"{draft.price_cny:.0f} ¥ × {eff_rate:.2f}"),
        BreakdownLine(f"Комиссия ({comm_pct:.0f}%)", commission, ""),
        BreakdownLine("Логистика и страховка", logistics + insurance + weight_fee, ""),
    ]
    margin = settings.calc_margin(float(total_rub))
    return CalculationResult(
        product=draft,
        breakdown=breakdown,
        subtotal_rub=float(total_rub),
        margin_rub=margin,
        total_with_margin_rub=float(total_rub) + margin,
        margin_percent=settings.get_margin_percent(float(total_rub)),
        exchange_rate=rate,
    )


async def _send_result(
    message: Message,
    ctx: ContextTypes.DEFAULT_TYPE,
    result,
    mode: str = "client",
    edit: bool = False,
):
    """Отправить/обновить сообщение с результатом расчёта."""
    ctx.user_data["last_result"] = result
    ctx.user_data["show_mode"] = mode

    text = fmt_result(result, mode)
    saved = ctx.user_data.get("saved_share_code")
    has_name = bool(_get_draft(ctx).name)
    kb = kb_result_saved(saved, mode, has_name) if saved else kb_result(mode, has_name)

    if edit:
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def _finish_calculation(message: Message, ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    result = await _do_calculate(ctx, user_id)
    if not result:
        await message.reply_text("Не удалось посчитать итог. Попробуйте позже.")
        return ConversationHandler.END

    rate = await er.get_rate()
    if rate and rate.age_seconds > EXCHANGE_RATE_STALE_SECONDS:
        await message.reply_text(
            f"⚠️ Курс устарел ({rate.age_human}). Рекомендую обновить его через /settings."
        )

    await _send_result(message, ctx, result, mode="client")
    return SHOW_RESULT


# ─── Шаг 1: Ссылка ───────────────────────────────────────────────────────────

# ─── Стикеры загрузки ────────────────────────────────────────────────────────
_S1 = "CAACAgIAAxkBAAFD4-1pqQ9sl9NKp_0EOA20i-paRQ2uHwACBgADwDZPE8fKovSybnB2OgQ"
_S2 = "CAACAgIAAxkBAAFED9xpq5v1wyl2SFLlBJ3jxXMx_GvLAAMWAAPANk8TYCHXLaIEtmc6BA"
_S3 = "CAACAgIAAxkBAAFED-xpq5yPcJQaT6tp0XeSytcQQordpgACBwADwDZPE0hhd1MIpyLHOgQ"
_S4 = "CAACAgIAAxkBAAFED_Zpq51SUxQBh51X_kqLq7HeITRFSgACIAADwDZPE_QPK7o-X_TPOgQ"


async def _loading_animation(chat_id: int, bot, state: dict) -> None:
    """Прогрессивная анимация: стикеры меняются на 15/30/60 секундах."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    stages = [
        (15, _S2, "⏳ Анализирую ссылку…\n\nБот не завис — подождите 20–40 секунд."),
        (15, _S3, "⏳ Анализирую ссылку…\n\nПочти готово, осталось буквально 10–15 секунд."),
        (40, _S4, None),  # timeout (итого 15+15+40=70 сек)
    ]
    for delay, sticker_id, text in stages:
        try:
            await asyncio.wait_for(state["done"].wait(), timeout=delay)
            return  # парсинг завершился раньше таймаута
        except asyncio.TimeoutError:
            pass
        if state["done"].is_set():
            return
        for m in state.get("msgs", []):
            try:
                await m.delete()
            except Exception:
                pass
        state["msgs"] = []
        if text is None:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Вернуться назад", callback_data="cancel")],
                [InlineKeyboardButton("🐛 Сообщить о проблеме", callback_data="report_problem")],
            ])
            s = await bot.send_sticker(chat_id, sticker_id)
            t = await bot.send_message(
                chat_id,
                "😔 Похоже, что-то сломалось.\n\nПриносим извинения за доставленные неудобства.",
                reply_markup=kb,
            )
            state["msgs"] = [s, t]
        else:
            s = await bot.send_sticker(chat_id, sticker_id)
            t = await bot.send_message(chat_id, text)
            state["msgs"] = [s, t]


async def start_calc(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа: пользователь прислал текст (ссылку или /calc)."""
    # Пропускаем если пользователь вводит/ввёл комментарий к товару в корзине
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    # Пропускаем если пользователь в потоке отправки сообщения администратору
    if ctx.user_data.get("_in_msg_flow"):
        return ConversationHandler.END
    # Пропускаем если админ вводит данные в панели расценок
    if ctx.user_data.get("editing_pricing_field"):
        return ConversationHandler.END
    # Пропускаем если админ вводит номера товаров для уведомлений
    if ctx.bot_data.get("admin_notify_mode") and is_admin(update.effective_user.id):
        return ConversationHandler.END
    import re as _re
    text = (update.message.text or "").strip()

    # Поддержка шаринга из приложения: извлекаем URL из любого текста
    url = text if is_valid_url(text) else extract_url(text)

    if not url:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from handlers.commands import send_start_photo
        await send_start_photo(ctx.bot, update.effective_chat.id, update.effective_user, ctx)
        return ConversationHandler.END

    # Таобао/1688 шаринг включает название товара в текст после URL:
    # "【淘宝】https://e.tb.cn/... tG-#22>ID 冬装金毛加厚棉衣狗狗衣服"
    name_hint = None
    if url != text.strip():
        after_url = text[text.find(url) + len(url):].strip()
        cn_m = _re.search(r'[\u4e00-\u9fff]{3,}[^\n]{0,60}', after_url)
        if cn_m:
            raw = cn_m.group(0).strip()
            # Обрезаем мусор от шаринга: "点击链接直接打开" и подобное
            for stop in ['点击', '打开', '立即', '查看', '链接', '，', ',']:
                idx = raw.find(stop)
                if idx > 5:
                    raw = raw[:idx]
                    break
            name_hint = raw.strip()[:60] or None

    ctx.user_data.pop("saved_share_code", None)
    ctx.user_data["last_url"] = url

    # Проверяем: этот URL уже есть в корзине? (резолвим редиректы перед сравнением)
    user_id = update.effective_user.id
    resolved = await resolve_url(url)
    if await db.cart_has_url(user_id, resolved):
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        await update.message.reply_text(
            "🛒 Этот товар уже есть в вашей корзине.\n\n"
            "Перейдите в корзину, чтобы изменить его, или отправьте другую ссылку для расчёта.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛒 Перейти в корзину", callback_data="cart:open"),
            ]]),
        )
        return ConversationHandler.END

    # Запускаем анимацию загрузки
    state: dict = {"msgs": [], "done": asyncio.Event()}
    s1 = await update.message.reply_sticker(_S1)
    m1 = await update.message.reply_text("⏳ Анализирую ссылку…")
    state["msgs"] = [s1, m1]
    anim_task = asyncio.create_task(
        _loading_animation(update.message.chat_id, ctx.bot, state)
    )

    parse_error = None
    try:
        draft = await parse_url(url)
    except Exception as e:
        log.exception(f"parse_url failed: {e}")
        parse_error = e

    # Останавливаем анимацию и удаляем все текущие сообщения
    state["done"].set()
    anim_task.cancel()
    try:
        await anim_task
    except (asyncio.CancelledError, Exception):
        pass
    for m in state.get("msgs", []):
        try:
            await m.delete()
        except Exception:
            pass

    if parse_error:
        await update.message.reply_text(
            "❌ Не удалось получить данные по ссылке. Попробуй ещё раз или введи /manual."
        )
        return AWAIT_LINK

    # Если название не найдено парсером — берём из шаринг-текста
    if not draft.name and name_hint:
        log.info(f"using name_hint from sharing text: {name_hint!r}")
        try:
            from services.translator import translate_if_cn
            draft.name = await translate_if_cn(name_hint)
        except Exception:
            draft.name = name_hint
        if draft.name and "name" not in draft.auto_detected:
            draft.auto_detected.append("name")

    # Groq — категория и вес, если не найдены автоматически
    needs_cat = not draft.category
    needs_weight = not draft.weight_kg
    if needs_cat or needs_weight:
        try:
            groq = await groq_detect(draft.name or "")
            if needs_cat and groq["category"]:
                draft.category = groq["category"]
                draft.auto_detected.append("category_groq")
            if needs_weight and groq["weight_kg"]:
                draft.weight_kg = groq["weight_kg"]
                draft.weight_estimated = True
                draft.auto_detected.append("weight_groq")
        except Exception as e:
            log.warning("groq_detect in start_calc failed: %s", e)

    _set_draft(ctx, draft)

    if draft.platform in (PLATFORM_TAOBAO, PLATFORM_1688) and (not draft.name or not draft.price_cny):
        await update.message.reply_text(
            "Could not load item data from the link. Send it to admin if this repeats."
        )
        return ConversationHandler.END

    if draft.name:
        asyncio.create_task(_save_draft_to_history(update.effective_user.id, draft))

    return await _show_product_card(update.message, ctx, draft)


async def _save_draft_to_history(user_id: int, draft: ProductDraft):
    """Save parsed draft to history in the background."""
    try:
        rate = await er.get_rate()
        admin = await db.get_admin_settings()
        admin["_effective_rate"] = await get_effective_rate()

        if draft.price_cny:
            total_rub = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)
            logistics = float(admin.get("logistics_rub", 500))
            insurance = float(admin.get("insurance_rub", 200))
            item_rub = total_rub - logistics - insurance
            breakdown = [
                BreakdownLine("Item", max(item_rub, 0)),
                BreakdownLine("Delivery", logistics),
                BreakdownLine("Insurance", insurance),
            ]
        else:
            total_rub = 0.0
            breakdown = [BreakdownLine("Item", 0.0)]

        if draft.variants and not draft.original_variants:
            draft.original_variants = list(draft.variants)

        result = CalculationResult(
            product=draft,
            breakdown=breakdown,
            subtotal_rub=total_rub,
            margin_rub=0.0,
            total_with_margin_rub=total_rub,
            margin_percent=0.0,
            exchange_rate=rate,
        )
        await db.save_calculation(user_id, result)
    except Exception as e:
        log.warning("_save_draft_to_history failed: %s", e)

async def _show_product_card(message: Message, ctx: ContextTypes.DEFAULT_TYPE, draft: ProductDraft, from_history: bool = False) -> int:
    """Показать карточку товара и ждать подтверждения."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rate = await er.get_rate()
    is_poizon = draft.platform == PLATFORM_POIZON

    # Есть ли варианты с 2+ опциями? — проверяем всегда, независимо от цены
    has_active_variants = any(
        len(g.get("options", [])) >= 2
        for g in (draft.variants or [])
    )

    # Считаем итог через admin settings
    total_rub = None
    delivery_time = None
    if draft.price_cny:
        try:
            import database as _db
            admin = await _db.get_admin_settings()
            admin["_effective_rate"] = await get_effective_rate()
            total_rub = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)
            delivery_time = admin.get("delivery_time", "до 2 недель")
            if has_active_variants:
                total_rub = None  # не показываем итог пока не выбраны варианты
        except Exception as e:
            log.warning("calculate_simple in _show_product_card failed: %s", e)

    card_text = fmt_product_card(draft, rate, total_rub=total_rub, delivery_time=delivery_time, has_active_variants=has_active_variants)
    has_total = total_rub is not None
    kb = kb_confirm_product(
        bool(draft.price_cny),
        has_name=bool(draft.name) and has_total,
        is_poizon=is_poizon,
        has_active_variants=has_active_variants,
        has_specs=bool(draft.specs or draft.extra_images or draft.available_sizes),
        from_history=from_history,
    )

    if draft.image_url:
        try:
            sent = await message.reply_photo(
                photo=draft.image_url,
                caption=card_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
            ctx.user_data["card_msg_id"] = sent.message_id
            ctx.user_data["card_chat_id"] = sent.chat.id
            ctx.user_data["card_is_photo"] = True
            return CONFIRM_PRODUCT
        except Exception:
            pass  # если фото не загрузилось — отправим без него

    sent = await message.reply_text(card_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    ctx.user_data["card_msg_id"] = sent.message_id
    ctx.user_data["card_chat_id"] = sent.chat.id
    ctx.user_data["card_is_photo"] = False
    return CONFIRM_PRODUCT


async def handle_confirm_cart(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавить в корзину прямо с карточки товара (CONFIRM_PRODUCT)."""
    query = update.callback_query
    await query.answer()

    if ctx.user_data.get("_cart_adding"):
        return CONFIRM_PRODUCT
    ctx.user_data["_cart_adding"] = True

    draft = _get_draft(ctx)
    if not draft.price_cny:
        ctx.user_data.pop("_cart_adding", None)
        await query.answer("Сначала укажи цену товара", show_alert=True)
        return CONFIRM_PRODUCT

    try:
        admin = await db.get_admin_settings()
        eff_rate = await get_effective_rate()
        admin["_effective_rate"] = eff_rate
        rate = await er.get_rate()
        settings = await _get_settings(query.from_user.id)

        total_rub = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)

        # Строим разбивку совпадающую с calculate_simple
        goods_rub       = draft.price_cny * eff_rate
        comm_pct        = float(admin.get("commission_pct", 10.0))
        min_commission  = float(admin.get("min_commission_rub", 300.0))
        commission      = max(goods_rub * comm_pct / 100, min_commission)
        logistics       = float(admin.get("logistics_rub", 500.0))
        insurance       = float(admin.get("insurance_rub", 200.0))
        price_per_kg    = float(admin.get("price_per_kg", 250.0))
        weight_rounded  = math.ceil(max(draft.weight_kg or 1.0, 1.0))
        weight_fee      = weight_rounded * price_per_kg

        breakdown = [
            BreakdownLine("Товар", goods_rub, f"{draft.price_cny:.0f} ¥ × {eff_rate:.2f}"),
            BreakdownLine(f"Комиссия ({comm_pct:.0f}%)", commission, ""),
            BreakdownLine("Логистика и страховка", logistics + insurance + weight_fee, ""),
        ]

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        margin = settings.calc_margin(float(total_rub))
        result = CalculationResult(
            product=draft,
            breakdown=breakdown,
            subtotal_rub=float(total_rub),
            margin_rub=margin,
            total_with_margin_rub=float(total_rub) + margin,
            margin_percent=settings.get_margin_percent(float(total_rub)),
            exchange_rate=rate,
        )

        calc_id, share_code = await db.save_calculation(query.from_user.id, result)
        result.calc_id = calc_id

        cart_edit_id = ctx.user_data.pop("cart_edit_calc_id", None)
        if cart_edit_id:
            await db.cart_update_item(query.from_user.id, cart_edit_id, calc_id)
            ctx.user_data.pop("cart_short_names", None)
        else:
            await db.cart_add(query.from_user.id, calc_id)
    finally:
        ctx.user_data.pop("_cart_adding", None)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Перейти в корзину", callback_data="cart:open")],
        [InlineKeyboardButton("🔄 Новый расчёт", callback_data="cart:new_calc")],
        [InlineKeyboardButton("◀️ Назад", callback_data="confirm:added_back")],
    ])
    await query.message.reply_text("✅ Товар добавлен в корзину!", reply_markup=kb)
    return CONFIRM_PRODUCT


async def handle_confirm_added_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Удалить сообщение 'Товар добавлен в корзину' и вернуться к карточке."""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    return CONFIRM_PRODUCT


async def handle_compare_from_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Сравнить с WB или Ozon прямо с карточки товара (до расчёта)."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    market = "ozon" if data == "compare:ozon" else "wb"
    ctx.user_data["compare_market"] = market
    draft = _get_draft(ctx)
    our_price = 0.0
    if draft.price_cny:
        try:
            import database as _db
            admin = await _db.get_admin_settings()
            admin["_effective_rate"] = await get_effective_rate()
            our_price = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)
        except Exception:
            rate = await er.get_rate()
            our_price = draft.price_cny * rate.cny_rub if rate else 0.0
    await _run_comparison(query.message, ctx, draft.name, our_price, market, draft.category)
    return CONFIRM_PRODUCT


async def handle_confirm_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка кнопок подтверждения карточки товара."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]  # ok / price / category

    if action == "ok":
        draft = _get_draft(ctx)
        return await _ask_size_from_query(query, ctx)

    if action == "price":
        await query.message.reply_text(
            "💰 Введи цену товара в *юанях (¥)*:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return AWAIT_PRICE

    if action == "category":
        await query.message.reply_text(
            "Выбери *категорию* товара:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_categories(),
        )
        return AWAIT_CATEGORY

    return CONFIRM_PRODUCT


async def handle_specs_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать характеристики товара: 3 фото + все спецификации."""
    query = update.callback_query
    await query.answer()
    _SPECS_STICKER = "CAACAgIAAxkBAAFED75pq5go0D9gmpBWWMBRJQ8Oo07P4QACGAADwDZPE9b6J7-cahj4OgQ"
    sticker_msg = await query.message.reply_sticker(_SPECS_STICKER)
    loading_msg = await query.message.reply_text("🔍 Загружаю характеристики...")
    try:
        draft = _get_draft(ctx)
        log.info(
            "handle_specs_request start: platform=%s url=%s specs=%s extra_images=%s",
            draft.platform,
            draft.url,
            len(draft.specs or {}),
            len(draft.extra_images or []),
        )
        if draft.platform == PLATFORM_POIZON:
            try:
                from services.parser import parse_poizon_html_specs
                html_info = await parse_poizon_html_specs(draft.url or ctx.user_data.get("last_url", ""))
                if html_info.get("specs"):
                    draft.specs = html_info["specs"]
                if html_info.get("extra_images"):
                    draft.extra_images = html_info["extra_images"]
                if html_info.get("image_url") and not draft.image_url:
                    draft.image_url = html_info["image_url"]
                if html_info.get("weight_kg"):
                    draft.weight_kg = html_info["weight_kg"]
                _set_draft(ctx, draft)
                log.info(
                    "handle_specs_request poizon html: url=%s specs=%s extra_images=%s",
                    draft.url,
                    len(draft.specs or {}),
                    len(draft.extra_images or []),
                )
            except Exception as e:
                log.warning(f"poizon specs refresh failed: {e}")

        # Переводим ключи и значения спецификаций через Groq
        from services.translator import translate_specs_with_groq
        specs = draft.specs or {}
        log.info("handle_specs_request translate: specs=%s", len(specs))
        try:
            translated_specs = await translate_specs_with_groq(specs)
        except Exception as e:
            log.warning(f"specs translate failed: {e}")
            translated_specs = specs

        try:
            await sticker_msg.delete()
            await loading_msg.delete()
        except Exception:
            pass

        # Форматируем спецификации
        lines = ["📋 *Характеристики товара*\n"]
        if translated_specs:
            for key, val in translated_specs.items():
                lines.append(f"• *{key}:* {val}")
        else:
            lines.append("_Спецификации не найдены_")
        if draft.available_sizes:
            lines.append(f"\n📏 *Размеры:* {', '.join(draft.available_sizes)}")
        if draft.weight_kg:
            lines.append(f"⚖️ *Вес:* {draft.weight_kg:.1f} кг")
        specs_text = "\n".join(lines)

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="specs:back")]])
        msg_ids = []

        # Все доступные фото товара
        photos = draft.extra_images if draft.extra_images else []
        if photos:
            from telegram import InputMediaPhoto
            # Telegram принимает максимум 10 фото в медиагруппе
            try:
                media = [InputMediaPhoto(media=url) for url in photos[:10]]
                photo_msgs = await query.message.reply_media_group(media=media)
                msg_ids.extend(m.message_id for m in photo_msgs)
            except Exception as e:
                log.warning(f"specs photos send failed: {e}")

        # Текст + кнопка "Назад"
        text_msg = await query.message.reply_text(
            specs_text, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb
        )
        msg_ids.append(text_msg.message_id)
        ctx.user_data["specs_msg_ids"] = msg_ids
    except Exception as e:
        log.exception(f"handle_specs_request error: {e}")
        try:
            await sticker_msg.delete()
            await loading_msg.delete()
        except Exception:
            pass
        await query.message.reply_text("❌ Не удалось загрузить характеристики")
    return CONFIRM_PRODUCT


async def handle_specs_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Удалить все сообщения с характеристиками (фото + текст)."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    msg_ids = ctx.user_data.pop("specs_msg_ids", [query.message.message_id])
    for mid in msg_ids:
        try:
            await query.get_bot().delete_message(chat_id, mid)
        except Exception:
            pass
    return CONFIRM_PRODUCT


async def handle_confirm_retry(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Повторный парсинг ссылки по кнопке 'Попробовать ещё раз'."""
    query = update.callback_query
    await query.answer()
    url = ctx.user_data.get("last_url")
    if not url:
        await query.message.reply_text("❌ Ссылка не сохранена, пришли заново.")
        return AWAIT_LINK

    msg = await query.message.reply_text(
        "⏳ Пробую ещё раз…\n\nПодождите 20–40 секунд."
    )
    try:
        draft = await parse_url(url)
    except Exception as e:
        log.exception(f"retry parse_url failed: {e}")
        await msg.edit_text("❌ Снова не получилось. Попробуй позже или введи цену вручную.")
        return CONFIRM_PRODUCT

    # Groq — категория и вес (так же как в start_calc)
    needs_cat = not draft.category
    needs_weight = not draft.weight_kg
    if needs_cat or needs_weight:
        try:
            groq = await groq_detect(draft.name or "")
            if needs_cat and groq["category"]:
                draft.category = groq["category"]
            if needs_weight and groq["weight_kg"]:
                draft.weight_kg = groq["weight_kg"]
                draft.weight_estimated = True
        except Exception as e:
            log.warning("groq_detect in retry failed: %s", e)

    _set_draft(ctx, draft)
    await msg.delete()

    if draft.name:
        asyncio.create_task(_save_draft_to_history(query.from_user.id, draft))

    return await _show_product_card(query.message, ctx, draft)


async def handle_clarify_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь нажал 'Уточнить мой вариант и цену'."""
    query = update.callback_query
    await query.answer()
    draft = _get_draft(ctx)
    groups = [g for g in (draft.variants or []) if len(g.get("options", [])) >= 2]
    ctx.user_data["variant_groups"] = groups
    ctx.user_data["variant_step"] = 0
    ctx.user_data["selected_variants"] = {}
    return await _show_variant_step(query.message, ctx)


async def _finalize_selected_variants(
    source_message: Message,
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> int:
    draft = _get_draft(ctx)
    selected = ctx.user_data.get("selected_variants", {})
    draft.size = " · ".join(f"{k}: {v}" for k, v in selected.items()) if selected else ""
    selected_raw = ctx.user_data.get("selected_variants_raw", {})
    variant_price_key = _variant_price_key_from_dict(
        {n: v for n, v in selected_raw.items() if v != "__other__"}
    ) if selected_raw else ""
    selected_variant_price = None
    if variant_price_key:
        selected_variant_price = (draft.variant_price_map or {}).get(variant_price_key)
    if selected_variant_price:
        draft.price_cny = selected_variant_price

    saved_groups = ctx.user_data.get("variant_groups", [])
    if saved_groups:
        draft.original_variants = saved_groups
    draft.variants = []
    _set_draft(ctx, draft)

    ctx.user_data.pop("variant_groups", None)
    ctx.user_data.pop("variant_step", None)
    ctx.user_data.pop("selected_variants", None)
    ctx.user_data.pop("variant_step_options", None)

    cart_edit_id = ctx.user_data.get("cart_edit_calc_id")
    if cart_edit_id:
        result = await _calc_for_cart(ctx, user_id)
        if result:
            calc_id, _ = await db.save_calculation(user_id, result)
            result.calc_id = calc_id
            await db.cart_update_item(user_id, cart_edit_id, calc_id)
            ctx.user_data.pop("cart_edit_calc_id", None)
            try:
                await source_message.delete()
            except Exception:
                pass

            cart_msg_id = ctx.user_data.pop("cart_edit_msg_id", None)
            cart_chat_id = ctx.user_data.pop("cart_edit_chat_id", None)
            cart_is_photo = ctx.user_data.pop("cart_edit_is_photo", False)
            if cart_msg_id and cart_chat_id:
                from handlers.cart import _kb_cart_item
                _admin = await db.get_admin_settings()
                text = fmt_result(
                    result, "client",
                    delivery_time=_admin.get("delivery_time"),
                    next_shipment_date=_admin.get("next_shipment_date"),
                )
                items = await db.cart_get_items(user_id)
                in_order = next((bool(item.get("in_order")) for item in items if item["id"] == calc_id), False)
                kb = _kb_cart_item(calc_id, in_order)
                try:
                    if cart_is_photo:
                        await ctx.bot.edit_message_caption(
                            chat_id=cart_chat_id, message_id=cart_msg_id,
                            caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                        )
                    else:
                        await ctx.bot.edit_message_text(
                            chat_id=cart_chat_id, message_id=cart_msg_id,
                            text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                        )
                except Exception as e:
                    log.warning(f"cart edit: failed to update card: {e}")
            return ConversationHandler.END

    try:
        await source_message.delete()
    except Exception:
        pass

    card_msg_id = ctx.user_data.get("card_msg_id")
    card_chat_id = ctx.user_data.get("card_chat_id")
    card_is_photo = ctx.user_data.get("card_is_photo", False)
    if card_msg_id and card_chat_id:
        try:
            rate = await er.get_rate()
            is_poizon = draft.platform == PLATFORM_POIZON
            import database as _db
            admin = await _db.get_admin_settings()
            admin["_effective_rate"] = await get_effective_rate()
            total_rub = calculate_simple(draft.price_cny, draft.weight_kg or 0.5, admin)
            delivery_time = admin.get("delivery_time", "до 2 недель")
            card_text = fmt_product_card(draft, rate, total_rub=total_rub, delivery_time=delivery_time)
            kb = kb_confirm_product(
                bool(draft.price_cny),
                has_name=bool(draft.name) and total_rub is not None,
                is_poizon=is_poizon,
                has_specs=bool(draft.specs or draft.extra_images or draft.available_sizes),
            )
            if card_is_photo:
                await ctx.bot.edit_message_caption(
                    chat_id=card_chat_id, message_id=card_msg_id,
                    caption=card_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                )
            else:
                await ctx.bot.edit_message_text(
                    chat_id=card_chat_id, message_id=card_msg_id,
                    text=card_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                )
            return CONFIRM_PRODUCT
        except Exception as e:
            log.warning("Failed to update product card in place: %s", e)

    return await _show_product_card(source_message, ctx, draft)


def _compatible_variant_options(
    draft: ProductDraft,
    selected_raw: dict[str, str],
    group_name: str,
    options: list[str],
) -> list[str]:
    variant_price_map = draft.variant_price_map or {}
    if not variant_price_map or not options:
        return options

    # selected_raw содержит оригинальные (нетронутые) ключи и значения,
    # совпадающие с ключами variant_price_map. Исключаем "__other__".
    filtered = {n: v for n, v in selected_raw.items() if v != "__other__"}

    compatible: list[str] = []
    for option in options:
        probe = dict(filtered)
        probe[group_name] = option
        for raw_key in variant_price_map:
            try:
                pairs = json.loads(raw_key)
            except Exception:
                continue
            mapping = {str(n): str(v) for n, v in pairs if str(n).strip() and str(v).strip()}
            if all(mapping.get(str(n)) == str(v) for n, v in probe.items()):
                compatible.append(option)
                break
    return compatible


async def _show_variant_step(message: Message, ctx: ContextTypes.DEFAULT_TYPE, edit: bool = False) -> int:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    groups = ctx.user_data.get("variant_groups", [])
    step = ctx.user_data.get("variant_step", 0)
    if step >= len(groups):
        return await _finalize_selected_variants(message, ctx, message.chat.id)
    draft = _get_draft(ctx)
    selected = ctx.user_data.get("selected_variants", {})
    selected_raw = ctx.user_data.get("selected_variants_raw", {})
    group = groups[step]
    name = group["name"]
    options = _compatible_variant_options(draft, selected_raw, name, list(group["options"]))
    ctx.user_data["variant_step_options"] = options

    # Переводим название группы и варианты с китайского на русский
    from services.translator import translate_market_text
    name_ru = await translate_market_text(name)
    translated_opts = []
    for opt in options:
        opt_ru = await translate_market_text(opt)
        translated_opts.append(opt_ru)

    # Если хоть одна опция длиннее 30 символов — выводим список в тексте, кнопки-цифры
    use_numeric = any(len(ru) > 30 for ru in translated_opts)
    if use_numeric:
        opts_text = "\n".join(f"{i + 1}. {ru}" for i, ru in enumerate(translated_opts))
        text = f"*{name_ru}?*\n\n{opts_text}"
        num_btns = [InlineKeyboardButton(str(i + 1), callback_data=f"var:i:{i}") for i in range(len(translated_opts))]
        rows = [num_btns[i:i + 3] for i in range(0, len(num_btns), 3)]
    else:
        text = f"*{name_ru}?*"
        option_btns = [InlineKeyboardButton(ru, callback_data=f"var:i:{i}") for i, ru in enumerate(translated_opts)]
        rows = [option_btns[i:i + 3] for i in range(0, len(option_btns), 3)]
    rows.append([
        InlineKeyboardButton("🔀 Другой вариант", callback_data="var:__other__"),
        InlineKeyboardButton("◀️ Назад", callback_data="var:step_back"),
    ])
    kb = InlineKeyboardMarkup(rows)
    if edit:
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        sent = await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        ctx.user_data["variant_question_msg_id"] = sent.message_id
        ctx.user_data["variant_question_chat_id"] = sent.chat.id
    return AWAIT_VARIANT_SELECTION


async def handle_variant_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    value = query.data.split("var:", 1)[1]
    groups = ctx.user_data.get("variant_groups", [])
    step = ctx.user_data.get("variant_step", 0)
    if step < len(groups):
        from services.translator import translate_market_text
        group = groups[step]
        group_name_ru = await translate_market_text(group["name"])
        raw = ctx.user_data.setdefault("selected_variants_raw", {})
        if value == "__other__":
            ctx.user_data["selected_variants"][group_name_ru] = "Другой вариант"
            raw[group["name"]] = "__other__"
        elif value.startswith("i:"):
            idx = int(value[2:])
            current_options = ctx.user_data.get("variant_step_options") or group["options"]
            opt_text = current_options[idx] if idx < len(current_options) else ""
            ctx.user_data["selected_variants"][group_name_ru] = await translate_market_text(opt_text)
            raw[group["name"]] = opt_text
        else:
            ctx.user_data["selected_variants"][group_name_ru] = await translate_market_text(value)
            raw[group["name"]] = value
    ctx.user_data["variant_step"] = step + 1
    return await _show_variant_step(query.message, ctx, edit=True)


async def handle_variant_step_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """◀️ Назад на шаге выбора варианта."""
    query = update.callback_query
    await query.answer()
    step = ctx.user_data.get("variant_step", 0)
    groups = ctx.user_data.get("variant_groups", [])

    if step == 0:
        # На первом шаге — удаляем сообщение с вопросом
        ctx.user_data.pop("variant_groups", None)
        ctx.user_data.pop("variant_step", None)
        ctx.user_data.pop("selected_variants", None)
        ctx.user_data.pop("selected_variants_raw", None)
        ctx.user_data.pop("variant_step_options", None)
        try:
            await query.message.delete()
        except Exception:
            pass
        # В cart-edit режиме просто завершаем — карточка корзины остаётся нетронутой
        if ctx.user_data.pop("cart_edit_calc_id", None):
            ctx.user_data.pop("cart_edit_msg_id", None)
            ctx.user_data.pop("cart_edit_chat_id", None)
            ctx.user_data.pop("cart_edit_is_photo", None)
            return ConversationHandler.END
        return CONFIRM_PRODUCT

    # Откатываем шаг, редактируем текущее сообщение (без создания нового)
    ctx.user_data["variant_step"] = step - 1
    selected = ctx.user_data.get("selected_variants", {})
    if groups and step - 1 < len(groups):
        from services.translator import translate_market_text
        group_name_ru = await translate_market_text(groups[step - 1]["name"])
        selected.pop(group_name_ru, None)
        ctx.user_data.get("selected_variants_raw", {}).pop(groups[step - 1]["name"], None)
    return await _show_variant_step(query.message, ctx, edit=True)


async def handle_variant_price_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь нажал '◀️ Назад' — вернуться к последнему шагу выбора варианта."""
    query = update.callback_query
    await query.answer()
    step = ctx.user_data.get("variant_step", 0)
    groups = ctx.user_data.get("variant_groups", [])
    if step > 0:
        ctx.user_data["variant_step"] = step - 1
        selected = ctx.user_data.get("selected_variants", {})
        if groups and step - 1 < len(groups):
            from services.translator import translate_market_text
            group_name_ru = await translate_market_text(groups[step - 1]["name"])
            selected.pop(group_name_ru, None)
            ctx.user_data.get("selected_variants_raw", {}).pop(groups[step - 1]["name"], None)
    return await _show_variant_step(query.message, ctx, edit=True)


async def handle_variant_price_use_parsed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь нажал 'Продолжить' — использовать найденную цену."""
    query = update.callback_query
    await query.answer()
    return await _finalize_selected_variants(query.message, ctx, query.from_user.id)


async def handle_variant_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь ввёл цену (и опционально вариант) после выбора характеристик."""
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    draft = _get_draft(ctx)

    # Ищем любое число 1–1 000 000 в любом месте текста (даже слитно с буквами)
    # Остаток текста после удаления числа → комментарий/вариант
    variant_override = None
    price: float | None = None

    price_match = re.search(r'(\d+(?:[.,]\d+)?)', text)
    if price_match:
        try:
            p = float(price_match.group(1).replace(",", "."))
            if 1 <= p <= 1_000_000:
                price = p
                # Убираем число из текста — остаток идёт как комментарий
                note = (text[:price_match.start()] + text[price_match.end():]).strip().strip(",").strip()
                variant_override = note or None
        except ValueError:
            pass

    if price is None:
        # Цены нет — используем найденную при парсинге, весь текст → заметка
        if not draft.price_cny:
            await update.message.reply_text("Введи корректную цену числом, например: `1200`", parse_mode=ParseMode.MARKDOWN)
            return AWAIT_VARIANT_PRICE
        draft.notes = text
    else:
        draft.price_cny = price
        # Остаток текста (без числа) → комментарий в итоговом сообщении
        if variant_override:
            draft.notes = variant_override

    selected = ctx.user_data.get("selected_variants", {})
    draft.size = " · ".join(f"{k}: {v}" for k, v in selected.items()) if selected else ""
    saved_groups = ctx.user_data.get("variant_groups", [])
    if saved_groups:
        draft.original_variants = saved_groups  # для "Изменить"
    draft.variants = []  # сбросить активные варианты → has_active_variants = False
    _set_draft(ctx, draft)
    ctx.user_data.pop("variant_groups", None)
    ctx.user_data.pop("variant_step", None)
    ctx.user_data.pop("selected_variants", None)
    ctx.user_data.pop("variant_step_options", None)

    # Если пришли из "Изменить" в корзине — считаем и обновляем карточку корзины
    cart_edit_id = ctx.user_data.get("cart_edit_calc_id")
    if cart_edit_id:
        result = await _calc_for_cart(ctx, update.effective_user.id)
        if result:
            calc_id, _ = await db.save_calculation(update.effective_user.id, result)
            result.calc_id = calc_id
            await db.cart_update_item(update.effective_user.id, cart_edit_id, calc_id)
            ctx.user_data.pop("cart_edit_calc_id", None)
            # Удаляем сообщение пользователя с ценой и сообщение-вопрос
            for msg_id, chat_id in [
                (update.message.message_id, update.message.chat.id),
                (ctx.user_data.pop("variant_question_msg_id", None), ctx.user_data.pop("variant_question_chat_id", None)),
            ]:
                if msg_id and chat_id:
                    try:
                        await ctx.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception:
                        pass
            # Обновляем карточку корзины
            cart_msg_id = ctx.user_data.pop("cart_edit_msg_id", None)
            cart_chat_id = ctx.user_data.pop("cart_edit_chat_id", None)
            cart_is_photo = ctx.user_data.pop("cart_edit_is_photo", False)
            if cart_msg_id and cart_chat_id:
                from handlers.cart import _kb_cart_item
                _admin = await db.get_admin_settings()
                text = fmt_result(
                    result, "client",
                    delivery_time=_admin.get("delivery_time"),
                    next_shipment_date=_admin.get("next_shipment_date"),
                )
                items = await db.cart_get_items(update.effective_user.id)
                in_order = next((bool(item.get("in_order")) for item in items if item["id"] == calc_id), False)
                kb = _kb_cart_item(calc_id, in_order)
                try:
                    if cart_is_photo:
                        await ctx.bot.edit_message_caption(
                            chat_id=cart_chat_id, message_id=cart_msg_id,
                            caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                        )
                    else:
                        await ctx.bot.edit_message_text(
                            chat_id=cart_chat_id, message_id=cart_msg_id,
                            text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
                        )
                except Exception as e:
                    log.warning(f"cart edit: failed to update card: {e}")
            return ConversationHandler.END

    return await _show_product_card(update.message, ctx, draft)


async def _ask_size_from_query(query, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Без размера", callback_data="skip:size")],
        [InlineKeyboardButton("◀️ Назад", callback_data="nav:back")],
    ])
    await query.message.reply_text(
        "Укажи *размер/вариант* товара (напр. «42», «L», «Black 256GB») или пропусти:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )
    return AWAIT_SIZE


async def handle_link_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Повторный ввод ссылки."""
    return await start_calc(update, ctx)


# ─── Ручной ввод (/manual) ────────────────────────────────────────────────────

async def manual_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.pop("saved_share_code", None)
    draft = ProductDraft()
    _set_draft(ctx, draft)
    await update.message.reply_text(
        "Введи цену товара в *юанях (CNY)*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_cancel(),
    )
    return AWAIT_PRICE


# ─── Шаг 2: Цена ─────────────────────────────────────────────────────────────

async def handle_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    text = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Введи корректную цену числом (например: `680` или `1250.50`)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return AWAIT_PRICE

    draft = _get_draft(ctx)
    draft.price_cny = price
    _set_draft(ctx, draft)

    await update.message.reply_text(f"✅ Цена принята: *{price:.0f} ¥*", parse_mode=ParseMode.MARKDOWN)

    # Если категория уже есть — к размеру, иначе спросим
    if not draft.category:
        await update.message.reply_text(
            "Выбери *категорию* товара:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_categories(),
        )
        return AWAIT_CATEGORY

    return await _ask_size(update, ctx)


# ─── Шаг 3: Название ─────────────────────────────────────────────────────────

def _kb_skip_name():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Пропустить", callback_data="skip:name")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")],
    ])


async def handle_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    name = (update.message.text or "").strip()[:100]
    draft = _get_draft(ctx)
    draft.name = name
    _set_draft(ctx, draft)
    return await _ask_size(update, ctx)


async def skip_name_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _ask_size(update.callback_query, ctx, use_message=False)


# ─── Шаг 4: Размер ───────────────────────────────────────────────────────────

async def _ask_size(trigger, ctx: ContextTypes.DEFAULT_TYPE, use_message: bool = True) -> int:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ Без размера", callback_data="skip:size")],
        [InlineKeyboardButton("◀️ Назад", callback_data="nav:back")],
    ])
    text = "Укажи *размер/вариант* товара (напр. «42», «L», «Black 256GB») или пропусти:"

    if use_message and hasattr(trigger, "reply_text"):
        await trigger.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    elif hasattr(trigger, "message") and trigger.message:
        await trigger.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await trigger.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return AWAIT_SIZE


async def handle_size(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    size = (update.message.text or "").strip()[:30]
    draft = _get_draft(ctx)
    draft.size = size
    _set_draft(ctx, draft)
    return await _ask_category_or_calculate(update.message, ctx)


async def skip_size_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    return await _ask_category_or_calculate(update.callback_query.message, ctx)


# ─── Шаг 5: Категория / вес ──────────────────────────────────────────────────

async def _ask_category_or_calculate(message: Message, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_draft(ctx)
    if not draft.category:
        await message.reply_text(
            "Выбери *категорию* товара — бот подставит типичный вес:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_add_back(kb_categories()),
        )
        return AWAIT_CATEGORY

    return await _finish_calculation(message, ctx, message.from_user.id)


async def handle_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data  # "cat:sneakers" or "cat:manual"

    key = data.split(":")[1]
    draft = _get_draft(ctx)

    if key == "manual":
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await query.message.reply_text(
            "Введи *вес* товара в кг (например: `1.2`):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="nav:back")]]),
        )
        return AWAIT_WEIGHT

    draft.category = key
    if not draft.weight_kg:
        draft.weight_kg = get_typical_weight(key)
        draft.weight_estimated = True
    _set_draft(ctx, draft)

    cat_name = CATEGORIES[key][0]
    await query.message.reply_text(
        f"✅ Категория: *{cat_name}*",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Валидация цены
    if draft.price_cny and draft.category:
        ok, warn = validate_price(draft.price_cny, draft.category)
        if not ok:
            await query.message.reply_text(f"⚠️ {warn}")

    return await _finish_calculation(query.message, ctx, query.from_user.id)


async def handle_weight(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    text = update.message.text.strip().replace(",", ".")
    try:
        weight = float(text)
        if weight <= 0 or weight > 50:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введи вес в кг числом (например: `1.2`)")
        return AWAIT_WEIGHT

    draft = _get_draft(ctx)
    draft.weight_kg = weight
    draft.weight_estimated = False
    _set_draft(ctx, draft)
    return await _finish_calculation(update.message, ctx, update.effective_user.id)


# ─── Шаг 6: Город ────────────────────────────────────────────────────────────

async def handle_result_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    result = ctx.user_data.get("last_result")

    if not result:
        await query.message.reply_text("Сессия истекла. Пришли новую ссылку.")
        return AWAIT_LINK

    # ── Переключить режим ─────────────────────────────────────────────────
    if data.startswith("mode:"):
        new_mode = data.split(":")[1]
        ctx.user_data["show_mode"] = new_mode
        await _send_result(query.message, ctx, result, mode=new_mode, edit=True)
        return SHOW_RESULT

    # ── Сохранить ─────────────────────────────────────────────────────────
    if data == "calc:save":
        calc_id, share_code = await db.save_calculation(query.from_user.id, result)
        result.calc_id = calc_id
        result.share_code = share_code
        ctx.user_data["saved_share_code"] = share_code
        mode = ctx.user_data.get("show_mode", "client")
        await _send_result(query.message, ctx, result, mode=mode, edit=True)
        await query.message.reply_text(
            f"✅ Расчёт сохранён!\n\n"
            f"🔗 *Код:* `{share_code}`\n"
            f"Отправь этот код клиенту — он сможет открыть расчёт через бот.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return SHOW_RESULT

    # ── В корзину ─────────────────────────────────────────────────────────
    if data == "calc:cart":
        if not result.calc_id:
            calc_id, share_code = await db.save_calculation(query.from_user.id, result)
            result.calc_id = calc_id
            result.share_code = share_code
            ctx.user_data["saved_share_code"] = share_code
        # Если редактируем из корзины — заменяем старый товар
        cart_edit_id = ctx.user_data.pop("cart_edit_calc_id", None)
        if cart_edit_id:
            await db.cart_update_item(query.from_user.id, cart_edit_id, result.calc_id)
            ctx.user_data.pop("cart_short_names", None)
        else:
            await db.cart_add(query.from_user.id, result.calc_id)
        mode = ctx.user_data.get("show_mode", "client")
        has_name = bool(_get_draft(ctx).name)
        await _send_result(query.message, ctx, result, mode=mode, edit=True)
        await query.message.reply_text("✅ Товар добавлен в корзину!")
        return SHOW_RESULT

    # ── Пересчитать ───────────────────────────────────────────────────────
    if data == "calc:recalc":
        return await _finish_calculation(query.message, ctx, query.from_user.id)
    # ── Новый расчёт ──────────────────────────────────────────────────────
    if data == "calc:new":
        ctx.user_data.clear()
        await query.message.reply_text(
            "Пришли ссылку на товар или /manual для ручного ввода:"
        )
        return AWAIT_LINK

    # ── Код расчёта ───────────────────────────────────────────────────────
    if data.startswith("share:"):
        share_code = data.split(":")[1]
        bot = query.get_bot()
        me = await bot.get_me()
        from utils.formatters import fmt_share_info
        await query.message.reply_text(
            fmt_share_info(share_code, me.username),
            parse_mode=ParseMode.MARKDOWN,
        )
        return SHOW_RESULT

    # ── Сгенерировать сообщение клиенту ───────────────────────────────────
    if data == "gen:msg":
        await query.message.reply_text(
            "Выбери шаблон сообщения клиенту:",
            reply_markup=kb_client_msg_templates(),
        )
        return SHOW_RESULT

    if data.startswith("tpl:"):
        tpl_key = data.split(":")[1]
        text = fmt_client_message(result, tpl_key)
        await query.message.reply_text(
            f"📋 *Текст для клиента:*\n\n{text}\n\n_Скопируй и перешли_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return SHOW_RESULT

    if data == "gen:back":
        mode = ctx.user_data.get("show_mode", "client")
        await _send_result(query.message, ctx, result, mode=mode, edit=True)
        return SHOW_RESULT

    # ── Сравнить с WB / Ozon ──────────────────────────────────────────────
    if data in ("compare:wb", "compare:ozon", "compare:wb_ozon"):
        market = "ozon" if data == "compare:ozon" else "wb"
        ctx.user_data["compare_market"] = market
        draft = _get_draft(ctx)
        name = draft.name or ctx.user_data.get("_compare_from_cart_name", "")
        if not name:
            await query.message.reply_text(
                "Введи *название товара* для поиска:\n\n"
                "_Например: «Nike Air Max 270» или «Кроссовки Найк»_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb_cancel(),
            )
            return AWAIT_COMPARE_NAME
        our_price = result.total_rounded if result else 0.0
        return await _run_comparison(query.message, ctx, name, our_price, market)

    return SHOW_RESULT


# ─── Сравнение WB/Ozon ───────────────────────────────────────────────────────

async def _run_comparison(
    message: Message,
    ctx: ContextTypes.DEFAULT_TYPE,
    query: str,
    our_price_rub: float,
    market: str = "wb",
    category: str = "",
    cart_mode: bool = False,
) -> int:
    """Запустить поиск на WB или Ozon и отправить результат с cross-кнопкой."""
    from services.market_compare import search_wildberries, search_ozon, extract_search_query
    from utils.formatters import fmt_comparison_result
    from utils.keyboards import kb_compare_cross, kb_compare_cross_cart
    _cross_kb_fn = kb_compare_cross_cart if cart_mode else kb_compare_cross

    search_query = await extract_search_query(query, category)

    market_name = "Wildberries" if market == "wb" else "Ozon"
    STICKER_COMPARE = "CAACAgIAAxkBAAFED75pq5go0D9gmpBWWMBRJQ8Oo07P4QACGAADwDZPE9b6J7-cahj4OgQ"
    sticker_msg = await message.reply_sticker(STICKER_COMPARE)
    loading_msg = await message.reply_text(
        f"⏳ Ищу *«{search_query}»* на {market_name}…",
        parse_mode=ParseMode.MARKDOWN,
    )

    if market == "wb":
        items = await search_wildberries(search_query)
    else:
        items = await search_ozon(search_query)

    await sticker_msg.delete()

    if items is None:
        # Антибот — сервер заблокирован
        await loading_msg.edit_text(
            f"⚠️ {market_name} временно недоступен.\n"
            "Сервис защищён от автоматических запросов. Попробуй позже.",
            reply_markup=kb_add_back(_cross_kb_fn(market)),
        )
        return SHOW_RESULT

    if not items:
        await loading_msg.edit_text(
            f"😔 Извините, похоже такой товар отсутствует на {market_name}.",
            reply_markup=kb_add_back(_cross_kb_fn(market)),
        )
        return SHOW_RESULT

    text = fmt_comparison_result(search_query, items, [], our_price_rub, market)
    cross_kb = kb_add_back(_cross_kb_fn(market))

    # Фото топ-1
    if items[0].image_url:
        top = items[0]
        try:
            import httpx as _httpx
            import io as _io
            _hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with _httpx.AsyncClient(timeout=10) as _cli:
                r = await _cli.get(top.image_url, headers=_hdrs, follow_redirects=True)
            if r.status_code == 200:
                await loading_msg.delete()
                await message.reply_photo(
                    photo=_io.BytesIO(r.content),
                    caption=text[:1024],
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=cross_kb,
                )
                return SHOW_RESULT
        except Exception as e:
            log.warning("%s photo send failed: %s", market_name, e)

    # Fallback: просто текст
    await loading_msg.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=cross_kb,
    )
    return SHOW_RESULT


async def handle_compare_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Получить название от пользователя и запустить сравнение."""
    if ctx.user_data.get("cart_comment_calc_id") or ctx.user_data.pop("_cart_comment_done", False):
        return ConversationHandler.END
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Введи название для поиска:")
        return AWAIT_COMPARE_NAME

    # Сохраняем введённое имя в draft, чтобы не спрашивать повторно
    draft = _get_draft(ctx)
    if not draft.name:
        draft.name = name
        _set_draft(ctx, draft)

    result = ctx.user_data.get("last_result")
    our_price = result.total_rounded if result else 0.0
    market = ctx.user_data.get("compare_market", "wb")
    return await _run_comparison(update.message, ctx, name, our_price, market)


# ─── Навигация назад ─────────────────────────────────────────────────────────

async def handle_nav_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться к карточке товара из любого шага."""
    query = update.callback_query
    await query.answer()
    draft = _get_draft(ctx)
    return await _show_product_card(query.message, ctx, draft)


async def handle_compare_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Закрыть результат сравнения."""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass
    return SHOW_RESULT if ctx.user_data.get("last_result") else CONFIRM_PRODUCT


# ─── Отмена ───────────────────────────────────────────────────────────────────

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    from handlers.commands import get_start_text
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    _buyer_mode = ctx.user_data.get("admin_buyer_mode", False)
    ctx.user_data.clear()
    if _buyer_mode:
        ctx.user_data["admin_buyer_mode"] = True
    from handlers.commands import build_start_kb
    kb = build_start_kb(update.effective_user.id, ctx)
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
        user = update.callback_query.from_user
        await send_start_photo(ctx.bot, update.effective_chat.id, user, ctx)
    else:
        await send_start_photo(ctx.bot, update.effective_chat.id, update.effective_user, ctx)
    return ConversationHandler.END


async def handle_report_problem(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Отправляем сообщение…")
    user = query.from_user
    url = ctx.user_data.get("last_url", "неизвестно")
    notify_text = (
        f"Problem report\n"
        f"From: @{user.username or user.first_name} (ID: `{user.id}`)\n"
        f"URL: {url}"
    )
    for admin_user_id in ADMIN_USER_IDS:
        try:
            await ctx.bot.send_message(
                admin_user_id,
                notify_text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.warning("report_problem send failed for %s: %s", admin_user_id, e)
    await query.message.reply_text(
        "✅ Сообщение отправлено администратору. Разберёмся!"
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ─── Редактирование из корзины ───────────────────────────────────────────────

async def start_from_cart_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: пользователь нажал 'Изменить уточнения' в корзине."""
    query = update.callback_query
    await query.answer()
    calc_id = int(query.data.split(":")[-1])
    user_id = query.from_user.id

    row = await db.get_calculation_by_id(calc_id, user_id)
    if not row:
        await query.message.reply_text("❌ Расчёт не найден.")
        return ConversationHandler.END

    rate = await er.get_rate()
    try:
        result = CalculationResult.from_dict(json.loads(row["calc_json"]), rate)
        draft = result.product
    except Exception as e:
        log.warning(f"start_from_cart_edit: failed to restore draft: {e}")
        await query.message.reply_text("❌ Не удалось восстановить данные товара.")
        return ConversationHandler.END

    _set_draft(ctx, draft)
    ctx.user_data["cart_edit_calc_id"] = calc_id
    # Запоминаем карточку корзины чтобы обновить её после редактирования
    ctx.user_data["cart_edit_msg_id"] = query.message.message_id
    ctx.user_data["cart_edit_chat_id"] = query.message.chat.id
    ctx.user_data["cart_edit_is_photo"] = bool(query.message.photo)
    ctx.user_data.pop("saved_share_code", None)
    ctx.user_data.pop("last_result", None)

    # Сразу в выбор вариантов (как после кнопки "Уточнить детали")
    groups = [g for g in (draft.original_variants or draft.variants or []) if len(g.get("options", [])) >= 2]
    ctx.user_data["variant_groups"] = groups
    ctx.user_data["variant_step"] = 0
    ctx.user_data["selected_variants"] = {}
    return await _show_variant_step(query.message, ctx)


async def handle_history_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Восстановить товар из истории и показать карточку (CONFIRM_PRODUCT)."""
    import json as _json
    query = update.callback_query
    await query.answer()

    calc_id = int(query.data.split(":")[-1])
    user_id = query.from_user.id

    row = await db.get_calculation_by_id(calc_id, user_id)
    if not row or not row.get("calc_json"):
        await query.message.reply_text("Расчёт не найден.")
        return ConversationHandler.END

    data_dict = _json.loads(row["calc_json"])
    saved_variants = data_dict.get("original_variants") or []
    draft = ProductDraft(
        url=data_dict.get("url", ""),
        platform=data_dict.get("platform", "unknown"),
        name=data_dict.get("name", ""),
        brand=data_dict.get("brand", ""),
        price_cny=data_dict.get("price_cny"),
        size="",         # сбрасываем — пользователь будет выбирать заново
        category=data_dict.get("category", ""),
        weight_kg=data_dict.get("weight_kg"),
        weight_estimated=data_dict.get("weight_estimated", False),
        city=data_dict.get("city", ""),
        delivery_type=data_dict.get("delivery_type", ""),
        image_url=data_dict.get("image_url", ""),
        specs=data_dict.get("specs") or {},
        available_sizes=data_dict.get("available_sizes") or [],
        notes=data_dict.get("notes", ""),
        variants=list(saved_variants),           # восстанавливаем варианты
        original_variants=list(saved_variants),  # и оригинал для "Изменить"
        variant_price_map=data_dict.get("variant_price_map") or {},
    )

    ctx.user_data.clear()
    _set_draft(ctx, draft)

    # Сохраняем ID сообщения истории чтобы вернуть кнопки при нажатии "Назад"
    ctx.user_data["_hist_msg_id"] = query.message.message_id
    ctx.user_data["_hist_chat_id"] = query.message.chat.id

    # Убираем кнопки с сообщения истории
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    return await _show_product_card(query.message, ctx, draft, from_history=True)


# ─── ConversationHandler ─────────────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, start_calc),
            CommandHandler("manual", manual_start),
            CommandHandler("calc", manual_start),
            CallbackQueryHandler(start_from_cart_edit, pattern=r"^cart:edit_calc:\d+$"),
            CallbackQueryHandler(handle_history_select, pattern=r"^hist:select:\d+$"),
        ],
        per_message=False,
        allow_reentry=False,
        states={
            AWAIT_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link_input),
            ],
            CONFIRM_PRODUCT: [
                CallbackQueryHandler(handle_history_select, pattern=r"^hist:select:\d+$"),
                CallbackQueryHandler(handle_specs_request, pattern="^confirm:specs$"),
                CallbackQueryHandler(handle_confirm_retry, pattern="^confirm:retry$"),
                CallbackQueryHandler(handle_specs_back, pattern="^specs:back$"),
                CallbackQueryHandler(handle_compare_back, pattern="^nav:back$"),
                CallbackQueryHandler(handle_clarify_start, pattern="^confirm:clarify$"),
                CallbackQueryHandler(handle_confirm_cart, pattern="^confirm:cart$"),
                CallbackQueryHandler(handle_confirm_added_back, pattern="^confirm:added_back$"),
                CallbackQueryHandler(handle_confirm_product, pattern="^confirm:"),
                CallbackQueryHandler(handle_compare_from_card, pattern="^compare:(wb|ozon|wb_ozon)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_calc),
            ],
            AWAIT_VARIANT_SELECTION: [
                CallbackQueryHandler(handle_variant_step_back, pattern="^var:step_back$"),
                CallbackQueryHandler(handle_variant_selection, pattern="^var:"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            AWAIT_VARIANT_PRICE: [
                CallbackQueryHandler(handle_variant_price_use_parsed, pattern="^var:price_use_parsed$"),
                CallbackQueryHandler(handle_variant_price_back, pattern="^var:price_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_variant_price),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            AWAIT_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price),
            ],
            AWAIT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name),
                CallbackQueryHandler(skip_name_callback, pattern="^skip:name$"),
            ],
            AWAIT_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_size),
                CallbackQueryHandler(skip_size_callback, pattern="^skip:size$"),
                CallbackQueryHandler(handle_nav_back, pattern="^nav:back$"),
            ],
            AWAIT_CATEGORY: [
                CallbackQueryHandler(handle_category, pattern="^cat:"),
                CallbackQueryHandler(handle_nav_back, pattern="^nav:back$"),
            ],
            AWAIT_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weight),
                CallbackQueryHandler(handle_nav_back, pattern="^nav:back$"),
            ],
            SHOW_RESULT: [
                CallbackQueryHandler(handle_compare_back, pattern="^nav:back$"),
                CallbackQueryHandler(
                    handle_result_action,
                    pattern="^(mode:|calc:|gen:|tpl:|share:|compare:)",
                ),
                # Новая ссылка — сбрасываем и начинаем заново
                MessageHandler(filters.TEXT & ~filters.COMMAND, start_calc),
            ],
            AWAIT_COMPARE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_compare_name),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CallbackQueryHandler(handle_report_problem, pattern="^report_problem$"),
            CallbackQueryHandler(start_from_cart_edit, pattern=r"^cart:edit_calc:\d+$"),
        ],
        name="main_conv",
        persistent=False,
    )



