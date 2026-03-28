"""Bot constants and pricing defaults."""

import os

from dotenv import load_dotenv

ENV_FILE: str = os.getenv("BOT_ENV_FILE", ".env")
load_dotenv(ENV_FILE)


def _parse_env_list(*names: str) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        raw = os.getenv(name, "")
        if not raw:
            continue
        for part in raw.split(","):
            value = part.strip()
            if value and value not in values:
                values.append(value)
    return tuple(values)


DEWU_TOKEN: str = os.getenv("DEWU_TOKEN", "")
RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list("RAPIDAPI_KEYS", "RAPIDAPI_KEY")
RAPIDAPI_HOST: str = os.getenv("RAPIDAPI_HOST", "open-poizon-api.p.rapidapi.com")
RAPIDAPI_FALLBACK_HOST: str = os.getenv("RAPIDAPI_FALLBACK_HOST", "open-dewu-api.p.rapidapi.com")
RAPIDAPI_FALLBACK_KEYS: tuple[str, ...] = _parse_env_list(
    "RAPIDAPI_FALLBACK_KEYS",
    "RAPIDAPI_KEYS",
    "RAPIDAPI_KEY",
)
TAOBAO_DATA_RAPIDAPI_HOST: str = os.getenv(
    "TAOBAO_DATA_RAPIDAPI_HOST",
    "api-for-data-taobao-1688.p.rapidapi.com",
)
TAOBAO_DATA_RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list(
    "TAOBAO_DATA_RAPIDAPI_KEYS",
    "TAOBAO_TMALL_RAPIDAPI_KEYS",
)
TAOBAO_TMALL_RAPIDAPI_HOST: str = os.getenv("TAOBAO_TMALL_RAPIDAPI_HOST", "taobao-tmall1.p.rapidapi.com")
TAOBAO_TMALL_RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list(
    "TAOBAO_TMALL_RAPIDAPI_KEYS",
)
TAOBAO_1688_RAPIDAPI_HOST: str = os.getenv("TAOBAO_1688_RAPIDAPI_HOST", "taobao-tmall-16881.p.rapidapi.com")
TAOBAO_1688_RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list(
    "TAOBAO_1688_RAPIDAPI_KEYS",
    "RAPIDAPI_KEYS",
    "RAPIDAPI_KEY",
)
OPEN_1688_RAPIDAPI_HOST: str = os.getenv("OPEN_1688_RAPIDAPI_HOST", "open-1688-api.p.rapidapi.com")
OPEN_1688_RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list(
    "OPEN_1688_RAPIDAPI_KEYS",
    "TAOBAO_1688_RAPIDAPI_KEYS",
    "RAPIDAPI_KEYS",
    "RAPIDAPI_KEY",
)
DATAHUB_1688_RAPIDAPI_HOST: str = os.getenv("DATAHUB_1688_RAPIDAPI_HOST", "1688-datahub.p.rapidapi.com")
DATAHUB_1688_RAPIDAPI_KEYS: tuple[str, ...] = _parse_env_list(
    "DATAHUB_1688_RAPIDAPI_KEYS",
    "TAOBAO_1688_RAPIDAPI_KEYS",
    "RAPIDAPI_KEYS",
    "RAPIDAPI_KEY",
)
RAPIDAPI_QUOTA_PERIODS: dict[str, str] = {
    "open-poizon-api.p.rapidapi.com": "monthly",
    "open-dewu-api.p.rapidapi.com": "monthly",
    "open-1688-api.p.rapidapi.com": "monthly",
    "1688-datahub.p.rapidapi.com": "monthly",
    "taobao-tmall1.p.rapidapi.com": "daily",
    "taobao-tmall-16881.p.rapidapi.com": "daily",
}
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
ADMIN_USER_ID: int = int(os.getenv("ADMIN_USER_ID", "0"))
ADMIN_USER_IDS: tuple[int, ...] = tuple(
    user_id
    for user_id in (
        int(value)
        for value in _parse_env_list("ADMIN_USER_IDS", "ADMIN_USER_ID")
    )
    if user_id > 0
)
ADMIN_CONTACT_USER_ID: int = int(os.getenv("ADMIN_CONTACT_USER_ID", "0"))
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_CONTACT_USERNAME: str = os.getenv("ADMIN_CONTACT_USERNAME", "")
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "")
PROXY: str = os.getenv("PROXY", "")
OZON_PROXY: str = os.getenv("OZON_PROXY", "")
MINI_APP_URL: str = os.getenv("MINI_APP_URL", "")
MINI_APP_PORT: int = int(os.getenv("MINI_APP_PORT", "8080"))


