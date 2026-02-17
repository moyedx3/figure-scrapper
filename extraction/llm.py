"""Claude LLM extraction for structured product data."""

import json
import logging
import os

from extraction.models import ProductAttributes

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """한국 피규어/굿즈 쇼핑몰 상품명에서 정확한 구조화 정보를 추출하세요.
이 데이터는 여러 사이트에서 **동일한 물리적 상품**을 매칭하는 데 사용됩니다.

상품명: {name}
사이트: {site}
카테고리: {category}
사이트 제조사 정보: {manufacturer}

## 추출 필드 및 규칙

### series (작품명)
원작 작품의 대표 제목. 언어 통일: 한국에서 통용되는 공식 한국어 제목 사용.
- "신 에반게리온 극장판" → "에반게리온"
- "보컬로이드" / "캐릭터 보컬 시리즈 01" → "보컬로이드"
- "NARUTO -나루토- 질풍전" → "나루토 질풍전"
- "귀멸의 칼날" (그대로)
- "My 히어로 아카데미아" / "나의 히어로 아카데미아" → "나의 히어로 아카데미아"
- 작품이 아닌 오리지널 캐릭터이면 null

### character_name (캐릭터명)
캐릭터의 이름만. 모든 사이트에서 동일한 캐릭터가 동일하게 표기되어야 합니다.
절대 포함하지 말 것: 제품번호, 상품라인명, 제조사명, 스케일, 버전명, "피규어" 등의 단어.
- ✅ "시모에 코하루", "하츠네 미쿠", "소류 아스카 랑그레이"
- ❌ "2968 시모에 코하루", "피그마 시모에 코하루", "하츠네 미쿠 사쿠라 미쿠 꽃놀이 코디 Ver."
- 복수 캐릭터 세트: "소류 아스카 랑그레이 & 마키나미 마리 일러스트리어스"
- 캐릭터가 없으면 (굿즈 세트 등) null

### manufacturer (제조사)
실제 제조사/브랜드. 한국어 정규화된 이름 사용:
- "굿스마일컴퍼니" (= G.S.C, 굿스마일, GOOD SMILE)
- "굿스마일아츠상하이" (별도 회사)
- "메가하우스" (= MegaHouse)
- "코토부키야" (= KOTOBUKIYA)
- "반다이" / "반다이스피릿" / "반프레스토" (각각 별도)
- "타이토" (= TAITO)
- "후류" (= FuRyu, Furyu)
- "세가" (= SEGA)
- "스피리테일" (= spiritale, SPIRITALE)
- "맥스팩토리" (= Max Factory)
- "프리잉" (= FREEing)
- "유니온크리에이티브" (= Union Creative)
- "에이펙스" (= APEX-TOYS, Apex)
- 사이트 제조사 정보가 있으면 참고하되, 상품명에서 확인 가능한 정보를 우선

### scale (스케일)
물리적 크기 비율만. "1/7", "1/6", "1/4", "1/8", "non-scale" 등.
- 넨도로이드, figma, 프라이즈 피규어는 스케일이 아님 → null
- 상품명에 명시된 경우만 기재

### version (버전/에디션)
동일 캐릭터의 다른 변형을 구분하는 정보:
- 의상/포즈: "바니 ver.", "수영복 Ver.", "메이드복 ver."
- 특별판: "호화판", "deluxe", "한정"
- 재판: "재판", "2차재판", "4차재판"
- 컬러: "어나더 컬러", "펄 핑크 컬러 Ver."
- 콜라보: "so-bin Ver.", "huke Ver."
- 일반 버전이면 null

### product_line (상품 라인)
제조사의 상품 시리즈/브랜드:
- "넨도로이드", "넨도로이드돌", "figma", "POP UP PARADE"
- "Coreful", "AMP", "Wonderland", "BiCute", "Lookup"
- "ARTFX J", "Exceed Creative", "Trio-Try-iT"
- "데스크탑 큐트", "누들 스토퍼", "후와푸치"
- "바이브레이션 스타즈", "MASTERLISE"
- "Precious GEM", "BIG SOFVIMATES"
- 특정 라인이 아닌 일반 피규어면 null

### product_type (상품 유형)
상품의 물리적 형태:
- "scale_figure": 스케일 피규어 (1/7, 1/6 등 명시된 것)
- "prize_figure": 프라이즈/경품 피규어 (타이토, 반프레스토, 후류 등의 저가 피규어)
- "nendoroid": 넨도로이드 (넨도로이드돌 포함)
- "figma": figma 액션 피규어
- "action_figure": 기타 액션 피규어
- "plushie": 봉제인형, 누이구루미, 인형
- "acrylic": 아크릴 스탠드, 아크릴 키홀더
- "keychain": 키홀더, 키링 (아크릴 제외)
- "badge": 캔뱃지, 뱃지, 핀
- "sticker": 스티커, 씰
- "blanket": 담요, 타올
- "model_kit": 프라모델, 조이드
- "goods_other": 기타 굿즈 (케이스, 지갑, 마그넷 등)

## 중요 원칙
1. character_name은 크로스사이트 매칭의 핵심입니다. 깨끗하고 일관되게.
2. manufacturer는 정규화하세요. 같은 회사는 항상 같은 이름으로.
3. product_type은 가격 비교의 전제조건입니다. figure끼리만 비교해야 의미 있음.
4. 확실하지 않은 정보는 null. 추측하지 마세요.

없는 정보는 null로. JSON만 응답:
{{"series": ..., "character_name": ..., "manufacturer": ..., "scale": ..., "version": ..., "product_line": ..., "product_type": ...}}"""

_PAGE_CONTEXT_SECTION = """
## 상품 페이지에서 추출한 추가 정보
아래는 실제 상품 상세 페이지에서 가져온 정보입니다. 상품명보다 이 정보가 더 정확할 수 있습니다.
{page_context}

이 정보를 적극 활용하되, 상품명과 교차 검증하세요.
- 페이지 제조사 정보가 있으면 이를 우선 사용하고 한국어로 정규화하세요.
- JAN/바코드가 있으면 동일 상품 식별에 도움이 됩니다.
- 페이지 원작명이 있으면 series 필드에 반영하세요 (한국어 정규화 필요).
"""


def extract_with_llm(
    name: str, site: str, category: str, manufacturer: str | None = None,
    page_detail: dict[str, str] | None = None,
) -> ProductAttributes:
    """Extract structured fields using Claude LLM.

    Args:
        page_detail: Optional dict of extra specs from the product detail page
                     (e.g. page_manufacturer, jan_code, series_hint, size).
    """
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

    # Safety: only allow Haiku or Sonnet models
    allowed = any(m in EXTRACTION_MODEL.lower() for m in ("haiku", "sonnet"))
    if not allowed:
        logger.error(
            f"EXTRACTION_MODEL must be Haiku or Sonnet, got '{EXTRACTION_MODEL}'. "
            "Refusing to use Opus for bulk extraction."
        )
        return ProductAttributes()

    client = Anthropic()
    prompt = _PROMPT_TEMPLATE.format(
        name=name,
        site=site,
        category=category or "",
        manufacturer=manufacturer or "없음",
    )

    # Append page detail context if available
    if page_detail:
        from extraction.page_fetcher import format_page_context
        page_ctx = format_page_context(page_detail)
        prompt += _PAGE_CONTEXT_SECTION.format(page_context=page_ctx)

    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        return ProductAttributes(**{k: v for k, v in data.items() if v is not None})

    except Exception as e:
        logger.warning(f"LLM extraction failed for '{name}': {e}")
        return ProductAttributes()
