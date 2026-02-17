"""SQLite database operations for figure scraper."""

import sqlite3
from datetime import datetime
from typing import Optional

from config import DB_PATH
from models import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    price INTEGER,
    status TEXT,
    category TEXT,
    figure_type TEXT,
    manufacturer TEXT,
    jan_code TEXT,
    release_date TEXT,
    order_deadline TEXT,
    size TEXT,
    material TEXT,
    has_bonus BOOLEAN DEFAULT 0,
    image_url TEXT,
    review_count INTEGER DEFAULT 0,
    url TEXT,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_checked_at DATETIME,
    soldout_at DATETIME,
    UNIQUE(site, product_id)
);

CREATE TABLE IF NOT EXISTS status_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    change_type TEXT,
    old_value TEXT,
    new_value TEXT,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_key TEXT NOT NULL,
    product_id INTEGER REFERENCES products(id),
    confidence REAL DEFAULT 1.0,
    UNIQUE(product_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    price INTEGER,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    notify_restock BOOLEAN DEFAULT 1,
    notify_price_drop BOOLEAN DEFAULT 0,
    target_price INTEGER,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()


def upsert_product(conn: sqlite3.Connection, product: Product) -> int:
    """Insert or update a product. Returns the database row id."""
    now = datetime.now().isoformat()
    row = conn.execute(
        "SELECT id, price, status FROM products WHERE site = ? AND product_id = ?",
        (product.site, product.product_id),
    ).fetchone()

    if row:
        conn.execute(
            """UPDATE products SET
                name = ?, price = ?, status = ?, category = ?, figure_type = ?,
                manufacturer = ?, jan_code = ?, release_date = ?, order_deadline = ?,
                size = ?, material = ?, has_bonus = ?, image_url = ?,
                review_count = ?, url = ?, last_checked_at = ?
            WHERE id = ?""",
            (
                product.name, product.price, product.status, product.category,
                product.figure_type, product.manufacturer, product.jan_code,
                product.release_date, product.order_deadline, product.size,
                product.material, product.has_bonus, product.image_url,
                product.review_count, product.url, now, row["id"],
            ),
        )
        return row["id"]
    else:
        cursor = conn.execute(
            """INSERT INTO products
                (site, product_id, name, price, status, category, figure_type,
                 manufacturer, jan_code, release_date, order_deadline, size,
                 material, has_bonus, image_url, review_count, url,
                 first_seen_at, last_checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product.site, product.product_id, product.name, product.price,
                product.status, product.category, product.figure_type,
                product.manufacturer, product.jan_code, product.release_date,
                product.order_deadline, product.size, product.material,
                product.has_bonus, product.image_url, product.review_count,
                product.url, now, now,
            ),
        )
        return cursor.lastrowid


def get_product(conn: sqlite3.Connection, site: str, product_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM products WHERE site = ? AND product_id = ?",
        (site, product_id),
    ).fetchone()
    return dict(row) if row else None


def get_products_by_site(conn: sqlite3.Connection, site: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM products WHERE site = ?", (site,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_known_product_ids(conn: sqlite3.Connection, site: str) -> set[str]:
    rows = conn.execute(
        "SELECT product_id FROM products WHERE site = ?", (site,)
    ).fetchall()
    return {r["product_id"] for r in rows}


def get_soldout_products(conn: sqlite3.Connection, site: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM products WHERE site = ? AND status = 'soldout'", (site,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_product_status(
    conn: sqlite3.Connection, db_id: int, new_status: str
):
    now = datetime.now().isoformat()
    updates = {"status": new_status, "last_checked_at": now}
    if new_status == "soldout":
        updates["soldout_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE products SET {set_clause} WHERE id = ?",
        (*updates.values(), db_id),
    )


def log_status_change(
    conn: sqlite3.Connection, product_db_id: int,
    change_type: str, old_value: str, new_value: str,
):
    conn.execute(
        "INSERT INTO status_changes (product_id, change_type, old_value, new_value) VALUES (?, ?, ?, ?)",
        (product_db_id, change_type, old_value, new_value),
    )


def log_price(conn: sqlite3.Connection, product_db_id: int, price: int):
    conn.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_db_id, price),
    )
