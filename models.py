"""Модели данных."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class ExchangeRate:
    cny_rub: float
    usd_rub: float
    eur_rub: float
    updated_at: datetime

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.updated_at).total_seconds()

    @property
    def age_human(self) -> str:
        age = int(self.age_seconds)
        if age < 60:
            return "только что"
        if age < 3600:
            return f"{age // 60} мин. назад"
        return f"{age // 3600} ч. назад"


@dataclass
class ProductDraft:
    """Карточка товара в процессе сборки (хранится в user_data)."""
    url: str = ""
    platform: str = "unknown"
    name: str = ""
    brand: str = ""
    price_cny: Optional[float] = None
    price_is_starting: bool = False
    size: str = ""
    category: str = ""
    weight_kg: Optional[float] = None
    weight_estimated: bool = False
    city: str = ""
    delivery_type: str = ""
    image_url: str = ""
    extra_images: list = None  # фото 2, 3, 4 для карточки характеристик
    specs: dict = None        # все атрибуты с сайта {"鞋面材质": "皮革", ...}
    available_sizes: list = None  # доступные размеры ["42", "43", ...]
    variants: list = None     # группы вариантов [{"name": "Цвет", "options": ["Чёрный", "Белый"]}, ...]
    variant_price_map: dict = None  # цены для конкретных комбинаций вариантов
    original_variants: list = None  # сохранённые группы вариантов для "Изменить" в корзине
    notes: str = ""           # заметка пользователя (вариант без цены)
    auto_detected: list = None

    def __post_init__(self):
        if self.auto_detected is None:
            self.auto_detected = []
        if self.specs is None:
            self.specs = {}
        if self.available_sizes is None:
            self.available_sizes = []
        if self.variants is None:
            self.variants = []
        if self.variant_price_map is None:
            self.variant_price_map = {}
        if self.original_variants is None:
            self.original_variants = []
        if self.extra_images is None:
            self.extra_images = []

    def is_ready(self) -> bool:
        return bool(
            self.price_cny
            and not self.price_is_starting
            and self.weight_kg
        )


@dataclass
class BreakdownLine:
    label: str
    amount_rub: float
    note: str = ""


@dataclass
class CalculationResult:
    """Полный результат расчёта."""
    product: ProductDraft
    breakdown: list  # list[BreakdownLine]
    subtotal_rub: float      # без маржи
    margin_rub: float
    total_with_margin_rub: float
    margin_percent: float
    exchange_rate: ExchangeRate
    calc_id: Optional[int] = None
    share_code: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def total_client_rub(self) -> float:
        return self.subtotal_rub

    @property
    def total_rounded(self) -> float:
        """Рекомендованная цена клиенту (округление до 50₽)."""
        t = self.total_with_margin_rub
        return round(t / 50) * 50

    def to_dict(self) -> dict:
        return {
            "url": self.product.url,
            "platform": self.product.platform,
            "name": self.product.name,
            "price_cny": self.product.price_cny,
            "price_is_starting": self.product.price_is_starting,
            "size": self.product.size,
            "category": self.product.category,
            "weight_kg": self.product.weight_kg,
            "weight_estimated": self.product.weight_estimated,
            "city": self.product.city,
            "delivery_type": self.product.delivery_type,
            "notes": getattr(self.product, "notes", ""),
            "image_url": getattr(self.product, "image_url", ""),
            "variants": getattr(self.product, "variants", []) or [],
            "original_variants": getattr(self.product, "original_variants", []) or [],
            "variant_price_map": getattr(self.product, "variant_price_map", {}) or {},
            "specs": getattr(self.product, "specs", {}) or {},
            "available_sizes": getattr(self.product, "available_sizes", []) or [],
            "extra_images": getattr(self.product, "extra_images", []) or [],
            "subtotal_rub": self.subtotal_rub,
            "margin_rub": self.margin_rub,
            "total_with_margin_rub": self.total_with_margin_rub,
            "margin_percent": self.margin_percent,
            "breakdown": [
                {"label": b.label, "amount_rub": b.amount_rub, "note": b.note}
                for b in self.breakdown
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, rate: "ExchangeRate") -> "CalculationResult":
        from config import CATEGORIES
        product = ProductDraft(
            url=data["url"],
            platform=data["platform"],
            name=data["name"],
            price_cny=data["price_cny"],
            price_is_starting=bool(data.get("price_is_starting", False)),
            size=data.get("size", ""),
            category=data.get("category", ""),
            weight_kg=data["weight_kg"],
            weight_estimated=data.get("weight_estimated", False),
            city=data["city"],
            delivery_type=data["delivery_type"],
            notes=data.get("notes", ""),
            image_url=data.get("image_url", ""),
            variants=data.get("variants", []),
            original_variants=data.get("original_variants", []),
            variant_price_map=data.get("variant_price_map", {}),
            specs=data.get("specs", {}),
            available_sizes=data.get("available_sizes", []),
            extra_images=data.get("extra_images", []),
        )
        breakdown = [
            BreakdownLine(b["label"], b["amount_rub"], b.get("note", ""))
            for b in data.get("breakdown", [])
        ]
        return cls(
            product=product,
            breakdown=breakdown,
            subtotal_rub=data["subtotal_rub"],
            margin_rub=data["margin_rub"],
            total_with_margin_rub=data["total_with_margin_rub"],
            margin_percent=data["margin_percent"],
            exchange_rate=rate,
        )


@dataclass
class UserSettings:
    user_id: int
    margin_steps: list = field(default_factory=list)  # [(threshold, percent), ...]
    margin_min_rub: float = 500.0

    def get_margin_percent(self, subtotal_rub: float) -> float:
        """Вернуть % маржи для данной суммы согласно ступеням."""
        percent = 10.0
        for threshold, pct in sorted(self.margin_steps, key=lambda x: x[0]):
            if subtotal_rub >= threshold:
                percent = pct
        return percent

    def calc_margin(self, subtotal_rub: float) -> float:
        pct = self.get_margin_percent(subtotal_rub)
        margin = subtotal_rub * pct / 100
        return max(margin, self.margin_min_rub)
