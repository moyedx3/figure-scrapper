"""Cached SQL queries for the admin analytics dashboard."""

import os
import sqlite3

import pandas as pd
import streamlit as st

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    """Read-only connection to prevent accidental writes."""
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


# --- User Overview ---


@st.cache_data(ttl=60)
def get_user_counts() -> dict:
    """Total, active, inactive user counts."""
    conn = get_conn()
    row = conn.execute(
        """SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as inactive
        FROM telegram_users"""
    ).fetchone()
    conn.close()
    return {"total": row[0], "active": row[1] or 0, "inactive": row[2] or 0}


@st.cache_data(ttl=60)
def get_user_growth() -> pd.DataFrame:
    """Daily new signups with cumulative total."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT DATE(created_at) as date,
                  COUNT(*) as new_users
           FROM telegram_users
           WHERE created_at IS NOT NULL
           GROUP BY DATE(created_at)
           ORDER BY date""",
        conn,
    )
    conn.close()
    if not df.empty:
        df["cumulative"] = df["new_users"].cumsum()
    return df


@st.cache_data(ttl=60)
def get_recent_signups(limit: int = 20) -> pd.DataFrame:
    """Most recent user signups."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT chat_id, username, is_active,
                  alert_new, alert_restock, alert_price, alert_soldout,
                  created_at, updated_at
           FROM telegram_users
           ORDER BY created_at DESC
           LIMIT ?""",
        conn,
        params=(limit,),
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_churned_users() -> pd.DataFrame:
    """Users who blocked the bot (is_active=0)."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT chat_id, username, created_at, updated_at as churned_at
           FROM telegram_users
           WHERE is_active = 0
           ORDER BY updated_at DESC""",
        conn,
    )
    conn.close()
    return df


# --- Alert Preferences & Watches ---


@st.cache_data(ttl=60)
def get_alert_preference_counts() -> pd.DataFrame:
    """Count of active users with each alert type enabled."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT
            SUM(alert_new) as "신상품",
            SUM(alert_restock) as "재입고",
            SUM(alert_price) as "가격변동",
            SUM(alert_soldout) as "품절"
        FROM telegram_users
        WHERE is_active = 1""",
        conn,
    )
    conn.close()
    if not df.empty:
        df = df.melt(var_name="알림유형", value_name="사용자수")
    return df


@st.cache_data(ttl=60)
def get_watch_adoption_rate() -> dict:
    """Percentage of active users with at least one watch keyword."""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM telegram_users WHERE is_active = 1"
    ).fetchone()[0]
    with_watches = conn.execute(
        """SELECT COUNT(DISTINCT uw.chat_id)
           FROM user_watches uw
           JOIN telegram_users tu ON uw.chat_id = tu.chat_id
           WHERE tu.is_active = 1"""
    ).fetchone()[0]
    total_watches = conn.execute(
        "SELECT COUNT(*) FROM user_watches"
    ).fetchone()[0]
    conn.close()
    pct = (with_watches / total * 100) if total > 0 else 0
    return {
        "total": total,
        "with_watches": with_watches,
        "total_watches": total_watches,
        "pct": round(pct, 1),
    }


@st.cache_data(ttl=60)
def get_top_watch_keywords(limit: int = 30) -> pd.DataFrame:
    """Most popular watch keywords across all active users."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT uw.keyword, COUNT(*) as user_count
           FROM user_watches uw
           JOIN telegram_users tu ON uw.chat_id = tu.chat_id
           WHERE tu.is_active = 1
           GROUP BY uw.keyword
           ORDER BY user_count DESC, uw.keyword
           LIMIT ?""",
        conn,
        params=(limit,),
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_watches_per_user_distribution() -> pd.DataFrame:
    """Distribution of how many watches each active user has."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT watch_count, COUNT(*) as user_count
           FROM (
               SELECT tu.chat_id,
                      COUNT(uw.keyword) as watch_count
               FROM telegram_users tu
               LEFT JOIN user_watches uw ON tu.chat_id = uw.chat_id
               WHERE tu.is_active = 1
               GROUP BY tu.chat_id
           )
           GROUP BY watch_count
           ORDER BY watch_count""",
        conn,
    )
    conn.close()
    return df


