"""Mini App auth helpers for Telegram and VK launch contexts."""

from base64 import b64encode
import hashlib
import hmac
import json
from urllib.parse import parse_qsl, urlencode, urlparse

from config import ADMIN_USER_IDS, BOT_TOKEN, VK_MINI_APP_SECURE_KEY


def _normalize_query_string(raw_value: str) -> str:
    normalized = str(raw_value or "").strip()
    if not normalized:
        raise ValueError("Empty query")
    if "://" in normalized:
        normalized = urlparse(normalized).query
    if normalized.startswith("?"):
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("Empty query")
    return normalized


def _parse_signed_query(raw_value: str) -> dict:
    normalized = _normalize_query_string(raw_value)
    try:
        parsed = dict(parse_qsl(normalized, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise ValueError(f"Cannot parse query: {exc}") from exc
    if not parsed:
        raise ValueError("Empty query")
    return parsed


def validate_init_data(init_data_raw: str, bot_token: str | None = None) -> dict:
    """Validate Telegram Mini App initData via HMAC-SHA256."""
    token = bot_token or BOT_TOKEN
    if not token:
        raise ValueError("BOT_TOKEN not configured")
    if not init_data_raw:
        raise ValueError("Empty initData")

    try:
        parsed = dict(parse_qsl(_normalize_query_string(init_data_raw), strict_parsing=True))
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


def get_user(validated: dict) -> dict:
    """Extract Telegram user payload from a previously validated initData payload."""
    raw_user = validated.get("user", "{}")

    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid user payload") from exc

    if not isinstance(user, dict):
        raise ValueError("Invalid user payload")

    return user


def get_user_id(validated: dict) -> int:
    """Extract user_id from a previously validated initData payload."""
    user = get_user(validated)
    return int(user.get("id", 0))


def get_user_id_from_init_data(init_data_raw: str, bot_token: str | None = None) -> int:
    """Shared route helper that turns raw initData into a trusted Telegram user_id."""
    validated = validate_init_data(init_data_raw, bot_token=bot_token)
    return get_user_id(validated)


def get_user_profile_from_init_data(init_data_raw: str, bot_token: str | None = None) -> dict:
    """Resolve trusted Telegram profile fields from raw signed initData."""
    validated = validate_init_data(init_data_raw, bot_token=bot_token)
    user = get_user(validated)
    return {
        "id": int(user.get("id", 0) or 0),
        "username": str(user.get("username") or "").strip(),
        "first_name": str(user.get("first_name") or "").strip(),
        "last_name": str(user.get("last_name") or "").strip(),
    }


def validate_vk_launch_params(
    launch_params_raw: str,
    secure_key: str | None = None,
) -> dict:
    """Validate VK Mini Apps launch params via HMAC-SHA256."""
    key = secure_key or VK_MINI_APP_SECURE_KEY
    if not key:
        raise ValueError("VK_MINI_APP_SECURE_KEY not configured")

    parsed = _parse_signed_query(launch_params_raw)
    received_sign = str(parsed.get("sign") or "").strip()
    if not received_sign:
        raise ValueError("Missing sign")

    ordered_vk_keys = sorted(key for key in parsed if key.startswith("vk_"))
    if not ordered_vk_keys:
        raise ValueError("Missing vk launch params")

    ordered_vk_payload = {key: parsed[key] for key in ordered_vk_keys}
    computed_sign = b64encode(
        hmac.new(
            key.encode(),
            urlencode(ordered_vk_payload, doseq=True).encode(),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8").rstrip("=").replace("+", "-").replace("/", "_")

    if not hmac.compare_digest(computed_sign, received_sign):
        raise ValueError("Sign mismatch")

    return parsed


def get_user_id_from_vk_launch_params(
    launch_params_raw: str,
    secure_key: str | None = None,
) -> int:
    """Resolve trusted VK user_id from signed launch params."""
    validated = validate_vk_launch_params(launch_params_raw, secure_key=secure_key)
    try:
        user_id = int(validated.get("vk_user_id") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid vk_user_id") from exc
    if user_id <= 0:
        raise ValueError("Invalid vk_user_id")
    return user_id


def get_user_profile_from_vk_launch_params(
    launch_params_raw: str,
    secure_key: str | None = None,
) -> dict:
    """Normalize VK launch identity into the app profile shape."""
    return {
        "id": get_user_id_from_vk_launch_params(launch_params_raw, secure_key=secure_key),
        "username": "",
        "first_name": "",
        "last_name": "",
    }


def is_admin(user_id: int) -> bool:
    """Check if user_id is present in the configured admin allowlist."""
    return user_id != 0 and user_id in ADMIN_USER_IDS
