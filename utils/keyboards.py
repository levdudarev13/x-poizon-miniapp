"""Фабрики клавиатур (InlineKeyboardMarkup)."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import CATEGORIES, CLIENT_MSG_TEMPLATES


def kb_confirm_product(
    has_price: bool,
    has_category: bool = False,
    has_name: bool = False,
    is_poizon: bool = False,
    has_active_variants: bool = False,
    has_specs: bool = False,
    from_history: bool = False,
) -> InlineKeyboardMarkup:
    """Кнопки под карточкой товара."""
    buttons = []
    # Кнопка корзины — первая и на всю ширину, только когда цена есть и расчёт готов
    if has_price and not has_active_variants:
        buttons.append([InlineKeyboardButton("🛒 Добавить в корзину", callback_data="confirm:cart")])
    if has_active_variants:
        buttons.append([InlineKeyboardButton("✏️ Уточнить мой вариант и цену", callback_data="confirm:clarify")])
    if has_specs:
        buttons.append([InlineKeyboardButton("🔍 Характеристики товара", callback_data="confirm:specs")])
    if has_name:
        buttons.append([
            InlineKeyboardButton("🟣 Сравнить с WB", callback_data="compare:wb"),
            InlineKeyboardButton("🔵 Сравнить с Ozon", callback_data="compare:ozon"),
        ])
    if from_history:
        buttons.append([InlineKeyboardButton("◀️ Назад к истории", callback_data="hist:back_card")])
    else:
        buttons.append([InlineKeyboardButton("❌ Отменить", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def kb_add_back(kb: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Добавить кнопку ◀️ Назад к любой клавиатуре."""
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(rows)


def kb_categories() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for key, (label, weight) in CATEGORIES.items():
        row.append(InlineKeyboardButton(f"{label} (~{weight} кг)", callback_data=f"cat:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Введу вес вручную", callback_data="cat:manual")])
    return InlineKeyboardMarkup(buttons)


def kb_result(mode: str = "client", has_name: bool = False) -> InlineKeyboardMarkup:
    """Кнопки под результатом расчёта."""
    if mode == "client":
        toggle_btn = InlineKeyboardButton("👁 Показать мне (с маржой)", callback_data="mode:buyer")
    else:
        toggle_btn = InlineKeyboardButton("👤 Режим клиента", callback_data="mode:client")

    rows = [
        [InlineKeyboardButton("🛒 Добавить в корзину", callback_data="calc:cart")],
        [toggle_btn],
        [InlineKeyboardButton("💾 Сохранить", callback_data="calc:save")],
        [
            InlineKeyboardButton("🔄 Пересчитать", callback_data="calc:recalc"),
            InlineKeyboardButton("🆕 Новый расчёт", callback_data="calc:new"),
        ],
        [InlineKeyboardButton("📨 Сообщение клиенту", callback_data="gen:msg")],
    ]
    if has_name:
        rows.append([
            InlineKeyboardButton("🟣 Сравнить с WB", callback_data="compare:wb"),
            InlineKeyboardButton("🔵 Сравнить с Ozon", callback_data="compare:ozon"),
        ])
    return InlineKeyboardMarkup(rows)


def kb_result_saved(share_code: str, mode: str = "client", has_name: bool = False) -> InlineKeyboardMarkup:
    """Кнопки после сохранения расчёта (добавляется кнопка с кодом)."""
    if mode == "client":
        toggle_btn = InlineKeyboardButton("👁 Показать мне (с маржой)", callback_data="mode:buyer")
    else:
        toggle_btn = InlineKeyboardButton("👤 Режим клиента", callback_data="mode:client")

    rows = [
        [InlineKeyboardButton("🛒 Открыть корзину", callback_data="cart:open")],
        [toggle_btn],
        [
            InlineKeyboardButton(f"🔗 Код расчёта: {share_code}", callback_data=f"share:{share_code}"),
        ],
        [
            InlineKeyboardButton("🔄 Пересчитать", callback_data="calc:recalc"),
            InlineKeyboardButton("🆕 Новый расчёт", callback_data="calc:new"),
        ],
        [InlineKeyboardButton("📨 Сообщение клиенту", callback_data="gen:msg")],
    ]
    if has_name:
        rows.append([
            InlineKeyboardButton("🟣 Сравнить с WB", callback_data="compare:wb"),
            InlineKeyboardButton("🔵 Сравнить с Ozon", callback_data="compare:ozon"),
        ])
    return InlineKeyboardMarkup(rows)


def kb_compare_cross(market: str) -> InlineKeyboardMarkup:
    """Кнопка сравнения с другим маркетплейсом после показа результата."""
    if market == "wb":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔵 Сравнить ещё с Ozon", callback_data="compare:ozon"),
        ]])
    else:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🟣 Сравнить ещё с WB", callback_data="compare:wb"),
        ]])


def kb_compare_cross_cart(market: str) -> InlineKeyboardMarkup:
    """Кнопка сравнения с другим маркетплейсом — для контекста корзины."""
    if market == "wb":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔵 Сравнить ещё с Ozon", callback_data="cart:cross:ozon"),
        ]])
    else:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🟣 Сравнить ещё с WB", callback_data="cart:cross:wb"),
        ]])


def kb_client_msg_templates() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Стандарт", callback_data="tpl:standard")],
        [InlineKeyboardButton("💳 Предоплата", callback_data="tpl:prepayment")],
        [InlineKeyboardButton("🚀 Отправил посылку", callback_data="tpl:tracking")],
        [InlineKeyboardButton("◀️ Назад", callback_data="gen:back")],
    ])


def kb_cart(item_count: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"🗑 Очистить корзину ({item_count} поз.)", callback_data="cart:clear")],
        [InlineKeyboardButton("🔄 Пересчитать всё", callback_data="cart:recalc")],
        [InlineKeyboardButton("◀️ Назад", callback_data="cart:back")],
    ]
    return InlineKeyboardMarkup(buttons)


def kb_history_numbered(items: list) -> InlineKeyboardMarkup:
    """Кнопки-цифры для истории (по 5 в ряд) + Назад."""
    buttons = []
    row = []
    for i, item in enumerate(items, 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"hist:select:{item['id']}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="hist:back")])
    return InlineKeyboardMarkup(buttons)


def kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить маржу", callback_data="settings:margin")],
        [InlineKeyboardButton("💱 Обновить курс", callback_data="settings:rate")],
        [InlineKeyboardButton("◀️ Закрыть", callback_data="settings:close")],
    ])


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ])
