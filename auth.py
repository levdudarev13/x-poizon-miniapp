"""Telegram WebApp initData validation and admin check."""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from config import ADMIN_USER_ID, BOT_TOKEN


def validate_init_data(init_data_raw: str, bot_token: str | None = None) -> dict:
    """Validate Telegram Mini App initData via HMAC-SHA256."""
    token = bot_token or BOT_TOKEN
    if not token:
        raise ValueError("BOT_TOKEN not configured")
    if not init_data_raw:
        raise ValueError("Empty initData")

    try:
        parsed = dict(parse_qsl(init_data_raw, strict_parsing=True))
    except ValueError as exc:
        raise ValueError(f"Cannot parse initData: {exc}") from exc

    if "hash" not in parsed:
        raise ValueError("Missing hash")

    received_hash = parsed.pop("hash")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=token.encode(),
        digestmod=hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Hash mismatch")

    return parsed


def get_user_id(validated: dict) -> int:
    """Extract user_id from a previously validated initData payload."""
    user_json = validated.get("user", "{}")
    user = json.loads(user_json)
    return int(user.get("id", 0))


def get_user_id_from_init_data(init_data_raw: str, bot_token: str | None = None) -> int:
    """Shared route helper that turns raw initData into a trusted Telegram user_id."""
    validated = validate_init_data(init_data_raw, bot_token=bot_token)
    return get_user_id(validated)


def is_admin(user_id: int) -> bool:
    """Check if user_id matches ADMIN_USER_ID."""
    return user_id != 0 and user_id == ADMIN_USER_ID
