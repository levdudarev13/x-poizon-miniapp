"""Async SQLite — все операции с базой данных."""
from contextlib import asynccontextmanager
import json
import random
import string
import aiosqlite
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import time
from config import (
    ADMIN_USER_IDS,
    DEFAULT_MARGIN_MIN_RUB,
    DEFAULT_MARGIN_STEPS,
    HISTORY_MAX_ITEMS,
    SHARE_CODE_LENGTH,
)
from services.delivery_pricing import (
    DEFAULT_DELIVERY_PRICE_SETTINGS,
    DEFAULT_DELIVERY_TIMING_SETTINGS,
)

ORDER_GUIDE_STEP_SIX_PREVIEW_SETTING_KEY = "order_guide_step_six_preview"
ORDER_GUIDE_STEP_EIGHT_PREVIEW_SETTING_KEY = "order_guide_step_eight_preview"
ORDER_GUIDE_STEP_SIX_SELECTED_ITEM_ID = "order-guide-step-six-item-3"
ORDER_GUIDE_STEP_EIGHT_ITEM_ID = "order-guide-step-eight-item-1"


def _build_order_guide_step_six_preview_item(
    item_id: str,
    short_name: str,
    name: str,
    size: str,
    price_rub: float,
    image_url: str,
) -> dict:
    return {
        "id": item_id,
        "short_name": short_name,
        "name": name,
        "size": size,
        "subtotal_rub": price_rub,
        "total_with_margin_rub": price_rub,
        "calc_json": json.dumps(
            {
                "image_url": image_url,
                "product": {
                    "name": name,
                    "image_url": image_url,
                },
            },
            ensure_ascii=False,
        ),
        "in_order": 0,
        "order_submitted": 0,
        "paid": 0,
        "shipped": 0,
        "arrived": 0,
    }


def _build_default_order_guide_step_six_preview() -> dict:
    return {
        "items": [
            _build_order_guide_step_six_preview_item(
                item_id="order-guide-step-six-item-1",
                short_name="ALORGEEK T-Shirt",
                name="ALORGEEK T Shirts Unisex Crew Neck Moderate Straight Fit",
                size="Apricot / L",
                price_rub=1196.4759,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20250312/e1ed99bb50e44546916e90394b66e913.jpg",
            ),
            _build_order_guide_step_six_preview_item(
                item_id="order-guide-step-six-item-2",
                short_name="DIOR Perfume Set",
                name="DIOR Men's Perfume Sample, Woody Fougere 10ml Birthday Gift For Girlfriend",
                size="10ml*8 / Shopping Bag Not Included",
                price_rub=8055.745999999999,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20250312/b74f5bd0fa294700bfaefcc7e3c2c6d4.jpg",
            ),
            _build_order_guide_step_six_preview_item(
                item_id=ORDER_GUIDE_STEP_SIX_SELECTED_ITEM_ID,
                short_name="Nike Sb Janoski+",
                name="Nike Sb Janoski+ Lilac Medium Soft Pink",
                size="42",
                price_rub=5067.50993,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20251205/702385d2d6294e90bcc78d1e2b0b5295.jpg",
            ),
            _build_order_guide_step_six_preview_item(
                item_id="order-guide-step-six-item-4",
                short_name="Alexander McQueen",
                name="Alexander McQueen Oversized Lace Up Sneakers Women's",
                size="36 / Original Shoe Box Not Included",
                price_rub=50970.288905,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20251217/e1b8757a474f4b499ca3f064e8921af1.jpg",
            ),
            _build_order_guide_step_six_preview_item(
                item_id="order-guide-step-six-item-5",
                short_name="Nike Dunk Low Cacao",
                name="Nike Dunk Low Cacao Wow Women's",
                size="43",
                price_rub=10072.16,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20251206/6c8447a89bc24797a6429732cc71ab5d.jpg",
            ),
        ],
        "selectedIds": [ORDER_GUIDE_STEP_SIX_SELECTED_ITEM_ID],
        "footerActionText": "В заявку",
    }


DEFAULT_ORDER_GUIDE_STEP_SIX_PREVIEW = json.dumps(
    _build_default_order_guide_step_six_preview(),
    ensure_ascii=False,
)


def _build_order_guide_step_eight_preview_item(
    item_id: str,
    short_name: str,
    name: str,
    size: str,
    price_cny: float,
    weight_kg: float,
    weight_estimated: bool,
    subtotal_rub: float,
    image_url: str,
) -> dict:
    return {
        "id": item_id,
        "short_name": short_name,
        "name": name,
        "size": size,
        "price_cny": price_cny,
        "weight_kg": weight_kg,
        "weight_estimated": weight_estimated,
        "subtotal_rub": subtotal_rub,
        "total_with_margin_rub": subtotal_rub,
        "calc_json": json.dumps(
            {
                "image_url": image_url,
                "product": {
                    "name": name,
                    "price_cny": price_cny,
                    "weight_kg": weight_kg,
                    "weight_estimated": weight_estimated,
                    "image_url": image_url,
                },
            },
            ensure_ascii=False,
        ),
        "in_order": 1,
        "order_submitted": 0,
        "paid": 0,
        "shipped": 0,
        "arrived": 0,
    }


def _build_default_order_guide_step_eight_preview() -> dict:
    delivery_settings = {
        "commission_pct": "10.0",
        "min_commission_rub": "250.0",
        "delivery_air_moscow_rub_500g": "1500.0",
        "delivery_standard_moscow_rub_500g": "500.0",
        "delivery_cdek_russia_rub_500g": "500.0",
        "delivery_air_moscow_days": "5-10 дней",
        "delivery_standard_moscow_days": "3-4 недели",
        "delivery_cdek_russia_days": "2-5 дней",
    }

    return {
        "items": [
            _build_order_guide_step_eight_preview_item(
                item_id=ORDER_GUIDE_STEP_EIGHT_ITEM_ID,
                short_name="Nike Sb Janoski кеды",
                name="Nike Sb Janoski+ Lilac Medium Soft Pink",
                size="42",
                price_cny=323.0,
                weight_kg=1.0,
                weight_estimated=True,
                subtotal_rub=5067.50993,
                image_url="https://cdn.poizon.com/pro-img/origin-img/20251205/702385d2d6294e90bcc78d1e2b0b5295.jpg",
            ),
        ],
        "deliveryStatus": {
            "isComplete": True,
            "deliveryData": {
                "recipient_name": "Денис Рыжов",
                "phone": "+79510204901",
                "city": "Владивосток",
                "street": "Жуковского",
                "house": "13",
                "apartment": "123",
                "comment": "Привет",
            },
            "updatedAt": "2026-03-25 02:38:53",
        },
        "pricingState": {
            "adminSettings": delivery_settings,
            "deliveryInfo": {
                "standard_days": delivery_settings["delivery_standard_moscow_days"],
                "express_days": delivery_settings["delivery_air_moscow_days"],
                "cdek_days": delivery_settings["delivery_cdek_russia_days"],
            },
            "rateRubPerCny": 11.4481,
        },
        "deliveryType": "standard",
    }


DEFAULT_ORDER_GUIDE_STEP_EIGHT_PREVIEW = json.dumps(
    _build_default_order_guide_step_eight_preview(),
    ensure_ascii=False,
)

# Дефолтные настройки расценок (используются до первого сохранения в БД)
DEFAULT_ADMIN_SETTINGS = {
    "commission_pct":      "10.0",         # комиссия/маржа, %
    "min_commission_rub":  "300.0",        # минимальная комиссия, ₽
    **DEFAULT_DELIVERY_PRICE_SETTINGS,
    **DEFAULT_DELIVERY_TIMING_SETTINGS,
    "rate_override":       "",             # курс ¥→₽ (пусто = авто)
    "rate_override_until": "0",            # timestamp до которого действует ручной курс
}

DEFAULT_ADMIN_SETTINGS[ORDER_GUIDE_STEP_SIX_PREVIEW_SETTING_KEY] = DEFAULT_ORDER_GUIDE_STEP_SIX_PREVIEW
DEFAULT_ADMIN_SETTINGS[ORDER_GUIDE_STEP_EIGHT_PREVIEW_SETTING_KEY] = DEFAULT_ORDER_GUIDE_STEP_EIGHT_PREVIEW

