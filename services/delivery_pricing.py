import math

STANDARD_DELIVERY_TYPE = "standard"
EXPRESS_DELIVERY_TYPE = "express"

DELIVERY_STANDARD_MOSCOW_RUB_500G_KEY = "delivery_standard_moscow_rub_500g"
DELIVERY_AIR_MOSCOW_RUB_500G_KEY = "delivery_air_moscow_rub_500g"
DELIVERY_CDEK_RUSSIA_RUB_500G_KEY = "delivery_cdek_russia_rub_500g"

DELIVERY_STANDARD_MOSCOW_DAYS_KEY = "delivery_standard_moscow_days"
DELIVERY_AIR_MOSCOW_DAYS_KEY = "delivery_air_moscow_days"
DELIVERY_CDEK_RUSSIA_DAYS_KEY = "delivery_cdek_russia_days"

DELIVERY_PRICE_FIELD_KEYS = (
    DELIVERY_AIR_MOSCOW_RUB_500G_KEY,
    DELIVERY_STANDARD_MOSCOW_RUB_500G_KEY,
    DELIVERY_CDEK_RUSSIA_RUB_500G_KEY,
)

DELIVERY_TIMING_FIELD_KEYS = (
    DELIVERY_AIR_MOSCOW_DAYS_KEY,
    DELIVERY_STANDARD_MOSCOW_DAYS_KEY,
    DELIVERY_CDEK_RUSSIA_DAYS_KEY,
)

DELIVERY_INCLUDES_NOTE = "В стоимость доставки входят облицовка и страховка."
DELIVERY_PAYMENT_NOTE = "Доставка оплачивается при получении."

DEFAULT_DELIVERY_PRICE_SETTINGS = {
    DELIVERY_AIR_MOSCOW_RUB_500G_KEY: "1400.0",
    DELIVERY_STANDARD_MOSCOW_RUB_500G_KEY: "500.0",
    DELIVERY_CDEK_RUSSIA_RUB_500G_KEY: "150.0",
}

DEFAULT_DELIVERY_TIMING_SETTINGS = {
    DELIVERY_AIR_MOSCOW_DAYS_KEY: "5-10 дней",
    DELIVERY_STANDARD_MOSCOW_DAYS_KEY: "15-25 дней",
    DELIVERY_CDEK_RUSSIA_DAYS_KEY: "2-5 дней",
}

DELIVERY_MODE_LABELS = {
    STANDARD_DELIVERY_TYPE: "Обычная доставка",
    EXPRESS_DELIVERY_TYPE: "Экспресс доставка",
}

DELIVERY_MODE_ROUTE_LABELS = {
    STANDARD_DELIVERY_TYPE: "Обычная до Москвы",
    EXPRESS_DELIVERY_TYPE: "Авиа до Москвы",
}


def parse_numeric_setting(value: object, default: float = 0.0) -> float:
    try:
        normalized = str(value or "").strip().replace(",", ".").replace(" ", "")
        if not normalized:
            return float(default)
        return float(normalized)
    except (TypeError, ValueError):
        return float(default)


def normalize_delivery_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"express", "fast", "air", "avia"}:
        return EXPRESS_DELIVERY_TYPE
    return STANDARD_DELIVERY_TYPE


def delivery_units_for_weight(weight_kg: object) -> int:
    try:
        weight_value = float(weight_kg or 0)
    except (TypeError, ValueError):
        weight_value = 0.0

    if not math.isfinite(weight_value) or weight_value <= 0:
        weight_value = 0.5

    return max(1, math.ceil(weight_value / 0.5))


