"""Parser for comics-art.co.kr."""

import logging

from bs4 import BeautifulSoup

from models import Product
from parsers.base import Cafe24BaseParser

logger = logging.getLogger(__name__)


class ComicsArtParser(Cafe24BaseParser):
    """
    comics-art.co.kr — ul.prdList.grid8 > li#anchorBoxId_*
    Product name: strong.name a span:last-child
    Price/metadata: ul.spec li (판매가, 제조사, 주문마감일, 발매월)
    Soldout: div.sold with inner img
    URL: /product/{slug}/{id}/category/{cate_no}/display/1/
    """

    def __init__(self):
        super().__init__("comicsart", "https://comics-art.co.kr")

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
                logger.warning(f"[comicsart] Failed to parse item: {e}")
        return products

    def _parse_item(self, li, category: str) -> Product | None:
        product_id = self._extract_id_from_anchor_box(li)
        if not product_id:
            return None

        # URL
        anchor = li.select_one('a[name^="anchorBoxName_"]')
        href = anchor["href"] if anchor else ""
        url = self._build_product_url(href)

        # Name — strong.name a span:last-child
        name_el = li.select_one("strong.name a")
        if not name_el:
            name_el = li.select_one("div.description a")
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

        # Metadata from ul.spec li
        price = None
        manufacturer = None
        order_deadline = None
        release_date = None

        spec_items = li.select("ul.spec li")
        for spec_li in spec_items:
            strong = spec_li.select_one("strong")
            label = strong.get_text(strip=True) if strong else ""
            # Get the last non-empty span value (some spans are empty)
            value_spans = spec_li.select("span")
            value = ""
            for vs in reversed(value_spans):
                text = vs.get_text(strip=True)
                if text and text != label.rstrip(":").strip():
                    value = text
                    break

            if "판매가" in label:
                price = self.extract_price(value)
            elif "제조사" in label:
                manufacturer = value
            elif "주문 마감일" in label or "마감일" in label:
                order_deadline = value
            elif "발매월" in label:
                release_date = value

        # Soldout — div.sold with img inside
        if self.detect_soldout_from_element(li):
            status = "soldout"

        image_url = self._get_image_url(li)

        return Product(
            site="comicsart",
            product_id=product_id,
            name=name,
            price=price,
            status=status,
            category=category,
            manufacturer=manufacturer,
            release_date=release_date,
            order_deadline=order_deadline,
            image_url=image_url,
            url=url,
        )
