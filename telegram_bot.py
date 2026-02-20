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

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    "new":     {"label": "🆕 저, 저기... 새로운 상품이 나왔어요...!",  "col": "alert_new"},
    "restock": {"label": "🔄 저, 저기...! 품절됐던 게 다시 들어왔어요...!",  "col": "alert_restock"},
    "price":   {"label": "💰 가, 가격이 바뀌었어요...!",  "col": "alert_price"},
    "soldout": {"label": "❌ 아... 품, 품절됐어요...",    "col": "alert_soldout"},
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


def _add_watch(conn: sqlite3.Connection, chat_id: int, keyword: str) -> str:
    """Add a watch keyword. Returns: 'added', 'exists', 'limit'."""
    keyword = keyword.strip().lower()
    count = conn.execute(
        "SELECT COUNT(*) FROM user_watches WHERE chat_id = ?", (chat_id,)
    ).fetchone()[0]
    if count >= 10:
        return "limit"
    try:
        conn.execute(
            "INSERT INTO user_watches (chat_id, keyword, created_at) VALUES (?, ?, ?)",
            (chat_id, keyword, now_kst()),
        )
        conn.commit()
        return "added"
    except sqlite3.IntegrityError:
        return "exists"


def _remove_watch(conn: sqlite3.Connection, chat_id: int, watch_id: int) -> bool:
    """Remove a watch by id. Returns True if deleted."""
    result = conn.execute(
        "DELETE FROM user_watches WHERE id = ? AND chat_id = ?",
        (watch_id, chat_id),
    )
    conn.commit()
    return result.rowcount > 0


def _remove_watch_by_keyword(conn: sqlite3.Connection, chat_id: int, keyword: str) -> bool:
    """Remove a watch by keyword text. Returns True if deleted."""
    keyword = keyword.strip().lower()
    result = conn.execute(
        "DELETE FROM user_watches WHERE chat_id = ? AND keyword = ?",
        (chat_id, keyword),
    )
    conn.commit()
    return result.rowcount > 0


