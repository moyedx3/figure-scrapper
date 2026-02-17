---
title: Figure Scraper Analytics Dashboard (Streamlit)
type: feat
date: 2026-02-17
---

# Figure Scraper Analytics Dashboard (Streamlit)

## Overview

Build a Streamlit multi-page dashboard that visualizes scraper data from `figures.db`. Seven views: overview, new products feed, cross-site price comparison, soldout velocity, restock patterns, site coverage, and reservation accuracy.

## Architecture

```
figure-scrapper/
├── dashboard.py              # Streamlit entrypoint (sidebar nav + global filters)
├── pages/
│   ├── 1_overview.py         # Summary metrics + recent changes
│   ├── 2_new_products.py     # New product feed with filters
│   ├── 3_price_compare.py    # Cross-site price comparison
│   ├── 4_soldout_velocity.py # Time-to-soldout charts
│   ├── 5_restock_patterns.py # Restock timing + frequency
│   ├── 6_site_coverage.py    # Site strength comparison
│   └── 7_reservation.py      # Predicted vs actual arrival
├── analytics/
│   ├── __init__.py
│   ├── queries.py            # All SQL queries (cached with st.cache_data)
│   ├── matching.py           # Cross-site product matching (JAN + fuzzy)
│   └── charts.py             # Reusable Plotly chart builders
└── requirements.txt          # Add: streamlit, plotly, pandas, rapidfuzz
```

### Data Flow

```
figures.db (SQLite, populated by scraper)
  → analytics/queries.py (cached SQL → pandas DataFrames)
    → pages/*.py (Streamlit UI + Plotly charts)
```

Dashboard is read-only — it never writes to `figures.db`.

## Implementation Phases

### Phase 3A: Foundation + Overview

**Files:** `dashboard.py`, `analytics/queries.py`, `analytics/charts.py`, `analytics/__init__.py`, `pages/1_overview.py`

**dashboard.py** — Streamlit entrypoint:
- `st.navigation` with 7 pages
- Sidebar: site filter (multiselect), date range picker
- Korean UI labels

**analytics/queries.py** — Cached SQL queries:
- `get_product_counts()` → products per site, per status
- `get_recent_changes(days=7)` → recent status_changes joined with products
- `get_recent_new_products(days=7)` → products ordered by first_seen_at DESC
- `get_price_stats()` → min/max/avg price per site
- `get_status_breakdown()` → available/soldout/preorder counts
- All queries use `@st.cache_data(ttl=300)` (5-min cache)

**analytics/charts.py** — Reusable Plotly chart functions:
- `status_pie_chart(df)` → pie chart of available/soldout/preorder
- `products_by_site_bar(df)` → horizontal bar chart
- `price_distribution_histogram(df)` → price range histogram
- `timeline_chart(df, date_col, value_col)` → line chart over time

**pages/1_overview.py** — Summary dashboard:
- Top row: `st.metric` cards — total products, new (24h), restocks (24h), soldout (24h)
- Row 2: products by site (bar), status breakdown (pie)
- Row 3: recent changes table (sortable dataframe)
- Row 4: price distribution histogram

**Success criteria:**
- `streamlit run dashboard.py` opens with working overview page
- All metrics populated from real DB data
- 5-second cache prevents repeated queries

---

### Phase 3B: New Products Feed

**Files:** `pages/2_new_products.py`

**Features:**
- Filterable product feed (last 24h / 7d / 30d / all)
- Filters: site (multiselect), status, price range (slider), name search (text input)
- Sortable dataframe with columns: site, name, price, status, category, first_seen_at
- Click-through links to product URLs
- Product count badge per filter combination

**Success criteria:**
- Can filter by site + price range + search text simultaneously
- Product URLs are clickable links in the dataframe

---

### Phase 3C: Cross-Site Price Comparison

**Files:** `analytics/matching.py`, `pages/3_price_compare.py`

**analytics/matching.py** — Product matching engine:
- `match_by_jan_code()` → exact match products sharing JAN/barcode across sites
- `match_by_fuzzy_name(threshold=0.75)` → rapidfuzz token_sort_ratio on product names, grouped by manufacturer
- `build_match_groups()` → returns groups of matched products with confidence scores
- Write matches to `product_matches` table for persistence

**pages/3_price_compare.py** — Price comparison view:
- Table: product name | site A price | site B price | ... | cheapest | price diff
- Highlight cheapest site in green
- Filter by: product name search, min price difference
- Bar chart: average price difference by site pair
- "Run matching" button to trigger fresh fuzzy match (expensive operation)

