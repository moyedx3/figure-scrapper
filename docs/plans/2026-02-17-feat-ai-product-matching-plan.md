---
title: AI-Powered Cross-Site Product Matching
type: feat
date: 2026-02-17
brainstorm: docs/brainstorms/2026-02-17-ai-product-matching-brainstorm.md
---

# AI-Powered Cross-Site Product Matching

## Overview

Replace the current fuzzy string matching (0.2% recall) with an AI-assisted structured data extraction pipeline. Product names are parsed into normalized fields (series, character, manufacturer, scale, version) on first-seen, enabling reliable cross-site matching via simple DB lookups.

**Strategy:** Rule-based extraction first, Claude Haiku fallback for ambiguous names. Extract once on ingest, match via DB queries — no LLM at query time.

## Architecture

```
Product scraped (new)
  → Rule-based extraction (regex patterns from 5 known sites)
  → If confidence < threshold → Claude Haiku extraction
  → Store structured fields in products table
  → Matching = SQL GROUP BY on (series, character, manufacturer, scale)
```

### Data Flow

```
parsers/*.py → detector.py (new product detected)
  → extraction/extractor.py (hybrid: rules → LLM fallback)
    → db.py upsert (structured fields saved)
      → analytics/matching.py (DB lookup matching, no fuzzy)
        → pages/3_price_compare.py (dashboard)
```

## Implementation Phases

### Phase 1: Schema + Extraction Module

**Files:** `db.py`, `models.py`, `config.py`, `extraction/__init__.py`, `extraction/extractor.py`, `extraction/rules.py`, `extraction/llm.py`, `extraction/models.py`

#### 1A: Schema Migration

Add columns to `products` table in `db.py`:

```sql
-- New structured extraction columns
series TEXT,              -- 작품명 (e.g., "오버로드", "스파이 패밀리")
character_name TEXT,      -- 캐릭터 (e.g., "샤르티아 블러드폴른")
scale TEXT,               -- 스케일 (e.g., "1/7", "1/6", "넨도로이드")
version TEXT,             -- 에디션 (e.g., "standard", "deluxe", "바니 ver.")
product_line TEXT,        -- 상품라인 (e.g., "POP UP PARADE", "figma")
extracted_manufacturer TEXT, -- LLM-extracted manufacturer (supplements existing field)
extraction_method TEXT,   -- "rules" or "llm"
extraction_confidence REAL, -- 0.0-1.0
extracted_at DATETIME
```

Use `character_name` (not `character`) to avoid SQLite reserved word issues.

Update `Product` dataclass in `models.py` with matching optional fields.

#### 1B: Extraction Models

**File:** `extraction/models.py`

Pydantic model for structured extraction output:

```python
class ProductAttributes(pydantic.BaseModel):
    series: str | None = None           # 작품명
    character_name: str | None = None   # 캐릭터명
    manufacturer: str | None = None     # 제조사
    scale: str | None = None            # 1/7, 1/4, 넨도로이드
    version: str | None = None          # standard, deluxe, color ver.
    product_line: str | None = None     # POP UP PARADE, figma, etc.
```

#### 1C: Rule-Based Extraction

**File:** `extraction/rules.py`

Pattern-based extraction using regex and known conventions:

- **Scale:** `r"1/(\d+)"` → "1/7", "1/6", "1/4"
- **Product lines:** keyword lookup — "넨도로이드"/"nendoroid", "figma", "POP UP PARADE", etc.
- **Version/edition:** `r"\b(디럭스|deluxe|통상|standard|바니|bunny)\s*(ver\.?|판|version)?"i`
- **Known series:** maintain a growing lookup dict of common series names (오버로드, 원신, 귀멸의 칼날, etc.)
- **Manufacturer:** leverage existing `manufacturer` field from parser, plus pattern extraction from name

Returns `(ProductAttributes, confidence: float)`. If confidence >= 0.7, skip LLM.

#### 1D: LLM Extraction

**File:** `extraction/llm.py`

Claude Haiku integration for products where rules produce low confidence:

```python
from anthropic import Anthropic
from extraction.models import ProductAttributes

def extract_with_llm(name: str, site: str, category: str) -> ProductAttributes:
    client = Anthropic()  # uses ANTHROPIC_API_KEY env var
    result = client.messages.parse(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        output_format=ProductAttributes,
    )
    return result.parsed_output
```

Prompt template (Korean context):

