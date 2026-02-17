"""Pydantic models for structured product extraction."""

from pydantic import BaseModel


class ProductAttributes(BaseModel):
    """Structured fields extracted from a product name."""

    series: str | None = None  # 작품명 (anime/game/manga title)
    character_name: str | None = None  # 캐릭터명
    manufacturer: str | None = None  # 제조사/브랜드
    scale: str | None = None  # 1/7, 1/6, non-scale, etc.
    version: str | None = None  # 바니 ver., 재판, deluxe, etc.
    product_line: str | None = None  # POP UP PARADE, figma, 넨도로이드, etc.
    product_type: str | None = None  # figure, plushie, keychain, acrylic, etc.