SHOWCASE_SLOT_COUNT = 10
ABOUT_DETAILS_SLIDE_COUNT = 7
FAQ_QUESTION_MAX_LENGTH = 180
FAQ_ANSWER_MAX_LENGTH = 2400
FAQ_LINK_URL_MAX_LENGTH = 640
FAQ_BUTTON_LABEL_MAX_LENGTH = 80
PROMO_BANNER_MAX_COUNT = 12
PROMO_BANNER_LABEL_MAX_LENGTH = 80
PROMO_BANNER_TITLE_MAX_LENGTH = 140
PROMO_BANNER_SUBTITLE_MAX_LENGTH = 220
PROMO_BANNER_BUTTON_LABEL_MAX_LENGTH = 80
PROMO_BANNER_BUTTON_COLOR_MAX_LENGTH = 32
PROMO_BANNER_LINK_URL_MAX_LENGTH = 640
PROMO_BANNER_IMAGE_URL_MAX_LENGTH = 640
PROMO_BANNER_IMAGE_ALT_MAX_LENGTH = 160
PROMO_BANNER_BLOCK_MAX_COUNT = 18
PROMO_BANNER_BLOCK_ID_MAX_LENGTH = 64
PROMO_BANNER_BLOCK_TEXT_MAX_LENGTH = 2800
PROMO_BANNER_BLOCK_CAPTION_MAX_LENGTH = 220
PROMO_BANNER_BLOCK_LIST_ITEM_MAX_LENGTH = 240
PROMO_BANNER_ALLOWED_BLOCK_TYPES = ("heading", "subheading", "text", "list", "image", "button")
DEFAULT_PROMO_BANNER_BUTTON_LABEL = "Подробнее"
PROMO_BANNER_ALLOWED_BUTTON_COLORS = (
    "acid-lime",
    "laser-cyan",
    "hyper-pink",
    "solar-orange",
    "acid-red",
    "nova-blue",
    "chrome-ice",
)
DEFAULT_PROMO_BANNER_BUTTON_COLOR = "acid-lime"
ORIGINALITY_FAQ_ENTRY = {
    "question": "Оригинальные ли товары я получу?",
    "answer": (
        "Да, исключительно оригинал.\n\n"
        "Китайская площадка-агрегатор гарантирует подлинность, и каждый товар проходит несколько этапов проверки:\n"
        "- проверка более чем по 10 критериям;\n"
        "- просвет ультрафиолетом;\n"
        "- химический анализ для спорных случаев.\n\n"
        "После проверки на каждую позицию крепятся индивидуальные клипсы и выдается сертификат.\n\n"
        "Дополнительно команда нашего сервиса вместе с партнерами Legit Check проводит вторую проверку на подлинность и брак, прикладывая собственный сертификат к каждому заказу."
    ),
    "link_url": "https://vk.ru/@logisticsx-pricing",
}
DELIVERY_TIME_FAQ_ENTRY = {
    "question": "Сколько времени занимает доставка?",
    "answer": (
        "Мы предлагаем два основных тарифа:\n\n"
        "- Обычная доставка: в среднем занимает 14-20 дней.\n"
        "- Экспресс-доставка: самый быстрый вариант, от 1 до 7 дней с момента поступления товара на склад в Китае.\n\n"
        "Сроки могут незначительно увеличиваться из-за государственных праздников в Китае, например Китайского Нового года, или во время массовых распродаж вроде 11.11. О таких изменениях мы всегда предупреждаем заранее."
    ),
    "link_url": "https://vk.ru/@logisticsx-pricing",
}
PRICE_BREAKDOWN_FAQ_ENTRY = {
    "question": "Из чего складывается итоговая стоимость заказа?",
    "answer": (
        "Цена формируется из нескольких составляющих:\n\n"
        "- Курс юаня: мы используем выгодный курс, потому что производим обмен напрямую через биржи.\n"
        "- Страховка: обязательное условие для вашей уверенности. В случае утери или порчи груза мы гарантируем полный возврат средств.\n"
        "- Доставка: рассчитывается по факту прибытия посылки в Москву на основании её веса и габаритов. Обычная доставка — 1000 ₽/кг, экспресс — 2800 ₽/кг."
    ),
    "link_url": "https://vk.ru/@logisticsx-pricing",
}
BUTTONS_MEANING_FAQ_ENTRY = {
    "question": "Что означают цветные кнопки в приложении площадки?",
    "answer": (
        "В приложении есть несколько цветовых меток и отдельных обозначений:\n\n"
        "- Бирюзовая кнопка: стандартный заказ напрямую от бренда, это самый быстрый вариант обработки.\n"
        "- Черная кнопка: доставка от стороннего поставщика. Она может быть выгоднее по цене, но обычно занимает больше времени.\n"
        "- Кнопка 95: возможность купить оригинальные Б/У вещи или товары без полного комплекта по более выгодной цене.\n"
        "- Отдельный символ у товара: позиция находится за пределами Китая, например в Европе, США или Японии. По таким товарам сроки доставки обычно длиннее из-за сложной логистики и таможни."
    ),
    "link_url": "https://vk.ru/@logisticsx-information",
}
ORDER_RECEIVE_FAQ_ENTRY = {
    "question": "Как я могу получить свой заказ в России?",
    "answer": (
        "Мы предлагаем два варианта получения заказа:\n\n"
        "- В Москве: доступен самовывоз по адресу ул. Смольная, 24А, БЦ, 11 этаж, с 10:00 до 22:00.\n"
        "- В регионах: мы отправляем заказы через СДЭК на следующий день после их прибытия в Москву. Благодаря нашему контракту со СДЭКом стоимость доставки для клиентов ниже на 70%."
    ),
    "link_url": "https://vk.ru/@logisticsx-pricing",
}
PARTNER_PROGRAM_FAQ_ENTRY = {
    "question": "Могу ли я заработать, рекомендуя ваш сервис?",
    "answer": (
        "Да, у нас действует партнерская программа для клиентов, которые уже совершали заказы.\n\n"
        "Вы можете получать выплаты за привлечение друзей:\n"
        "- За обычные заказы: от 500 до 1500 рублей, в зависимости от суммы трат вашего друга.\n"
        "- За Mystery Box: 10% от стоимости бокса.\n\n"
        "Чтобы бонус был зачислен, ваш знакомый должен указать ваше имя и фамилию или ссылку на ваш аккаунт при оформлении заказа."
    ),
    "link_url": "https://vk.ru/@logisticsx-partner",
}
MYSTERY_BOX_FAQ_ENTRY = {
    "question": "Что такое Mystery Box и в чем их преимущество?",
    "answer": (
        "Mystery Box — это лимитированные серии боксов размеров M, L и XL стоимостью от 5 000 до 15 000 рублей.\n\n"
        "Главные преимущества:\n"
        "- гарантированная окупаемость: вы никогда не уйдете в минус;\n"
        "- внутри могут оказаться вещи брендов Louis Vuitton или Gucci, стоимость которых в несколько раз превышает цену самого бокса;\n"
        "- для повторных покупателей боксов действует кэшбэк 10%."
    ),
    "link_url": "https://vk.ru/@logisticsx-partner",
}
WHOLESALE_FAQ_ENTRY = {
    "question": "Есть ли у вас специальные условия для оптовиков?",
    "answer": (
        "Да, у нас есть специальные условия для оптовых клиентов.\n\n"
        "Заказ считается оптовым, если в нем более 5 позиций.\n\n"
        "Для таких клиентов мы предлагаем:\n"
        "- индивидуальные условия по цене;\n"
        "- индивидуальные условия по доставке в зависимости от типа и количества товара.\n\n"
        "Мы уже успешно сотрудничаем с крупными ресейлерами и оффлайн-магазинами в России."
    ),
    "link_url": "https://vk.ru/@logisticsx-pricing",
}
FAILED_CHECK_FAQ_ENTRY = {
    "question": "Что делать, если товар не прошел проверку площадки или пришел брак?",
    "answer": (
        "Обычно около 5% товаров не проходят внутреннюю проверку платформы на оригинальность или качество.\n\n"
        "В такой ситуации мы предлагаем два варианта:\n"
        "- повторный выкуп товара;\n"
        "- полный возврат средств.\n\n"
        "Если инцидент произошел уже во время транспортировки, например при утере или повреждении, мы сразу возвращаем деньги благодаря обязательной страховке."
    ),
    "link_url": "https://vk.ru/@logisticsx-information",
}
FAST_ORDER_FAQ_ENTRY = {
    "question": "Как быстрее всего рассчитать стоимость и оформить заказ?",
    "answer": (
        "Для вашего удобства работает мини-приложение, где можно мгновенно узнать стоимость товара и оформить заказ.\n\n"
        "Если вы не знаете, с чего начать и как пользоваться мини-приложением, вы можете пройти обучение, нажав на кнопку ниже.\n\n"
        "Также вы всегда можете написать менеджерам в личные сообщения сообщества. Среднее время ответа составляет всего 2 минуты."
    ),
    "link_url": "",
    "button_label": "Пройти обучение",
}
DEFAULT_FAQ_ENTRIES = (
    ORIGINALITY_FAQ_ENTRY,
    DELIVERY_TIME_FAQ_ENTRY,
    PRICE_BREAKDOWN_FAQ_ENTRY,
    BUTTONS_MEANING_FAQ_ENTRY,
    ORDER_RECEIVE_FAQ_ENTRY,
    PARTNER_PROGRAM_FAQ_ENTRY,
    MYSTERY_BOX_FAQ_ENTRY,
    WHOLESALE_FAQ_ENTRY,
    FAILED_CHECK_FAQ_ENTRY,
    FAST_ORDER_FAQ_ENTRY,
)

DEFAULT_PROMO_BANNERS = (
    {
        "label": "Logistics X",
        "title": "Первый вход в miniapp без лишних переходов",
        "subtitle": "Здесь собраны быстрые действия для первого заказа и актуальные условия сервиса.",
        "image_url": "/S4vXEAP-ycA.jpg",
        "image_alt": "Промо-баннер Logistics X",
        "story_image_url": "/S4vXEAP-ycA.jpg",
        "story_image_alt": "Промо-баннер Logistics X",
        "button_label": "Подробнее",
        "button_url": "https://vk.ru/logisticsx",
        "button_color": "acid-lime",
        "show_on_entry": True,
        "blocks": [
            {
                "id": "welcome-heading",
                "type": "heading",
                "text": "Что можно сделать внутри miniapp",
            },
            {
                "id": "welcome-copy",
                "type": "text",
                "text": "Рассчитать стоимость по ссылке Poizon, собрать корзину и отправить заказ можно прямо внутри Telegram без пересылки данных вручную.",
            },
            {
                "id": "welcome-list",
                "type": "list",
                "items": [
                    "Мгновенный расчет по ссылке на товар",
                    "Корзина, доставка и отправка заказа в одном потоке",
                    "Поддержка и статус заказов всегда под рукой",
                ],
            },
        ],
    },
    {
        "label": "Partner",
        "title": "Партнерская программа Logistics X",
        "subtitle": "Приглашайте друзей и переводите заинтересованных покупателей через свою ссылку.",
        "image_url": "/17.png",
        "image_alt": "Партнерский баннер Logistics X",
        "story_image_url": "/17.png",
        "story_image_alt": "Партнерский баннер Logistics X",
        "button_label": "Узнать условия",
        "button_url": "https://vk.ru/@logisticsx-partner",
        "button_color": "hyper-pink",
        "show_on_entry": False,
        "blocks": [
            {
                "id": "partner-heading",
                "type": "heading",
                "text": "Как работает партнерская механика",
            },
            {
                "id": "partner-copy",
                "type": "text",
                "text": "После оформления заказов ваши рекомендации можно переводить в вознаграждение. Важно, чтобы покупатель указал вашу ссылку или имя при оформлении.",
            },
            {
                "id": "partner-list",
                "type": "list",
                "items": [
                    "Выплаты за приглашенных покупателей",
                    "Отдельные условия для mystery box и повторных клиентов",
                    "Подробные правила и примеры начислений по кнопке ниже",
                ],
            },
        ],
    },
)

DEFAULT_ABOUT_DETAILS_SLIDES = (
    {
        "slot": 1,
        "image_url": "/011-017/011.jpg",
        "image_alt": "Слайд 1",
    },
    {
        "slot": 2,
        "image_url": "/011-017/012.png",
        "image_alt": "Слайд 2",
    },
    {
        "slot": 3,
        "image_url": "/011-017/013.jpg",
        "image_alt": "Слайд 3",
    },
    {
        "slot": 4,
        "image_url": "/011-017/014.png",
        "image_alt": "Слайд 4",
    },
    {
        "slot": 5,
        "image_url": "/011-017/015.png",
        "image_alt": "Слайд 5",
    },
    {
        "slot": 6,
        "image_url": "/011-017/016.png",
        "image_alt": "Слайд 6",
    },
    {
        "slot": 7,
        "image_url": "/011-017/017.png",
        "image_alt": "Слайд 7",
    },
)

DB_PATH = "buyer_bot.db"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MINIAPP_ACTIVE_LOOKBACK_DAYS = 7
ADMIN_BROADCAST_SEGMENT_LABELS = {
    "all_users": "Все пользователи",
    "active_miniapp_7d": "Активные miniapp за 7 дней",
    "cart_holders": "Есть товары в корзине",
    "request_builders": "Собирают заявку",
    "ordered_customers": "Оформили/оплатили заказ",
}
ADMIN_SEGMENT_FALLBACK_LABELS = {
    "ordered_customers": "Оформили/оплатили заказ",
    "request_builders": "Собирают заявку",
    "cart_holders": "Держат товары только в корзине",
    "other_users": "Остальные пользователи",
}
DELIVERY_PROFILE_FIELDS = (
    "recipient_name",
    "phone",
    "city",
    "street",
    "house",
    "apartment",
    "comment",
)


