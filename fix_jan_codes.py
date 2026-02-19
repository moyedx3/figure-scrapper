#!/usr/bin/env python3
"""One-time script to fix duplicate JAN codes caused by CDN caching.

1. Finds same-site duplicate JAN codes
2. Clears all duplicates (sets jan_code = NULL)
3. Re-fetches correct JAN codes from product detail pages with longer delays
4. Re-runs matching

Run on VPS:
    source .venv/bin/activate
    python fix_jan_codes.py
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

    # Step 1: Find same-site duplicate JAN codes
    dupes = conn.execute("""
        SELECT site, jan_code, GROUP_CONCAT(product_id) as pids, COUNT(*) as cnt
        FROM products
        WHERE jan_code IS NOT NULL AND jan_code != ''
        GROUP BY site, jan_code
        HAVING cnt > 1
    """).fetchall()

    if not dupes:
        print("No duplicate JAN codes found. Nothing to fix.")
        conn.close()
        return

    # Collect all affected products
    affected = []
    for row in dupes:
        site = row["site"]
        jan = row["jan_code"]
        pids = row["pids"].split(",")
        print(f"  [{site}] JAN {jan} -> {len(pids)} products: {', '.join(pids)}")
        for pid in pids:
            affected.append((site, pid))

    print(f"\nFound {len(dupes)} duplicate JAN groups, {len(affected)} products affected.")

    # Step 2: Clear all duplicate JAN codes
    for site, pid in affected:
        conn.execute(
            "UPDATE products SET jan_code = NULL WHERE site = ? AND product_id = ?",
            (site, pid),
        )
    conn.commit()
    print(f"Cleared JAN codes for {len(affected)} products.")

    # Step 3: Re-fetch correct JAN codes with longer delays
    print(f"\nRe-fetching JAN codes from product pages (2s delay between requests)...")
    fixed = 0
    failed = 0
    for i, (site, pid) in enumerate(affected, 1):
        row = conn.execute(
            "SELECT url FROM products WHERE site = ? AND product_id = ?",
            (site, pid),
        ).fetchone()

        url = row["url"] if row else None
        if not url or site == "comicsart":
            print(f"  [{i}/{len(affected)}] [{site}] {pid} — skipped (no url)")
            continue

        time.sleep(2.0)  # longer delay to avoid CDN caching

        specs = fetch_product_detail(url, site)
        if specs and specs.get("jan_code"):
            jan = specs["jan_code"].strip()
            if len(jan) >= 8:
                conn.execute(
                    "UPDATE products SET jan_code = ? WHERE site = ? AND product_id = ?",
                    (jan, site, pid),
                )
                fixed += 1
                print(f"  [{i}/{len(affected)}] [{site}] {pid} -> JAN {jan}")
            else:
                print(f"  [{i}/{len(affected)}] [{site}] {pid} — invalid JAN: {jan}")
                failed += 1
        else:
            print(f"  [{i}/{len(affected)}] [{site}] {pid} — no JAN found on page")
            failed += 1

    conn.commit()
    print(f"\nDone: {fixed} fixed, {failed} no JAN found.")

    # Step 4: Verify no duplicates remain
    remaining = conn.execute("""
        SELECT site, jan_code, COUNT(*) as cnt
        FROM products
        WHERE jan_code IS NOT NULL AND jan_code != ''
        GROUP BY site, jan_code
        HAVING cnt > 1
    """).fetchall()

    if remaining:
        print(f"\nWARNING: {len(remaining)} duplicate groups still remain!")
        for row in remaining:
            print(f"  [{row['site']}] JAN {row['jan_code']} x{row['cnt']}")
    else:
        print("\nAll duplicate JAN codes resolved.")

    conn.close()

    # Step 5: Re-run matching
    print("\nRe-running product matching...")
    from analytics.matching import run_matching
    n_groups = run_matching()
    print(f"Matching complete: {n_groups} groups.")


if __name__ == "__main__":
    main()
