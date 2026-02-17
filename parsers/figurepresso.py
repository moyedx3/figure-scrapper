"""Parser for figurepresso.com."""

import logging

from bs4 import BeautifulSoup

from models import Product
from parsers.base import Cafe24BaseParser

logger = logging.getLogger(__name__)


class FigurepressoParser(Cafe24BaseParser):
    """
    figurepresso.com — ul.prdList.grid7 > li#anchorBoxId_*
    Product name: p.name a span:last-child
    Price: ul.spec li span (판매가)
    Soldout: img[alt="품절"] vs img[alt="장바구니 담기"]
    URL: /product/{slug}/{id}/category/{cate_no}/display/1/
    """

    def __init__(self):
        super().__init__("figurepresso", "https://figurepresso.com")

    def parse_product_list(self, soup: BeautifulSoup, category: str = "") -> list[Product]:
        products = []
        items = soup.select("ul.prdList li.xans-record-")
        if not items:
            items = soup.select("ul.prdList li[id^='anchorBoxId_']")

        for li in items:
            try:
                product = self._parse_item(li, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.warning(f"[figurepresso] Failed to parse item: {e}")
        return products

    def _parse_item(self, li, category: str) -> Product | None:
        # Product ID
        product_id = self._extract_id_from_anchor_box(li)
        if not product_id:
            return None

        # Product URL
        anchor = li.select_one('a[name^="anchorBoxName_"]')
        href = anchor["href"] if anchor else ""
        url = self._build_product_url(href)

        # Product name — p.name a span (last visible span)
        name_el = li.select_one("p.name a")
        if not name_el:
            name_el = li.select_one("div.description a")
        raw_name = ""
        if name_el:
            spans = name_el.select("span")
            # Get last span that isn't hidden (displaynone)
            for span in reversed(spans):
                if "displaynone" not in span.get("class", []):
                    raw_name = span.get_text(strip=True)
                    break
            if not raw_name:
                raw_name = name_el.get_text(strip=True)

        if not raw_name:
            return None

        # Status from name prefix
        status, name = self.parse_status_prefix(raw_name)

        # Price — ul.spec li span
        price = None
        spec_items = li.select("ul.spec li span")
        for span in spec_items:
            text = span.get_text(strip=True)
            if "원" in text:
                price = self.extract_price(text)
                break

        # Soldout detection
        if self.detect_soldout_from_element(li):
            status = "soldout"
        else:
            # Check cart button alt text
            cart_img = li.select_one('img[alt="장바구니 담기"]')
            soldout_img = li.select_one('img[alt="품절"]')
            if soldout_img and not cart_img:
                status = "soldout"

        # Image
        image_url = self._get_image_url(li)

        return Product(
            site="figurepresso",
            product_id=product_id,
            name=name,
            price=price,
            status=status,
            category=category,
            image_url=image_url,
            url=url,
        )