**Success criteria:**
- Products with same JAN code matched across sites
- Fuzzy matching groups similar products (e.g., same figure, different naming)
- Cheapest site highlighted per product

---

### Phase 3D: Soldout Velocity

**Files:** `pages/4_soldout_velocity.py`, additions to `analytics/queries.py`

**New queries:**
- `get_soldout_velocity()` → first_seen_at to soldout_at delta for soldout products
- `get_velocity_by_manufacturer()` → avg time-to-soldout grouped by manufacturer
- `get_velocity_by_site()` → avg time-to-soldout grouped by site
- `get_velocity_by_price_range()` → binned by price brackets

**Page features:**
- Histogram: time-to-soldout distribution (hours/days)
- Bar chart: avg soldout speed by manufacturer (top 20)
- Bar chart: avg soldout speed by site
- Scatter: price vs time-to-soldout (do expensive items sell faster?)
- Filters: site, price range, date range

**Note:** This view requires accumulated data over time. With a fresh DB, show "Collecting data — results improve after several days of scraping" message when insufficient data exists.

**Success criteria:**
- Histogram renders with real soldout data
- Manufacturer breakdown shows which makers' products sell fastest

---

### Phase 3E: Restock Patterns

**Files:** `pages/5_restock_patterns.py`, additions to `analytics/queries.py`

**New queries:**
- `get_restock_events()` → status_changes where old=soldout, new=available, joined with products
- `get_avg_restock_time_by_site()` → average soldout→available duration per site
- `get_restock_frequency()` → how many restocks per month per site
- `get_price_on_restock()` → compare price before soldout vs after restock

**Page features:**
- Table: recent restocks with product name, site, soldout duration, price change
- Bar chart: avg restock time by site (which site restocks fastest?)
- Line chart: monthly restock count by site (trend)
- Scatter: price change on restock (do prices go up after restock?)

**Success criteria:**
- Restock events listed with timing data
- Site comparison shows which shops restock most frequently

---

### Phase 3F: Site Coverage

**Files:** `pages/6_site_coverage.py`, additions to `analytics/queries.py`

**New queries:**
- `get_products_by_category_site()` → cross-tab of category × site
- `get_unique_products_per_site()` → products only found on one site
- `get_shared_products()` → products found on multiple sites (via product_matches)
- `get_price_competitiveness()` → for shared products, which site is cheapest most often

**Page features:**
- Heatmap: product count by category × site
- Bar chart: unique vs shared product ratio per site
- Table: site strengths summary (most products in category X)
- Stacked bar: status distribution per site (what % is soldout per site?)

**Success criteria:**
- Heatmap clearly shows which site dominates which category
- Unique product counts per site visible

---

### Phase 3G: Reservation Accuracy

**Files:** `pages/7_reservation.py`, additions to `analytics/queries.py`

**New queries:**
- `get_reservation_accuracy()` → compare release_date (predicted) with actual status change to 'available' timestamp
- `get_delay_by_manufacturer()` → avg delay per manufacturer
- `get_delay_by_site()` → avg delay per site

**Page features:**
- Table: product, predicted arrival, actual arrival, delay (days)
- Bar chart: avg delay by manufacturer (who's always late?)
- Bar chart: avg delay by site
- Metric cards: overall on-time %, avg delay days

**Note:** Requires release_date to be populated AND products transitioning to available. May have limited data initially.

**Success criteria:**
- Delay calculation works for products with both release_date and status change timestamps

---

## Acceptance Criteria

### Functional Requirements

- [ ] `streamlit run dashboard.py` launches multi-page dashboard
- [ ] All 7 pages render with real data from figures.db
- [ ] Sidebar filters (site, date range) apply globally
- [ ] Cross-site matching works (JAN code + fuzzy name)
- [ ] Charts are interactive (Plotly hover, zoom, pan)
- [ ] Product URLs are clickable
- [ ] Graceful empty states when insufficient data

### Non-Functional Requirements

- [ ] Page load under 3 seconds with cached data
- [ ] SQL queries cached with 5-min TTL
- [ ] Dashboard is read-only (no writes to figures.db)
- [ ] Korean labels on all UI elements

## Dependencies

- `streamlit` — dashboard framework
- `plotly` — interactive charts
- `pandas` — data manipulation
- `rapidfuzz` — fuzzy string matching for cross-site product matching

## References

- Existing DB schema: `db.py`
- Research spec analytics section: `scrapper-research-spec.md` section 7
- Streamlit multi-page docs: `st.navigation` with `st.Page`
- Caching: `@st.cache_data(ttl=300)`