def rapidapi_quota_period(host: str) -> str:
    return RAPIDAPI_QUOTA_PERIODS.get(host, "unknown")


PLATFORM_POIZON = "poizon"
PLATFORM_TAOBAO = "taobao"
PLATFORM_1688 = "1688"
PLATFORM_UNKNOWN = "unknown"

PLATFORM_DISPLAY = {
    PLATFORM_POIZON: "Poizon",
    PLATFORM_TAOBAO: "Taobao",
    PLATFORM_1688: "1688",
    PLATFORM_UNKNOWN: "Unknown",
}

PLATFORM_URL_PATTERNS = {
    PLATFORM_POIZON: ["dewu.com", "poizon.com", "dw4.co", "du.com"],
    PLATFORM_TAOBAO: ["taobao.com", "tb.cn", "s.click.taobao", "e.tb.cn"],
    PLATFORM_1688: ["1688.com"],
}

PLATFORM_COMMISSIONS = {
    PLATFORM_POIZON: 0.08,
    PLATFORM_TAOBAO: 0.03,
    PLATFORM_1688: 0.02,
    PLATFORM_UNKNOWN: 0.05,
}

CHINA_DOMESTIC_SHIPPING_CNY = {
    PLATFORM_POIZON: 0.0,
    PLATFORM_TAOBAO: 60.0,
    PLATFORM_1688: 50.0,
    PLATFORM_UNKNOWN: 55.0,
}

DELIVERY_FAST = "fast"
DELIVERY_STANDARD = "standard"
DELIVERY_CHEAP = "cheap"

DELIVERY_DISPLAY = {
    DELIVERY_FAST: "Fast",
    DELIVERY_STANDARD: "Standard",
    DELIVERY_CHEAP: "Budget",
}

DELIVERY_DAYS = {
    DELIVERY_FAST: "7-14 days",
    DELIVERY_STANDARD: "14-21 days",
    DELIVERY_CHEAP: "21-40 days",
}

DELIVERY_RATE_RUB_PER_KG = {
    DELIVERY_FAST: 2000.0,
    DELIVERY_STANDARD: 1300.0,
    DELIVERY_CHEAP: 800.0,
}

DELIVERY_MIN_WEIGHT_KG = 0.3
WAREHOUSE_FEE_RUB = 120.0

INSURANCE_THRESHOLD_RUB = 5000.0
INSURANCE_RATE = 0.015

CATEGORIES = {
    "sneakers": ("Sneakers / Shoes", 1.0),
    "clothing": ("Clothing", 0.5),
    "accessories": ("Accessories", 0.2),
    "bag": ("Bag", 0.7),
    "electronics": ("Electronics", 0.8),
    "other": ("Other", 0.5),
}

PRICE_RANGES_CNY = {
    "sneakers": (150, 15000),
    "clothing": (50, 5000),
    "accessories": (20, 3000),
    "bag": (80, 8000),
    "electronics": (100, 30000),
    "other": (10, 100000),
}

CITIES = {
    "moscow": "Moscow",
    "spb": "Saint Petersburg",
    "ekb": "Ekaterinburg",
    "nsk": "Novosibirsk",
    "other": "Other city",
}

CITY_SURCHARGE_RUB = {
    "moscow": 0.0,
    "spb": 400.0,
    "ekb": 600.0,
    "nsk": 700.0,
    "other": 500.0,
}

DEFAULT_MARGIN_STEPS = [
    (0, 15.0),
    (3000, 12.0),
    (10000, 10.0),
    (25000, 8.0),
]
DEFAULT_MARGIN_MIN_RUB = 500.0

EXCHANGE_RATE_STALE_SECONDS = 7200
HISTORY_MAX_ITEMS = 20
SHARE_CODE_LENGTH = 6

CLIENT_MSG_TEMPLATES = {
    "standard": (
        "Hi! Here is the order estimate.\n\n"
        "{product_name}\n\n"
        "Price: {total_rub}\n"
        "Delivery time: {delivery_days}\n\n"
        "The estimate includes the item, buying service and delivery from China.\n"
        "The price is based on the current rate {cny_rate} RUB/CNY."
    ),
    "prepayment": (
        "To place the order:\n\n"
        "1. Confirm the item\n"
        "2. Pay 100% in advance\n"
        "3. We buy it out and ship it\n"
        "4. Delivery takes {delivery_days}\n\n"
        "Questions? Reply here."
    ),
    "tracking": (
        "Your order has been shipped.\n\n"
        "{product_name}\n\n"
        "Tracking: {tracking}\n"
        "ETA: {delivery_days}"
    ),
}