```
이 일본 피규어/굿즈 상품명에서 구조화된 정보를 추출하세요.

상품명: {name}
사이트: {site}
카테고리: {category}

추출할 필드:
- series: 작품명 (애니메이션/게임/만화 제목)
- character_name: 캐릭터명
- manufacturer: 제조사/브랜드
- scale: 스케일 (예: 1/7, 넨도로이드)
- version: 에디션/버전 (예: standard, deluxe, 바니 ver.)
- product_line: 상품 라인 (예: POP UP PARADE, figma)

없는 정보는 null로 반환하세요.
```

#### 1E: Hybrid Orchestrator

**File:** `extraction/extractor.py`

```python
def extract_product_attributes(product: Product) -> tuple[ProductAttributes, str, float]:
    """Returns (attributes, method, confidence)."""
    attrs, confidence = extract_with_rules(product.name, product.manufacturer)
    if confidence >= 0.7:
        return attrs, "rules", confidence

    if not EXTRACTION_LLM_ENABLED:
        return attrs, "rules", confidence

    llm_attrs = extract_with_llm(product.name, product.site, product.category)
    return llm_attrs, "llm", 0.85  # LLM gets baseline 0.85 confidence
```

**Success criteria:**
- `extraction/` module exists with rules.py, llm.py, extractor.py, models.py
- Rule-based extraction handles common patterns (scale, product line, known series)
- LLM extraction works as fallback via Anthropic SDK
- Schema migration adds structured columns to products table

---

### Phase 2: Pipeline Integration

**Files:** `detector.py`, `scraper.py`, `config.py`

#### 2A: Config Updates

**File:** `config.py`

```python
# AI Extraction settings
EXTRACTION_LLM_ENABLED = True      # Set False to use rules-only
EXTRACTION_CONFIDENCE_THRESHOLD = 0.7  # Below this, use LLM
EXTRACTION_MODEL = "claude-haiku-4-5-20251001"
```

API key via environment variable `ANTHROPIC_API_KEY` (standard Anthropic SDK pattern).

#### 2B: Hook into Change Detector

**File:** `detector.py`

In `process_products()`, after detecting a new product, call extraction:

```python
# After upsert_product (new products only)
if is_new and EXTRACTION_LLM_ENABLED:
    attrs, method, confidence = extract_product_attributes(product)
    save_extraction(conn, db_id, attrs, method, confidence)
```

Add `save_extraction()` to `db.py` — updates the structured columns on the product row.

#### 2C: Backfill Command

**File:** `scraper.py` (new CLI flag `--extract`)

```bash
python3 scraper.py --extract          # Extract all unprocessed products
python3 scraper.py --extract --site rabbits  # Extract for one site
```

Processes products where `extracted_at IS NULL`, in batches.

For the initial 2,917 products:
- Rule-based: instant, covers ~40-60% with good confidence
- LLM fallback: ~1,200 calls at ~$0.001 each = ~$1.20 total cost

Consider using the Anthropic Batch API for backfill (50% cost reduction):

```python
batch = client.messages.batches.create(requests=[...])
# Poll for completion, then process results
```

**Success criteria:**
- New products automatically get extracted on scrape
- `--extract` CLI flag backfills existing products
- Extraction is optional (works without API key, rules-only mode)
- Cost for initial backfill < $2

---

### Phase 3: Structured Matching

**Files:** `analytics/matching.py`, `analytics/queries.py`

#### 3A: Replace Fuzzy Matching

Replace `match_by_fuzzy_name()` and `build_match_groups()` with structured field matching:

```sql
-- Find match groups: products with same (series, character, manufacturer, scale)
SELECT series, character_name, extracted_manufacturer, scale,
       GROUP_CONCAT(id) as product_ids,
       COUNT(DISTINCT site) as site_count
FROM products
WHERE series IS NOT NULL AND character_name IS NOT NULL
GROUP BY series, character_name, extracted_manufacturer, scale
HAVING COUNT(DISTINCT site) >= 2
```

Keep JAN code matching as highest-priority tier.

New matching tiers:
1. **JAN code** — exact match, confidence 1.0
2. **Structured fields** — all 4 fields match, confidence = avg extraction confidence
3. **Partial structured** — series + character match (different manufacturer/scale), confidence 0.6

#### 3B: Update `run_matching()`

No longer needs expensive fuzzy computation. Matching becomes a cached SQL query:

