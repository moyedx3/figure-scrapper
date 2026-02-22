---
title: "feat: Mercari Japan secondhand price monitoring"
type: feat
date: 2026-02-23
priority: medium
status: research-complete
---

# Mercari Japan Integration — Secondhand Price Monitoring

## Why

Phase 5 of the roadmap: used market integration. Mercari Japan is the largest secondhand marketplace in Japan for anime figures. Tracking sold prices gives us **market value** data, and monitoring active listings lets us alert on deals.

## Feasibility Summary

| Factor | Assessment |
|--------|-----------|
| Public API | **None** — Mercari has no public API |
| Best tool | **[mercapi](https://github.com/take-kun/mercapi)** (Python, reverse-engineered internal API) |
| JAN code search | **Not supported** — must search by product name |
| Bot protection | DPoP cryptographic signing required (mercapi handles this) |
| ToS | **Prohibits scraping** — practical enforcement is technical (IP blocks), not legal |
| Fragility | **Medium-high** — undocumented API can change, breaking mercapi |
| JP IP needed? | **Likely** — Mercari JP is geo-restricted, may need Japanese proxy |
| Cost | mercapi is free; may need JP proxy (~$5-10/mo) |

## mercapi Library

```bash
pip install mercapi
```

```python
from mercapi import Mercapi

m = Mercapi()  # generates unique ECDSA key pair for DPoP signing

# Search for a figure by name
results = await m.search(
    query='ホロライブ フィギュア',
    price_min=3000,
    price_max=30000,
    status=[1],  # on_sale only
)

for item in results.items:
    print(f'{item.name} - ¥{item.price}')
    full = await item.full_item()  # fetch detail page
```

Key constraints:
- **Async only** — needs `asyncio.run()` or async event loop
- **Single instance** — don't create multiple `Mercapi()` objects (triggers bot detection)
- **No JAN search** — must use product name (Japanese) as search query
- AWS IPs are blacklisted; Hetzner (our VPS) is less targeted but still a risk

## Proposed Architecture

```
[Mercari Monitor] — separate process, polls every 2h
    → mercapi search by product name (Japanese)
    → Store listings in mercari_listings table
    → Compute price stats in mercari_price_stats table
    → Queue alerts for deals → pending_alerts
                    ↓
[Telegram Bot] — existing, picks up alerts
    → "메르카리 특가: {figure name} ¥{price} (시세 ¥{median})"
```

### New DB Tables

```sql
CREATE TABLE IF NOT EXISTS mercari_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mercari_id TEXT UNIQUE NOT NULL,     -- Mercari item ID (e.g., m90925725213)
    product_id INTEGER REFERENCES products(id),  -- matched local product
    search_query TEXT,                   -- query used to find this
    name TEXT NOT NULL,
    price INTEGER NOT NULL,              -- JPY
    item_condition TEXT,                 -- new, like_new, good, fair, poor
    status TEXT,                         -- on_sale, trading, sold_out
    seller_id TEXT,
    image_url TEXT,
    url TEXT,
    first_seen_at DATETIME,
    last_checked_at DATETIME,
    sold_at DATETIME                     -- when status changed to sold_out
);

CREATE TABLE IF NOT EXISTS mercari_price_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    median_sold_price INTEGER,
    min_sold_price INTEGER,
    max_sold_price INTEGER,
    num_sold_samples INTEGER,
    lowest_active_price INTEGER,
    num_active_listings INTEGER,
    computed_at DATETIME
);
```

### Matching Strategy

Since Mercari doesn't support JAN code search:
1. Use `character_name` + `series` from our `products` table (already extracted by LLM)
2. Translate to Japanese product name where possible
3. Filter by figure category on Mercari
4. Fuzzy match results back to our products (name similarity + price range sanity check)

## Implementation Steps

- [ ] Install `mercapi` and add to `requirements.txt`
- [ ] Test basic mercapi search from VPS (check if JP proxy needed)
- [ ] If geo-blocked: set up Japanese proxy (residential or datacenter)
- [ ] Create `mercari_monitor.py` — async search loop with conservative rate limiting
- [ ] Add `mercari_listings` + `mercari_price_stats` tables to `db.py`
- [ ] Build product name → Japanese search query mapping
- [ ] Implement matching logic (mercari listing → local product)
- [ ] Compute price stats (median sold price, deal detection)
- [ ] Integrate alerts into existing `pending_alerts` pipeline
- [ ] Add Telegram alert formatting for Mercari deals
- [ ] Create systemd service `figure-mercari-monitor.service`
- [ ] Add dashboard page for Mercari price data (admin or public)

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| mercapi breaks on API change | Pin version, monitor GitHub issues, have graceful fallback |
| IP blocked | Use JP residential proxy, rotate user agents |
| ToS violation | Keep personal-use scale, low request rate (25 searches/hr max) |
| Name-based matching is fuzzy | Start with high-confidence matches only (exact name matches) |
| JPY→KRW conversion needed | Use a free exchange rate API or daily cached rate |

## Rate Limiting Guidelines

- Max 1 `Mercapi()` instance per process
- 3-5 second delay between requests (random jitter)
- ~25 searches per hour max
- Start with 10-20 watched figures, expand gradually
- Cache results aggressively (don't re-search the same query within 2 hours)

## Open Questions

1. **Which figures to monitor?** All products with JAN codes? Only user-watched keywords? Top 50 most popular?
2. **JP proxy**: Test from Hetzner VPS first — mercapi might work without proxy
3. **Japanese product names**: Where do we get them? LLM translation? Manual mapping? MyFigureCollection.net?
4. **Alert threshold**: What price discount triggers a "deal" alert? (e.g., 20% below median?)
5. **번개장터 (Korean secondhand)**: Should we also integrate the Korean equivalent?

## References

- [mercapi GitHub](https://github.com/take-kun/mercapi) — Python library (v0.4.2)
- [mercapi PyPI](https://pypi.org/project/mercapi/)
- [Mercari Search API v2 Engineering Blog](https://engineering.mercari.com/en/blog/entry/20211005-search-api-v2/)
- [Existing brainstorm](../brainstorms/2026-02-19-mercari-integration-brainstorm.md)
