"""Parser for maniahouse.co.kr."""

import logging
import re

from bs4 import BeautifulSoup

from models import Product
from parsers.base import Cafe24BaseParser

logger = logging.getLogger(__name__)


class ManiahouseParser(Cafe24BaseParser):
    """
    maniahouse.co.kr — div.xans-product-listnormal > ul > li.xans-record-
    Different from other sites: uses listnormal layout, not prdList grid.
    Product name: a.name span
    Price/metadata: ul.xans-product-listitem li span.value
    URL: /product/detail.html?product_no=XXXXX
    """

    def __init__(self):
        super().__init__("maniahouse", "https://maniahouse.co.kr")

    def parse_product_list(self, soup: BeautifulSoup, category: str = "") -> list[Product]:
        products = []
        # maniahouse uses xans-product-listnormal layout
        container = soup.select_one("div.xans-product-listnormal")
        if not container:
            logger.warning("[maniahouse] Could not find xans-product-listnormal container")
            return products

        items = container.select("li.xans-record-")
        for li in items:
            try:
                product = self._parse_item(li, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.warning(f"[maniahouse] Failed to parse item: {e}")
        return products

    def _parse_item(self, li, category: str) -> Product | None:
        # Product ID — from href (product_no=XXXXX) or checkbox class
        product_id = None
        link = li.select_one("a.prdImg") or li.select_one("a.name")
        href = link["href"] if link else ""

        if href:
            product_id = self.extract_product_id_from_url(href)

        if not product_id:
            product_id = self._extract_id_from_anchor_box(li)

        if not product_id:
            return None

        url = self._build_product_url(href)

        # Name — a.name span
        name_el = li.select_one("a.name")
        raw_name = ""
        if name_el:
            span = name_el.select_one("span")
            raw_name = span.get_text(strip=True) if span else name_el.get_text(strip=True)

        if not raw_name:
            return None

        status, name = self.parse_status_prefix(raw_name)

        # Metadata — ul.xans-product-listitem li
        price = None
        manufacturer = None
        review_count = 0

        spec_items = li.select("ul.xans-product-listitem li")
        for spec_li in spec_items:
            strong = spec_li.select_one("strong.title")
            if not strong:
                continue
            label = strong.get_text(strip=True)
            label_text = label.rstrip(":").strip()
            # Find last non-empty span that isn't the label
            value_spans = spec_li.select("span")
            value = ""
            for vs in reversed(value_spans):
                text = vs.get_text(strip=True)
                if text and text != label_text and text != ":" and text != label:
                    value = text
                    break

            if "판매가" in label:
                price = self.extract_price(value)
            elif "제조사" in label:
                manufacturer = value

        # Review count from likePrdCount span
        like_span = li.select_one("span[class*='likePrdCount']")
        if like_span:
            count_text = like_span.get_text(strip=True)
            if count_text.isdigit():
                review_count = int(count_text)

        # Soldout detection
        if self.detect_soldout_from_element(li):
            status = "soldout"

        image_url = self._get_image_url(li)

        return Product(
            site="maniahouse",
            product_id=product_id,
            name=name,
            price=price,
            status=status,
            category=category,
            manufacturer=manufacturer,
            review_count=review_count,
            image_url=image_url,
            url=url,
        )
