"""Claude Haiku LLM extraction for ambiguous product names."""

import json
import logging
import os

from extraction.models import ProductAttributes

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """한국 피규어 쇼핑몰 상품명에서 구조화된 정보를 추출하세요.

상품명: {name}
사이트: {site}
카테고리: {category}

추출 규칙:
- series: 작품명 (애니/게임/만화 제목만). 예: "블루 아카이브", "오버로드", "귀멸의 칼날"
- character_name: 캐릭터 이름만. 제품번호(No.2968 등), 상품라인명(넨도로이드, 피그마 등), 스케일, 제조사명을 절대 포함하지 마세요. 같은 캐릭터는 항상 동일하게 표기하세요.
  - 올바른 예: "시모에 코하루", "라이오스 토덴", "샤르티아 블러드폴른"
  - 잘못된 예: "2968 시모에 코하루", "피그마 시모에 코하루", "681 시모에코하루"
- manufacturer: 제조사/브랜드명. 예: "굿스마일컴퍼니", "메가하우스", "코토부키야"
- scale: 스케일만. "1/7", "1/4", "non-scale" 등. 넨도로이드/figma는 스케일이 아님 → null
- version: 특별판/에디션만. 일반 버전이면 null. 예: "바니 ver.", "호화판", "deluxe", "재판"
- product_line: 상품 라인. "넨도로이드", "figma", "POP UP PARADE", "ARTFX J", "Lookup" 등

핵심: character_name은 다른 사이트에서 같은 캐릭터를 찾을 때 사용됩니다. 깨끗한 캐릭터 이름만 넣으세요.

없는 정보는 null로 반환. JSON만 응답:
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

    # Safety: only allow Haiku models to prevent accidental cost spikes
    if "haiku" not in EXTRACTION_MODEL.lower():
        logger.error(
            f"EXTRACTION_MODEL must be a Haiku model, got '{EXTRACTION_MODEL}'. "
            "Refusing to use expensive model for extraction."
        )
        return ProductAttributes()

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
