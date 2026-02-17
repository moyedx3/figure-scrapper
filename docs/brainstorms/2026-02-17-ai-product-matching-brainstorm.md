---
title: AI-Powered Cross-Site Product Matching
date: 2026-02-17
status: ready-for-plan
---

# AI-Powered Cross-Site Product Matching

## What We're Building

An AI-assisted structured data extraction pipeline that parses messy product names into normalized fields, enabling reliable cross-site product matching. This replaces the current fuzzy string matching (rapidfuzz) which only achieves 0.2% match rate due to wildly different naming conventions across sites.

## Why This Approach

**Problem:** Same figure product named completely differently across sites:
- comicsart: `"(공식 파트너샵) 유니온 크리에이티브 오버로드 샤르티아 블러드폴른 10주년 so-bin"`
- maniahouse: `"[3월중입고예정] 오버로드 샤르티아블러드폴른 10th Anniversary so-bin ver. 유니온 67"`

**Why structured extraction > fuzzy matching:**
- Scales to 10+ sites including secondhand markets (where names are even messier)
- Matching becomes a DB lookup, not an expensive computation
- Extracted fields enrich the dashboard (better filtering, grouping)
- One-time cost per product, no repeated LLM calls

## Key Decisions

1. **Hybrid extraction strategy** — Rule-based parsing first (regex, known patterns). LLM (Claude Haiku) only when rules can't extract cleanly. Keeps cost minimal.

2. **Extract on first-seen** — Run extraction when a product is first scraped. Store structured fields in DB. Matching uses DB lookups only — no LLM at query time.

3. **LLM provider: Claude (Anthropic)** — Haiku model. Fast, cheap (~$0.001/product), excellent Korean understanding.

4. **Core structured fields:**
   - `series` (작품명) — e.g., "오버로드", "투 러브 트러블 다크니스"
   - `character` (캐릭터) — e.g., "샤르티아 블러드폴른", "유우키 미캉"
   - `manufacturer` (제조사) — e.g., "유니온 크리에이티브", "MIMOSA"
   - `scale` — e.g., "1/7", "1/6", "넨도로이드"
   - `version` (에디션) — e.g., "standard", "deluxe", "바니 ver."
   - *Expand as needed* — add fields like `artist`, `product_line` (figma, POP UP PARADE) as patterns emerge from the 5 sites

5. **Matching logic:** Products match when `series + character + manufacturer + scale` align. `version` distinguishes variants within a match group.

## Data Context

- 2,917 products across 5 Cafe24-based Korean figure sites
- 0% JAN code coverage (no barcodes available)
- 31% manufacturer coverage (biggest metadata gap)
- Current fuzzy matching: 3 groups found (0.2% recall)
- Names mix Korean, English, Japanese with no consistent convention

## Open Questions

- Batch size for initial backfill (all 2,917 at once vs chunked?)
- How to handle extraction failures/low-confidence results
- Schema: new columns on `products` table vs separate `product_attributes` table?
- Should we re-extract when product name changes (rare but possible)?