def _get_watches(conn: sqlite3.Connection, chat_id: int) -> list[dict]:
    """Get all watches for a user."""
    rows = conn.execute(
        "SELECT id, keyword FROM user_watches WHERE chat_id = ? ORDER BY id",
        (chat_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_watch_count(conn: sqlite3.Connection, chat_id: int) -> int:
    """Get number of watches for a user."""
    return conn.execute(
        "SELECT COUNT(*) FROM user_watches WHERE chat_id = ?", (chat_id,)
    ).fetchone()[0]


def _deactivate_user(conn: sqlite3.Connection, chat_id: int):
    """Mark user as inactive (blocked the bot)."""
    conn.execute(
        "UPDATE telegram_users SET is_active = 0, updated_at = ? WHERE chat_id = ?",
        (now_kst(), chat_id),
    )
    conn.commit()
    logger.info(f"Deactivated user {chat_id} (blocked bot)")


def _get_cross_site_prices(conn: sqlite3.Connection, product_db_id: int) -> tuple[list[dict], bool]:
    """Get prices from other sites for the same product via matching groups.

    Returns (matches, is_suspicious) where is_suspicious is True if
    max price >= 2x min price (likely deposit vs full price).
    """
    row = conn.execute(
        "SELECT match_key FROM product_matches WHERE product_id = ?",
        (product_db_id,),
    ).fetchone()
    if not row:
        return [], False

    matches = conn.execute("""
        SELECT p.site, p.name, p.price, p.status, p.url
        FROM product_matches pm
        JOIN products p ON pm.product_id = p.id
        WHERE pm.match_key = ? AND pm.product_id != ?
        ORDER BY p.price ASC NULLS LAST
    """, (row["match_key"], product_db_id)).fetchall()
    results = [dict(m) for m in matches]

    # Check if group has suspicious pricing (2x+ spread)
    all_prices_rows = conn.execute("""
        SELECT p.price
        FROM product_matches pm
        JOIN products p ON pm.product_id = p.id
        WHERE pm.match_key = ? AND p.price IS NOT NULL AND p.price > 0
    """, (row["match_key"],)).fetchall()
    prices = [r["price"] for r in all_prices_rows]
    is_suspicious = len(prices) >= 2 and max(prices) >= 2 * min(prices)

    return results, is_suspicious


# ──────────────────────────────────────────────
# Alert formatting
# ──────────────────────────────────────────────

def _format_price(price: int | None) -> str:
    if price is None:
        return "가격 미정"
    return f"₩{price:,}"


def _matches_watch(keyword: str, series: str | None, character_name: str | None, product_name: str) -> bool:
    """Check if a watch keyword matches a product. Case-insensitive substring."""
    kw = keyword  # already lowercase from storage
    if series and kw in series.lower():
        return True
    if character_name and kw in character_name.lower():
        return True
    if kw in product_name.lower():
        return True
    return False


def _format_alert_caption(
    alert: dict,
    cross_prices: list[dict],
    suspicious_match: bool = False,
    matched_keyword: str | None = None,
) -> str:
    """Format an alert into an HTML caption for Telegram."""
    change_type = alert["change_type"]
    header = ALERT_TYPES.get(change_type, {}).get("label", change_type)
    site_name = SITE_NAMES.get(alert["site"], alert["site"])

    lines = []
    if matched_keyword:
        lines.append(f"🔔 {_escape_html(matched_keyword)}\n")
    lines.append(f"{header}\n")
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

    # Per-type flavor text
    if change_type == "new" and alert.get("new_value"):
        status_map = {
            "available": "📦 아, 아직 구매 가능해요...! 서, 서두르지 않아도... 아니 서두르는 게 나을지도...",
            "preorder": "📦 예, 예약 중이에요...! 서, 서두르는 게 좋을지도...",
            "soldout": "📦 아... 벌써 품절이에요... 죄, 죄송해요...",
        }
        lines.append(status_map.get(alert["new_value"], f"📦 {alert['new_value']}"))
    elif change_type == "restock":
        lines.append("또, 또 놓치면... 다음은 모르겠어요...")
    elif change_type == "price":
        old_p = int(alert["old_value"]) if alert["old_value"] else None
        new_p = int(alert["new_value"]) if alert["new_value"] else None
        if old_p and new_p and new_p < old_p:
            lines.append("싸, 싸졌어요... 지금이 기회일지도...")
        elif old_p and new_p and new_p > old_p:
            lines.append("비, 비싸졌어요... 죄, 죄송해요...")
    elif change_type == "soldout":
        lines.append("죄, 죄송해요... 좀 더 빨리 알려드렸어야 했는데...")
        lines.append("재입고 되면 바로 알려드릴게요...!")

    # Cross-site prices
    if cross_prices:
        if suspicious_match:
            lines.append(f"\n🔗 다, 다른 사이트도 찾아봤는데... ⚠️ 가격 차이가 너무 커서 좀 이상해요...")
            lines.append("예, 예약금만 받는 건지도 모르겠어요... 확인해보시는 게...")
        else:
            lines.append(f"\n🔗 다, 다른 사이트도 찾아봤어요...:")
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

    summary_labels = {
        "new": "🆕 신규 상품",
        "restock": "🔄 재입고",
        "price": "💰 가격 변동",
        "soldout": "❌ 품절",
    }
    lines = ["📊 저, 저기... 알림이 좀 많이 밀렸어요...\n"]
    for ct, label in summary_labels.items():
        if ct in counts:
            lines.append(f"{label}: {counts[ct]}개")
    lines.append("\n한, 한꺼번에 보내서 죄송해요... 아래에서 확인해주세요...!")
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
        "아, 안녕하세요...! 피, 피규어 알림 봇에 오신 것을 환영합니다...!\n\n"
        "저, 저는 5개 사이트에서 피규어 신상품이나 재입고, 가격 변동 같은 거... 알려드리는 봇이에요...\n\n"
        "관심 가져주셔서 감사해요... 저 같은 봇한테 와주시다니...\n\n"
        "소... 솔직히 국내샵은... 비싸다고 생각해요...\n\n"
        "아, 열심히 할게요...! 실망시키지 않도록...!\n\n"
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
        "⚙️ 아, 알림 설정이에요...!\n"
        "버, 버튼을 눌러서 알림을 켜거나 끌 수 있어요...\n"
        "저, 저한테 맡겨주시면... 열심히 알려드릴게요...!\n"
        "혹시 알림이 너무 많으면... 말씀해주세요... 싫어지는 건 아니겠죠...?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — show available commands."""
    await update.message.reply_text(
        "📖 저, 저한테 할 수 있는 명령어들이에요...!\n\n"
        "/start — 봇, 봇 시작하고 등록하는 거에요...\n"
        "/settings — 아, 알림 설정을 바꿀 수 있어요...\n"
        "/watch 원신 — 관, 관심 키워드를 추가할 수 있어요...\n"
        "/unwatch 원신 — 관심 키워드를 삭제해요...\n"
        "/mywatches — 관, 관심 목록을 볼 수 있어요...\n"
        "/status — 지, 지금 봇이 어떤 상태인지 볼 수 있어요...\n"
        "/help — 지, 지금 보고 계신 이거에요...\n\n"
        "모, 모르는 거 있으면 물어봐주세요... 아, 물어봐주지 않아도 괜찮긴 하지만... 아니 그건 아니고...!",
        parse_mode=ParseMode.HTML,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — show bot stats."""
    conn = get_connection()

    product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    site_count = conn.execute("SELECT COUNT(DISTINCT site) FROM products").fetchone()[0]
    last_alert = conn.execute(
        "SELECT MAX(created_at) FROM pending_alerts"
    ).fetchone()[0]

    conn.close()

    await update.message.reply_text(
        "📊 저, 저의 현황이에요...!\n\n"
        f"📦 추적 중인 상품: {product_count:,}개... 마, 많죠...? 저 나름 열심히 하고 있어요...\n"
        f"🏪 모니터링 사이트: {site_count}개\n"
        f"🕐 마지막 알림: {last_alert or '없음'}\n\n"
        "옷, 옷장 안에서 계속 지켜보고 있을게요...!",
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
# Watch command handlers
# ──────────────────────────────────────────────

async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /watch <keyword> — add a watch keyword."""
    conn = get_connection()
    _get_or_create_user(conn, update.effective_chat.id, update.effective_user.username)

    keyword = " ".join(context.args) if context.args else ""
    if not keyword.strip():
        conn.close()
        await update.message.reply_text(
            "아, 저기... 키워드를 알려주셔야 해요...!\n"
            "사용법: /watch 원신 또는 /watch 하츠네 미쿠",
            parse_mode=ParseMode.HTML,
        )
        return

    keyword = keyword.strip()
    if len(keyword) < 2:
        conn.close()
        await update.message.reply_text(
            "아, 저기... 2글자 이상으로 입력해주시면...!",
            parse_mode=ParseMode.HTML,
        )
        return

    result = _add_watch(conn, update.effective_chat.id, keyword)
    count = _get_watch_count(conn, update.effective_chat.id)
    conn.close()

    if result == "added":
        await update.message.reply_text(
            f'저, 저기... "{_escape_html(keyword)}" 추가했어요...! '
            f"이제 관련 상품이 나오면 바로 알려드릴게요...!\n"
            f"📋 현재 관심 목록: {count}/10개",
            parse_mode=ParseMode.HTML,
        )
    elif result == "exists":
        await update.message.reply_text(
            "아, 그건 이미 목록에 있어요...! 걱정 마세요, 잘 지켜보고 있을게요...!",
            parse_mode=ParseMode.HTML,
        )
    elif result == "limit":
        await update.message.reply_text(
            "죄, 죄송해요... 관심 목록이 가득 찼어요... (10/10개)\n"
            "/mywatches에서 안 보는 키워드를 지워주시면...!",
            parse_mode=ParseMode.HTML,
        )


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unwatch <keyword> — remove a watch keyword."""
    conn = get_connection()
    _get_or_create_user(conn, update.effective_chat.id, update.effective_user.username)

    keyword = " ".join(context.args) if context.args else ""
    if not keyword.strip():
        conn.close()
        await update.message.reply_text(
            "아, 저기... 삭제할 키워드를 알려주셔야 해요...!\n"
            "사용법: /unwatch 원신",
            parse_mode=ParseMode.HTML,
        )
        return

    removed = _remove_watch_by_keyword(conn, update.effective_chat.id, keyword.strip())
    count = _get_watch_count(conn, update.effective_chat.id)
    conn.close()

    if removed:
        await update.message.reply_text(
            f'"{_escape_html(keyword.strip())}" 삭제했어요...! 📋 남은 관심 목록: {count}/10개',
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            "어, 그 키워드는 목록에 없는 것 같은데... /mywatches에서 확인해보실래요...?",
            parse_mode=ParseMode.HTML,
        )


async def cmd_mywatches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mywatches — show current watches with remove buttons."""
    conn = get_connection()
    _get_or_create_user(conn, update.effective_chat.id, update.effective_user.username)
    watches = _get_watches(conn, update.effective_chat.id)
    conn.close()

    if not watches:
        await update.message.reply_text(
            "아, 아직 관심 목록이 비어있어요...\n"
            "/watch 원신 이렇게 추가해주시면... 관련 상품만 알려드릴게요...!\n"
            "관심 목록이 없으면 모든 알림을 보내드려요...!",
            parse_mode=ParseMode.HTML,
        )
        return

    buttons = []
    for w in watches:
        buttons.append([InlineKeyboardButton(
            f"❌ {w['keyword']}",
            callback_data=f"unwatch_{w['id']}",
        )])
    keyboard = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        f"📋 저, 저한테 맡겨주신 관심 목록이에요...! ({len(watches)}/10개)\n"
        "버튼을 누르면 삭제할 수 있어요...",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def callback_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button press to remove a watch."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data or not data.startswith("unwatch_"):
        return

    try:
        watch_id = int(data.replace("unwatch_", ""))
    except ValueError:
        return

    conn = get_connection()
    _remove_watch(conn, update.effective_chat.id, watch_id)
    watches = _get_watches(conn, update.effective_chat.id)
    conn.close()

    if not watches:
        await query.edit_message_text(
            "📋 관심 목록이 비었어요...!\n"
            "이제 모든 알림을 보내드릴게요...!",
            parse_mode=ParseMode.HTML,
        )
        return

    buttons = []
    for w in watches:
        buttons.append([InlineKeyboardButton(
            f"❌ {w['keyword']}",
            callback_data=f"unwatch_{w['id']}",
        )])
    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(
        f"📋 저, 저한테 맡겨주신 관심 목록이에요...! ({len(watches)}/10개)\n"
        "버튼을 누르면 삭제할 수 있어요...",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


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

    # Preload all user watches {chat_id: [keyword, ...]}
    watch_rows = conn.execute(
        "SELECT chat_id, keyword FROM user_watches"
    ).fetchall()
    user_watches: dict[int, list[str]] = {}
    for wr in watch_rows:
        user_watches.setdefault(wr["chat_id"], []).append(wr["keyword"])

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

            # Load product structured fields for watch matching
            prod_row = conn.execute(
                "SELECT series, character_name FROM products WHERE id = ?",
                (alert["product_db_id"],),
            ).fetchone()
            p_series = prod_row["series"] if prod_row else None
            p_char = prod_row["character_name"] if prod_row else None
            p_name = alert["product_name"]

            # Group users by matched watch keyword (None = no watches)
            match_groups: dict[str | None, list[int]] = {}
            for chat_id in target_users:
                watches = user_watches.get(chat_id, [])
                if not watches:
                    match_groups.setdefault(None, []).append(chat_id)
                else:
                    matched = None
                    for kw in watches:
                        if _matches_watch(kw, p_series, p_char, p_name):
                            matched = kw
                            break
                    if matched is not None:
                        match_groups.setdefault(matched, []).append(chat_id)
                    # else: user has watches but none matched — skip

            if not match_groups:
                conn.execute(
                    "UPDATE pending_alerts SET sent_at = ? WHERE id = ?",
                    (now_kst(), alert["id"]),
                )
                continue

            cross_prices, suspicious_match = _get_cross_site_prices(conn, alert["product_db_id"])
            keyboard = _build_alert_keyboard(alert)

            for matched_kw, group_users in match_groups.items():
                caption = _format_alert_caption(alert, cross_prices, suspicious_match, matched_kw)

                for chat_id in group_users:
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

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start", "봇 시작 및 등록"),
            BotCommand("settings", "알림 설정 변경"),
            BotCommand("watch", "관심 키워드 추가"),
            BotCommand("unwatch", "관심 키워드 삭제"),
            BotCommand("mywatches", "관심 목록 보기"),
            BotCommand("status", "봇 현황 확인"),
            BotCommand("help", "도움말 보기"),
        ])

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    # Watch command handlers
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("mywatches", cmd_mywatches))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(callback_toggle, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(callback_unwatch, pattern="^unwatch_"))

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
