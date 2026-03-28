"""Получение и кэширование курса валют (ЦБ РФ)."""
import httpx
from datetime import datetime
from typing import Optional

from models import ExchangeRate
import database as db

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"

# In-memory кэш
_cached: Optional[ExchangeRate] = None


async def fetch_from_cbr() -> Optional[ExchangeRate]:
    """Запросить свежий курс с сайта ЦБ РФ."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(CBR_URL)
            resp.raise_for_status()
            data = resp.json()

        valute = data.get("Valute", {})

        def get_rate(code: str) -> float:
            v = valute.get(code, {})
            val = v.get("Value", 0)
            nominal = v.get("Nominal", 1)
            return round(val / nominal, 4) if nominal else 0.0

        cny = get_rate("CNY")
        usd = get_rate("USD")
        eur = get_rate("EUR")

        if cny > 0:
            await db.save_exchange_rate(cny, usd, eur)
            rate = ExchangeRate(cny_rub=cny, usd_rub=usd, eur_rub=eur, updated_at=datetime.now())
            return rate
    except Exception:
        pass
    return None


async def get_rate(force_refresh: bool = False) -> Optional[ExchangeRate]:
    """Вернуть актуальный курс (из кэша или запросить заново)."""
    global _cached

    if not force_refresh and _cached and _cached.age_seconds < 3600:
        return _cached

    # Пробуем получить свежий курс
    fresh = await fetch_from_cbr()
    if fresh:
        _cached = fresh
        return _cached

    # Берём из БД (если сеть недоступна)
    row = await db.get_latest_exchange_rate()
    if row:
        updated_at = datetime.fromisoformat(row["updated_at"])
        _cached = ExchangeRate(
            cny_rub=row["cny_rub"],
            usd_rub=row["usd_rub"],
            eur_rub=row["eur_rub"],
            updated_at=updated_at,
        )
        return _cached

    # Аварийный фолбэк
    return ExchangeRate(cny_rub=12.5, usd_rub=90.0, eur_rub=97.0, updated_at=datetime.now())
