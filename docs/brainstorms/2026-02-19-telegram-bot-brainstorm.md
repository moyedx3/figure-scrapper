# Telegram Bot for Figure Price Alerts

**Date:** 2026-02-19
**Status:** Design finalized, ready for planning

## What We're Building

A Telegram bot that Korean figure collectors interact with directly to:
1. **Receive alerts** for new products, restocks, price drops, and soldouts
2. **Choose alert types** they want (toggle new/restock/price/soldout)
3. **See cross-site price comparisons** in alert messages when a product exists
   on multiple sites

No Telegram channel. No interactive search/watchlist commands for MVP.
Just alerts with user-configurable preferences.

## Why This Approach

### Separate Service (not inline in scraper)

The bot runs as its own systemd service, separate from the scraper.
Communication happens via the SQLite database:

- Scraper writes changes → `pending_alerts` table
- Bot polls `pending_alerts`, sends messages, marks as sent

**Why separate:**
- Bot stays responsive for `/start` and `/settings` even during scrapes
- Can restart bot without affecting scraper and vice versa
- If Telegram API is slow/down, scraper isn't blocked
- Clean separation of concerns

### python-telegram-bot library (v22.x)

- Most popular Python Telegram library, high reputation
- Async with `Application.builder()` pattern
- Built-in `ConversationHandler` for `/settings` flow
- `sendPhoto` supports URL directly (no download needed)
- Active maintenance, supports latest Bot API features

### Rich alerts with cross-site prices

Each alert sends a photo message (product image) with a formatted caption:
- Product name, price, site, status
- If product is in a matching group: show prices from all sites
- Direct link to product page
- Inline keyboard button linking to product URL

## Key Decisions

1. **Separate systemd service** - Bot process independent from scraper
2. **Users choose alert types** via `/settings` with inline keyboard toggles
3. **Rich photo messages** with caption + cross-site price comparison
4. **Broadcast to all opted-in users** - no per-product watchlist for MVP
5. **python-telegram-bot v22.x** - async, well-documented, high quality
6. **pending_alerts table** - scraper writes, bot reads and sends
7. **No interactive search** - alerts only for MVP, search can come later
8. **Summary + details for bulk alerts** - send a summary header first, then individual messages
9. **Include dashboard link** - inline button linking to Streamlit price comparison page
10. **Korean only** - all bot UI, messages, commands in Korean

## User Flow

### Onboarding
1. User finds bot (shared link or search)
2. Sends `/start`
3. Bot registers user in `telegram_users` table
4. Bot shows welcome message + current alert settings
5. All alert types ON by default

### Settings
1. User sends `/settings`
2. Bot shows inline keyboard with toggles:
   ```
   🆕 신규 상품: ✅ ON
   🔄 재입고: ✅ ON
   💰 가격 변동: ✅ ON
   ❌ 품절: ❌ OFF
   ```
3. User taps a button to toggle on/off
4. Bot updates the message with new state

### Receiving Alerts
After each scrape cycle (every 15 min), bot sends alerts.

**If multiple changes detected**, bot sends a summary header first:
```
📊 피규어 알림 요약

🆕 신규 상품: 5개
🔄 재입고: 2개
💰 가격 변동: 3개

아래에서 상세 내용을 확인하세요.
```
Then individual messages follow.

**New product example:**
```
🆕 신규 상품

넨도로이드 아크나이츠 W

💰 ₩52,000
🏪 피규어프레소
📦 예약중

🔗 다른 사이트 가격:
 · 매니아하우스: ₩54,800
 · 따빼몰: ₩51,200

[상품 보기] [대시보드에서 비교]
```

**Price drop example:**
```
💰 가격 변동

POP UP PARADE 호시마치 스이세이

₩38,000 → ₩32,000 (−16%)
🏪 래빗츠컴퍼니

🔗 다른 사이트 가격:
 · 코믹스아트: ₩35,500
 · 피규어프레소: ₩36,000

[상품 보기]
```

**Restock example:**
```
🔄 재입고

넨도로이드 블루 아카이브 시로코

💰 ₩62,000
🏪 매니아하우스

[상품 보기]
```

## Data Model

### New tables

```sql
-- Users who have started the bot
CREATE TABLE telegram_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    alert_new BOOLEAN DEFAULT 1,
    alert_restock BOOLEAN DEFAULT 1,
    alert_price BOOLEAN DEFAULT 1,
    alert_soldout BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

-- Queue of alerts to send
CREATE TABLE pending_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_type TEXT NOT NULL,        -- new/restock/price/soldout
    product_id INTEGER NOT NULL,
    site TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    image_url TEXT,
    created_at TEXT,
    sent_at TEXT                      -- NULL until sent
);
```

### Integration points

- **Scraper** (`scheduler.py` / `scraper.py`): After `scrape_all()` returns
  changes, insert into `pending_alerts`
- **Bot process**: Polls `pending_alerts` WHERE `sent_at IS NULL`, sends
  messages to all matching users, marks as sent
- **Matching data**: Bot queries `product_matches` to build cross-site
  price comparison for each alert

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and show welcome message |
| `/settings` | Toggle alert type preferences |
| `/help` | Show available commands |
| `/status` | Show bot stats (products tracked, sites, last scrape time) |

## Technical Notes

### Telegram Bot API
- `sendPhoto`: Supports photo URL directly (use `image_url` from DB)
- Caption limit: 1024 characters (enough for our format)
- `parse_mode: "HTML"` for bold/italic formatting in captions
- `InlineKeyboardMarkup` for settings toggles and product links
- `CallbackQueryHandler` for handling button presses
- Rate limit: ~30 messages/second to different chats (sufficient)

### Systemd Service
- `figure-telegram-bot.service` alongside existing services
- Runs `python telegram_bot.py` with the bot's polling loop
- Auto-restart on failure

### Config
- `TELEGRAM_BOT_TOKEN` in `.env`
- `TELEGRAM_ENABLED` flag in `config.py`
- Site display names already in `SITES` config for Korean labels

## Resolved Questions

1. **Alert batching** → Summary header first, then individual messages
2. **Dashboard link** → Yes, include as inline keyboard button
3. **Language** → Korean only

## Remaining Open Questions

1. **Image fallback** - If `image_url` is NULL, send text-only message?
   (Likely yes - fall back to `sendMessage` instead of `sendPhoto`)
2. **Error handling** - If a user blocks the bot, mark `is_active = 0`?
   (Yes - catch `Forbidden` exception and deactivate user)
3. **Dashboard URL** - What's the public-facing URL for the Streamlit dashboard?
   (Need to configure or expose via reverse proxy)

## Next Steps

Run `/workflows:plan` to create implementation plan.
