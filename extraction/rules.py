"""Rule-based extraction using regex patterns from known sites."""

import re
from typing import Optional

from extraction.models import ProductAttributes

# --- Scale patterns ---
_SCALE_RE = re.compile(r"1/(\d+)\s*(?:스케일)?", re.IGNORECASE)
_NON_SCALE_RE = re.compile(r"논\s*스케일", re.IGNORECASE)

# --- Product lines (order matters: longer/more specific first) ---
_PRODUCT_LINES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"POP\s*UP\s*PARADE", re.IGNORECASE), "POP UP PARADE"),
    (re.compile(r"HELLO!\s*GOOD\s*SMILE", re.IGNORECASE), "HELLO! GOOD SMILE"),
    (re.compile(r"Huggy\s*Good\s*Smile|허기\s*굿스마일", re.IGNORECASE), "Huggy Good Smile"),
    (re.compile(r"ARTFX\s*J", re.IGNORECASE), "ARTFX J"),
    (re.compile(r"ARTFX", re.IGNORECASE), "ARTFX"),
    (re.compile(r"넨도로이드|nendoroid", re.IGNORECASE), "넨도로이드"),
    (re.compile(r"figma", re.IGNORECASE), "figma"),
    (re.compile(r"S\.H\.\s*Figuarts|figuarts", re.IGNORECASE), "S.H.Figuarts"),
    (re.compile(r"GRANDISTA|그랜디스타", re.IGNORECASE), "GRANDISTA"),
    (re.compile(r"룩업|Lookup|Look\s*Up", re.IGNORECASE), "Lookup"),
    (re.compile(r"Trio-Try-iT", re.IGNORECASE), "Trio-Try-iT"),
    (re.compile(r"누들\s*스토퍼|Noodle\s*Stopper", re.IGNORECASE), "Noodle Stopper"),
    (re.compile(r"오히루네코", re.IGNORECASE), "오히루네코"),
    (re.compile(r"PalVerse", re.IGNORECASE), "PalVerse"),
    (re.compile(r"프레임\s*암즈|Frame\s*Arms", re.IGNORECASE), "Frame Arms"),
    (re.compile(r"쵸코푸니", re.IGNORECASE), "쵸코푸니"),
    (re.compile(r"페탓토", re.IGNORECASE), "페탓토"),
    (re.compile(r"G\.E\.M\.", re.IGNORECASE), "G.E.M."),
    (re.compile(r"Q\s*posket", re.IGNORECASE), "Q posket"),
]

# --- Known manufacturers (extracted from bracket patterns) ---
_KNOWN_MANUFACTURERS: dict[str, str] = {
    "반프레스토": "반프레스토",
    "메가하우스": "메가하우스",
    "굿스마일컴퍼니": "굿스마일컴퍼니",
    "굿스마일": "굿스마일컴퍼니",
    "굿스마일아츠상하이": "굿스마일 아츠 상하이",
    "굿스마일 아츠 상하이": "굿스마일 아츠 상하이",
    "코토부키야": "코토부키야",
    "후류": "후류",
    "세가": "세가",
    "부시로드": "부시로드",
    "클레이넬": "클레이넬",
    "리보스": "리보스",
    "미토스": "미토스",
    "반다이": "반다이",
    "타카라토미": "타카라토미",
    "유니온 크리에이티브": "유니온 크리에이티브",
    "맥스팩토리": "맥스팩토리",
    "알터": "알터",
    "프리잉": "프리잉",
    "아쿠아마린": "아쿠아마린",
    "오키토이즈": "오키토이즈",
    "플레어": "플레어",
    "하비사쿠라": "하비사쿠라",
    "시스템서비스": "시스템서비스",
}

# Regex for bracket-enclosed manufacturer: [굿스마일컴퍼니]
_BRACKET_MFR_RE = re.compile(r"\[([^\]]+)\]")
# Regex for parenthesized manufacturer with English: 코토부키야 (Kotobukiya)
_PAREN_MFR_RE = re.compile(r"(\S+)\s*\(([A-Za-z][\w\s.&]+)\)")