def _now_in_moscow(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(MOSCOW_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=MOSCOW_TZ)
    return now.astimezone(MOSCOW_TZ)


def _to_sqlite_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _moscow_day_bounds_utc(now: datetime | None = None) -> tuple[str, str]:
    current = _now_in_moscow(now)
    start_local = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return _to_sqlite_utc(start_local), _to_sqlite_utc(end_local)


def _moscow_day_key(now: datetime | None = None) -> str:
    return _now_in_moscow(now).strftime("%Y-%m-%d")


def _moscow_recent_start_key(now: datetime | None = None, *, days: int = MINIAPP_ACTIVE_LOOKBACK_DAYS) -> str:
    safe_days = max(1, int(days or 1))
    current = _now_in_moscow(now)
    return (current - timedelta(days=safe_days - 1)).strftime("%Y-%m-%d")


def _admin_filter_clause(*, prefix: str = "AND", column: str = "user_id") -> tuple[str, list[int]]:
    admin_ids = [int(user_id) for user_id in ADMIN_USER_IDS if int(user_id or 0) > 0]
    if not admin_ids:
        return "", []
    placeholders = ",".join("?" for _ in admin_ids)
    return f" {prefix} {column} NOT IN ({placeholders})", admin_ids


def _timestamp_in_window(value: object, start_utc: str, end_utc: str) -> bool:
    timestamp = str(value or "").strip()
    if not timestamp:
        return False
    return start_utc <= timestamp < end_utc


def _sum_total_with_margin(rows: list[aiosqlite.Row]) -> float:
    return float(sum(float(row["total_with_margin_rub"] or 0) for row in rows))


def _normalize_delivery_profile_payload(delivery_payload: dict | None) -> dict:
    payload = delivery_payload if isinstance(delivery_payload, dict) else {}
    return {
        field: str(payload.get(field) or "").strip()
        for field in DELIVERY_PROFILE_FIELDS
    }


def _normalize_faq_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _normalize_faq_link_url(value: object) -> str:
    normalized_url = str(value or "").strip()[:FAQ_LINK_URL_MAX_LENGTH]
    if not normalized_url:
        return ""
    if normalized_url.startswith(("http://", "https://", "tg://")):
        return normalized_url
    return f"https://{normalized_url.lstrip('/')}"


def _normalize_faq_button_label(value: object) -> str:
    return str(value or "").strip()[:FAQ_BUTTON_LABEL_MAX_LENGTH]


def _normalize_faq_entry_payload(faq_payload: dict | None) -> dict:
    payload = faq_payload if isinstance(faq_payload, dict) else {}
    return {
        "question": _normalize_faq_text(payload.get("question"), FAQ_QUESTION_MAX_LENGTH),
        "answer": _normalize_faq_text(payload.get("answer"), FAQ_ANSWER_MAX_LENGTH),
        "link_url": _normalize_faq_link_url(payload.get("link_url")),
        "button_label": _normalize_faq_button_label(payload.get("button_label")),
    }


def _normalize_banner_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _normalize_banner_link_url(value: object) -> str:
    normalized_url = str(value or "").strip()[:PROMO_BANNER_LINK_URL_MAX_LENGTH]
    if not normalized_url:
        return ""
    if normalized_url.startswith(("http://", "https://", "tg://", "mailto:")):
        return normalized_url
    return f"https://{normalized_url.lstrip('/')}"


def _normalize_banner_button_color(value: object) -> str:
    normalized_color = str(value or "").strip().lower()[:PROMO_BANNER_BUTTON_COLOR_MAX_LENGTH]
    if normalized_color == "volt-yellow":
        normalized_color = "acid-red"
    if normalized_color in PROMO_BANNER_ALLOWED_BUTTON_COLORS:
        return normalized_color
    return DEFAULT_PROMO_BANNER_BUTTON_COLOR


def _normalize_banner_image_url(value: object) -> str:
    normalized_url = str(value or "").strip()[:PROMO_BANNER_IMAGE_URL_MAX_LENGTH]
    if not normalized_url:
        return ""
    if normalized_url.startswith(("/", "http://", "https://")):
        return normalized_url
    return f"/{normalized_url.lstrip('/')}"


def _normalize_banner_block_id(value: object, fallback: str) -> str:
    raw_value = str(value or "").strip()[:PROMO_BANNER_BLOCK_ID_MAX_LENGTH]
    normalized = "".join(
        char if char.isalnum() or char in ("-", "_") else "-"
        for char in raw_value
    ).strip("-_")
    if normalized:
        return normalized[:PROMO_BANNER_BLOCK_ID_MAX_LENGTH]
    return fallback[:PROMO_BANNER_BLOCK_ID_MAX_LENGTH]


def _normalize_banner_blocks(raw_blocks: object) -> list[dict]:
    blocks = raw_blocks if isinstance(raw_blocks, list) else []
    normalized_blocks: list[dict] = []
    used_ids: set[str] = set()

    for index, raw_block in enumerate(blocks[:PROMO_BANNER_BLOCK_MAX_COUNT], start=1):
        if not isinstance(raw_block, dict):
            continue

        block_type = str(raw_block.get("type") or "").strip().lower()
        if block_type not in PROMO_BANNER_ALLOWED_BLOCK_TYPES:
            continue

        fallback_id = f"block-{index}"
        block_id = _normalize_banner_block_id(raw_block.get("id"), fallback_id)
        while block_id in used_ids:
            block_id = _normalize_banner_block_id(f"{block_id}-{index}", fallback_id)
        used_ids.add(block_id)

        if block_type in {"heading", "subheading", "text"}:
            text_value = _normalize_banner_text(
                raw_block.get("text"),
                PROMO_BANNER_BLOCK_TEXT_MAX_LENGTH,
            )
            if not text_value:
                continue
            normalized_blocks.append({
                "id": block_id,
                "type": block_type,
                "text": text_value,
            })
            continue

        if block_type == "list":
            raw_items = raw_block.get("items")
            if isinstance(raw_items, str):
                raw_items = raw_items.splitlines()
            items = [
                _normalize_banner_text(item, PROMO_BANNER_BLOCK_LIST_ITEM_MAX_LENGTH)
                for item in (raw_items if isinstance(raw_items, list) else [])
            ]
            items = [item for item in items if item]
            if not items:
                continue
            normalized_blocks.append({
                "id": block_id,
                "type": "list",
                "items": items,
            })
            continue

        if block_type == "button":
            button_url = _normalize_banner_link_url(raw_block.get("button_url"))
            button_label = _normalize_banner_text(
                raw_block.get("button_label"),
                PROMO_BANNER_BUTTON_LABEL_MAX_LENGTH,
            )
            if not button_label and not button_url:
                continue
            normalized_blocks.append({
                "id": block_id,
                "type": "button",
                "button_label": button_label,
                "button_url": button_url,
                "button_color": _normalize_banner_button_color(raw_block.get("button_color")),
            })
            continue

        image_url = _normalize_banner_image_url(raw_block.get("image_url"))
        if not image_url:
            continue

        normalized_blocks.append({
            "id": block_id,
            "type": "image",
            "image_url": image_url,
            "alt_text": _normalize_banner_text(
                raw_block.get("alt_text"),
                PROMO_BANNER_IMAGE_ALT_MAX_LENGTH,
            ),
            "caption": _normalize_banner_text(
                raw_block.get("caption"),
                PROMO_BANNER_BLOCK_CAPTION_MAX_LENGTH,
            ),
        })

    return normalized_blocks


def _normalize_banner_entry_payload(banner_payload: dict | None) -> dict:
    payload = banner_payload if isinstance(banner_payload, dict) else {}
    normalized_blocks = _normalize_banner_blocks(payload.get("blocks"))
    primary_button_block = next(
        (block for block in normalized_blocks if str(block.get("type") or "") == "button"),
        None,
    )
    button_url = _normalize_banner_link_url(payload.get("button_url"))
    button_label = _normalize_banner_text(
        payload.get("button_label"),
        PROMO_BANNER_BUTTON_LABEL_MAX_LENGTH,
    )
    raw_button_color = payload.get("button_color")
    button_color = _normalize_banner_button_color(raw_button_color)

    if primary_button_block:
        button_label = str(primary_button_block.get("button_label") or "")
        button_url = str(primary_button_block.get("button_url") or "")
        if str(raw_button_color or "").strip() == "":
            button_color = _normalize_banner_button_color(primary_button_block.get("button_color"))
    elif button_url or button_label:
        normalized_blocks.append({
            "id": _normalize_banner_block_id("", f"button-{len(normalized_blocks) + 1}"),
            "type": "button",
            "button_label": button_label,
            "button_url": button_url,
            "button_color": button_color,
        })

    title = _normalize_banner_text(payload.get("title"), PROMO_BANNER_TITLE_MAX_LENGTH)
    label = _normalize_banner_text(payload.get("label"), PROMO_BANNER_LABEL_MAX_LENGTH)
    story_image_url = _normalize_banner_image_url(payload.get("story_image_url"))

    return {
        "label": label,
        "title": title,
        "subtitle": _normalize_banner_text(payload.get("subtitle"), PROMO_BANNER_SUBTITLE_MAX_LENGTH),
        "button_label": button_label,
        "button_url": button_url,
        "button_color": button_color,
        "image_url": _normalize_banner_image_url(payload.get("image_url")),
        "image_alt": _normalize_banner_text(
            payload.get("image_alt"),
            PROMO_BANNER_IMAGE_ALT_MAX_LENGTH,
        ) or title,
        "story_image_url": story_image_url,
        "story_image_alt": (
            _normalize_banner_text(
                payload.get("story_image_alt"),
                PROMO_BANNER_IMAGE_ALT_MAX_LENGTH,
            ) or title
        ) if story_image_url else "",
        "show_on_entry": 1 if bool(payload.get("show_on_entry")) else 0,
        "blocks": normalized_blocks,
    }


@asynccontextmanager
async def _connect():
    """Open DB connection with WAL-safe busy_timeout."""
    db = await aiosqlite.connect(DB_PATH)
    try:
        await db.execute("PRAGMA busy_timeout=5000")
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT,
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                margin_steps TEXT NOT NULL DEFAULT '[]',
                margin_min_rub REAL NOT NULL DEFAULT 500.0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS calculations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                product_url TEXT,
                platform    TEXT,
                name        TEXT,
                price_cny   REAL,
                size        TEXT,
                category    TEXT,
                weight_kg   REAL,
                weight_estimated INTEGER DEFAULT 0,
                city        TEXT,
                delivery_type TEXT,
                subtotal_rub REAL,
                total_with_margin_rub REAL,
                margin_rub  REAL,
                margin_percent REAL,
                calc_json   TEXT,
                share_code  TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS cart_items (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                calculation_id INTEGER NOT NULL,
                in_order       INTEGER NOT NULL DEFAULT 0,
                added_at       TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS delivery_profiles (
                user_id       INTEGER PRIMARY KEY,
                delivery_json TEXT NOT NULL DEFAULT '{}',
                updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS admin_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS admin_showcase_slots (
                slot         INTEGER PRIMARY KEY,
                url          TEXT NOT NULL DEFAULT '',
                product_json TEXT NOT NULL DEFAULT '',
                updated_at   REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS admin_about_slides (
                slot       INTEGER PRIMARY KEY,
                image_url  TEXT NOT NULL DEFAULT '',
                image_alt  TEXT NOT NULL DEFAULT '',
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS admin_banners (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                label        TEXT NOT NULL DEFAULT '',
                title        TEXT NOT NULL DEFAULT '',
                subtitle     TEXT NOT NULL DEFAULT '',
                button_label TEXT NOT NULL DEFAULT '',
                button_url   TEXT NOT NULL DEFAULT '',
                button_color TEXT NOT NULL DEFAULT 'acid-lime',
                image_url    TEXT NOT NULL DEFAULT '',
                image_alt    TEXT NOT NULL DEFAULT '',
                story_image_url TEXT NOT NULL DEFAULT '',
                story_image_alt TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '[]',
                position     INTEGER NOT NULL DEFAULT 0,
                show_on_entry INTEGER NOT NULL DEFAULT 0,
                created_at   REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at   REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS faq_entries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                question   TEXT NOT NULL DEFAULT '',
                answer     TEXT NOT NULL DEFAULT '',
                link_url   TEXT NOT NULL DEFAULT '',
                button_label TEXT NOT NULL DEFAULT '',
                position   INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS exchange_rates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                cny_rub    REAL NOT NULL,
                usd_rub    REAL NOT NULL,
                eur_rub    REAL NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_messages (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                username TEXT    NOT NULL DEFAULT '',
                msg_type TEXT    NOT NULL DEFAULT 'contact',
                text     TEXT    NOT NULL,
                sent_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS miniapp_activity_daily (
                user_id       INTEGER NOT NULL,
                activity_date TEXT    NOT NULL,
                first_seen_at TEXT    NOT NULL DEFAULT (datetime('now')),
                last_seen_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                request_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, activity_date)
            );
        """)
        await db.executemany(
            "INSERT OR IGNORE INTO admin_settings (key, value, updated_at) VALUES (?,?,?)",
            [
                (key, str(value), time.time())
                for key, value in DEFAULT_ADMIN_SETTINGS.items()
            ],
        )
        # Миграции cart_items
        for col, col_type in [
            ("in_order",       "INTEGER NOT NULL DEFAULT 0"),
            ("order_added_at", "TEXT"),
            ("paid",           "INTEGER NOT NULL DEFAULT 0"),
            ("shipped",        "INTEGER NOT NULL DEFAULT 0"),
            ("arrived",        "INTEGER NOT NULL DEFAULT 0"),
            ("order_submitted","INTEGER NOT NULL DEFAULT 0"),
            ("tracking_number","TEXT NOT NULL DEFAULT ''"),
            ("item_number",    "TEXT NOT NULL DEFAULT ''"),
            ("delivery_snapshot_json", "TEXT NOT NULL DEFAULT ''"),
            ("submission_batch_id", "TEXT NOT NULL DEFAULT ''"),
            ("submitted_at", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE cart_items ADD COLUMN {col} {col_type}")
                await db.commit()
            except Exception:
                pass  # колонка уже существует

        # Миграция: short_name для корзины
        try:
            await db.execute("ALTER TABLE calculations ADD COLUMN short_name TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Миграция: добавить бан-колонки в users
        for col, col_type in [
            ("first_name",          "TEXT    NOT NULL DEFAULT ''"),
            ("last_name",           "TEXT    NOT NULL DEFAULT ''"),
            ("ban_level",           "INTEGER DEFAULT 0"),
            ("ban_until",           "REAL    DEFAULT 0"),
            ("ban_last_notified",   "REAL    DEFAULT 0"),
            ("order_removes_today", "INTEGER DEFAULT 0"),
            ("order_removes_date",  "TEXT    DEFAULT ''"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                await db.commit()
            except Exception:
                pass  # колонка уже существует

        try:
            await db.execute("ALTER TABLE faq_entries ADD COLUMN link_url TEXT NOT NULL DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE faq_entries ADD COLUMN button_label TEXT NOT NULL DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        try:
            await db.execute(
                f"ALTER TABLE admin_banners ADD COLUMN button_color TEXT NOT NULL DEFAULT '{DEFAULT_PROMO_BANNER_BUTTON_COLOR}'"
            )
            await db.commit()
        except Exception:
            pass

        story_columns_added = False
        for col, col_type in [
            ("story_image_url", "TEXT NOT NULL DEFAULT ''"),
            ("story_image_alt", "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                await db.execute(f"ALTER TABLE admin_banners ADD COLUMN {col} {col_type}")
                await db.commit()
                story_columns_added = True
            except Exception:
                pass

        if story_columns_added:
            try:
                await db.execute(
                    "UPDATE admin_banners SET story_image_url=image_url "
                    "WHERE COALESCE(story_image_url, '') = '' AND COALESCE(image_url, '') != ''"
                )
                await db.execute(
                    "UPDATE admin_banners SET story_image_alt=image_alt "
                    "WHERE COALESCE(story_image_alt, '') = '' AND COALESCE(image_alt, '') != ''"
                )
                await db.commit()
            except Exception:
                pass

        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM faq_entries") as cur:
            faq_count_row = await cur.fetchone()

        if int((faq_count_row or [0])[0] or 0) > 0:
            await _ensure_default_faq_entries(db)

        async with db.execute("SELECT COUNT(*) FROM admin_banners") as cur:
            banner_count_row = await cur.fetchone()

        if int((banner_count_row or [0])[0] or 0) == 0:
            await _ensure_default_promo_banners(db)

        await _ensure_default_about_slides(db)
        await db.commit()


# ─── Пользователи ─────────────────────────────────────────────────────────────

def _normalize_user_identity_part(value) -> str:
    return str(value or "").strip()


async def get_or_create_user(
    user_id: int,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
) -> dict:
    normalized_username = _normalize_user_identity_part(username).lstrip("@")
    normalized_first_name = _normalize_user_identity_part(first_name)
    normalized_last_name = _normalize_user_identity_part(last_name)

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row:
            user = dict(row)
            next_username = normalized_username or str(user.get("username") or "").strip()
            next_first_name = normalized_first_name or str(user.get("first_name") or "").strip()
            next_last_name = normalized_last_name or str(user.get("last_name") or "").strip()

            if (
                next_username != str(user.get("username") or "").strip()
                or next_first_name != str(user.get("first_name") or "").strip()
                or next_last_name != str(user.get("last_name") or "").strip()
            ):
                await db.execute(
                    "UPDATE users SET username=?, first_name=?, last_name=? WHERE user_id=?",
                    (next_username, next_first_name, next_last_name, user_id),
                )
                await db.commit()
                user["username"] = next_username
                user["first_name"] = next_first_name
                user["last_name"] = next_last_name

            return user
        default_steps = json.dumps(DEFAULT_MARGIN_STEPS)
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, margin_steps, margin_min_rub)
            VALUES (?,?,?,?,?,?)
            """,
            (
                user_id,
                normalized_username,
                normalized_first_name,
                normalized_last_name,
                default_steps,
                DEFAULT_MARGIN_MIN_RUB,
            ),
        )
        await db.commit()
        return {
            "user_id": user_id,
            "username": normalized_username,
            "first_name": normalized_first_name,
            "last_name": normalized_last_name,
            "margin_steps": default_steps,
            "margin_min_rub": DEFAULT_MARGIN_MIN_RUB,
        }


async def update_user_margin(user_id: int, steps: list, min_rub: float):
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET margin_steps=?, margin_min_rub=? WHERE user_id=?",
            (json.dumps(steps), min_rub, user_id),
        )
        await db.commit()


# ─── Расчёты ──────────────────────────────────────────────────────────────────

async def get_delivery_profile(user_id: int) -> dict:
    normalized_payload = _normalize_delivery_profile_payload(None)

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT delivery_json, updated_at FROM delivery_profiles WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        return {**normalized_payload, "updated_at": ""}

    try:
        delivery_payload = json.loads(row["delivery_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        delivery_payload = {}

    return {
        **_normalize_delivery_profile_payload(delivery_payload),
        "updated_at": str(row["updated_at"] or ""),
    }


async def save_delivery_profile(user_id: int, delivery_payload: dict) -> dict:
    normalized_payload = _normalize_delivery_profile_payload(delivery_payload)
    serialized_payload = json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True)

    async with _connect() as db:
        await db.execute(
            """INSERT INTO delivery_profiles (user_id, delivery_json, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                   delivery_json=excluded.delivery_json,
                   updated_at=datetime('now')""",
            (user_id, serialized_payload),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT updated_at FROM delivery_profiles WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

    return {
        **normalized_payload,
        "updated_at": str(row["updated_at"] or "") if row else "",
    }


async def cart_apply_delivery_snapshot(
    user_id: int,
    delivery_payload: dict,
    submission_batch_id: str,
    submitted_at: str,
):
    serialized_payload = json.dumps(
        _normalize_delivery_profile_payload(delivery_payload),
        ensure_ascii=False,
        sort_keys=True,
    )

    async with _connect() as db:
        await db.execute(
            """UPDATE cart_items
               SET delivery_snapshot_json=?, submission_batch_id=?, submitted_at=?
               WHERE user_id=? AND in_order=1 AND order_submitted=0""",
            (serialized_payload, submission_batch_id, submitted_at, user_id),
        )
        await db.commit()


def _gen_share_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=SHARE_CODE_LENGTH))


async def save_calculation(user_id: int, result) -> tuple[int, str]:
    """Сохранить расчёт, вернуть (id, share_code)."""
    share_code = _gen_share_code()
    p = result.product
    async with _connect() as db:
        cur = await db.execute(
            """INSERT INTO calculations
               (user_id, product_url, platform, name, price_cny, size, category,
                weight_kg, weight_estimated, city, delivery_type,
                subtotal_rub, total_with_margin_rub, margin_rub, margin_percent,
                calc_json, share_code)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id, p.url, p.platform, p.name, p.price_cny,
                p.size, p.category, p.weight_kg, int(p.weight_estimated),
                p.city, p.delivery_type,
                result.subtotal_rub, result.total_with_margin_rub,
                result.margin_rub, result.margin_percent,
                json.dumps(result.to_dict()), share_code,
            ),
        )
        await db.commit()
        calc_id = cur.lastrowid

    # Обрезаем историю до MAX_ITEMS
    async with _connect() as db:
        await db.execute(
            """DELETE FROM calculations WHERE user_id=? AND id NOT IN (
                SELECT id FROM calculations WHERE user_id=?
                ORDER BY created_at DESC LIMIT ?
            )""",
            (user_id, user_id, HISTORY_MAX_ITEMS),
        )
        await db.commit()

    return calc_id, share_code


async def update_calculation(calc_id: int, user_id: int, result) -> None:
    """Update an existing calculation's data (e.g. after variant change)."""
    p = result.product
    async with _connect() as conn:
        await conn.execute(
            """UPDATE calculations
               SET price_cny=?, size=?, weight_kg=?, weight_estimated=?, city=?, delivery_type=?, subtotal_rub=?,
                   total_with_margin_rub=?, margin_rub=?, margin_percent=?,
                   calc_json=?
               WHERE id=? AND user_id=?""",
            (
                p.price_cny, p.size,
                p.weight_kg, int(bool(p.weight_estimated)), p.city, p.delivery_type,
                result.subtotal_rub, result.total_with_margin_rub,
                result.margin_rub, result.margin_percent,
                json.dumps(result.to_dict()),
                calc_id, user_id,
            ),
        )
        await conn.commit()


async def update_short_name(calc_id: int, short_name: str):
    async with _connect() as db:
        await db.execute(
            "UPDATE calculations SET short_name=? WHERE id=?",
            (short_name, calc_id),
        )
        await db.commit()


async def get_calculation_by_id(calc_id: int, user_id: int) -> Optional[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM calculations WHERE id=? AND user_id=?", (calc_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_calculation_admin(calc_id: int) -> Optional[dict]:
    """Получить расчёт по ID без проверки user_id (для администратора)."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM calculations WHERE id=?", (calc_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_calculation_by_share(share_code: str) -> Optional[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM calculations WHERE share_code=?", (share_code,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_history(user_id: int, limit: int = 15) -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, name, price_cny, subtotal_rub, total_with_margin_rub,
                      delivery_type, city, created_at, share_code, product_url,
                      platform, calc_json
               FROM calculations
               WHERE user_id=? AND id IN (
                   SELECT MAX(id)
                   FROM calculations
                   WHERE user_id=?
                   GROUP BY COALESCE(product_url, CAST(id AS TEXT))
               )
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ─── Корзина ──────────────────────────────────────────────────────────────────

async def cart_add(user_id: int, calc_id: int):
    async with _connect() as db:
        # Проверяем дубликат по product_url (с учётом NULL)
        async with db.execute(
            """SELECT ci.id FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               WHERE ci.user_id=?
                 AND (
                   (c.product_url IS NOT NULL AND c.product_url = (
                       SELECT product_url FROM calculations WHERE id=?
                   ))
                   OR
                   (c.product_url IS NULL AND ci.calculation_id = ?)
                 )""",
            (user_id, calc_id, calc_id),
        ) as cur:
            exists = await cur.fetchone()
        if exists:
            # Обновить существующую запись на новый расчёт (новый размер/вариант)
            # Сбрасываем статусы заказа, чтобы товар снова был виден в корзине
            await db.execute(
                "UPDATE cart_items SET calculation_id=?, added_at=datetime('now'), "
                "in_order=0, order_submitted=0, paid=0, shipped=0, arrived=0, order_added_at=NULL, "
                "tracking_number='', item_number='', delivery_snapshot_json='', submission_batch_id='', submitted_at=NULL "
                "WHERE id=?",
                (calc_id, exists[0]),
            )
        else:
            await db.execute(
                "INSERT INTO cart_items (user_id, calculation_id) VALUES (?,?)",
                (user_id, calc_id),
            )
        await db.commit()


async def cart_remove(user_id: int, calc_id: int):
    async with _connect() as db:
        await db.execute(
            "DELETE FROM cart_items WHERE user_id=? AND calculation_id=?",
            (user_id, calc_id),
        )
        await db.commit()


async def cart_clear(user_id: int):
    async with _connect() as db:
        await db.execute("DELETE FROM cart_items WHERE user_id=?", (user_id,))
        await db.commit()


async def cart_get_items(user_id: int) -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        # Дедупликация: по каждому product_url берём только последнюю запись
        async with db.execute(
                """SELECT c.id, c.name, c.price_cny, c.subtotal_rub, c.total_with_margin_rub,
                      c.weight_kg, c.weight_estimated, c.delivery_type, c.city, c.calc_json,
                      c.platform, c.size, c.product_url, c.short_name,
                      ci.in_order, ci.paid, ci.order_added_at, ci.shipped, ci.arrived,
                      ci.tracking_number, ci.item_number,
                      ci.order_submitted
               FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               WHERE ci.user_id=?
                 AND ci.id = (
                   SELECT ci2.id FROM cart_items ci2
                   JOIN calculations c2 ON c2.id = ci2.calculation_id
                   WHERE ci2.user_id = ci.user_id
                     AND COALESCE(c2.product_url, '') = COALESCE(c.product_url, '')
                   ORDER BY ci2.added_at DESC
                   LIMIT 1
                 )
               ORDER BY ci.added_at""",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def cart_get_pending_order_items(user_id: int) -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT c.id, c.name, c.price_cny, c.subtotal_rub, c.total_with_margin_rub,
                      c.weight_kg, c.weight_estimated, c.delivery_type, c.city, c.calc_json,
                      c.platform, c.size, c.product_url
               FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               WHERE ci.user_id=?
                 AND ci.in_order=1
                 AND ci.order_submitted=0
               ORDER BY COALESCE(ci.order_added_at, ci.added_at), ci.id""",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def cart_get_all_orders() -> list[dict]:
    """Все товары с in_order=1 от всех пользователей (для администратора)."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT ci.user_id, ci.calculation_id AS calc_id,
                      ci.paid, ci.order_added_at, ci.shipped, ci.arrived,
                      ci.tracking_number, ci.item_number,
                      ci.order_submitted, ci.delivery_snapshot_json,
                      ci.submission_batch_id, ci.submitted_at,
                      c.name, c.product_url, c.price_cny, c.subtotal_rub,
                      c.total_with_margin_rub, c.platform, c.short_name, c.size, c.calc_json,
                      u.username, u.first_name, u.last_name
               FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               JOIN users u ON u.user_id = ci.user_id
               WHERE ci.in_order = 1
                 AND ci.order_submitted = 1
               ORDER BY ci.user_id, COALESCE(ci.order_added_at, ci.added_at)""",
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def cart_set_paid(user_id: int, calc_id: int, value: bool):
    """Пометить/снять оплату для товара в заявке."""
    async with _connect() as db:
        await db.execute(
            "UPDATE cart_items SET paid=? WHERE user_id=? AND calculation_id=?",
            (int(value), user_id, calc_id),
        )
        await db.commit()


async def cart_set_tracking_number(user_id: int, calc_id: int, tracking_number: str):
    """Сохранить трек-номер для товара в заявке."""
    normalized_value = str(tracking_number or "").strip()

    async with _connect() as db:
        await db.execute(
            "UPDATE cart_items SET tracking_number=? WHERE user_id=? AND calculation_id=?",
            (normalized_value, user_id, calc_id),
        )
        await db.commit()


async def cart_set_item_number(user_id: int, calc_id: int, item_number: str):
    """Сохранить клиентский номер товара для позиции в заявке."""
    normalized_value = str(item_number or "").strip()

    async with _connect() as db:
        await db.execute(
            "UPDATE cart_items SET item_number=? WHERE user_id=? AND calculation_id=?",
            (normalized_value, user_id, calc_id),
        )
        await db.commit()


async def cart_set_order(user_id: int, calc_id: int, value: bool):
    """Пометить/снять пометку 'в заявке' для товара в корзине."""
    async with _connect() as db:
        if value:
            # При добавлении в заявку — фиксируем время, сбрасываем статус оплаты
            await db.execute(
                "UPDATE cart_items SET in_order=1, order_added_at=datetime('now'), paid=0, shipped=0, "
                "arrived=0, order_submitted=0, tracking_number='', item_number='', delivery_snapshot_json='', "
                "submission_batch_id='', submitted_at=NULL "
                "WHERE user_id=? AND calculation_id=?",
                (user_id, calc_id),
            )
        else:
            await db.execute(
                "UPDATE cart_items SET in_order=0, shipped=0, arrived=0, order_submitted=0, tracking_number='', item_number='', "
                "delivery_snapshot_json='', submission_batch_id='', submitted_at=NULL "
                "WHERE user_id=? AND calculation_id=?",
                (user_id, calc_id),
            )
        await db.commit()


async def cart_submit_order(user_id: int):
    """Пометить все товары in_order=1 как отправленные на рассмотрение."""
    async with _connect() as db:
        await db.execute(
            "UPDATE cart_items SET order_submitted=1 WHERE user_id=? AND in_order=1 AND order_submitted=0",
            (user_id,),
        )
        await db.commit()


async def cart_get_all_carts() -> list[dict]:
    """Все товары корзин всех пользователей для администратора (дедупликация по URL)."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT ci.user_id, ci.calculation_id AS calc_id,
                      ci.in_order, ci.added_at,
                      c.name, c.product_url, c.price_cny, c.subtotal_rub, c.total_with_margin_rub,
                      c.platform, c.short_name, c.calc_json,
                      u.username, u.first_name, u.last_name
               FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               JOIN users u ON u.user_id = ci.user_id
               WHERE ci.id = (
                   SELECT ci2.id FROM cart_items ci2
                   JOIN calculations c2 ON c2.id = ci2.calculation_id
                   WHERE ci2.user_id = ci.user_id
                     AND COALESCE(c2.product_url, '') = COALESCE(c.product_url, '')
                   ORDER BY ci2.added_at DESC
                   LIMIT 1
               )
               ORDER BY ci.user_id, ci.added_at""",
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def cart_has_url(user_id: int, url: str) -> bool:
    """Проверить, есть ли товар с таким URL в корзине пользователя."""
    async with _connect() as db:
        async with db.execute(
            """SELECT 1 FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               WHERE ci.user_id=? AND c.product_url=?
               LIMIT 1""",
            (user_id, url),
        ) as cur:
            row = await cur.fetchone()
    return row is not None


async def cart_update_item(user_id: int, old_calc_id: int, new_calc_id: int):
    """Заменить товар в корзине (используется при 'Изменить уточнения')."""
    async with _connect() as db:
        await db.execute(
            "UPDATE cart_items SET calculation_id=? WHERE user_id=? AND calculation_id=?",
            (new_calc_id, user_id, old_calc_id),
        )
        await db.commit()


async def get_shipped_calc_ids() -> list[int]:
    """Получить список calc_id товаров, отмеченных как отправленные (shipped=1, arrived=0)."""
    async with _connect() as db:
        async with db.execute(
            "SELECT DISTINCT calculation_id FROM cart_items WHERE shipped=1 AND arrived=0"
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def cart_set_shipped(calc_ids: list[int]):
    """Пометить товары как отправленные."""
    if not calc_ids:
        return
    async with _connect() as db:
        placeholders = ",".join("?" * len(calc_ids))
        await db.execute(
            f"UPDATE cart_items SET shipped=1 WHERE calculation_id IN ({placeholders})",
            calc_ids,
        )
        await db.commit()


async def cart_set_arrived(calc_ids: list[int]):
    """Пометить товары как доставленные (arrived=1, shipped=0)."""
    if not calc_ids:
        return
    async with _connect() as db:
        placeholders = ",".join("?" * len(calc_ids))
        await db.execute(
            f"UPDATE cart_items SET arrived=1, shipped=0 WHERE calculation_id IN ({placeholders})",
            calc_ids,
        )
        await db.commit()


# ─── Настройки админа ─────────────────────────────────────────────────────────

async def get_admin_settings() -> dict:
    """Вернуть все настройки расценок. Незаданные ключи берутся из DEFAULT_ADMIN_SETTINGS."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM admin_settings") as cur:
            rows = await cur.fetchall()
    result = dict(DEFAULT_ADMIN_SETTINGS)
    for row in rows:
        key = str(row["key"] or "").strip()
        if key in DEFAULT_ADMIN_SETTINGS:
            result[key] = row["value"]
    return result


async def set_admin_setting(key: str, value: str):
    """Сохранить одну настройку расценок."""
    async with _connect() as db:
        await db.execute(
            "INSERT INTO admin_settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, time.time()),
        )
        await db.commit()


# ─── Курс валюты ──────────────────────────────────────────────────────────────

async def get_admin_showcase_slots() -> list[dict]:
    """Return showcase slots 1..SHOWCASE_SLOT_COUNT with cached product payloads."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT slot, url, product_json, updated_at FROM admin_showcase_slots ORDER BY slot ASC"
        ) as cur:
            rows = await cur.fetchall()

    slot_map = {
        int(row["slot"]): {
            "slot": int(row["slot"]),
            "url": str(row["url"] or ""),
            "product_json": str(row["product_json"] or ""),
            "updated_at": float(row["updated_at"] or 0),
        }
        for row in rows
    }

    return [
        slot_map.get(slot, {
            "slot": slot,
            "url": "",
            "product_json": "",
            "updated_at": 0.0,
        })
        for slot in range(1, SHOWCASE_SLOT_COUNT + 1)
    ]


async def set_admin_showcase_slot(slot: int, url: str, product_json: str):
    """Persist one showcase slot with its source url and cached product payload."""
    if slot < 1 or slot > SHOWCASE_SLOT_COUNT:
        raise ValueError("showcase slot is out of range")

    async with _connect() as db:
        await db.execute(
            "INSERT INTO admin_showcase_slots (slot, url, product_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(slot) DO UPDATE SET url=excluded.url, product_json=excluded.product_json, updated_at=excluded.updated_at",
            (slot, str(url or ""), str(product_json or ""), time.time()),
        )
        await db.commit()


def _serialize_about_slide_row(row: aiosqlite.Row | None) -> dict | None:
    if not row:
        return None

    slot = int(row["slot"] or 0)
    image_alt = str(row["image_alt"] or "").strip() or str(default_slide.get("image_alt") or f"Слайд {slot}")

    return {
        "slot": slot,
        "image_url": str(row["image_url"] or "").strip(),
        "image_alt": image_alt[:PROMO_BANNER_IMAGE_ALT_MAX_LENGTH],
        "updated_at": float(row["updated_at"] or 0),
    }


async def _ensure_default_about_slides(db_conn: aiosqlite.Connection):
    seeded_at = time.time()
    await db_conn.executemany(
        "INSERT OR IGNORE INTO admin_about_slides (slot, image_url, image_alt, updated_at) VALUES (?,?,?,?)",
        [
            (
                int(entry["slot"]),
                str(entry["image_url"]),
                str(entry["image_alt"]),
                seeded_at,
            )
            for entry in DEFAULT_ABOUT_DETAILS_SLIDES
        ],
    )


async def get_admin_about_slides() -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT slot, image_url, image_alt, updated_at FROM admin_about_slides ORDER BY slot ASC"
        ) as cur:
            rows = await cur.fetchall()

    return [
        slide
        for slide in (
            _serialize_about_slide_row(row)
            for row in rows
        )
        if slide
    ]

    return [
        slide_map.get(
            slot,
            {
                "slot": slot,
                "image_url": str(default_entry.get("image_url") or ""),
                "image_alt": str(default_entry.get("image_alt") or f"Слайд {slot}"),
                "updated_at": 0.0,
            },
        )
        for slot, default_entry in (
            (
                int(entry.get("slot") or 0),
                entry,
            )
            for entry in DEFAULT_ABOUT_DETAILS_SLIDES
        )
        if slot > 0
    ]


async def set_admin_about_slide(slot: int, image_url: str, image_alt: str = "", *, insert: bool = False):
    if slot < 1:
        raise ValueError("about slide slot is invalid")

    normalized_image_url = _normalize_banner_image_url(image_url)
    if not normalized_image_url:
        raise ValueError("about slide image is required")

    default_slide = {"image_alt": f"Слайд {slot}"}
    raw_image_alt = str(image_alt or "").strip()
    insert = insert or raw_image_alt.startswith("__insert__")
    normalized_image_alt = raw_image_alt.replace("__insert__", "", 1).strip()[:PROMO_BANNER_IMAGE_ALT_MAX_LENGTH]
    if not normalized_image_alt:
        normalized_image_alt = str(default_slide.get("image_alt") or f"Слайд {slot}")

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM admin_about_slides") as cur:
            count_row = await cur.fetchone()
        current_count = int((count_row or [0])[0] or 0)

        async with db.execute(
            "SELECT slot FROM admin_about_slides WHERE slot=? LIMIT 1",
            (slot,),
        ) as cur:
            existing_row = await cur.fetchone()

        if insert:
            if slot > current_count + 1:
                raise ValueError("about slide slot is invalid")
            if existing_row:
                await db.execute(
                    "UPDATE admin_about_slides SET slot = -(slot + 1) WHERE slot >= ?",
                    (slot,),
                )
                await db.execute("UPDATE admin_about_slides SET slot = ABS(slot) WHERE slot < 0")
        elif not existing_row and slot != current_count + 1:
            raise ValueError("about slide slot is invalid")
        await db.execute(
            "INSERT INTO admin_about_slides (slot, image_url, image_alt, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(slot) DO UPDATE SET image_url=excluded.image_url, image_alt=excluded.image_alt, updated_at=excluded.updated_at",
            (slot, normalized_image_url, normalized_image_alt, time.time()),
        )
        await db.commit()


async def _resequence_admin_about_slides(db_conn: aiosqlite.Connection):
    db_conn.row_factory = aiosqlite.Row
    async with db_conn.execute(
        "SELECT slot, image_url, image_alt, updated_at FROM admin_about_slides ORDER BY slot ASC"
    ) as cur:
        rows = await cur.fetchall()

    resequenced_rows = [
        (
            next_slot,
            str(row["image_url"] or "").strip(),
            str(row["image_alt"] or "").strip() or f"Слайд {next_slot}",
            float(row["updated_at"] or 0),
        )
        for next_slot, row in enumerate(rows, start=1)
    ]

    await db_conn.execute("DELETE FROM admin_about_slides")
    if resequenced_rows:
        await db_conn.executemany(
            "INSERT INTO admin_about_slides (slot, image_url, image_alt, updated_at) VALUES (?,?,?,?)",
            resequenced_rows,
        )


async def delete_admin_about_slide(slot: int):
    if slot < 1:
        raise ValueError("about slide slot is invalid")

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT slot FROM admin_about_slides WHERE slot=? LIMIT 1",
            (slot,),
        ) as cur:
            existing_row = await cur.fetchone()

        if not existing_row:
            raise ValueError("about slide not found")

        await db.execute("DELETE FROM admin_about_slides WHERE slot=?", (slot,))
        await _resequence_admin_about_slides(db)
        await db.commit()


def _serialize_banner_row(row: aiosqlite.Row | None) -> dict | None:
    if not row:
        return None

    try:
        blocks = _normalize_banner_blocks(json.loads(str(row["content_json"] or "[]")))
    except (TypeError, ValueError, json.JSONDecodeError):
        blocks = []

    return {
        "id": int(row["id"] or 0),
        "label": str(row["label"] or ""),
        "title": str(row["title"] or ""),
        "subtitle": str(row["subtitle"] or ""),
        "button_label": str(row["button_label"] or ""),
        "button_url": str(row["button_url"] or ""),
        "button_color": _normalize_banner_button_color(row["button_color"]),
        "image_url": str(row["image_url"] or ""),
        "image_alt": str(row["image_alt"] or ""),
        "story_image_url": str(row["story_image_url"] or ""),
        "story_image_alt": str(row["story_image_alt"] or ""),
        "blocks": blocks,
        "position": int(row["position"] or 0),
        "show_on_entry": int(row["show_on_entry"] or 0),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    }


async def _resequence_admin_banners(db_conn: aiosqlite.Connection):
    db_conn.row_factory = aiosqlite.Row
    async with db_conn.execute(
        "SELECT id FROM admin_banners ORDER BY position ASC, id ASC"
    ) as cur:
        rows = await cur.fetchall()

    for position, row in enumerate(rows, start=1):
        await db_conn.execute(
            "UPDATE admin_banners SET position=? WHERE id=?",
            (position, int(row["id"] or 0)),
        )


async def _ensure_default_promo_banners(db_conn: aiosqlite.Connection):
    db_conn.row_factory = aiosqlite.Row
    async with db_conn.execute("SELECT COUNT(*) FROM admin_banners") as cur:
        count_row = await cur.fetchone()

    if int((count_row or [0])[0] or 0) > 0:
        return

    seeded_at = time.time()
    await db_conn.executemany(
        "INSERT INTO admin_banners (label, title, subtitle, button_label, button_url, button_color, image_url, image_alt, story_image_url, story_image_alt, content_json, position, show_on_entry, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                entry["label"],
                entry["title"],
                entry["subtitle"],
                entry["button_label"],
                entry["button_url"],
                _normalize_banner_button_color(entry.get("button_color")),
                entry["image_url"],
                entry["image_alt"],
                entry.get("story_image_url") or entry["image_url"],
                entry.get("story_image_alt") or entry["image_alt"],
                json.dumps(entry["blocks"], ensure_ascii=False),
                position,
                1 if entry.get("show_on_entry") else 0,
                seeded_at,
                seeded_at,
            )
            for position, entry in enumerate(DEFAULT_PROMO_BANNERS, start=1)
        ],
    )


async def get_admin_banners() -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM admin_banners") as cur:
            count_row = await cur.fetchone()

        if int((count_row or [0])[0] or 0) == 0:
            await _ensure_default_promo_banners(db)
            await db.commit()

        async with db.execute(
            "SELECT id, label, title, subtitle, button_label, button_url, button_color, image_url, image_alt, story_image_url, story_image_alt, content_json, position, show_on_entry, created_at, updated_at "
            "FROM admin_banners ORDER BY position ASC, id ASC LIMIT ?",
            (PROMO_BANNER_MAX_COUNT,),
        ) as cur:
            rows = await cur.fetchall()

    return [_serialize_banner_row(row) for row in rows if row]


async def save_admin_banner(
    banner_id: int,
    label: str,
    title: str,
    subtitle: str,
    button_label: str,
    button_url: str,
    button_color: str,
    image_url: str,
    image_alt: str,
    story_image_url: str,
    story_image_alt: str,
    show_on_entry: bool,
    blocks: list[dict] | None = None,
) -> dict:
    normalized_banner = _normalize_banner_entry_payload({
        "label": label,
        "title": title,
        "subtitle": subtitle,
        "button_label": button_label,
        "button_url": button_url,
        "button_color": button_color,
        "image_url": image_url,
        "image_alt": image_alt,
        "story_image_url": story_image_url,
        "story_image_alt": story_image_alt,
        "show_on_entry": show_on_entry,
        "blocks": blocks or [],
    })

    banner_id = int(banner_id or 0)
    now_ts = time.time()
    content_json = json.dumps(normalized_banner["blocks"], ensure_ascii=False)

    async with _connect() as db:
        db.row_factory = aiosqlite.Row

        if banner_id > 0:
            async with db.execute(
                "SELECT id, position FROM admin_banners WHERE id=?",
                (banner_id,),
            ) as cur:
                existing_row = await cur.fetchone()

            if not existing_row:
                raise ValueError("banner not found")

            await db.execute(
                "UPDATE admin_banners SET label=?, title=?, subtitle=?, button_label=?, button_url=?, button_color=?, image_url=?, image_alt=?, story_image_url=?, story_image_alt=?, content_json=?, show_on_entry=?, updated_at=? WHERE id=?",
                (
                    normalized_banner["label"],
                    normalized_banner["title"],
                    normalized_banner["subtitle"],
                    normalized_banner["button_label"],
                    normalized_banner["button_url"],
                    normalized_banner["button_color"],
                    normalized_banner["image_url"],
                    normalized_banner["image_alt"],
                    normalized_banner["story_image_url"],
                    normalized_banner["story_image_alt"],
                    content_json,
                    normalized_banner["show_on_entry"],
                    now_ts,
                    banner_id,
                ),
            )
        else:
            async with db.execute("SELECT COUNT(*) FROM admin_banners") as cur:
                count_row = await cur.fetchone()

            current_count = int((count_row or [0])[0] or 0)
            if current_count >= PROMO_BANNER_MAX_COUNT:
                raise ValueError("banner limit reached")

            async with db.execute("SELECT COALESCE(MAX(position), 0) FROM admin_banners") as cur:
                position_row = await cur.fetchone()

            next_position = int((position_row or [0])[0] or 0) + 1
            cursor = await db.execute(
                "INSERT INTO admin_banners (label, title, subtitle, button_label, button_url, button_color, image_url, image_alt, story_image_url, story_image_alt, content_json, position, show_on_entry, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    normalized_banner["label"],
                    normalized_banner["title"],
                    normalized_banner["subtitle"],
                    normalized_banner["button_label"],
                    normalized_banner["button_url"],
                    normalized_banner["button_color"],
                    normalized_banner["image_url"],
                    normalized_banner["image_alt"],
                    normalized_banner["story_image_url"],
                    normalized_banner["story_image_alt"],
                    content_json,
                    next_position,
                    normalized_banner["show_on_entry"],
                    now_ts,
                    now_ts,
                ),
            )
            banner_id = int(cursor.lastrowid or 0)

        async with db.execute(
            "SELECT id, label, title, subtitle, button_label, button_url, button_color, image_url, image_alt, story_image_url, story_image_alt, content_json, position, show_on_entry, created_at, updated_at "
            "FROM admin_banners WHERE id=?",
            (banner_id,),
        ) as cur:
            saved_row = await cur.fetchone()

        await db.commit()

    return _serialize_banner_row(saved_row) or {}


async def delete_admin_banner(banner_id: int):
    banner_id = int(banner_id or 0)
    if banner_id <= 0:
        raise ValueError("banner id is invalid")

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM admin_banners WHERE id=?",
            (banner_id,),
        ) as cur:
            existing_row = await cur.fetchone()

        if not existing_row:
            raise ValueError("banner not found")

        await db.execute("DELETE FROM admin_banners WHERE id=?", (banner_id,))
        await _resequence_admin_banners(db)
        await db.commit()


