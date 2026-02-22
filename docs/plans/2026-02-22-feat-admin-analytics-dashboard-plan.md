# Admin Analytics Dashboard Plan

## Context

The figure-scrapper has 9 Telegram subscribers, watch keywords, and thousands of alerts flowing through — but no visibility into usage patterns. This admin dashboard provides a password-protected view into user engagement, message delivery, watch adoption, and system health. Built entirely from existing DB data (no bot code changes needed).

## Overview

| Aspect | Decision |
|--------|----------|
| **App** | `admin_dashboard.py` — single-file with `st.tabs()` (4 sections) |
| **Port** | 8502 (public dashboard is 8501) |
| **Auth** | `ADMIN_PASSWORD` env var + `st.session_state` gate; refuse to start if unset |
| **URL** | `https://admin.moyed.xyz` via Caddy reverse proxy |
| **DB access** | Read-only mode (`sqlite3.connect("file:...?mode=ro", uri=True)`) |
| **Queries** | New `analytics/admin_queries.py` (isolated from public dashboard) |
| **Charts** | New `analytics/admin_charts.py` (reuses `LAYOUT_DEFAULTS`, `SITE_COLORS` from existing `charts.py`) |
| **Cache TTL** | 60s (fresher than public dashboard's 300s) |
| **UI language** | Korean (matching existing dashboard) |

## Files to Create/Modify

### New Files (3)

1. **`analytics/admin_queries.py`** — ~14 cached query functions for user, alert, watch, and system metrics
2. **`analytics/admin_charts.py`** — ~8 Plotly chart builders (growth line, preference bar, keyword bar, alert volume area, latency histogram, heatmap, etc.)
3. **`admin_dashboard.py`** — Streamlit entrypoint: password gate + sidebar + 4 tabs

### Modified Files (1)

4. **`.github/workflows/deploy.yml`** (line 21) — Add `figure-admin-dashboard` to restart list with `|| true` fallback

### VPS Infrastructure (manual, not in git)

5. **`/etc/systemd/system/figure-admin-dashboard.service`** — New systemd unit
6. **`/etc/caddy/Caddyfile`** — Add `admin.moyed.xyz` reverse proxy block
7. **`/home/kkang/figure-scrapper/.env`** — Add `ADMIN_PASSWORD=<password>`
8. **GoDaddy DNS** — A record: `admin` → `46.224.154.129`

## Dashboard Sections (4 Tabs)

### Tab 1: 👥 사용자 현황 (User Overview)

| Component | Data Source | Query |
|-----------|------------|-------|
| Metrics: total / active / inactive users | `telegram_users` | `COUNT(*)`, `SUM(is_active=1)`, `SUM(is_active=0)` |
| User growth chart (cumulative + daily new) | `telegram_users.created_at` | `GROUP BY DATE(created_at)` with cumsum |
| Recent signups table (last 20) | `telegram_users` | `ORDER BY created_at DESC LIMIT 20` |
| Churned users table | `telegram_users WHERE is_active=0` | `ORDER BY updated_at DESC` |

- "Active" = `is_active=1` (has not blocked the bot). Simple and matches the existing data model.

### Tab 2: 🔔 알림 설정 & 관심 (Preferences & Watches)

| Component | Data Source | Query |
|-----------|------------|-------|
| Metrics: active users / users with watches / adoption rate % | `telegram_users` + `user_watches` | `COUNT(DISTINCT chat_id)` with join |
| Alert type adoption bar chart | `telegram_users` | `SUM(alert_new)`, `SUM(alert_restock)`, `SUM(alert_price)`, `SUM(alert_soldout)` |
| Watches per user distribution | `user_watches` LEFT JOIN `telegram_users` | `COUNT(uw.id) GROUP BY chat_id` |
| Top 20 watch keywords bar chart + table | `user_watches` JOIN `telegram_users` | `GROUP BY keyword ORDER BY count DESC` |

### Tab 3: 📨 메시지 전송 (Message Delivery)

| Component | Data Source | Query |
|-----------|------------|-------|
| Queue depth warning (unsent alerts) | `pending_alerts WHERE sent_at IS NULL` | `COUNT(*)`, `MIN(created_at)` |
| Metrics: total sent + breakdown by type | `pending_alerts WHERE sent_at IS NOT NULL` | `GROUP BY change_type` |
| Daily alert volume area chart (last 30d) | `pending_alerts.created_at` | `GROUP BY DATE(created_at), change_type` |
| Alert volume by site bar chart | `pending_alerts` | `GROUP BY site` |
| Delivery latency metrics (avg, P95) + histogram | `pending_alerts` | `julianday(sent_at) - julianday(created_at)` |

- **7-day data limitation**: `cleanup_old_alerts` in the bot deletes sent alerts after 7 days. The dashboard will note this: "최근 7일 데이터만 표시됩니다."
- **Stale alert exclusion**: Exclude alerts with latency > 1 hour from P50/P95 calculations (these are stale-batch summaries, not real delivery latency).

### Tab 4: 🛠️ 시스템 상태 (System Health)

| Component | Data Source | Query |
|-----------|------------|-------|
| Metrics: DB file size (MB) / total rows / table count | `os.path.getsize()` + `COUNT(*)` per table | Iterates key tables |
| Last scrape per site table | `products` | `MAX(last_checked_at) GROUP BY site` |
| Table row counts | All tables | `COUNT(*)` per table |
| Scrape activity heatmap (14 days, hour × date) | `products.last_checked_at` | `GROUP BY DATE, HOUR` pivot |
| Recent status changes table (last 50) | `status_changes` JOIN `products` | `ORDER BY changed_at DESC LIMIT 50` |

## Key Implementation Details

### Password Gate Pattern

```python
# Uses st.session_state for persistence across reruns
# Refuses to start if ADMIN_PASSWORD env var is unset/empty
# st.rerun() after successful auth to clear input
# Logout button in sidebar clears session state
```

### DB Connection (Read-Only)

```python
def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
```

Prevents accidental writes. Distinct from public dashboard's `get_conn()` in `analytics/queries.py`.

### `st.stop()` Gotcha

`st.stop()` halts the **entire script**, even inside a `with tab:` block. So inside tabs, use conditional guards (`if not df.empty:`) instead of `st.stop()`. Only use `st.stop()` in the auth gate (before tabs render).

### Charts — Reuse from `analytics/charts.py`

```python
from analytics.charts import LAYOUT_DEFAULTS, SITE_COLORS, STATUS_COLORS
```

New admin-specific constants:
```python
ALERT_TYPE_COLORS = {"new": "#2ECC71", "restock": "#3498DB", "price": "#F39C12", "soldout": "#E74C3C"}
ALERT_TYPE_LABELS = {"new": "신상품", "restock": "재입고", "price": "가격변동", "soldout": "품절"}
```

### Deploy Workflow Change

```yaml
# Line 21 — add admin dashboard with fallback
sudo systemctl restart figure-scraper figure-telegram-bot figure-dashboard
sudo systemctl restart figure-admin-dashboard || true
```

The `|| true` prevents deploy failure before the VPS service is created.

### Systemd Service Template

```ini
[Unit]
Description=Figure Admin Dashboard (Streamlit)
After=network.target

[Service]
Type=simple
User=kkang
WorkingDirectory=/home/kkang/figure-scrapper
EnvironmentFile=/home/kkang/figure-scrapper/.env
ExecStart=/home/kkang/figure-scrapper/.venv/bin/streamlit run admin_dashboard.py \
    --server.port 8502 --server.address 127.0.0.1 --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Caddy Config Addition

```
admin.moyed.xyz {
    reverse_proxy localhost:8502
}
```

## Implementation Order

1. `analytics/admin_queries.py` — all query functions (testable independently)
2. `analytics/admin_charts.py` — chart builders (imports from queries for type hints only)
3. `admin_dashboard.py` — integrates queries + charts, password gate, 4 tabs
4. `.github/workflows/deploy.yml` — one-line addition
5. VPS setup (after merge): DNS → Caddy → systemd service → .env → start

## Verification

### Local Testing
1. `ADMIN_PASSWORD=test streamlit run admin_dashboard.py --server.port 8502`
2. Verify password gate blocks without correct password
3. Verify correct password shows dashboard (tabs may be empty without production data — that's OK)
4. Verify logout clears session
5. Verify refresh button clears cache

### VPS Testing (after deploy)
1. `https://admin.moyed.xyz` loads with HTTPS and shows password prompt
2. Wrong password shows error; correct password shows all 4 tabs with real data
3. `https://figures.moyed.xyz` (public dashboard) is unaffected
4. `sudo journalctl -u figure-admin-dashboard -f` shows no errors
5. All 4 services restart cleanly on next `git push`

## Acceptance Criteria

- [ ] Password gate blocks unauthenticated access; refuses to start without `ADMIN_PASSWORD`
- [ ] 4 tabs render with real data on VPS (users, preferences, alerts, system health)
- [ ] Read-only DB connection (no accidental writes possible)
- [ ] `https://admin.moyed.xyz` accessible with HTTPS (Caddy auto-cert)
- [ ] Public dashboard at `figures.moyed.xyz` unaffected
- [ ] GitHub Actions deploys all 4 services successfully
- [ ] Korean UI labels matching existing dashboard conventions
