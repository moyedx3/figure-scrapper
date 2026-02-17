"""Data models for figure scraper."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    site: str
    product_id: str
    name: str
    price: Optional[int] = None
    status: str = "available"  # 'available' | 'soldout' | 'preorder'
    category: Optional[str] = None
    figure_type: Optional[str] = None
    manufacturer: Optional[str] = None
    jan_code: Optional[str] = None
    release_date: Optional[str] = None
    order_deadline: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    has_bonus: bool = False
    image_url: Optional[str] = None
    review_count: int = 0
    url: Optional[str] = None
    # Structured extraction fields
    series: Optional[str] = None
    character_name: Optional[str] = None
    scale: Optional[str] = None
    version: Optional[str] = None
    product_line: Optional[str] = None
    extracted_manufacturer: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_confidence: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StatusChange:
    product_db_id: int
    change_type: str  # 'status' | 'price' | 'new'
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_at: datetime = field(default_factory=datetime.now)
