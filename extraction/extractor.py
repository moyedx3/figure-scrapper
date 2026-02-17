"""Hybrid extraction orchestrator: rules first, LLM fallback."""

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
) -> tuple[ProductAttributes, str, float]:
    """Extract structured fields from a product name.

    Returns (attributes, method, confidence).
    """
    # Step 1: Try rule-based extraction
    attrs, confidence = extract_with_rules(name, manufacturer)

    if confidence >= EXTRACTION_CONFIDENCE_THRESHOLD:
        return attrs, "rules", confidence

    # Step 2: LLM fallback (if enabled)
    if not EXTRACTION_LLM_ENABLED:
        return attrs, "rules", confidence

    try:
        from extraction.llm import extract_with_llm

        llm_attrs = extract_with_llm(name, site, category)

        # Merge: use LLM result but keep rule-based values where LLM returned None
        merged = ProductAttributes(
            series=llm_attrs.series or attrs.series,
            character_name=llm_attrs.character_name or attrs.character_name,
            manufacturer=llm_attrs.manufacturer or attrs.manufacturer,
            scale=llm_attrs.scale or attrs.scale,
            version=llm_attrs.version or attrs.version,
            product_line=llm_attrs.product_line or attrs.product_line,
        )
        return merged, "llm", 0.85

    except Exception as e:
        logger.warning(f"LLM extraction failed, using rules only: {e}")
        return attrs, "rules", confidence
