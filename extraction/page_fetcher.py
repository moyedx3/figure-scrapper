"""Fetch product detail pages and extract structured specs from Cafe24 shops."""

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)

# Delay between page fetches to be polite
_FETCH_DELAY = 0.5

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        })
    return _session


# Maps site-specific label text to our normalized field names.
# Each site may use different labels for the same concept.
_LABEL_MAP: dict[str, dict[str, str]] = {
    "figurepresso": {
        "원작명": "series_hint",
        "제조사": "page_manufacturer",
        "코드": "jan_code",
        "크기": "size",
        "재질": "material",
    },
    "maniahouse": {
        "제조사": "page_manufacturer",
        "JAN": "jan_code",
    },
    "ttabbaemall": {
        "제조사": "page_manufacturer",
        "JAN코드": "jan_code",
        "상품 소재": "material",
        "크기": "size",
        "상품 설명": "description",
    },
    "rabbits": {
        "제조사": "page_manufacturer",
        "바코드": "jan_code",
        "사양": "material",
        "크기": "size",
    },
    "comicsart": {
        "제조사": "page_manufacturer",
    },
}


def fetch_product_detail(url: str, site: str) -> Optional[dict[str, str]]:
    """Fetch a product detail page and extract specs table data.

    Returns a dict of normalized field names to values, or None if fetch fails.
    """
    if not url:
        return None

    session = _get_session()
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        time.sleep(_FETCH_DELAY)
    except requests.RequestException as e:
        logger.debug(f"[{site}] Failed to fetch detail page {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    label_map = _LABEL_MAP.get(site, {})
    if not label_map:
        return None

    specs: dict[str, str] = {}

    # Parse all tables on the page — Cafe24 detail pages have specs in <th>/<td> rows
    for table in soup.select("table"):
        for row in table.select("tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True).rstrip(":")
            value = td.get_text(strip=True)
            if not value or value == label:
                continue

            # Check if this label maps to a known field
            for label_key, field_name in label_map.items():
                if label_key in label:
                    specs[field_name] = value
                    break

    return specs if specs else None


def format_page_context(specs: dict[str, str]) -> str:
    """Format page specs into a text block for the LLM prompt."""
    lines = []
    field_labels = {
        "series_hint": "페이지 원작명",
        "page_manufacturer": "페이지 제조사",
        "jan_code": "JAN/바코드",
        "size": "크기",
        "material": "재질/소재",
        "description": "상품 설명",
    }
    for field, value in specs.items():
        label = field_labels.get(field, field)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)
