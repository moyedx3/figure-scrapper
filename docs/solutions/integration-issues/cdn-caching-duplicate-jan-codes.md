---
title: Duplicate JAN Codes from Cafe24 CDN Caching During Rapid Sequential Scraping
date: 2026-02-19
category: integration-issues
tags: [cdn-caching, jan-code, cafe24, scraping, data-integrity, matching]
module: [scraper, extraction, matching]
symptoms:
  - Wrong products matched together in price comparison groups
  - Same JAN code on multiple different products within same site
  - Price comparison showing ₩25,000 product in a ₩74,200 group
  - Consecutive product IDs all sharing first product's JAN barcode
severity: medium
---

# Duplicate JAN Codes from Cafe24 CDN Caching

## Symptom

Cross-site matching groups contained obviously wrong products. For example, a ₩25,000 Arknights noodle stopper figure was grouped with ₩74,200 Wuthering Waves nendoroids because they shared the same JAN barcode in the DB.

Query to detect:
```sql
SELECT jan_code, COUNT(*) as cnt, GROUP_CONCAT(product_id, ', ')
FROM products
WHERE jan_code IS NOT NULL AND jan_code != ''
GROUP BY site, jan_code
HAVING cnt > 1;
```
Found **43 duplicate JAN groups** affecting ~86 products.

## Root Cause

Two issues combined:

### 1. Redundant page fetches with tight timing

When new products are discovered, the detail page was fetched **twice**:
- **First** in `_extract_and_save()` → passed to LLM as context → **JAN code discarded**
- **Second** in `_post_scrape_enrich()` → tight loop with only **0.5s delay** → JAN saved

The second loop fetched pages back-to-back. Cafe24's CDN cached the first response and returned it for subsequent requests within the cache window.

### 2. No duplicate validation

Nothing checked whether the same JAN code was assigned to multiple products on the same site. One physical product = one listing per site, so same-site JAN duplicates are always bad data.

### Evidence

Products 7915, 7917, 7919 (consecutive IDs, same scrape batch):
```
pid=7915 → actual JAN=4580828660540 (correct — 명조 넨도로이드 장리)
pid=7917 → actual JAN=4560228207781 (stored: 4580828660540 — WRONG)
pid=7919 → actual JAN=4571623512318 (stored: 4580828660540 — WRONG)
```

## Solution

### Fix 1: Save JAN during first fetch (`detector.py`)

`_extract_and_save()` now captures and saves the JAN code from the initial page fetch, eliminating the need for a second fetch:

```python
attrs, method, confidence, page_specs = extract_product_attributes(...)
save_extraction(self.conn, db_id, attrs.model_dump(), method, confidence)

# Save JAN code from page fetch right away
if page_specs and page_specs.get("jan_code"):
    jan = page_specs["jan_code"].strip()
    if len(jan) >= 8:
        self.conn.execute("UPDATE products SET jan_code = ? WHERE id = ?", (jan, db_id))
```

### Fix 2: Return page_specs from extractor (`extraction/extractor.py`)

Changed return type from 3-tuple to 4-tuple so the page data (including JAN) isn't thrown away:

```python
def extract_product_attributes(...) -> tuple[ProductAttributes, str, float, dict | None]:
    # Fetch page ONCE, early, before rules/LLM branching
    page_detail = fetch_product_detail(url, site) if url else None
    # ... rules/LLM logic ...
    return attrs, method, confidence, page_detail  # page_detail preserved
```

### Fix 3: Skip redundant fetches + safety check (`scraper.py`)

`_post_scrape_enrich()` now:
- Skips products that already got JAN during extraction
- Uses 2.0s delay (was 0.5s) for any fallback fetches
- Runs `_clear_duplicate_jan_codes()` after every enrichment

### Fix 4: Exclude bad JANs from matching (`analytics/matching.py`)

`match_by_jan_code()` filters out JAN codes that appear multiple times on the same site before building match groups.

### Fix 5: One-time cleanup script (`fix_jan_codes.py`)

Clears all duplicate JANs, re-fetches correct codes with 2s delays, rebuilds matching.

## Files Changed

| File | Change |
|------|--------|
| `extraction/extractor.py` | Return `page_specs` as 4th value |
| `detector.py` | Save JAN from first fetch in `_extract_and_save()` |
| `scraper.py` | Skip redundant fetches, 2s delay, `_clear_duplicate_jan_codes()` |
| `analytics/matching.py` | Filter same-site duplicate JANs |
| `fix_jan_codes.py` | One-time data cleanup script |

## Prevention: Adding New Sites Checklist

When adding a new Cafe24 site:

- [ ] **Test CDN caching**: Fetch 3 consecutive product detail pages with 0.5s delay — compare JAN codes. If they match, the CDN is caching.
- [ ] **Add label mapping** in `extraction/page_fetcher.py` `_LABEL_MAP` for the new site's Korean field names (JAN코드, 바코드, 코드, etc.)
- [ ] **Verify fetch delay**: Minimum 2.0s for detail page fetches. Test at 1.0s, 1.5s, 2.0s to find the safe threshold.
- [ ] **Run duplicate check** after first bulk scrape: `SELECT site, jan_code, COUNT(*) ... GROUP BY site, jan_code HAVING cnt > 1`
- [ ] **Don't fetch pages twice**: Always save all useful data (JAN, manufacturer, specs) from the first fetch.
- [ ] **Same-site duplicate JANs are ALWAYS bad data** — one physical product cannot have multiple listings with different names/prices on the same site.

## Key Rules

1. **Detail page fetch delay**: Minimum 2.0s (0.5s caused this bug)
2. **Single fetch, save everything**: Never discard data from a page fetch only to re-fetch later
3. **Same-site JAN uniqueness**: If `site + jan_code` is not unique, the data is corrupted
4. **Always run cleanup**: `_clear_duplicate_jan_codes()` after any batch operation
5. **Validate JAN length**: Must be ≥ 8 characters before saving
