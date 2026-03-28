"""Async SQLite — все операции с базой данных."""
from contextlib import asynccontextmanager
import json
import random
import string
import aiosqlite
from datetime import datetime
from typing import Optional

import time
from config import HISTORY_MAX_ITEMS, SHARE_CODE_LENGTH, DEFAULT_MARGIN_STEPS, DEFAULT_MARGIN_MIN_RUB

# Дефолтные настройки расценок (используются до первого сохранения в БД)
DEFAULT_ADMIN_SETTINGS = {
    "commission_pct":      "10.0",         # комиссия/маржа, %
    "min_commission_rub":  "300.0",        # минимальная комиссия, ₽
    "logistics_rub":       "500.0",        # логистика, ₽
    "insurance_rub":       "200.0",        # страховка, ₽
    "price_per_kg":        "250.0",        # цена за 1 кг (мин. 1 кг, округл. вверх), ₽
    "delivery_time":       "до 2 недель",  # срок доставки (текст)
    "next_shipment_date":  "00.00.0000",   # дата ближайшей отправки
    "rate_override":       "",             # курс ¥→₽ (пусто = авто)
    "rate_override_until": "0",            # timestamp до которого действует ручной курс
}

SHOWCASE_SLOT_COUNT = 10

DB_PATH = "buyer_bot.db"
DELIVERY_PROFILE_FIELDS = (
    "recipient_name",
    "phone",
    "city",
    "street",
    "house",
    "apartment",
    "comment",
)


def _normalize_delivery_profile_payload(delivery_payload: dict | None) -> dict:
    payload = delivery_payload if isinstance(delivery_payload, dict) else {}
    return {
        field: str(payload.get(field) or "").strip()
        for field in DELIVERY_PROFILE_FIELDS
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
        """)
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

        await db.commit()


# ─── Пользователи ─────────────────────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str = "") -> dict:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if row:
            return dict(row)
        default_steps = json.dumps(DEFAULT_MARGIN_STEPS)
        await db.execute(
            "INSERT INTO users (user_id, username, margin_steps, margin_min_rub) VALUES (?,?,?,?)",
            (user_id, username, default_steps, DEFAULT_MARGIN_MIN_RUB),
        )
        await db.commit()
        return {
            "user_id": user_id,
            "username": username,
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
               SET price_cny=?, size=?, subtotal_rub=?,
                   total_with_margin_rub=?, margin_rub=?, margin_percent=?,
                   calc_json=?
               WHERE id=? AND user_id=?""",
            (
                p.price_cny, p.size,
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
                      u.username
               FROM cart_items ci
               JOIN calculations c ON c.id = ci.calculation_id
               JOIN users u ON u.user_id = ci.user_id
               WHERE ci.in_order = 1
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
                      u.username
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
        result[row["key"]] = row["value"]
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
