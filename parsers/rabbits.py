"""Parser for rabbits.kr."""

import logging

from bs4 import BeautifulSoup

from models import Product
from parsers.base import Cafe24BaseParser

logger = logging.getLogger(__name__)


class RabbitsParser(Cafe24BaseParser):
    """
    rabbits.kr — ul.prdList.grid6 > li#anchorBoxId_*
    Product name: p.name a (direct text, not in span)
    Price: data-price="^91500" on li, or ul.spec li span
    Bonus badges: 특전증정, 특전포함, 공식유통 (icon images in div.status)
    URL: /product/{slug}/{id}/category/{cate_no}/display/1/
    """

    def __init__(self):
        super().__init__("rabbits", "https://rabbits.kr")

    def parse_product_list(self, soup: BeautifulSoup, category: str = "") -> list[Product]:
        products = []
        items = soup.select("ul.prdList li[id^='anchorBoxId_']")
        if not items:
            items = soup.select("ul.prdList li.xans-record-")

        for li in items:
            try:
                product = self._parse_item(li, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.warning(f"[rabbits] Failed to parse item: {e}")
        return products

    def _parse_item(self, li, category: str) -> Product | None:
        product_id = self._extract_id_from_anchor_box(li)
        if not product_id:
            return None

        # URL
        anchor = li.select_one('a[name^="anchorBoxName_"]')
        href = anchor["href"] if anchor else ""
        url = self._build_product_url(href)

        # Name — p.name a: name is a direct text node after hidden span.title
        name_el = li.select_one("p.name a")
        raw_name = ""
        if name_el:
            from bs4 import NavigableString
            # Get direct text nodes (skip Tag children like hidden spans)
            text_parts = [
                str(child).strip()
                for child in name_el.children
                if isinstance(child, NavigableString) and str(child).strip()
            ]
            if text_parts:
                raw_name = " ".join(text_parts)
            else:
                # Fallback: full text minus hidden span text
                hidden_text = ""
                for span in name_el.select("span.displaynone, span.title"):
                    hidden_text += span.get_text()
                raw_name = name_el.get_text(strip=True)
                if hidden_text:
                    raw_name = raw_name.replace(hidden_text.strip(), "").strip()
                # Strip leading ":" if leftover
                raw_name = raw_name.lstrip(":").strip()

        if not raw_name:
            return None

        status, name = self.parse_status_prefix(raw_name)

        # Price — data-price attribute (e.g., "^91500" or "^170000^85000") or spec list
        price = None
        data_price = li.get("data-price", "")
        if data_price:
            price = self.extract_sale_price_from_data_attr(data_price)
        if price is None:
            spec_items = li.select("ul.spec li span")
            for span in spec_items:
                text = span.get_text(strip=True)
                if "원" in text:
                    price = self.extract_price(text)
                    break

        # Soldout
        if self.detect_soldout_from_element(li):
            status = "soldout"

        # Bonus detection from product name
        has_bonus = "특전포함" in raw_name or "특전증정" in raw_name

        image_url = self._get_image_url(li)

        return Product(
            site="rabbits",
            product_id=product_id,
            name=name,
            price=price,
            status=status,
            category=category,
            has_bonus=has_bonus,
            image_url=image_url,
            url=url,
        )