def is_moscow_city(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    return "moscow" in normalized or "моск" in normalized


def get_delivery_info(settings: dict | None = None) -> dict:
    settings = settings or {}
    return {
        "standard_days": str(
            settings.get(
                DELIVERY_STANDARD_MOSCOW_DAYS_KEY,
                DEFAULT_DELIVERY_TIMING_SETTINGS[DELIVERY_STANDARD_MOSCOW_DAYS_KEY],
            )
            or ""
        ).strip(),
        "express_days": str(
            settings.get(
                DELIVERY_AIR_MOSCOW_DAYS_KEY,
                DEFAULT_DELIVERY_TIMING_SETTINGS[DELIVERY_AIR_MOSCOW_DAYS_KEY],
            )
            or ""
        ).strip(),
        "cdek_days": str(
            settings.get(
                DELIVERY_CDEK_RUSSIA_DAYS_KEY,
                DEFAULT_DELIVERY_TIMING_SETTINGS[DELIVERY_CDEK_RUSSIA_DAYS_KEY],
            )
            or ""
        ).strip(),
        "includes_note": DELIVERY_INCLUDES_NOTE,
        "payment_note": DELIVERY_PAYMENT_NOTE,
    }


def calculate_delivery_components(
    settings: dict | None,
    *,
    weight_kg: object,
    weight_estimated: bool = False,
    delivery_type: object = STANDARD_DELIVERY_TYPE,
    include_cdek: bool = False,
) -> dict:
    settings = settings or {}
    normalized_type = normalize_delivery_type(delivery_type)
    units_500g = delivery_units_for_weight(weight_kg)
    units_note = f"{units_500g} × 500 г"
    if weight_estimated:
        units_note = f"~{units_note}"

    to_moscow_key = (
        DELIVERY_AIR_MOSCOW_RUB_500G_KEY
        if normalized_type == EXPRESS_DELIVERY_TYPE
        else DELIVERY_STANDARD_MOSCOW_RUB_500G_KEY
    )
    to_moscow_rate = parse_numeric_setting(
        settings.get(to_moscow_key),
        parse_numeric_setting(DEFAULT_DELIVERY_PRICE_SETTINGS[to_moscow_key]),
    )
    cdek_rate = parse_numeric_setting(
        settings.get(DELIVERY_CDEK_RUSSIA_RUB_500G_KEY),
        parse_numeric_setting(DEFAULT_DELIVERY_PRICE_SETTINGS[DELIVERY_CDEK_RUSSIA_RUB_500G_KEY]),
    )

    to_moscow_rub = units_500g * to_moscow_rate
    cdek_rub = units_500g * cdek_rate if include_cdek else 0.0

    return {
        "delivery_type": normalized_type,
        "mode_label": DELIVERY_MODE_LABELS[normalized_type],
        "route_label": DELIVERY_MODE_ROUTE_LABELS[normalized_type],
        "units_500g": units_500g,
        "units_note": units_note,
        "to_moscow_rub": to_moscow_rub,
        "cdek_rub": cdek_rub,
        "total_rub": to_moscow_rub + cdek_rub,
    }


def calculate_pricing_components(
    settings: dict | None,
    *,
    price_cny: object,
    effective_rate: object,
    weight_kg: object,
    weight_estimated: bool = False,
    delivery_type: object = STANDARD_DELIVERY_TYPE,
    include_cdek: bool = False,
) -> dict:
    settings = settings or {}
    goods_rub = float(price_cny or 0) * float(effective_rate or 0)
    commission_pct = parse_numeric_setting(settings.get("commission_pct"), 10.0)
    min_commission_rub = parse_numeric_setting(settings.get("min_commission_rub"), 300.0)
    commission_rub = max(goods_rub * commission_pct / 100, min_commission_rub)
    delivery = calculate_delivery_components(
        settings,
        weight_kg=weight_kg,
        weight_estimated=weight_estimated,
        delivery_type=delivery_type,
        include_cdek=include_cdek,
    )
    subtotal_rub = goods_rub + commission_rub + delivery["total_rub"]

    return {
        "goods_rub": goods_rub,
        "commission_pct": commission_pct,
        "min_commission_rub": min_commission_rub,
        "commission_rub": commission_rub,
        "subtotal_rub": subtotal_rub,
        "delivery": delivery,
    }