def _serialize_faq_entry_row(row: aiosqlite.Row | None) -> dict | None:
    if not row:
        return None

    return {
        "id": int(row["id"] or 0),
        "question": str(row["question"] or ""),
        "answer": str(row["answer"] or ""),
        "link_url": str(row["link_url"] or ""),
        "button_label": str(row["button_label"] or ""),
        "position": int(row["position"] or 0),
        "created_at": float(row["created_at"] or 0),
        "updated_at": float(row["updated_at"] or 0),
    }


async def _resequence_faq_entries(db_conn: aiosqlite.Connection):
    db_conn.row_factory = aiosqlite.Row
    async with db_conn.execute(
        "SELECT id FROM faq_entries ORDER BY position ASC, id ASC"
    ) as cur:
        rows = await cur.fetchall()

    for position, row in enumerate(rows, start=1):
        await db_conn.execute(
            "UPDATE faq_entries SET position=? WHERE id=?",
            (position, int(row["id"] or 0)),
        )


async def _ensure_default_faq_entries(db_conn: aiosqlite.Connection):
    db_conn.row_factory = aiosqlite.Row
    async with db_conn.execute("SELECT COALESCE(MAX(position), 0) FROM faq_entries") as cur:
        position_row = await cur.fetchone()

    next_position = int((position_row or [0])[0] or 0) + 1

    for default_entry in DEFAULT_FAQ_ENTRIES:
        normalized_entry = _normalize_faq_entry_payload(default_entry)

        async with db_conn.execute(
            "SELECT id, answer, link_url, button_label FROM faq_entries WHERE question=? LIMIT 1",
            (normalized_entry["question"],),
        ) as cur:
            existing_row = await cur.fetchone()

        if existing_row:
            stored_answer = str(existing_row["answer"] or "")
            stored_link_url = str(existing_row["link_url"] or "")
            stored_button_label = str(existing_row["button_label"] or "")
            if (
                stored_answer == normalized_entry["answer"]
                and stored_link_url == normalized_entry["link_url"]
                and stored_button_label == normalized_entry["button_label"]
            ):
                continue

            await db_conn.execute(
                "UPDATE faq_entries SET answer=?, link_url=?, button_label=?, updated_at=? WHERE id=?",
                (
                    normalized_entry["answer"],
                    normalized_entry["link_url"],
                    normalized_entry["button_label"],
                    time.time(),
                    int(existing_row["id"] or 0),
                ),
            )
            continue

        seeded_at = time.time()
        await db_conn.execute(
            "INSERT INTO faq_entries (question, answer, link_url, button_label, position, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (
                normalized_entry["question"],
                normalized_entry["answer"],
                normalized_entry["link_url"],
                normalized_entry["button_label"],
                next_position,
                seeded_at,
                seeded_at,
            ),
        )
        next_position += 1


