"""Shared RapidAPI key ordering with runtime and .env persistence."""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from config import (
    DATAHUB_1688_RAPIDAPI_HOST,
    OPEN_1688_RAPIDAPI_HOST,
    RAPIDAPI_FALLBACK_HOST,
    RAPIDAPI_HOST,
    TAOBAO_DATA_RAPIDAPI_HOST,
    TAOBAO_1688_RAPIDAPI_HOST,
    TAOBAO_TMALL_RAPIDAPI_HOST,
)

log = logging.getLogger(__name__)

ENV_FILE_PATH = Path(__file__).resolve().parent.parent / os.getenv("BOT_ENV_FILE", ".env")

_HOST_ENV_NAMES: dict[str, tuple[str, ...]] = {
    RAPIDAPI_HOST: ("RAPIDAPI_KEYS", "RAPIDAPI_KEY"),
    RAPIDAPI_FALLBACK_HOST: ("RAPIDAPI_FALLBACK_KEYS", "RAPIDAPI_KEYS", "RAPIDAPI_KEY"),
    TAOBAO_DATA_RAPIDAPI_HOST: ("TAOBAO_DATA_RAPIDAPI_KEYS", "TAOBAO_TMALL_RAPIDAPI_KEYS"),
    TAOBAO_TMALL_RAPIDAPI_HOST: ("TAOBAO_TMALL_RAPIDAPI_KEYS",),
    TAOBAO_1688_RAPIDAPI_HOST: ("TAOBAO_1688_RAPIDAPI_KEYS", "RAPIDAPI_KEYS", "RAPIDAPI_KEY"),
    OPEN_1688_RAPIDAPI_HOST: (
        "OPEN_1688_RAPIDAPI_KEYS",
        "TAOBAO_1688_RAPIDAPI_KEYS",
        "RAPIDAPI_KEYS",
        "RAPIDAPI_KEY",
    ),
    DATAHUB_1688_RAPIDAPI_HOST: (
        "DATAHUB_1688_RAPIDAPI_KEYS",
        "TAOBAO_1688_RAPIDAPI_KEYS",
        "RAPIDAPI_KEYS",
        "RAPIDAPI_KEY",
    ),
}

_HOST_PREFERRED_ENV_NAMES: dict[str, tuple[str, ...]] = {
    # Keep the paid primary Poizon key at the front on startup for the primary host.
    RAPIDAPI_HOST: ("RAPIDAPI_KEY",),
}

_STATE_LOCK = threading.RLock()


@dataclass
class _KeyPoolState:
    env_names: tuple[str, ...]
    source_name: str | None
    keys: list[str] = field(default_factory=list)


_POOL_STATES: dict[str, _KeyPoolState] = {}


def _parse_env_values(env_names: tuple[str, ...]) -> tuple[list[str], str | None]:
    values: list[str] = []
    for name in env_names:
        raw = os.getenv(name, "")
        if not raw:
            continue
        for part in raw.split(","):
            value = part.strip()
            if value and value not in values:
                values.append(value)
    source_name = env_names[0] if env_names else None
    return values, source_name


def _state_for_host_locked(host: str) -> _KeyPoolState:
    state = _POOL_STATES.get(host)
    if state is not None:
        return state

    env_names = _HOST_ENV_NAMES.get(host, ())
    keys, source_name = _parse_env_values(env_names)
    preferred_names = _HOST_PREFERRED_ENV_NAMES.get(host, ())
    preferred_keys, _ = _parse_env_values(preferred_names)
    if preferred_keys:
        keys = _preferred_order(keys, preferred_keys)
    state = _KeyPoolState(env_names=env_names, source_name=source_name, keys=keys)
    _POOL_STATES[host] = state
    if preferred_keys:
        _persist_env_order_locked(source_name, state.keys)
    return state


def _preferred_order(existing: list[str], preferred: list[str]) -> list[str]:
    ordered = [value for value in preferred if value in existing]
    ordered.extend(value for value in existing if value not in ordered)
    return ordered


def _sync_shared_sources_locked(source_name: str | None, preferred_keys: list[str]) -> None:
    if not source_name:
        return
    for state in _POOL_STATES.values():
        if state.source_name != source_name:
            continue
        state.keys = _preferred_order(state.keys, preferred_keys)


def _persist_env_order_locked(env_name: str | None, keys: list[str]) -> None:
    if not env_name or not keys:
        return

    serialized = ",".join(keys)
    os.environ[env_name] = serialized

    try:
        content = ENV_FILE_PATH.read_text(encoding="utf-8") if ENV_FILE_PATH.exists() else ""
        line = f"{env_name}={serialized}"
        pattern = re.compile(rf"(?m)^{re.escape(env_name)}=.*$")
        if pattern.search(content):
            updated = pattern.sub(line, content)
        else:
            updated = content.rstrip("\r\n")
            if updated:
                updated += "\n"
            updated += f"{line}\n"
        if updated != content:
            ENV_FILE_PATH.write_text(updated, encoding="utf-8")
    except Exception:
        log.warning("Failed to persist RapidAPI key order for %s", env_name, exc_info=True)


def get_rapidapi_keys(host: str) -> tuple[str, ...]:
    with _STATE_LOCK:
        return tuple(_state_for_host_locked(host).keys)


def rotate_rapidapi_key_to_end(host: str, rapidapi_key: str) -> tuple[str, ...]:
    clean_key = str(rapidapi_key or "").strip()
    if not clean_key:
        return ()

    with _STATE_LOCK:
        state = _state_for_host_locked(host)
        if clean_key not in state.keys:
            return tuple(state.keys)
        if len(state.keys) < 2 or state.keys[-1] == clean_key:
            return tuple(state.keys)

        state.keys = [value for value in state.keys if value != clean_key]
        state.keys.append(clean_key)
        _sync_shared_sources_locked(state.source_name, state.keys)
        _persist_env_order_locked(state.source_name, state.keys)
        log.info("RapidAPI key order updated for host=%s after quota hit", host)
        return tuple(state.keys)


def reset_rapidapi_key_cache() -> None:
    with _STATE_LOCK:
        _POOL_STATES.clear()
