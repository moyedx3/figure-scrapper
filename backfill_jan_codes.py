#!/usr/bin/env python3
"""Backfill missing JAN codes by fetching product detail pages.

Fetches in parallel across sites (CDN caching is per-site),
with 2s delays within each site to avoid stale cached responses.

Uses fetch_product_detail() from page_fetcher.py — the single source
of truth for detail page parsing. Do NOT duplicate parsing logic here.

Run on VPS:
    source .venv/bin/activate
    python backfill_jan_codes.py
"""

import sqlite3
import threading
import time
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup

from config import DB_PATH, REQUEST_TIMEOUT, USER_AGENT
from extraction.page_fetcher import fetch_product_detail, _LABEL_MAP

_SITE_DELAY = 2.0


def _process_site(site: str, products: list[dict], results: list, lock: threading.Lock):
    """Process all products for a single site with delays."""
    fixed = 0
    skipped = 0
    for i, row in enumerate(products, 1):
        if i > 1:
            time.sleep(_SITE_DELAY)

        # Reuse the main parsing function — single source of truth
        specs = fetch_product_detail(row["url"], site)
        jan = None
        if specs and specs.get("jan_code"):
            jan = specs["jan_code"].strip()
            if len(jan) < 8:
                jan = None

        if jan:
            with lock:
                results.append((jan, row["id"]))
            fixed += 1
        else:
            skipped += 1

        if i % 25 == 0:
            print(f"  [{site}] {i}/{len(products)} ({fixed} fixed)")

    print(f"  [{site}] done: {fixed} fixed, {skipped} no JAN")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, site, product_id, name, url
        FROM products
        WHERE (jan_code IS NULL OR jan_code = '')
          AND url IS NOT NULL AND url != ''
        ORDER BY site, CAST(product_id AS INTEGER)
    """).fetchall()

    total = len(rows)
    print(f"Found {total} products missing JAN codes.\n")

    if total == 0:
        conn.close()
        return

    # Group by site
    by_site: dict[str, list] = defaultdict(list)
    for row in rows:
        by_site[row["site"]].append(dict(row))

    for site, products in by_site.items():
        print(f"  {site}: {len(products)} products")
    print()

    # Fetch in parallel — one thread per site
    results: list[tuple[str, int]] = []  # (jan_code, product_id)
    lock = threading.Lock()
    threads = []

    for site, products in by_site.items():
        t = threading.Thread(target=_process_site, args=(site, products, results, lock))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    # Write all results to DB
    for jan, db_id in results:
        conn.execute("UPDATE products SET jan_code = ? WHERE id = ?", (jan, db_id))
    conn.commit()

    print(f"\nTotal: {len(results)} JAN codes fetched.")

    # Final duplicate check
    dupes = conn.execute("""
        SELECT site, jan_code, COUNT(*) as cnt
        FROM products
        WHERE jan_code IS NOT NULL AND jan_code != ''
        GROUP BY site, jan_code
        HAVING cnt > 1
    """).fetchall()

    if dupes:
        print(f"\nWARNING: {len(dupes)} same-site duplicate JANs found after backfill!")
        print("Cleaning up...")
        cleared = 0
        for d in dupes:
            pids_rows = conn.execute(
                "SELECT product_id FROM products WHERE site = ? AND jan_code = ? ORDER BY CAST(product_id AS INTEGER)",
                (d["site"], d["jan_code"]),
            ).fetchall()
            for p in pids_rows[1:]:
                conn.execute(
                    "UPDATE products SET jan_code = NULL WHERE site = ? AND product_id = ?",
                    (d["site"], p["product_id"]),
                )
                cleared += 1
        conn.commit()
        print(f"  Cleared {cleared} duplicate JANs.")
    else:
        print("No same-site duplicate JANs. Data is clean.")

    conn.close()

    # Re-run matching
    print("\nRe-running product matching...")
    from analytics.matching import run_matching
    n_groups = run_matching()
    print(f"Matching complete: {n_groups} groups.")


if __name__ == "__main__":
    main()
