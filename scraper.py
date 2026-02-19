#!/usr/bin/env python3
"""Main entry point for figure scraper."""

import argparse
import logging
import sys

from dotenv import load_dotenv
load_dotenv()

from config import SITES
from db import get_connection, init_db
from detector import ChangeDetector
from parsers import PARSERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def scrape_site(site_name: str) -> list:
    """Scrape a single site and return detected changes."""
    if site_name not in SITES:
        logger.error(f"Unknown site: {site_name}")
        return []

    site_config = SITES[site_name]
    parser_class = PARSERS.get(site_name)
    if not parser_class:
        logger.error(f"No parser for site: {site_name}")
        return []

    parser = parser_class()
    conn = get_connection()
    detector = ChangeDetector(conn)
    all_changes = []

    logger.info(f"--- Scraping {site_config['display_name']} ({site_name}) ---")

    for cat_name, cat_path in site_config["categories"].items():
        logger.info(f"  Category: {cat_name}")
        try:
            products = parser.get_all_pages(cat_path, category=cat_name)
            logger.info(f"  Found {len(products)} products")
            changes = detector.process_products(site_name, products)
            all_changes.extend(changes)
        except Exception as e:
            logger.error(f"  Failed to scrape {cat_name}: {e}")

    conn.close()

    # Print change summary
    for change in all_changes:
        if change.change_type == "new":
            logger.info(
                f"  NEW: {change.product.name} "
                f"({change.product.price or '?'}원) [{change.product.status}]"
            )
        elif change.change_type == "restock":
            logger.info(f"  RESTOCK: {change.product.name}")
        elif change.change_type == "price":
            logger.info(
                f"  PRICE: {change.product.name} "
                f"{change.old_value}원 → {change.new_value}원"
            )
        elif change.change_type == "soldout":
            logger.info(f"  SOLDOUT: {change.product.name}")

    return all_changes


def scrape_all() -> list:
    """Scrape all configured sites."""
    all_changes = []
    for site_name in SITES:
        try:
            changes = scrape_site(site_name)
            all_changes.extend(changes)
        except Exception as e:
            logger.error(f"Failed to scrape {site_name}: {e}")
    return all_changes


def extract_existing(site: str | None = None, force_llm: bool = False, re_extract: bool = False):
    """Backfill extraction for products that haven't been extracted yet.

    If re_extract=True, re-processes ALL products (even already extracted ones).
    """
    from db import get_unextracted_products, save_extraction
    from extraction.extractor import extract_product_attributes

    conn = get_connection()
    if re_extract:
        query = "SELECT * FROM products"
        params: list = []
        if site:
            query += " WHERE site = ?"
            params.append(site)
        products = [dict(r) for r in conn.execute(query, params).fetchall()]
    else:
        products = get_unextracted_products(conn, site)
    total = len(products)
    mode = "re-extract" if re_extract else ("force-LLM" if force_llm else "hybrid")
    logger.info(f"Extracting {total} products ({mode})" + (f" (site={site})" if site else ""))

    success = 0
    method_counts: dict[str, int] = {}
    for i, row in enumerate(products, 1):
        try:
            attrs, method, confidence, page_specs = extract_product_attributes(
                name=row["name"],
                site=row["site"],
                category=row.get("category", ""),
                manufacturer=row.get("manufacturer"),
                url=row.get("url"),
                force_llm=force_llm or re_extract,
            )
            save_extraction(conn, row["id"], attrs.model_dump(), method, confidence)
            # Save JAN code from page fetch if available
            if page_specs and page_specs.get("jan_code"):
                jan = page_specs["jan_code"].strip()
                if len(jan) >= 8:
                    conn.execute(
                        "UPDATE products SET jan_code = ? WHERE id = ?",
                        (jan, row["id"]),
                    )
            success += 1
            method_counts[method] = method_counts.get(method, 0) + 1
            if i % 50 == 0:
                conn.commit()
                methods_str = ", ".join(f"{k}={v}" for k, v in sorted(method_counts.items()))
                logger.info(f"  Progress: {i}/{total} ({methods_str})")
        except Exception as e:
            logger.warning(f"  Failed to extract [{row['site']}] {row['name']}: {e}")

    conn.commit()
    conn.close()
    methods_str = ", ".join(f"{k}={v}" for k, v in sorted(method_counts.items()))
    logger.info(f"=== Extraction done: {success}/{total} products ({methods_str}) ===")


