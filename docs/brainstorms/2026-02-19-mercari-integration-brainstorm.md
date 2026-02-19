# Mercari Japan Integration Brainstorm

**Date:** 2026-02-19
**Status:** Design finalized, ready for planning

## What We're Building

Add Mercari Japan (used goods marketplace) as a price data source for figures.
This enables users to compare retail prices (from existing 5 sites) with used
market prices on Mercari, and get alerts when tracked figures appear for sale.

### Goals
1. **Price comparison** - Show used market prices alongside retail prices
2. **Availability alerts** - Notify when specific figures appear on Mercari

### Scope: Figures Only
- Use `category_id=81` (figures) in all Mercari searches
- Search by product name from existing DB (not JAN code)
- Filter results by category to avoid non-figure matches

## Why This Approach

### Architecture: Standalone Module + Unified Dashboard

**Standalone module (`mercari/`)** because:
- Mercari data is fundamentally different from retail catalog data
  - Temporary listings (sold, expired) vs. permanent product pages
  - API-based (mercapi + DPoP auth) vs. HTML scraping
  - Multiple listings per product vs. one product page per site
- Can fail/restart independently without affecting main scraper
- Own rate limiting and scheduling needs

**Unified dashboard view** because:
- Users should see retail + used prices in one place
- A single product query should show both retail and Mercari data
- Join `mercari_prices` with `products` via matching groups

### Data Model: Snapshot Pricing

Store periodic price snapshots per product, not individual listings:
- `mercari_prices` table: product match key, avg_price, min_price, max_price,
  listing_count, fetched_at
- One row per product per fetch cycle
- Historical snapshots enable trend analysis

### Matching: Name-Based Search

Search Mercari using product names from our DB:
- Extract meaningful keywords from product names (remove site-specific prefixes)
- Filter by `category_id=81` (figures)
- Store search results as price aggregates

### Frequency: Daily

- One scheduled run per day
- ~3,000 searches (one per active product)
- Rate-limited with delays between requests
- Runs as separate systemd service or cron job

## Key Decisions

1. **Standalone module** - Separate from main scraper (`mercari/` package)
2. **Snapshot pricing** - Store aggregated prices, not individual listings
3. **Name-based search** - Use product names as Mercari keywords
4. **Daily frequency** - Balance freshness vs. ban risk
5. **Unified dashboard** - Join Mercari data with retail data for single-view queries
6. **mercapi library** - Handles DPoP authentication complexity

## Technical Details

### mercapi Library
- `pip install mercapi`
- Async Python (asyncio)
- Handles DPoP token signing (ECDSA JWT)
- Search API: keyword + category filter
- Python 3.9-3.13 compatible

### New DB Table: `mercari_prices`
```sql
CREATE TABLE mercari_prices (
    id INTEGER PRIMARY KEY,
    product_group_id TEXT,     -- links to matching group
    search_query TEXT,         -- what we searched for
    avg_price INTEGER,
    min_price INTEGER,
    max_price INTEGER,
    listing_count INTEGER,
    on_sale_count INTEGER,     -- currently available
    sold_count INTEGER,        -- recently sold (price reference)
    fetched_at TEXT
);
```

### New Files (Planned)
- `mercari/__init__.py` - Package init
- `mercari/fetcher.py` - Search and aggregate Mercari listings
- `mercari/scheduler.py` - Daily job runner
- `mercari/keywords.py` - Product name to search keyword extraction
- `pages/X_mercari.py` - Dashboard page for used market prices

### Dashboard Integration
- New "Used Market" section on product detail / price comparison pages
- Shows: avg used price, price range, listing count, trend
- Unified query: retail prices + Mercari prices side by side

## Open Questions

1. **Keyword extraction strategy** - How to clean product names for good search
   results? (e.g., remove Korean site prefixes, extract Japanese figure name)
2. **Ban risk mitigation** - What delays/backoff needed? Should we randomize?
3. **Sold listings** - Include sold prices in snapshots for market reference?
4. **Telegram alerts** - Should Mercari availability trigger Telegram notifications?
5. **Search scope** - Search all ~3,000 products or only "interesting" ones
   (e.g., preorder, soldout on retail)?

## Next Steps

Run `/workflows:plan` to create implementation plan.