async def get_faq_entries() -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM faq_entries") as cur:
            count_row = await cur.fetchone()

        faq_count = int((count_row or [0])[0] or 0)
        if faq_count == 0:
            seeded_at = time.time()
            await db.executemany(
                "INSERT INTO faq_entries (question, answer, link_url, button_label, position, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        entry["question"],
                        entry["answer"],
                        entry.get("link_url", ""),
                        entry.get("button_label", ""),
                        position,
                        seeded_at,
                        seeded_at,
                    )
                    for position, entry in enumerate(DEFAULT_FAQ_ENTRIES, start=1)
                ],
            )
            await db.commit()

        async with db.execute(
            "SELECT id, question, answer, link_url, button_label, position, created_at, updated_at "
            "FROM faq_entries ORDER BY position ASC, id ASC"
        ) as cur:
            rows = await cur.fetchall()

    return [_serialize_faq_entry_row(row) for row in rows if row]


async def save_faq_entry(
    entry_id: int,
    question: str,
    answer: str,
    link_url: str = "",
    button_label: str = "",
) -> dict:
    normalized_entry = _normalize_faq_entry_payload({
        "question": question,
        "answer": answer,
        "link_url": link_url,
        "button_label": button_label,
    })
    normalized_question = normalized_entry["question"]
    normalized_answer = normalized_entry["answer"]
    normalized_link_url = normalized_entry["link_url"]
    normalized_button_label = normalized_entry["button_label"]

    if not normalized_question:
        raise ValueError("question is required")
    if not normalized_answer:
        raise ValueError("answer is required")

    entry_id = int(entry_id or 0)
    now_ts = time.time()

    async with _connect() as db:
        db.row_factory = aiosqlite.Row

        if entry_id > 0:
            async with db.execute(
                "SELECT id FROM faq_entries WHERE id=?",
                (entry_id,),
            ) as cur:
                existing_row = await cur.fetchone()

            if not existing_row:
                raise ValueError("faq entry not found")

            await db.execute(
                "UPDATE faq_entries SET question=?, answer=?, link_url=?, button_label=?, updated_at=? WHERE id=?",
                (
                    normalized_question,
                    normalized_answer,
                    normalized_link_url,
                    normalized_button_label,
                    now_ts,
                    entry_id,
                ),
            )
        else:
            async with db.execute("SELECT COALESCE(MAX(position), 0) FROM faq_entries") as cur:
                position_row = await cur.fetchone()

            next_position = int((position_row or [0])[0] or 0) + 1
            cursor = await db.execute(
                "INSERT INTO faq_entries (question, answer, link_url, button_label, position, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    normalized_question,
                    normalized_answer,
                    normalized_link_url,
                    normalized_button_label,
                    next_position,
                    now_ts,
                    now_ts,
                ),
            )
            entry_id = int(cursor.lastrowid or 0)

        async with db.execute(
            "SELECT id, question, answer, link_url, button_label, position, created_at, updated_at FROM faq_entries WHERE id=?",
            (entry_id,),
        ) as cur:
            saved_row = await cur.fetchone()

        await db.commit()

    return _serialize_faq_entry_row(saved_row) or {}


