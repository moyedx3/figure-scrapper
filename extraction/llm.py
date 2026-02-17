"""Claude Haiku LLM extraction for ambiguous product names."""

import json
import logging
import os

from extraction.models import ProductAttributes

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """이 일본 피규어/굿즈 상품명에서 구조화된 정보를 추출하세요.

상품명: {name}
사이트: {site}
카테고리: {category}

추출할 필드:
- series: 작품명 (애니메이션/게임/만화 제목). 한글 표기 우선.
- character_name: 캐릭터명. 한글 표기 우선.
- manufacturer: 제조사/브랜드명. 한글 표기 우선.
- scale: 스케일 (예: "1/7", "1/4", "non-scale")
- version: 에디션/버전 (예: "standard", "deluxe", "바니 ver.", "호화판"). 일반 버전이면 null.
- product_line: 상품 라인 (예: "POP UP PARADE", "figma", "넨도로이드", "ARTFX J")

없는 정보는 null로 반환하세요.

JSON으로만 응답하세요:
{{"series": ..., "character_name": ..., "manufacturer": ..., "scale": ..., "version": ..., "product_line": ...}}"""


def extract_with_llm(
    name: str, site: str, category: str
) -> ProductAttributes:
    """Extract structured fields using Claude Haiku."""
    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed, skipping LLM extraction")
        return ProductAttributes()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping LLM extraction")
        return ProductAttributes()

    from config import EXTRACTION_MODEL

    client = Anthropic()
    prompt = _PROMPT_TEMPLATE.format(name=name, site=site, category=category or "")

    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        return ProductAttributes(**{k: v for k, v in data.items() if v is not None})

    except Exception as e:
        logger.warning(f"LLM extraction failed for '{name}': {e}")
        return ProductAttributes()
