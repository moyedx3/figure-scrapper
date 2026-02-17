"""Parser for ttabbaemall.co.kr."""

import logging
import re

from bs4 import BeautifulSoup

from models import Product
from parsers.base import Cafe24BaseParser

logger = logging.getLogger(__name__)


class TtabbaemallParser(Cafe24BaseParser):
    """
    ttabbaemall.co.kr — ul.prdList.grid6 > li#anchorBoxId_*
    Product name: p.name a span:last-child
    Price: li[rel="판매가"] span, or data-price="^3000"
    URL: /product/detail.html?product_no=XXXXX
    """

    def __init__(self):
        super().__init__("ttabbaemall", "https://ttabbaemall.co.kr")

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
                logger.warning(f"[ttabbaemall] Failed to parse item: {e}")
        return products

    def _parse_item(self, li, category: str) -> Product | None:
        product_id = self._extract_id_from_anchor_box(li)
        if not product_id:
            return None

        # URL
        anchor = li.select_one('a[name^="anchorBoxName_"]')
        href = anchor["href"] if anchor else ""
        url = self._build_product_url(href)

        # Name — p.name a span:last-child
        name_el = li.select_one("p.name a")
        raw_name = ""
        if name_el:
            spans = name_el.select("span")
            for span in reversed(spans):
                if "displaynone" not in span.get("class", []):
                    raw_name = span.get_text(strip=True)
                    break
            if not raw_name:
                raw_name = name_el.get_text(strip=True)

        if not raw_name:
            return None

        status, name = self.parse_status_prefix(raw_name)

        # Price — data-price (e.g., "^69000^64000") or li[rel="판매가"] span or ul.spec li span
        price = None
        data_price = li.get("data-price", "")
        if data_price:
            price = self.extract_sale_price_from_data_attr(data_price)

        if price is None:
            # Try li[rel="판매가"] span
            price_li = li.select_one('li[rel="판매가"]')
            if price_li:
                price_span = price_li.select("span")
                for span in price_span:
                    text = span.get_text(strip=True)
                    if "원" in text:
                        price = self.extract_price(text)
                        break

        if price is None:
            spec_items = li.select("ul.spec li span")
            for span in spec_items:
                text = span.get_text(strip=True)
                if "원" in text:
                    price = self.extract_price(text)
                    break

        # Order deadline — look for 예약 마감일 text
        order_deadline = None
        spec_items = li.select("ul.spec li")
        for spec_li in spec_items:
            text = spec_li.get_text(strip=True)
            match = re.search(r"예약\s*마감일\s*[:：]\s*(.+)", text)
            if match:
                order_deadline = match.group(1).strip()
                break

        # Soldout
        if self.detect_soldout_from_element(li):
            status = "soldout"

        image_url = self._get_image_url(li)

        return Product(
            site="ttabbaemall",
            product_id=product_id,
            name=name,
            price=price,
            status=status,
            category=category,
            order_deadline=order_deadline,
            image_url=image_url,
            url=url,
        )