# --- Known series ---
_KNOWN_SERIES: dict[str, str] = {
    "귀멸의 칼날": "귀멸의 칼날",
    "원신": "원신",
    "블루 아카이브": "블루 아카이브",
    "블루아카이브": "블루 아카이브",
    "하이큐": "하이큐!!",
    "하이큐!!": "하이큐!!",
    "오버로드": "오버로드",
    "스파이 패밀리": "스파이 패밀리",
    "SPY×FAMILY": "스파이 패밀리",
    "홀로라이브": "홀로라이브",
    "던전밥": "던전밥",
    "네코파라": "네코파라",
    "블루록": "블루록",
    "벽람항로": "벽람항로",
    "나루토": "나루토",
    "나루토 질풍전": "나루토 질풍전",
    "보컬로이드": "보컬로이드",
    "북두의 권": "북두의 권",
    "젠레스 존 제로": "젠레스 존 제로",
    "승리의 여신: 니케": "승리의 여신: 니케",
    "승리의 여신 니케": "승리의 여신: 니케",
    "니케": "승리의 여신: 니케",
    "페르소나5": "페르소나5",
    "장송의 프리렌": "장송의 프리렌",
    "앙상블 스타즈": "앙상블 스타즈",
    "바람의 검심": "바람의 검심",
    "투 러브 트러블": "투 러브 트러블",
    "러브 라이브": "러브 라이브",
    "에반게리온": "에반게리온",
    "진격의 거인": "진격의 거인",
    "원피스": "원피스",
    "드래곤볼": "드래곤볼",
    "주술회전": "주술회전",
    "체인소 맨": "체인소 맨",
    "나의 히어로 아카데미아": "나의 히어로 아카데미아",
    "리코리스 리코일": "리코리스 리코일",
    "명일방주": "명일방주",
    "프리큐어": "프리큐어",
    "세일러문": "세일러문",
    "소녀전선": "소녀전선",
    "종말의 발키리": "종말의 발키리",
    "명조": "명조",
}

# --- Version/edition patterns ---
_VERSION_RE = re.compile(
    r"(디럭스|deluxe|통상판?|standard|바니|bunny|호화판|limited|한정판?|재판)"
    r"[\s]*(ver\.?|판|version|에디션|edition)?",
    re.IGNORECASE,
)
_SPECIFIC_VER_RE = re.compile(
    r"(\S+)\s*[Vv]er\.?",
)

# --- Noise patterns to strip before analysis ---
_NOISE_PATTERNS = [
    r"\[예약상품/[^\]]*\]",
    r"\[\d+년\d+월[^\]]*입고[^\]]*\]",
    r"\[\d+월[^\]]*입고[^\]]*\]",
    r"\(당일발송\)",
    r"\(\d+월\s*\d+주차\s*입고예정\)",
    r"\(\d+년\s*\d+월\s*발매\)",
    r"\[특가세일\]",
    r"\[독점유통\]",
    r"\[총판\]",
    r"특전포함|특전증정",
    r"\(한정/특전포함\)",
    r"\(캡슐\)",
    r"\(선택\)",
    r"\(굿즈\)",
    r"\(프라모델\)",
    r"\(공식\s*파트너샵\)",
]


def _strip_noise(name: str) -> str:
    """Remove site-specific noise from product name."""
    cleaned = name
    for pattern in _NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_scale(name: str) -> Optional[str]:
    """Extract figure scale from name."""
    m = _SCALE_RE.search(name)
    if m:
        return f"1/{m.group(1)}"
    if _NON_SCALE_RE.search(name):
        return "non-scale"
    return None


def _extract_product_line(name: str) -> Optional[str]:
    """Extract product line from name."""
    for pattern, line_name in _PRODUCT_LINES:
        if pattern.search(name):
            return line_name
    return None


def _extract_manufacturer(name: str, existing_mfr: Optional[str] = None) -> Optional[str]:
    """Extract manufacturer from name or use existing metadata."""
    # Check bracket patterns like [메가하우스]
    brackets = _BRACKET_MFR_RE.findall(name)
    for bracket_text in brackets:
        cleaned = bracket_text.strip()
        if cleaned in _KNOWN_MANUFACTURERS:
            return _KNOWN_MANUFACTURERS[cleaned]

    # Check parenthesized patterns like 코토부키야 (Kotobukiya)
    paren_matches = _PAREN_MFR_RE.findall(name)
    for korean, _english in paren_matches:
        if korean in _KNOWN_MANUFACTURERS:
            return _KNOWN_MANUFACTURERS[korean]

    # Check if name starts with a known manufacturer
    for key, normalized in _KNOWN_MANUFACTURERS.items():
        if key in name:
            return normalized

    # Fall back to existing metadata
    if existing_mfr:
        # Normalize existing manufacturer
        for key, normalized in _KNOWN_MANUFACTURERS.items():
            if key in existing_mfr:
                return normalized
        return existing_mfr

    return None