```python
@st.cache_data(ttl=300)
def run_structured_matching() -> pd.DataFrame:
    """Match products by structured fields. Returns match groups."""
    # SQL GROUP BY on extracted fields
    # Much faster than fuzzy comparison
```

The "매칭 실행" button on the dashboard can be removed or repurposed — matching is now automatic whenever data refreshes.

**Success criteria:**
- Matching uses structured field lookups (no rapidfuzz needed)
- Match quality dramatically higher than 0.2% recall
- Matching runs in <1 second (SQL query, not string comparison)
- Variants (deluxe/standard) grouped under same match but distinguished by `version`

---

### Phase 4: Dashboard Updates

**Files:** `pages/3_price_compare.py`, `pages/6_site_coverage.py`, `pages/8_extraction_status.py` (new)

#### 4A: Price Comparison Page Refresh

Update `pages/3_price_compare.py`:
- Remove "매칭 실행" button (matching is now automatic)
- Show structured fields in comparison table (series, character instead of raw name)
- Group variants (deluxe/standard) visually within a match group
- Show extraction confidence per product

#### 4B: Site Coverage Update

Update `pages/6_site_coverage.py`:
- Use structured matches for unique/shared product counts
- Add series coverage comparison (which site has most products from series X?)

#### 4C: Extraction Status Page (optional)

New `pages/8_extraction_status.py`:
- Metrics: total extracted, rules vs LLM breakdown, avg confidence
- Unextracted products list
- Per-site extraction coverage
- Trigger manual extraction for unprocessed products

**Success criteria:**
- Price comparison shows structured data, not raw noisy names
- Matching works automatically without user button press
- Extraction coverage visible in dashboard

---

## File Summary

```
figure-scrapper/
├── extraction/                    # NEW module
│   ├── __init__.py
│   ├── models.py                 # Pydantic ProductAttributes
│   ├── rules.py                  # Regex/pattern-based extraction
│   ├── llm.py                    # Claude Haiku integration
│   └── extractor.py              # Hybrid orchestrator
├── db.py                         # MODIFY: add structured columns + save_extraction()
├── models.py                     # MODIFY: add extraction fields to Product
├── config.py                     # MODIFY: add extraction settings
├── detector.py                   # MODIFY: hook extraction on new products
├── scraper.py                    # MODIFY: add --extract CLI flag
├── analytics/
│   ├── matching.py               # MODIFY: structured field matching
│   └── queries.py                # MODIFY: add extraction queries
├── pages/
│   ├── 3_price_compare.py        # MODIFY: show structured data
│   ├── 6_site_coverage.py        # MODIFY: use structured matches
│   └── 8_extraction_status.py    # NEW: extraction monitoring
└── requirements.txt              # MODIFY: add anthropic, pydantic
```

## Acceptance Criteria

### Functional
- [x] Products get structured fields extracted on first scrape
- [x] Rule-based extraction handles scale, product line, known series
- [x] Claude Haiku extracts remaining products when API key is configured
- [x] Cross-site matching uses structured lookups (series + character + manufacturer + scale)
- [x] Match recall dramatically improves from 0.2% (3 → 30 groups)
- [x] `--extract` CLI backfills existing 2,917 products
- [x] Dashboard shows structured comparison data
- [x] System works in rules-only mode (no API key = graceful degradation)

### Non-Functional
- [x] LLM extraction cost < $2 for initial backfill
- [x] Matching query runs in <1 second
- [x] No LLM calls at dashboard query time
- [x] Extraction adds <2 seconds per new product to scrape cycle

## Dependencies

- `anthropic` — Claude API client (for LLM extraction)
- `pydantic` — Structured output models (required by anthropic SDK's `messages.parse`)
- Environment variable: `ANTHROPIC_API_KEY`

## Cost Estimate

- Initial backfill (~1,200 LLM calls): ~$1.20
- Ongoing: ~5-20 new products per scrape cycle = ~$0.02/day
- Batch API (if used for backfill): 50% discount = ~$0.60

## References

- Brainstorm: `docs/brainstorms/2026-02-17-ai-product-matching-brainstorm.md`
- Current matching: `analytics/matching.py`
- Anthropic SDK structured output: `client.messages.parse()` with Pydantic models
- Anthropic Batch API: `client.messages.batches.create()` for cost-effective bulk processing
- Integration point: `detector.py:46-52` (new product detection)
- Schema: `db.py:11-34` (products table)
