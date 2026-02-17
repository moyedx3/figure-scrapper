---
title: Precise Product Database with Sonnet Extraction
date: 2026-02-17
topic: extraction-quality
---

# Precise Product Database with Sonnet Extraction

## Problem

Current extraction (Haiku) produces noisy, inconsistent data:

1. **Character names polluted**: "Precious GEM 시리즈 소류 아스카 랑그레이 & 마키나미 마리 일러스트리어스" — product line leaked into character field
2. **No product type discrimination**: ₩8K keychains grouped with ₩425K scale figures because same character
3. **Manufacturer inconsistency**: Same company appears as "굿스마일컴퍼니", "GSC", "굿스마일", "G.S.C"
4. **Missing language normalization**: Korean, English, Japanese variants not unified
5. **Result**: 248 match groups but ~99% are wrong. Same character ≠ same product.

## What We're Building

A precise, clean product database where each product has accurately extracted:

- **series**: Canonical series name (normalized across languages)
- **character_name**: Clean character name only, no product codes or line names
- **product_type**: Figure, plushie, keychain, acrylic, badge, sticker, blanket, etc. (LLM-determined natural categories)
- **manufacturer**: Normalized canonical name
- **scale**: Physical scale (1/7, 1/6, non-scale, null)
- **version/edition**: Specific product variant (바니 ver., 재판, Precious GEM, 쵸코노세, etc.)
- **product_line**: Product line (넨도로이드, figma, POP UP PARADE, Coreful, AMP, etc.)

Goal: When matching, **exact same product** across sites = same manufacturer + same product_line + same character + same version. A "correct match" means you could price-compare the identical physical item.

## Why This Approach

**Single-pass Sonnet extraction** was chosen over alternatives:

- **vs Two-pass (extract → normalize)**: 2x cost, more complexity. Start simple.
- **vs Reference dictionary**: Upfront work to build dictionary. Can add later if single-pass consistency isn't enough.
- **vs Haiku**: Haiku's extraction quality was the root cause. Sonnet needed for understanding Korean product naming conventions, language normalization, and nuanced type classification.

## Key Decisions

1. **Model**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) — needed for quality, Haiku too noisy
2. **New field**: `product_type` — LLM determines natural categories from data (not predefined enum)
3. **Rollout**: Sample 50 first → validate quality → tune prompt → full re-extract all 2,854
4. **Match definition**: Exact same physical product (manufacturer + line + character + version)
5. **Language normalization**: Sonnet handles Korean/English/Japanese unification in-prompt

## Open Questions

- Should we store the LLM's raw response alongside extracted fields for debugging?
- Do we need a "canonical product ID" concept, or just rely on field combinations?
- How to handle multi-character products (e.g., "아스카 & 마리" set)?
- Cost estimate: ~2,854 products × Sonnet pricing ≈ $9-12 for full run