def _extract_series(name: str) -> Optional[str]:
    """Extract series/franchise name."""
    # Check bracket patterns like [귀멸의 칼날]
    brackets = _BRACKET_MFR_RE.findall(name)
    for bracket_text in brackets:
        cleaned = bracket_text.strip()
        if cleaned in _KNOWN_SERIES:
            return _KNOWN_SERIES[cleaned]

    # Check known series in full name
    for key, normalized in _KNOWN_SERIES.items():
        if key in name:
            return normalized

    return None


def _extract_version(name: str) -> Optional[str]:
    """Extract version/edition info."""
    # Try specific "X Ver." pattern first
    m = _SPECIFIC_VER_RE.search(name)
    if m:
        ver_text = m.group(0).strip()
        # Skip if it's just a character name fragment
        if len(ver_text) > 3:
            return ver_text

    m = _VERSION_RE.search(name)
    if m:
        return m.group(0).strip()

    return None


def _extract_character(name: str, series: Optional[str], manufacturer: Optional[str],
                       product_line: Optional[str]) -> Optional[str]:
    """Extract character name — the hardest part.

    Strategy: strip known components (noise, manufacturer, series, product line,
    scale, version markers) and take what remains as the character name.
    """
    cleaned = _strip_noise(name)

    # Remove bracket content (manufacturers, series, status)
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)
    # Remove parenthesized content
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)

    # Remove known components
    if product_line:
        for pattern, _ in _PRODUCT_LINES:
            cleaned = pattern.sub(" ", cleaned)

    # Remove scale
    cleaned = _SCALE_RE.sub(" ", cleaned)
    cleaned = _NON_SCALE_RE.sub(" ", cleaned)

    # Remove version markers
    cleaned = _VERSION_RE.sub(" ", cleaned)
    cleaned = _SPECIFIC_VER_RE.sub(" ", cleaned)

    # Remove known manufacturers from text
    for key in _KNOWN_MANUFACTURERS:
        cleaned = cleaned.replace(key, " ")

    # Remove known series from text
    if series:
        for key, normalized in _KNOWN_SERIES.items():
            if normalized == series:
                cleaned = cleaned.replace(key, " ")

    # Remove common noise words
    noise_words = [
        "스케일", "피규어", "figure", "No.", "L 사이즈", "사이즈",
        "Illustrated by", "by", "Vol.", "단품",
    ]
    for word in noise_words:
        cleaned = re.sub(re.escape(word), " ", cleaned, flags=re.IGNORECASE)

    # Remove numbers that look like product codes (4+ digits at end)
    cleaned = re.sub(r"\b\d{4,}\s*$", "", cleaned)
    # Remove "No.XXXX" pattern
    cleaned = re.sub(r"No\.\s*\d+", " ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If there's something meaningful left (>2 chars), that's the character
    if len(cleaned) > 2:
        return cleaned

    return None


def extract_with_rules(
    name: str, existing_manufacturer: Optional[str] = None
) -> tuple[ProductAttributes, float]:
    """Extract structured fields from product name using regex rules.

    Returns (attributes, confidence) where confidence is 0.0-1.0.
    """
    scale = _extract_scale(name)
    product_line = _extract_product_line(name)
    manufacturer = _extract_manufacturer(name, existing_manufacturer)
    series = _extract_series(name)
    version = _extract_version(name)
    character_name = _extract_character(name, series, manufacturer, product_line)

    attrs = ProductAttributes(
        series=series,
        character_name=character_name,
        manufacturer=manufacturer,
        scale=scale,
        version=version,
        product_line=product_line,
    )

    # Calculate confidence based on how many fields we extracted
    filled = sum(1 for v in [series, character_name, manufacturer, scale] if v)
    if filled >= 3:
        confidence = 0.8
    elif filled >= 2:
        confidence = 0.6
    elif filled >= 1:
        confidence = 0.4
    else:
        confidence = 0.1

    # Boost if we have a product line (strong signal)
    if product_line:
        confidence = min(confidence + 0.1, 1.0)

    return attrs, confidence
