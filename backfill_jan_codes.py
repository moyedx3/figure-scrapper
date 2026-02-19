#!/usr/bin/env python3
"""Backfill missing JAN codes by fetching product detail pages.

Fetches JAN codes for products that have jan_code = NULL,
with 2s delays between requests to avoid CDN caching.

Run on VPS:
    source .venv/bin/activate
    python backfill_jan_codes.py
"""

import sqlite3
import time

from dotenv import load_dotenv
load_dotenv()

from config import DB_PATH
from extraction.page_fetcher import fetch_product_detail


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all products missing JAN codes (excluding comicsart which has no detail page JAN)
    rows = conn.execute("""
        SELECT id, site, product_id, name, url
        FROM products
        WHERE (jan_code IS NULL OR jan_code = '')
          AND site != 'comicsart'
          AND url IS NOT NULL AND url != ''
        ORDER BY site, CAST(product_id AS INTEGER)
    """).fetchall()

    total = len(rows)
    print(f"Found {total} products missing JAN codes (excluding comicsart).\n")

    if total == 0:
        conn.close()
        return

    fixed = 0
    skipped = 0
    by_site: dict[str, int] = {}

    for i, row in enumerate(rows, 1):
        site = row["site"]
        pid = row["product_id"]
        url = row["url"]

        time.sleep(2.0)

        specs = fetch_product_detail(url, site)
        if specs and specs.get("jan_code"):
            jan = specs["jan_code"].strip()
            if len(jan) >= 8:
                conn.execute(
                    "UPDATE products SET jan_code = ? WHERE id = ?",
                    (jan, row["id"]),
                )
                fixed += 1
                by_site[site] = by_site.get(site, 0) + 1
            else:
                skipped += 1
        else:
            skipped += 1

        if i % 25 == 0:
            conn.commit()
            print(f"  Progress: {i}/{total} ({fixed} fixed, {skipped} no JAN on page)")

    conn.commit()

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
            for p in pids_rows[1:]:  # keep first, clear rest
                conn.execute(
                    "UPDATE products SET jan_code = NULL WHERE site = ? AND product_id = ?",
                    (d["site"], p["product_id"]),
                )
                cleared += 1
        conn.commit()
        print(f"  Cleared {cleared} duplicate JANs.")

    conn.close()

    print(f"\nDone: {fixed} JAN codes fetched, {skipped} pages had no JAN.")
    for site, cnt in sorted(by_site.items()):
        print(f"  {site}: {cnt}")

    # Re-run matching
    print("\nRe-running product matching...")
    from analytics.matching import run_matching
    n_groups = run_matching()
    print(f"Matching complete: {n_groups} groups.")


if __name__ == "__main__":
    main()
