#!/usr/bin/env python3
"""Main entry point for figure scraper."""

import argparse
import logging
import sys

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


def extract_existing(site: str | None = None):
    """Backfill extraction for products that haven't been extracted yet."""
    from db import get_unextracted_products, save_extraction
    from extraction.extractor import extract_product_attributes

    conn = get_connection()
    products = get_unextracted_products(conn, site)
    total = len(products)
    logger.info(f"Extracting {total} unprocessed products" + (f" (site={site})" if site else ""))

    success = 0
    for i, row in enumerate(products, 1):
        try:
            attrs, method, confidence = extract_product_attributes(
                name=row["name"],
                site=row["site"],
                category=row.get("category", ""),
                manufacturer=row.get("manufacturer"),
            )
            save_extraction(conn, row["id"], attrs.model_dump(), method, confidence)
            success += 1
            if i % 100 == 0:
                conn.commit()
                logger.info(f"  Progress: {i}/{total} ({success} extracted)")
        except Exception as e:
            logger.warning(f"  Failed to extract [{row['site']}] {row['name']}: {e}")

    conn.commit()
    conn.close()
    logger.info(f"=== Extraction done: {success}/{total} products extracted ===")


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
    args = parser.parse_args()

    init_db()

    if args.extract:
        extract_existing(args.site)
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
    else:
        # Run with scheduler
        from scheduler import run_scheduler
        run_scheduler()


if __name__ == "__main__":
    main()
