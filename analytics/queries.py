"""Cached SQL queries for the analytics dashboard."""

import sqlite3

import pandas as pd
import streamlit as st

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# --- Overview ---


@st.cache_data(ttl=300)
def get_product_counts() -> pd.DataFrame:
    """Product count per site."""
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT site, COUNT(*) as count FROM products GROUP BY site ORDER BY count DESC",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_status_breakdown() -> pd.DataFrame:
    """Product count per status."""
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT status, COUNT(*) as count FROM products GROUP BY status",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_total_products() -> int:
    conn = get_conn()
    result = pd.read_sql_query("SELECT COUNT(*) as total FROM products", conn)
    conn.close()
    return int(result["total"].iloc[0])


@st.cache_data(ttl=300)
def get_recent_new_products(days: int = 7) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, product_id, name, price, status, category,
                  manufacturer, image_url, url, first_seen_at
           FROM products
           WHERE first_seen_at >= datetime('now', ?)
           ORDER BY first_seen_at DESC""",
        conn,
        params=(f"-{days} days",),
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_recent_changes(days: int = 7) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT sc.change_type, sc.old_value, sc.new_value, sc.changed_at,
                  p.site, p.name, p.price, p.url
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           WHERE sc.changed_at >= datetime('now', ?)
           ORDER BY sc.changed_at DESC""",
        conn,
        params=(f"-{days} days",),
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_count_by_change_type(days: int = 1) -> dict:
    """Count of new/restock/soldout/price changes in the last N days."""
    conn = get_conn()
    new_count = pd.read_sql_query(
        "SELECT COUNT(*) as c FROM products WHERE first_seen_at >= datetime('now', ?)",
        conn,
        params=(f"-{days} days",),
    )["c"].iloc[0]

    changes = pd.read_sql_query(
        """SELECT change_type, new_value, COUNT(*) as c
           FROM status_changes
           WHERE changed_at >= datetime('now', ?)
           GROUP BY change_type, new_value""",
        conn,
        params=(f"-{days} days",),
    )
    conn.close()

    restocks = 0
    soldouts = 0
    price_changes = 0
    for _, row in changes.iterrows():
        if row["change_type"] == "status" and row["new_value"] == "available":
            restocks = int(row["c"])
        elif row["change_type"] == "status" and row["new_value"] == "soldout":
            soldouts = int(row["c"])
        elif row["change_type"] == "price":
            price_changes = int(row["c"])

    return {
        "new": int(new_count),
        "restocks": restocks,
        "soldouts": soldouts,
        "price_changes": price_changes,
    }


@st.cache_data(ttl=300)
def get_price_distribution() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT site, price FROM products WHERE price IS NOT NULL AND price > 0",
        conn,
    )
    conn.close()
    return df


# --- All products (for filtering) ---


@st.cache_data(ttl=300)
def get_all_products() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, product_id, name, price, status, category,
                  figure_type, manufacturer, jan_code, release_date,
                  order_deadline, has_bonus, image_url, url,
                  first_seen_at, last_checked_at, soldout_at
           FROM products
           ORDER BY first_seen_at DESC""",
        conn,
    )
    conn.close()
    return df


# --- Soldout Velocity ---


@st.cache_data(ttl=300)
def get_soldout_velocity() -> pd.DataFrame:
    """Products with soldout_at — compute time from first_seen to soldout."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, name, price, manufacturer, category, figure_type,
                  first_seen_at, soldout_at,
                  (julianday(soldout_at) - julianday(first_seen_at)) * 24 as hours_to_soldout
           FROM products
           WHERE soldout_at IS NOT NULL AND first_seen_at IS NOT NULL
             AND soldout_at > first_seen_at""",
        conn,
    )
    conn.close()
    return df


# --- Restock ---


@st.cache_data(ttl=300)
def get_restock_events() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT sc.changed_at, sc.old_value, sc.new_value,
                  p.site, p.name, p.price, p.manufacturer, p.url
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           WHERE sc.change_type = 'status'
             AND sc.old_value = 'soldout'
             AND sc.new_value = 'available'
           ORDER BY sc.changed_at DESC""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_restock_with_duration() -> pd.DataFrame:
    """Restock events with soldout duration (hours between soldout and restock)."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT sc.changed_at as restock_at,
                  p.site, p.name, p.price, p.manufacturer, p.url,
                  p.soldout_at,
                  CASE WHEN p.soldout_at IS NOT NULL
                       THEN (julianday(sc.changed_at) - julianday(p.soldout_at)) * 24
                       ELSE NULL END as soldout_hours
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           WHERE sc.change_type = 'status'
             AND sc.old_value = 'soldout'
             AND sc.new_value = 'available'
           ORDER BY sc.changed_at DESC""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_monthly_restock_counts() -> pd.DataFrame:
    """Monthly restock count by site."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT p.site,
                  strftime('%Y-%m', sc.changed_at) as month,
                  COUNT(*) as count
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           WHERE sc.change_type = 'status'
             AND sc.old_value = 'soldout'
             AND sc.new_value = 'available'
           GROUP BY p.site, month
           ORDER BY month""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_price_change_on_restock() -> pd.DataFrame:
    """Price changes that occurred near restock events."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT p.site, p.name, p.manufacturer,
                  CAST(sc.old_value AS INTEGER) as old_price,
                  CAST(sc.new_value AS INTEGER) as new_price,
                  sc.changed_at
           FROM status_changes sc
           JOIN products p ON sc.product_id = p.id
           WHERE sc.change_type = 'price'
             AND sc.old_value != sc.new_value
           ORDER BY sc.changed_at DESC""",
        conn,
    )
    conn.close()
    return df


# --- Site Coverage ---


@st.cache_data(ttl=300)
def get_products_by_category_site() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, category, COUNT(*) as count
           FROM products
           WHERE category IS NOT NULL AND category != ''
           GROUP BY site, category""",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_status_by_site() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, status, COUNT(*) as count
           FROM products
           GROUP BY site, status""",
        conn,
    )
    conn.close()
    return df


# --- Reservation Accuracy ---


@st.cache_data(ttl=300)
def get_products_with_release_date() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT site, name, price, manufacturer, release_date, status,
                  first_seen_at, soldout_at
           FROM products
           WHERE release_date IS NOT NULL AND release_date != ''""",
        conn,
    )
    conn.close()
    return df


# --- Price History ---


@st.cache_data(ttl=300)
def get_price_history(product_db_id: int) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT price, recorded_at
           FROM price_history
           WHERE product_id = ?
           ORDER BY recorded_at""",
        conn,
        params=(product_db_id,),
    )
    conn.close()
    return df
