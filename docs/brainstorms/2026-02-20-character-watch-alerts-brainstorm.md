---
title: Character/Series Watch Alerts
date: 2026-02-20
status: brainstorm-complete
---

# Character/Series Watch Alerts

## What We're Building

Users can subscribe to specific characters or series via `/watch <keyword>` in the Telegram bot. When subscriptions are set, alerts are filtered to only send products matching at least one of the user's watch keywords. Users with no watches continue to receive all alerts (current behavior).

## Why This Approach

**Simple keyword watches** (no series vs character type distinction):
- Users don't need to know whether "원신" is a series or "하츠네 미쿠" is a character — they just type the name
- One `/watch` command handles everything
- Matching checks extracted `series` and `character_name` first (structured, clean), then falls back to raw `product_name` substring (catches unextracted products)
- Can always add typed watches later if keyword-only proves too noisy (YAGNI)

## Key Decisions

1. **Filter level**: Both series and character, no type distinction — just keywords
2. **Interaction with existing toggles**: Additive — no watches = get everything (backward compatible). Watches narrow the filter within enabled alert types.
3. **UX**: `/watch <keyword>` to add, `/unwatch <keyword>` to remove, `/mywatches` to list with inline remove buttons
4. **Matching strategy**: Structured fields first (`series`, `character_name`), product name substring fallback. Case-insensitive. Substring matching (e.g., "미쿠" matches "하츠네 미쿠").
5. **Filtering happens at dispatch time** (`process_pending_alerts`), not queue time — watches can change anytime and apply immediately
6. **Watch limit**: Max 10 per user — forces selectivity, keeps it focused
7. **Minimum keyword length**: 2 characters — prevents meaningless single-char watches
8. **Watch tag in alerts**: Show matched keyword at the top of alert caption (e.g., "🔔 원신") so users know why they got the alert
9. **Remove UX**: `/mywatches` shows inline buttons for tap-to-remove (matches `/settings` pattern)

## Schema

New table:
```sql
CREATE TABLE IF NOT EXISTS user_watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(chat_id, keyword)
);
```

## Alert Dispatch Logic Change

In `process_pending_alerts`, when deciding whether to send an alert to a user:

```
1. Check user's alert type toggle (existing) — if OFF, skip
2. Check user's watches:
   a. No watches → send (current behavior, no watch tag)
   b. Has watches → match product against watches:
      - Load product's series + character_name via JOIN products ON product_db_id
      - For each watch keyword:
        - Case-insensitive substring check against series
        - Case-insensitive substring check against character_name
        - Fallback: case-insensitive substring check against product_name
      - Any match → send with "🔔 <keyword>" tag. No match → skip.
```

## New Bot Commands

| Command | Behavior |
|---------|----------|
| `/watch 원신` | Add "원신" to user's watch list |
| `/unwatch 원신` | Remove "원신" from watch list |
| `/mywatches` | Show all current watches with inline ❌ remove buttons |

### Bot Messages (shy personality)

**`/watch 원신` (success)**:
> 저, 저기... "원신" 추가했어요...! 이제 원신 관련 상품이 나오면 바로 알려드릴게요...!
> 📋 현재 관심 목록: 1/10개

**`/watch` (no keyword)**:
> 아, 저기... 키워드를 알려주셔야 해요...!
> 사용법: `/watch 원신` 또는 `/watch 하츠네 미쿠`

**`/watch` (limit reached)**:
> 죄, 죄송해요... 관심 목록이 가득 찼어요... (10/10개)
> `/mywatches`에서 안 보는 키워드를 지워주시면...!

**`/watch` (keyword too short)**:
> 아, 저기... 2글자 이상으로 입력해주시면...!

**`/watch` (already exists)**:
> 아, 그건 이미 목록에 있어요...! 걱정 마세요, 잘 지켜보고 있을게요...!

**`/mywatches` (has watches)**:
> 📋 저, 저한테 맡겨주신 관심 목록이에요...! (3/10개)
> 버튼을 누르면 삭제할 수 있어요...
> [❌ 원신] [❌ 하츠네 미쿠] [❌ 블루 아카이브]

**`/mywatches` (empty)**:
> 아, 아직 관심 목록이 비어있어요...
> `/watch 원신` 이렇게 추가해주시면... 관련 상품만 알려드릴게요...!
> 관심 목록이 없으면 모든 알림을 보내드려요...!

**`/unwatch 원신` (success)**:
> "원신" 삭제했어요...! 📋 남은 관심 목록: 2/10개

**`/unwatch` (not found)**:
> 어, 그 키워드는 목록에 없는 것 같은데... `/mywatches`에서 확인해보실래요...?

### Alert caption with watch tag

When a watch matches, prepend the tag before the existing alert header:
```
🔔 원신

🆕 저, 저기... 새로운 상품이 나왔어요...!
[굿스마일컴퍼니] 넨도로이드 원신 장리
💰 ₩74,200
🏪 피규어프레소
...
```

## Matching Priority

For each user watch keyword, match in this order (stop on first match):
1. Product `series` field — case-insensitive substring
2. Product `character_name` field — case-insensitive substring
3. Product `name` (raw) — case-insensitive substring

This means structured fields take priority (cleaner), with product name as safety net.

## Out of Scope (for now)

- Per-product watchlist (watch a specific product_id for restock)
- Browse/discovery UI with inline buttons
- Typed watches (series vs character distinction)
- Site-specific filtering
- Regex or wildcard pattern watches
