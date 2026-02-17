"""Base parser for Cafe24-based figure shopping malls."""

import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from config import REQUEST_DELAY, REQUEST_TIMEOUT, USER_AGENT, MAX_PAGES
from models import Product

logger = logging.getLogger(__name__)


class Cafe24BaseParser:
    """Shared parsing logic for Cafe24-based figure shops."""

    def __init__(self, site_name: str, base_url: str):
        self.site_name = site_name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return parsed BeautifulSoup, or None on error."""
        full_url = url if url.startswith("http") else urljoin(self.base_url, url)
        try:
            resp = self.session.get(full_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.error(f"[{self.site_name}] Failed to fetch {full_url}: {e}")
            return None

    def parse_product_list(self, soup: BeautifulSoup, category: str = "") -> list[Product]:
        """Parse product list page. Override in subclasses."""
        raise NotImplementedError

    def get_all_pages(
        self, path: str, category: str = "", max_pages: int = MAX_PAGES
    ) -> list[Product]:
        """Scrape multiple pages of a category listing."""
        all_products = []
        for page_num in range(1, max_pages + 1):
            page_url = self._add_page_param(path, page_num)
            soup = self.fetch_page(page_url)
            if not soup:
                break
            products = self.parse_product_list(soup, category)
            if not products:
                break
            # Filter out reservation payment entries
            products = [p for p in products if "예약금결제" not in p.name]
            all_products.extend(products)
            logger.info(
                f"[{self.site_name}] Page {page_num}: {len(products)} products"
            )
        return all_products

    # --- Shared extraction helpers ---

    @staticmethod
    def extract_product_id_from_url(url: str) -> Optional[str]:
        """Extract numeric product ID from a Cafe24 product URL.

        Handles both styles:
          /product/slug/12345/category/...  → '12345'
          /product/detail.html?product_no=12345  → '12345'
        """
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "product_no" in qs:
            return qs["product_no"][0]
        # SEO slug style: /product/{slug}/{id}/...
        match = re.search(r"/product/[^/]+/(\d+)/", parsed.path)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def extract_price(text: str) -> Optional[int]:
        """Parse Korean price text like '198,000원' → 198000."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None

    @staticmethod
    def extract_sale_price_from_data_attr(data_price: str) -> Optional[int]:
        """Parse Cafe24 data-price attribute like '^69000^64000' → 64000.

        Format is '^consumer_price^sale_price' or '^price'.
        Returns the sale (last) price.
        """
        if not data_price:
            return None
        parts = [p for p in data_price.split("^") if p]
        if not parts:
            return None
        # Last part is the sale/actual price
        cleaned = re.sub(r"[^\d]", "", parts[-1])
        return int(cleaned) if cleaned else None

    @staticmethod
    def parse_status_prefix(name: str) -> tuple[str, str]:
        """Extract status prefix from product name.

        Returns (status, cleaned_name).
        Examples:
          '[입고완료][제조사] 상품명' → ('available', '[제조사] 상품명')
          '[26년 2분기 입고예정] 상품명' → ('preorder', '상품명')
          '[예약마감임박] 상품명' → ('preorder', '상품명')
          '[예약] 상품명' → ('preorder', '상품명')
          '일반 상품명' → ('available', '일반 상품명')
        """
        status = "available"
        cleaned = name.strip()

        # Check for status-indicating prefixes
        preorder_patterns = [
            r"\[예약(?:마감임박)?\]",
            r"\[\d+년\s*\d+분기\s*입고예정\]",
            r"\[\d+년\s*\d+월\s*입고예정\]",
            r"\[예약판매\]",
        ]
        for pattern in preorder_patterns:
            if re.match(pattern, cleaned):
                status = "preorder"
                cleaned = re.sub(pattern, "", cleaned, count=1).strip()
                break

        if re.match(r"\[입고완료\]", cleaned):
            status = "available"
            cleaned = re.sub(r"\[입고완료\]", "", cleaned, count=1).strip()

        return status, cleaned

    @staticmethod
    def detect_soldout_from_element(li: Tag) -> bool:
        """Check if a product card indicates soldout.

        Looks for img[alt='품절'] or the absence of cart button.
        """
        soldout_img = li.select_one('img[alt="품절"]')
        if soldout_img:
            return True

        # Check div.sold for comics-art style
        sold_div = li.select_one("div.sold")
        if sold_div:
            sold_img = sold_div.select_one("img")
            if sold_img:
                return True

        return False

    def _build_product_url(self, href: str) -> str:
        """Convert relative href to full URL."""
        if href.startswith("http"):
            return href
        return urljoin(self.base_url, href)

    @staticmethod
    def _add_page_param(path: str, page: int) -> str:
        """Add or update ?page=N parameter to a URL path."""
        parsed = urlparse(path)
        qs = parse_qs(parsed.query)
        qs["page"] = [str(page)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _extract_id_from_anchor_box(li: Tag) -> Optional[str]:
        """Extract product ID from li[id='anchorBoxId_XXXXX']."""
        li_id = li.get("id", "")
        if li_id.startswith("anchorBoxId_"):
            return li_id.replace("anchorBoxId_", "")
        # Fallback: checkbox class xECPCNO_XXXXX
        checkbox = li.select_one("input.ProductCompareClass")
        if checkbox:
            for cls in checkbox.get("class", []):
                if cls.startswith("xECPCNO_"):
                    return cls.replace("xECPCNO_", "")
        return None

    @staticmethod
    def _get_image_url(li: Tag) -> Optional[str]:
        """Extract product thumbnail image URL."""
        # Try anchorBox link image first
        anchor = li.select_one('a[name^="anchorBoxName_"]')
        if anchor:
            img = anchor.select_one("img")
            if img and img.get("src"):
                src = img["src"]
                return f"https:{src}" if src.startswith("//") else src

        # Try a.prdImg img (maniahouse style)
        prd_img = li.select_one("a.prdImg img")
        if prd_img and prd_img.get("src"):
            src = prd_img["src"]
            return f"https:{src}" if src.startswith("//") else src

        # Try div.add_thumb img (rabbits/ttabbaemall style)
        thumb_img = li.select_one("div.add_thumb img")
        if thumb_img and thumb_img.get("src"):
            src = thumb_img["src"]
            return f"https:{src}" if src.startswith("//") else src

        return None