async def delete_faq_entry(entry_id: int):
    entry_id = int(entry_id or 0)
    if entry_id <= 0:
        raise ValueError("faq entry id is invalid")

    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM faq_entries WHERE id=?",
            (entry_id,),
        ) as cur:
            existing_row = await cur.fetchone()

        if not existing_row:
            raise ValueError("faq entry not found")

        await db.execute("DELETE FROM faq_entries WHERE id=?", (entry_id,))
        await _resequence_faq_entries(db)
        await db.commit()


async def save_exchange_rate(cny_rub: float, usd_rub: float, eur_rub: float):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO exchange_rates (cny_rub, usd_rub, eur_rub) VALUES (?,?,?)",
            (cny_rub, usd_rub, eur_rub),
        )
        await db.commit()


async def get_latest_exchange_rate() -> Optional[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM exchange_rates ORDER BY updated_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


# ─── Бан-система ───────────────────────────────────────────────────────────────

async def get_ban_info(user_id: int) -> dict:
    """Вернуть бан-информацию пользователя."""
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT ban_level, ban_until, ban_last_notified, order_removes_today, order_removes_date "
            "FROM users WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return {"ban_level": 0, "ban_until": 0.0, "ban_last_notified": 0.0,
                "order_removes_today": 0, "order_removes_date": ""}
    return dict(row)