def _post_scrape_enrich(changes: list):
    """After scraping, fetch JAN codes for new products that didn't get one
    during extraction, then re-run matching."""
    import time
    from extraction.page_fetcher import fetch_product_detail

    new_changes = [c for c in changes if c.change_type == "new"]
    if not new_changes:
        return

    # Only fetch JAN for products that didn't already get one in _extract_and_save
    conn = get_connection()
    jan_found = 0
    for change in new_changes:
        p = change.product
        if not p.url or p.site == "comicsart":
            continue

        # Check if JAN was already saved during extraction
        row = conn.execute(
            "SELECT jan_code FROM products WHERE site = ? AND product_id = ?",
            (p.site, p.product_id),
        ).fetchone()
        if row and row["jan_code"]:
            continue

        # Longer delay to avoid CDN caching stale responses
        time.sleep(2.0)

        specs = fetch_product_detail(p.url, p.site)
        if specs and specs.get("jan_code"):
            jan = specs["jan_code"].strip()
            if len(jan) >= 8:
                conn.execute(
                    "UPDATE products SET jan_code = ? WHERE site = ? AND product_id = ?",
                    (jan, p.site, p.product_id),
                )
                jan_found += 1

    conn.commit()

    if jan_found:
        logger.info(f"=== Post-scrape: {jan_found} JAN codes fetched for new products ===")

    # Safety check: clear same-site duplicate JAN codes (bad data from CDN caching)
    dupes_cleared = _clear_duplicate_jan_codes(conn)
    if dupes_cleared:
        logger.warning(f"=== Post-scrape: cleared {dupes_cleared} duplicate JAN codes ===")

    conn.close()

    # Re-run matching to pick up new cross-site groups
    from analytics.matching import run_matching
    n_groups = run_matching()
    logger.info(f"=== Post-scrape: matching updated — {n_groups} groups ===")


def _clear_duplicate_jan_codes(conn) -> int:
    """Detect and nullify same-site duplicate JAN codes.

    If multiple products on the same site share a JAN code, keep only the first
    one (lowest product ID) and clear the rest — same-site duplicates are always
    bad data from CDN caching.
    """
    dupes = conn.execute("""
        SELECT site, jan_code, GROUP_CONCAT(product_id) as pids, COUNT(*) as cnt
        FROM products
        WHERE jan_code IS NOT NULL AND jan_code != ''
        GROUP BY site, jan_code
        HAVING cnt > 1
    """).fetchall()

    cleared = 0
    for row in dupes:
        site = row["site"]
        jan = row["jan_code"]
        pids = row["pids"].split(",")
        # Keep the first (lowest) product_id, clear the rest
        keep_pid = min(pids, key=lambda x: int(x))
        for pid in pids:
            if pid != keep_pid:
                conn.execute(
                    "UPDATE products SET jan_code = NULL WHERE site = ? AND product_id = ?",
                    (site, pid),
                )
                cleared += 1

    if cleared:
        conn.commit()
    return cleared


def main():
    parser = argparse.ArgumentParser(description="Figure website scraper")
    parser.add_argument(
        "--site", type=str, help="Scrape a single site (e.g., figurepresso)"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once and exit (no scheduler)"
    )
    parser.add_argument(
        "--extract", action="store_true", help="Backfill extraction for unprocessed products"
    )
    parser.add_argument(
        "--force-llm", action="store_true", help="Force LLM extraction for all products (skip rules threshold)"
    )
    parser.add_argument(
        "--re-extract", action="store_true", help="Re-extract ALL products (even already extracted)"
    )
    args = parser.parse_args()

    init_db()

    if args.extract or args.re_extract:
        extract_existing(
            args.site,
            force_llm=getattr(args, "force_llm", False),
            re_extract=getattr(args, "re_extract", False),
        )
        return

    if args.once or args.site:
        if args.site:
            changes = scrape_site(args.site)
        else:
            changes = scrape_all()

        total = len(changes)
        new = sum(1 for c in changes if c.change_type == "new")
        restocks = sum(1 for c in changes if c.change_type == "restock")
        logger.info(f"=== Done. {total} changes ({new} new, {restocks} restocks) ===")

        # Post-scrape: fetch JAN codes for new products and re-run matching
        if new > 0:
            _post_scrape_enrich(changes)
    else:
        # Run with scheduler
        from scheduler import run_scheduler
        run_scheduler()


if __name__ == "__main__":
    main()
