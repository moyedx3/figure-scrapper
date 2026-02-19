#!/usr/bin/env python3
"""Telegram bot for figure price alerts.

Runs as a separate process from the scraper. Polls the pending_alerts
table and sends rich photo messages to subscribed users.

Run:
    python telegram_bot.py
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TimedOut, NetworkError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import (
    ALERT_STALE_HOURS,
    ALERT_SUMMARY_THRESHOLD,
    DASHBOARD_URL,
    DB_PATH,
    SITES,
    TELEGRAM_BOT_TOKEN,
)
from db import KST, get_connection, now_kst

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Alert type display config (Korean)
ALERT_TYPES = {
    "new":     {"label": "🆕 신규 상품",  "col": "alert_new"},
    "restock": {"label": "🔄 재입고",     "col": "alert_restock"},
    "price":   {"label": "💰 가격 변동",  "col": "alert_price"},
    "soldout": {"label": "❌ 품절",       "col": "alert_soldout"},
}

# Site display names from config
SITE_NAMES = {k: v["display_name"] for k, v in SITES.items()}


# ──────────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────────

def _get_or_create_user(conn: sqlite3.Connection, chat_id: int, username: str | None) -> dict:
    """Get existing user or create a new one. Returns user row as dict."""
    row = conn.execute(
        "SELECT * FROM telegram_users WHERE chat_id = ?", (chat_id,)
    ).fetchone()

    if row:
        # Reactivate if previously blocked
        if not row["is_active"]:
            conn.execute(
                "UPDATE telegram_users SET is_active = 1, updated_at = ? WHERE chat_id = ?",
                (now_kst(), chat_id),
            )
            conn.commit()
        return dict(conn.execute(
            "SELECT * FROM telegram_users WHERE chat_id = ?", (chat_id,)
        ).fetchone())

    now = now_kst()
    conn.execute(
        """INSERT INTO telegram_users (chat_id, username, created_at, updated_at)
           VALUES (?, ?, ?, ?)""",
        (chat_id, username, now, now),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM telegram_users WHERE chat_id = ?", (chat_id,)
    ).fetchone())


def _toggle_alert(conn: sqlite3.Connection, chat_id: int, alert_type: str) -> bool:
    """Toggle an alert type for a user. Returns new value."""
    col = ALERT_TYPES[alert_type]["col"]
    conn.execute(
        f"UPDATE telegram_users SET {col} = NOT {col}, updated_at = ? WHERE chat_id = ?",
        (now_kst(), chat_id),
    )
    conn.commit()
    row = conn.execute(
        f"SELECT {col} FROM telegram_users WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return bool(row[col])


def _get_active_users_for_type(conn: sqlite3.Connection, change_type: str) -> list[int]:
    """Get chat_ids of active users who want this alert type."""
    col = ALERT_TYPES.get(change_type, {}).get("col")
    if not col:
        return []
    rows = conn.execute(
        f"SELECT chat_id FROM telegram_users WHERE is_active = 1 AND {col} = 1"
    ).fetchall()
    return [r["chat_id"] for r in rows]


def _deactivate_user(conn: sqlite3.Connection, chat_id: int):
    """Mark user as inactive (blocked the bot)."""
    conn.execute(
        "UPDATE telegram_users SET is_active = 0, updated_at = ? WHERE chat_id = ?",
        (now_kst(), chat_id),
    )
    conn.commit()
    logger.info(f"Deactivated user {chat_id} (blocked bot)")


def _get_cross_site_prices(conn: sqlite3.Connection, product_db_id: int) -> list[dict]:
    """Get prices from other sites for the same product via matching groups."""
    row = conn.execute(
        "SELECT match_key FROM product_matches WHERE product_id = ?",
        (product_db_id,),
    ).fetchone()
    if not row:
        return []

    matches = conn.execute("""
        SELECT p.site, p.name, p.price, p.status, p.url
        FROM product_matches pm
        JOIN products p ON pm.product_id = p.id
        WHERE pm.match_key = ? AND pm.product_id != ?
        ORDER BY p.price ASC NULLS LAST
    """, (row["match_key"], product_db_id)).fetchall()
    return [dict(m) for m in matches]


# ──────────────────────────────────────────────
# Alert formatting
# ──────────────────────────────────────────────

def _format_price(price: int | None) -> str:
    if price is None:
        return "가격 미정"
    return f"₩{price:,}"


def _format_alert_caption(alert: dict, cross_prices: list[dict]) -> str:
    """Format an alert into an HTML caption for Telegram."""
    change_type = alert["change_type"]
    header = ALERT_TYPES.get(change_type, {}).get("label", change_type)
    site_name = SITE_NAMES.get(alert["site"], alert["site"])

    lines = [f"{header}\n"]
    lines.append(f"<b>{_escape_html(alert['product_name'])}</b>\n")

    if change_type == "price":
        old_p = int(alert["old_value"]) if alert["old_value"] else None
        new_p = int(alert["new_value"]) if alert["new_value"] else None
        if old_p and new_p:
            pct = (new_p - old_p) / old_p * 100
            sign = "+" if pct > 0 else ""
            lines.append(f"💰 {_format_price(old_p)} → {_format_price(new_p)} ({sign}{pct:.0f}%)")
        else:
            lines.append(f"💰 {_format_price(alert['product_price'])}")
    else:
        lines.append(f"💰 {_format_price(alert['product_price'])}")

    lines.append(f"🏪 {site_name}")

    if change_type == "new" and alert.get("new_value"):
        status_map = {"available": "구매 가능", "preorder": "예약중", "soldout": "품절"}
        status_kr = status_map.get(alert["new_value"], alert["new_value"])
        lines.append(f"📦 {status_kr}")

    # Cross-site prices
    if cross_prices:
        lines.append(f"\n🔗 <b>다른 사이트 가격:</b>")
        for cp in cross_prices[:4]:  # Max 4 to stay under caption limit
            cp_site = SITE_NAMES.get(cp["site"], cp["site"])
            cp_price = _format_price(cp["price"])
            lines.append(f" · {cp_site}: {cp_price}")

    return "\n".join(lines)


def _format_summary(alerts: list[dict]) -> str:
    """Format a batch summary header message."""
    counts = {}
    for a in alerts:
        ct = a["change_type"]
        counts[ct] = counts.get(ct, 0) + 1

    lines = ["📊 <b>피규어 알림 요약</b>\n"]
    for ct, info in ALERT_TYPES.items():
        if ct in counts:
            lines.append(f"{info['label']}: {counts[ct]}개")
    lines.append("\n아래에서 상세 내용을 확인하세요.")
    return "\n".join(lines)


def _build_alert_keyboard(alert: dict) -> InlineKeyboardMarkup | None:
    """Build inline keyboard buttons for an alert message."""
    buttons = []
    if alert.get("product_url"):
        buttons.append(InlineKeyboardButton("🔗 상품 보기", url=alert["product_url"]))
    if DASHBOARD_URL:
        buttons.append(InlineKeyboardButton("📊 대시보드", url=DASHBOARD_URL))
    if not buttons:
        return None
    return InlineKeyboardMarkup([buttons])


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ──────────────────────────────────────────────
# Settings keyboard
# ──────────────────────────────────────────────

def _build_settings_keyboard(user: dict) -> InlineKeyboardMarkup:
    """Build inline keyboard for alert settings toggles."""
    buttons = []
    for alert_type, info in ALERT_TYPES.items():
        col = info["col"]
        is_on = user.get(col, False)
        emoji = "✅" if is_on else "❌"
        label = f"{info['label']}: {emoji}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"toggle_{alert_type}")])
    return InlineKeyboardMarkup(buttons)


# ──────────────────────────────────────────────
# Command handlers
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — register user and show welcome."""
    conn = get_connection()
    user = _get_or_create_user(
        conn,
        update.effective_chat.id,
        update.effective_user.username,
    )
    conn.close()

    keyboard = _build_settings_keyboard(user)
    await update.message.reply_text(
        "👋 <b>피규어 알림 봇에 오신 것을 환영합니다!</b>\n\n"
        "5개 사이트의 피규어 신규 상품, 재입고, 가격 변동 알림을 받을 수 있습니다.\n\n"
        "📌 <b>현재 알림 설정:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings — show alert toggle keyboard."""
    conn = get_connection()
    user = _get_or_create_user(
        conn,
        update.effective_chat.id,
        update.effective_user.username,
    )
    conn.close()

    keyboard = _build_settings_keyboard(user)
    await update.message.reply_text(
        "⚙️ <b>알림 설정</b>\n\n버튼을 눌러 알림을 켜거나 끌 수 있습니다.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — show available commands."""
    await update.message.reply_text(
        "📖 <b>사용 가능한 명령어</b>\n\n"
        "/start — 봇 시작 및 등록\n"
        "/settings — 알림 설정 변경\n"
        "/status — 봇 현황 확인\n"
        "/help — 이 도움말 보기",
        parse_mode=ParseMode.HTML,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — show bot stats."""
    conn = get_connection()

    product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    site_count = conn.execute("SELECT COUNT(DISTINCT site) FROM products").fetchone()[0]
    user_count = conn.execute(
        "SELECT COUNT(*) FROM telegram_users WHERE is_active = 1"
    ).fetchone()[0]
    last_alert = conn.execute(
        "SELECT MAX(created_at) FROM pending_alerts"
    ).fetchone()[0]

    conn.close()

    await update.message.reply_text(
        "📊 <b>봇 현황</b>\n\n"
        f"📦 추적 중인 상품: {product_count:,}개\n"
        f"🏪 모니터링 사이트: {site_count}개\n"
        f"👤 활성 사용자: {user_count}명\n"
        f"🕐 마지막 알림: {last_alert or '없음'}",
        parse_mode=ParseMode.HTML,
    )


async def callback_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle settings toggle button press."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data or not data.startswith("toggle_"):
        return

    alert_type = data.replace("toggle_", "")
    if alert_type not in ALERT_TYPES:
        return

    conn = get_connection()
    _toggle_alert(conn, update.effective_chat.id, alert_type)
    user = dict(conn.execute(
        "SELECT * FROM telegram_users WHERE chat_id = ?",
        (update.effective_chat.id,),
    ).fetchone())
    conn.close()

    keyboard = _build_settings_keyboard(user)
    await query.edit_message_reply_markup(reply_markup=keyboard)


# ──────────────────────────────────────────────
# Alert dispatcher (runs on job queue)
# ──────────────────────────────────────────────

async def process_pending_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Poll pending_alerts and send to matching users."""
    conn = get_connection()

    # Check for stale backlog (bot was offline)
    oldest = conn.execute(
        "SELECT MIN(created_at) FROM pending_alerts WHERE sent_at IS NULL"
    ).fetchone()[0]

    if oldest:
        stale_cutoff = (datetime.now(KST) - timedelta(hours=ALERT_STALE_HOURS)).strftime("%Y-%m-%d %H:%M:%S")

        if oldest < stale_cutoff:
            # Summarize stale alerts instead of flooding
            stale_alerts = conn.execute(
                "SELECT change_type, COUNT(*) as cnt FROM pending_alerts WHERE sent_at IS NULL GROUP BY change_type"
            ).fetchall()

            total = sum(r["cnt"] for r in stale_alerts)
            lines = ["⏰ <b>봇이 오프라인 동안의 알림 요약</b>\n"]
            for r in stale_alerts:
                info = ALERT_TYPES.get(r["change_type"], {})
                label = info.get("label", r["change_type"])
                lines.append(f"{label}: {r['cnt']}개")
            lines.append(f"\n총 {total}개의 알림이 있었습니다.")
            summary_text = "\n".join(lines)

            # Send to all active users
            users = conn.execute(
                "SELECT chat_id FROM telegram_users WHERE is_active = 1"
            ).fetchall()
            for user in users:
                try:
                    await context.bot.send_message(
                        chat_id=user["chat_id"],
                        text=summary_text,
                        parse_mode=ParseMode.HTML,
                    )
                except Forbidden:
                    _deactivate_user(conn, user["chat_id"])
                except Exception as e:
                    logger.warning(f"Failed to send stale summary to {user['chat_id']}: {e}")

            # Mark all stale as sent
            conn.execute(
                "UPDATE pending_alerts SET sent_at = ? WHERE sent_at IS NULL",
                (now_kst(),),
            )
            conn.commit()
            conn.close()
            logger.info(f"Sent stale backlog summary ({total} alerts)")
            return

    # Normal processing: get unsent alerts grouped by batch
    unsent = conn.execute("""
        SELECT * FROM pending_alerts
        WHERE sent_at IS NULL
        ORDER BY batch_id, id
    """).fetchall()

    if not unsent:
        conn.close()
        return

    unsent = [dict(r) for r in unsent]

    # Group by batch_id
    batches: dict[str, list[dict]] = {}
    for alert in unsent:
        batches.setdefault(alert["batch_id"], []).append(alert)

    sent_count = 0

    for batch_id, alerts in batches.items():
        # Collect all unique change types in this batch
        change_types = set(a["change_type"] for a in alerts)

        # Get all users who should receive at least one alert type
        type_to_users: dict[str, list[int]] = {}
        for ct in change_types:
            type_to_users[ct] = _get_active_users_for_type(conn, ct)

        # All users who get any alert in this batch
        all_users = set()
        for users in type_to_users.values():
            all_users.update(users)

        if not all_users:
            # No users want any of these — mark as sent
            for alert in alerts:
                conn.execute(
                    "UPDATE pending_alerts SET sent_at = ? WHERE id = ?",
                    (now_kst(), alert["id"]),
                )
            conn.commit()
            continue

        # Send summary header if batch is large enough
        if len(alerts) >= ALERT_SUMMARY_THRESHOLD:
            summary = _format_summary(alerts)
            for chat_id in all_users:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=summary,
                        parse_mode=ParseMode.HTML,
                    )
                    await asyncio.sleep(0.05)
                except Forbidden:
                    _deactivate_user(conn, chat_id)
                except Exception as e:
                    logger.warning(f"Failed to send summary to {chat_id}: {e}")

        # Send individual alerts
        for alert in alerts:
            target_users = type_to_users.get(alert["change_type"], [])
            if not target_users:
                conn.execute(
                    "UPDATE pending_alerts SET sent_at = ? WHERE id = ?",
                    (now_kst(), alert["id"]),
                )
                continue

            cross_prices = _get_cross_site_prices(conn, alert["product_db_id"])
            caption = _format_alert_caption(alert, cross_prices)
            keyboard = _build_alert_keyboard(alert)

            for chat_id in target_users:
                try:
                    if alert.get("image_url"):
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=alert["image_url"],
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=keyboard,
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=keyboard,
                        )
                    await asyncio.sleep(0.05)
                except Forbidden:
                    _deactivate_user(conn, chat_id)
                except (TimedOut, NetworkError) as e:
                    # Retry once after short delay
                    logger.warning(f"Transient error sending to {chat_id}, retrying: {e}")
                    await asyncio.sleep(5)
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=keyboard,
                        )
                    except Exception:
                        logger.warning(f"Retry failed for {chat_id}")
                except Exception as e:
                    # sendPhoto may fail if CDN blocks Telegram — fallback to text
                    if alert.get("image_url"):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=caption,
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard,
                            )
                        except Exception:
                            logger.warning(f"Text fallback also failed for {chat_id}: {e}")
                    else:
                        logger.warning(f"Failed to send alert to {chat_id}: {e}")

            # Mark alert as sent
            conn.execute(
                "UPDATE pending_alerts SET sent_at = ? WHERE id = ?",
                (now_kst(), alert["id"]),
            )
            sent_count += 1

        conn.commit()

    conn.close()
    if sent_count:
        logger.info(f"Sent {sent_count} alerts")


async def cleanup_old_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete old sent alerts to keep the table small."""
    conn = get_connection()
    result = conn.execute(
        "DELETE FROM pending_alerts WHERE sent_at IS NOT NULL AND created_at < datetime('now', '+9 hours', '-7 days')"
    )
    deleted = result.rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Cleaned up {deleted} old alerts")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return

    # Ensure DB tables exist
    from db import init_db
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    # Callback handler for settings toggles
    app.add_handler(CallbackQueryHandler(callback_toggle, pattern="^toggle_"))

    # Job queue: poll pending alerts every 30 seconds
    app.job_queue.run_repeating(
        process_pending_alerts,
        interval=30,
        first=10,  # Start 10s after boot to let things settle
        name="alert_dispatcher",
    )

    # Job queue: clean up old alerts daily
    app.job_queue.run_repeating(
        cleanup_old_alerts,
        interval=86400,  # 24 hours
        first=3600,      # First run 1 hour after start
        name="alert_cleanup",
    )

    logger.info("Telegram bot starting... (polling every 30s for alerts)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