async def set_ban(user_id: int, level: int, until: float):
    """Установить бан: level — уровень (1-5), until — timestamp окончания (-1 = навсегда)."""
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET ban_level=?, ban_until=? WHERE user_id=?",
            (level, until, user_id),
        )
        await db.commit()


async def update_ban_notified(user_id: int):
    """Обновить timestamp последнего бан-уведомления."""
    async with _connect() as db:
        await db.execute(
            "UPDATE users SET ban_last_notified=? WHERE user_id=?",
            (time.time(), user_id),
        )
        await db.commit()


async def increment_order_removes(user_id: int) -> int:
    """Увеличить счётчик удалений из заявки за сегодня. Сбрасывается в полночь.
    Возвращает новое значение счётчика.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT order_removes_today, order_removes_date FROM users WHERE user_id=?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return 0
        if (row["order_removes_date"] or "") != today:
            new_count = 1
        else:
            new_count = (row["order_removes_today"] or 0) + 1
        await db.execute(
            "UPDATE users SET order_removes_today=?, order_removes_date=? WHERE user_id=?",
            (new_count, today, user_id),
        )
        await db.commit()
    return new_count


# ─── Сообщения пользователей ───────────────────────────────────────────────────

async def msg_save(user_id: int, username: str, msg_type: str, text: str):
    async with _connect() as db:
        await db.execute(
            "INSERT INTO user_messages (user_id, username, msg_type, text) VALUES (?,?,?,?)",
            (user_id, username, msg_type, text),
        )
        await db.commit()


async def msg_get_all() -> list[dict]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, user_id, username, msg_type, text, sent_at "
            "FROM user_messages ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def msg_delete_all():
    async with _connect() as db:
        await db.execute("DELETE FROM user_messages")
        await db.commit()


async def record_miniapp_activity(user_id: int, *, occurred_at: datetime | None = None) -> None:
    safe_user_id = int(user_id or 0)
    if safe_user_id <= 0:
        return

    now_local = _now_in_moscow(occurred_at)
    activity_date = now_local.strftime("%Y-%m-%d")
    occurred_at_utc = _to_sqlite_utc(now_local)
    default_steps = json.dumps(DEFAULT_MARGIN_STEPS)

    async with _connect() as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, margin_steps, margin_min_rub) VALUES (?,?,?,?)",
            (safe_user_id, "", default_steps, DEFAULT_MARGIN_MIN_RUB),
        )
        await db.execute(
            """
            INSERT INTO miniapp_activity_daily (user_id, activity_date, first_seen_at, last_seen_at, request_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, activity_date) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                request_count=miniapp_activity_daily.request_count + 1
            """,
            (safe_user_id, activity_date, occurred_at_utc, occurred_at_utc),
        )
        await db.commit()


async def _collect_admin_user_signals(now: datetime | None = None) -> dict:
    now_local = _now_in_moscow(now)
    today_key = _moscow_day_key(now_local)
    recent_start_key = _moscow_recent_start_key(now_local)
    day_start_utc, day_end_utc = _moscow_day_bounds_utc(now_local)

    user_filter_sql, user_filter_params = _admin_filter_clause()
    activity_filter_sql, activity_filter_params = _admin_filter_clause(column="user_id")
    cart_filter_sql, cart_filter_params = _admin_filter_clause(column="ci.user_id")

    async with _connect() as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            f"SELECT user_id FROM users WHERE 1=1{user_filter_sql}",
            user_filter_params,
        ) as cur:
            all_user_rows = await cur.fetchall()

        async with db.execute(
            f"SELECT COUNT(*) AS total FROM users WHERE created_at >= ? AND created_at < ?{user_filter_sql}",
            [day_start_utc, day_end_utc, *user_filter_params],
        ) as cur:
            new_users_today_row = await cur.fetchone()

        async with db.execute(
            f"SELECT DISTINCT user_id FROM miniapp_activity_daily WHERE activity_date = ?{activity_filter_sql}",
            [today_key, *activity_filter_params],
        ) as cur:
            active_today_rows = await cur.fetchall()

        async with db.execute(
            (
                "SELECT DISTINCT user_id FROM miniapp_activity_daily "
                f"WHERE activity_date >= ? AND activity_date <= ?{activity_filter_sql}"
            ),
            [recent_start_key, today_key, *activity_filter_params],
        ) as cur:
            active_7d_rows = await cur.fetchall()

        async with db.execute(
            f"""
            SELECT ci.user_id, ci.in_order, ci.order_submitted, ci.added_at, c.total_with_margin_rub
            FROM cart_items ci
            JOIN calculations c ON c.id = ci.calculation_id
            WHERE ci.id = (
                SELECT ci2.id
                FROM cart_items ci2
                JOIN calculations c2 ON c2.id = ci2.calculation_id
                WHERE ci2.user_id = ci.user_id
                  AND COALESCE(c2.product_url, '') = COALESCE(c.product_url, '')
                ORDER BY ci2.added_at DESC
                LIMIT 1
            ){cart_filter_sql}
            """,
            cart_filter_params,
        ) as cur:
            current_cart_rows = await cur.fetchall()

        async with db.execute(
            f"""
            SELECT ci.user_id, ci.paid, ci.submitted_at, c.total_with_margin_rub
            FROM cart_items ci
            JOIN calculations c ON c.id = ci.calculation_id
            WHERE ci.order_submitted = 1{cart_filter_sql}
            """,
            cart_filter_params,
        ) as cur:
            submitted_order_rows = await cur.fetchall()

    all_user_ids = {
        int(row["user_id"] or 0)
        for row in all_user_rows
        if int(row["user_id"] or 0) > 0
    }
    active_today_ids = {
        int(row["user_id"] or 0)
        for row in active_today_rows
        if int(row["user_id"] or 0) > 0
    } & all_user_ids
    active_7d_ids = {
        int(row["user_id"] or 0)
        for row in active_7d_rows
        if int(row["user_id"] or 0) > 0
    } & all_user_ids

    cart_only_rows = [
        row
        for row in current_cart_rows
        if not bool(row["order_submitted"]) and not bool(row["in_order"])
    ]
    request_builder_rows = [
        row
        for row in current_cart_rows
        if not bool(row["order_submitted"]) and bool(row["in_order"])
    ]
    order_new_today_rows = [
        row
        for row in submitted_order_rows
        if _timestamp_in_window(row["submitted_at"], day_start_utc, day_end_utc)
    ]
    cart_new_today_rows = [
        row
        for row in cart_only_rows
        if _timestamp_in_window(row["added_at"], day_start_utc, day_end_utc)
    ]

    cart_holder_ids = {
        int(row["user_id"] or 0)
        for row in cart_only_rows
        if int(row["user_id"] or 0) > 0
    }
    request_builder_ids = {
        int(row["user_id"] or 0)
        for row in request_builder_rows
        if int(row["user_id"] or 0) > 0
    }
    order_submitter_ids = {
        int(row["user_id"] or 0)
        for row in submitted_order_rows
        if int(row["user_id"] or 0) > 0
    }
    ordered_customer_ids = set(order_submitter_ids)
    request_segment_ids = request_builder_ids - ordered_customer_ids
    cart_segment_ids = cart_holder_ids - ordered_customer_ids - request_segment_ids
    other_user_ids = all_user_ids - ordered_customer_ids - request_segment_ids - cart_segment_ids

    return {
        "now_local": now_local,
        "today_label": now_local.strftime("%d.%m.%Y"),
        "all_user_ids": all_user_ids,
        "active_today_ids": active_today_ids,
        "active_7d_ids": active_7d_ids,
        "new_users_today": int((new_users_today_row or [0])[0] or 0),
        "cart_only_rows": cart_only_rows,
        "cart_new_today_rows": cart_new_today_rows,
        "submitted_order_rows": submitted_order_rows,
        "order_new_today_rows": order_new_today_rows,
        "broadcast_segments": {
            "all_users": set(all_user_ids),
            "active_miniapp_7d": set(active_7d_ids),
            "cart_holders": set(cart_holder_ids),
            "request_builders": set(request_builder_ids),
            "ordered_customers": set(order_submitter_ids),
        },
        "funnel_segments": {
            "ordered_customers": ordered_customer_ids,
            "request_builders": request_segment_ids,
            "cart_holders": cart_segment_ids,
            "other_users": other_user_ids,
        },
    }


async def get_admin_stats(now: datetime | None = None) -> dict:
    signals = await _collect_admin_user_signals(now)
    total_users = len(signals["all_user_ids"])

    def _segment_payload(key: str, users: set[int]) -> dict:
        count = len(users)
        percent = round((count / total_users) * 100, 1) if total_users else 0.0
        return {
            "key": key,
            "label": ADMIN_SEGMENT_FALLBACK_LABELS[key],
            "count": count,
            "percent": percent,
        }

    return {
        "timezone_label": "МСК",
        "today_label": signals["today_label"],
        "activity_lookback_days": MINIAPP_ACTIVE_LOOKBACK_DAYS,
        "users": {
            "total": total_users,
            "active_today": len(signals["active_today_ids"]),
            "new_today": int(signals["new_users_today"]),
        },
        "cart": {
            "items_total": len(signals["cart_only_rows"]),
            "amount_total_rub": _sum_total_with_margin(signals["cart_only_rows"]),
            "items_new_today": len(signals["cart_new_today_rows"]),
            "amount_new_today_rub": _sum_total_with_margin(signals["cart_new_today_rows"]),
        },
        "orders": {
            "items_total": len(signals["submitted_order_rows"]),
            "amount_total_rub": _sum_total_with_margin(signals["submitted_order_rows"]),
            "items_new_today": len(signals["order_new_today_rows"]),
            "amount_new_today_rub": _sum_total_with_margin(signals["order_new_today_rows"]),
        },
        "segments": [
            _segment_payload("ordered_customers", signals["funnel_segments"]["ordered_customers"]),
            _segment_payload("request_builders", signals["funnel_segments"]["request_builders"]),
            _segment_payload("cart_holders", signals["funnel_segments"]["cart_holders"]),
            _segment_payload("other_users", signals["funnel_segments"]["other_users"]),
        ],
        "broadcast_segments": {
            key: len(user_ids)
            for key, user_ids in signals["broadcast_segments"].items()
        },
    }


async def get_admin_broadcast_segment_counts(now: datetime | None = None) -> dict[str, int]:
    signals = await _collect_admin_user_signals(now)
    return {
        key: len(user_ids)
        for key, user_ids in signals["broadcast_segments"].items()
    }


async def get_admin_broadcast_recipient_ids(segment_key: str, now: datetime | None = None) -> list[int]:
    normalized_key = str(segment_key or "").strip()
    if normalized_key not in ADMIN_BROADCAST_SEGMENT_LABELS:
        raise ValueError("unknown_broadcast_segment")

    signals = await _collect_admin_user_signals(now)
    recipients = signals["broadcast_segments"].get(normalized_key, set())
    return sorted(int(user_id) for user_id in recipients if int(user_id or 0) > 0)