# --- Message Delivery ---


@st.cache_data(ttl=60)
def get_alert_volume_by_type() -> pd.DataFrame:
    """Total sent alerts grouped by change_type."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT change_type, COUNT(*) as count
           FROM pending_alerts
           WHERE sent_at IS NOT NULL
           GROUP BY change_type
           ORDER BY count DESC""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_alert_volume_over_time(days: int = 30) -> pd.DataFrame:
    """Daily alert counts by type for the last N days."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT DATE(created_at) as date,
                  change_type,
                  COUNT(*) as count
           FROM pending_alerts
           WHERE created_at >= datetime('now', '+9 hours', ?)
           GROUP BY date, change_type
           ORDER BY date""",
        conn,
        params=(f"-{days} days",),
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_delivery_latency() -> pd.DataFrame:
    """Delivery latency in seconds for sent alerts (excluding stale summaries > 1h)."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT
            change_type,
            (julianday(sent_at) - julianday(created_at)) * 86400 as latency_seconds
           FROM pending_alerts
           WHERE sent_at IS NOT NULL
             AND created_at IS NOT NULL
             AND sent_at > created_at
             AND (julianday(sent_at) - julianday(created_at)) * 86400 < 3600""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_pending_queue_depth() -> dict:
    """Number of unsent alerts in the queue."""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM pending_alerts WHERE sent_at IS NULL"
    ).fetchone()[0]
    oldest = conn.execute(
        "SELECT MIN(created_at) FROM pending_alerts WHERE sent_at IS NULL"
    ).fetchone()[0]
    conn.close()
    return {"pending": total, "oldest": oldest}


@st.cache_data(ttl=60)
def get_alert_volume_by_site() -> pd.DataFrame:
    """Sent alert counts grouped by site."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, COUNT(*) as count
           FROM pending_alerts
           WHERE sent_at IS NOT NULL
           GROUP BY site
           ORDER BY count DESC""",
        conn,
    )
    conn.close()
    return df


# --- System Health ---


@st.cache_data(ttl=60)
def get_last_scrape_per_site() -> pd.DataFrame:
    """Most recent scrape time and product count per site."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site,
                  MAX(last_checked_at) as last_scrape,
                  COUNT(*) as product_count
           FROM products
           GROUP BY site
           ORDER BY last_scrape DESC""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_recent_status_changes(limit: int = 50) -> pd.DataFrame:
    """Most recent status changes across all products."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT sc.change_type, sc.old_value, sc.new_value, sc.changed_at,
                  p.site, p.name
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           ORDER BY sc.changed_at DESC
           LIMIT ?""",
        conn,
        params=(limit,),
    )
    conn.close()
    return df


@st.cache_data(ttl=60)
def get_db_table_sizes() -> pd.DataFrame:
    """Row counts for all key tables."""
    conn = get_conn()
    tables = [
        "products", "status_changes", "pending_alerts",
        "telegram_users", "user_watches", "price_history",
        "product_matches",
    ]
    rows = []
    for table in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            rows.append({"table": table, "rows": count})
        except Exception:
            rows.append({"table": table, "rows": 0})
    conn.close()
    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def get_db_file_size_mb() -> float:
    """SQLite database file size in MB."""
    try:
        size = os.path.getsize(DB_PATH)
        return round(size / (1024 * 1024), 2)
    except OSError:
        return 0.0


@st.cache_data(ttl=60)
def get_scrape_activity_heatmap(days: int = 14) -> pd.DataFrame:
    """Hourly product update counts over the last N days."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT DATE(last_checked_at) as date,
                  CAST(strftime('%H', last_checked_at) AS INTEGER) as hour,
                  COUNT(*) as count
           FROM products
           WHERE last_checked_at >= datetime('now', '+9 hours', ?)
           GROUP BY date, hour
           ORDER BY date, hour""",
        conn,
        params=(f"-{days} days",),
    )
    conn.close()
    return df
