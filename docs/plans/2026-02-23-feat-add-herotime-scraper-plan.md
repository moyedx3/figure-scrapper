---
title: "feat: Add herotime.co.kr scraper"
type: feat
date: 2026-02-23
priority: high
status: ready
---

# Add herotime.co.kr (히어로타임) Scraper

## Why

herotime.co.kr is the only new Cafe24 figure shop that has **JAN codes on product detail pages** — making it the single best site to add for cross-site price matching. It claims to be "Korea's largest figure hobby shop" with 84,000+ products across figures, plastic models, and goods.

## Site Profile

| Field | Value |
|-------|-------|
| URL | https://herotime.co.kr |
| Platform | **Cafe24** |
| JAN codes | **YES** — displayed as `JAN CODE` in product specs |
| Products | ~84,000+ (figures + gunpla + goods) |
| Key categories | Preorder, In-Stock, Same-Day Shipping, Shop Exclusive |
| Closest existing parser | **figurepresso** (slug URLs, `anchorBoxId_` pattern) |

## Category URLs to Scrape

```python
"herotime": {
    "name": "herotime",
    "display_name": "히어로타임",
    "base_url": "https://herotime.co.kr",
    "categories": {
        "preorder": "/product/list.html?cate_no=1270",
        "in_stock": "/product/list.html?cate_no=1559",
        "same_day_shipping": "/product/list.html?cate_no=335",
        "shop_exclusive": "/product/list.html?cate_no=2413",
    },
    "product_url_pattern": "/product/{slug}/{product_id}/category/{cate_no}/display/1/",
},
```

## Technical Notes

### Listing Page Structure
- Container: `ul.xans-product-listnormal` (standard Cafe24)
- Product items: `li.xans-record-` with `id="anchorBoxId_{product_id}"`
- 20 products per page, pagination via `&page=N`
- Product name has `상품명 :` prefix that needs stripping
- Price has `**판매가 :**` prefix that needs stripping
- Soldout: `img[alt="품절"]`

### Product Detail Page
- Both URL formats work: slug style and `/product/detail.html?product_no={id}`
- JAN code label: `JAN CODE` (with space) in product specs table
- Other metadata: 제조사 (manufacturer), 재질 (material), 상품크기 (size), 원산지 (origin)
- Status prefixes use **parentheses** not brackets: `(입고완료)`, `(예약)`, `(잔금결제)`, `(리퍼상품)`, `(3월 입고예정)`

### Parser Differences from figurepresso
1. Product name/price have label prefixes to strip (`상품명 :`, `판매가 :`)
2. Status prefixes use `()` instead of `[]` — `parse_status_prefix()` in `base.py` may need extension
3. JAN code label is `JAN CODE` (with space) — check `page_fetcher.py` `_LABEL_MAP` handles this
4. Very large catalog (84k+) — consider which categories to scrape and `MAX_PAGES` setting

## Implementation Steps

- [ ] Add `herotime` entry to `config.py` SITES dict
- [ ] Create `parsers/herotime.py` (model after `parsers/figurepresso.py`)
  - Override product name/price parsing to strip `상품명 :` / `판매가 :` prefixes
  - Handle `()` parenthesis status prefixes: `(입고완료)`, `(예약)`, etc.
- [ ] Verify `page_fetcher.py` handles `JAN CODE` label (check `_LABEL_MAP`)
- [ ] Test scrape: `python scraper.py --site herotime --once`
- [ ] Verify JAN codes are extracted on product detail pages
- [ ] Verify cross-site matching works with existing products via JAN
- [ ] Deploy to VPS and monitor first few scrape cycles
- [ ] Update README site table

## Estimated Effort

Small — mostly config + a thin parser file. The Cafe24 base parser does the heavy lifting.
