"""Hybrid extraction orchestrator: page fetch + rules + LLM."""

import logging

from config import EXTRACTION_CONFIDENCE_THRESHOLD, EXTRACTION_LLM_ENABLED
from extraction.models import ProductAttributes
from extraction.rules import extract_with_rules

logger = logging.getLogger(__name__)


def extract_product_attributes(
    name: str,
    site: str = "",
    category: str = "",
    manufacturer: str | None = None,
    url: str | None = None,
    force_llm: bool = False,
) -> tuple[ProductAttributes, str, float, dict | None]:
    """Extract structured fields from a product name.

    Returns (attributes, method, confidence, page_specs).
    page_specs contains data fetched from the detail page (including jan_code).
    If url is provided, tries to fetch the product detail page for richer context.
    If force_llm=True, always use LLM (skips rules threshold check).
    """
    # Step 1: Try rule-based extraction
    attrs, confidence = extract_with_rules(name, manufacturer)

    # Step 1a: Fetch product detail page (needed for both rules-only and LLM paths)
    page_detail = None
    if url:
        try:
            from extraction.page_fetcher import fetch_product_detail
            page_detail = fetch_product_detail(url, site)
        except Exception as e:
            logger.debug(f"Page fetch failed for {url}: {e}")

    if not force_llm and confidence >= EXTRACTION_CONFIDENCE_THRESHOLD:
        return attrs, "rules", confidence, page_detail

    # Step 2: LLM (fallback or forced)
    if not EXTRACTION_LLM_ENABLED:
        return attrs, "rules", confidence, page_detail

    try:
        from extraction.llm import extract_with_llm

        llm_attrs = extract_with_llm(
            name, site, category, manufacturer, page_detail=page_detail,
        )

        # Merge: use LLM result but keep rule-based values where LLM returned None
        merged = ProductAttributes(
            series=llm_attrs.series or attrs.series,
            character_name=llm_attrs.character_name or attrs.character_name,
            manufacturer=llm_attrs.manufacturer or attrs.manufacturer,
            scale=llm_attrs.scale or attrs.scale,
            version=llm_attrs.version or attrs.version,
            product_line=llm_attrs.product_line or attrs.product_line,
            product_type=llm_attrs.product_type,
        )
        method = "llm+page" if page_detail else "llm"
        return merged, method, 0.90 if page_detail else 0.85, page_detail

    except Exception as e:
        logger.warning(f"LLM extraction failed, using rules only: {e}")
        return attrs, "rules", confidence, page_detail
