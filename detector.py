"""Change detection for new products, restocks, and price changes."""

import logging
import sqlite3
from dataclasses import dataclass

from db import (
    get_known_product_ids,
    get_product,
    log_price,
    log_status_change,
    save_extraction,
    upsert_product,
)
from extraction.extractor import extract_product_attributes
from models import Product

logger = logging.getLogger(__name__)


@dataclass
class Change:
    change_type: str  # 'new' | 'restock' | 'price' | 'soldout'
    product: Product
    old_value: str = ""
    new_value: str = ""


class ChangeDetector:
    """Detects new products, restocks, and price changes."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def process_products(self, site: str, products: list[Product]) -> list[Change]:
        """Process scraped products and detect all changes.

        Returns list of Change objects for new products, restocks, and price changes.
        Also updates the database.
        """
        changes = []
        known_ids = get_known_product_ids(self.conn, site)

        for product in products:
            if product.product_id in known_ids:
                # Existing product — check for changes
                changes.extend(self._check_existing(product))
            else:
                # New product
                changes.append(Change(
                    change_type="new",
                    product=product,
                    new_value=product.status,
                ))

            is_new = product.product_id not in known_ids

            # Upsert into DB
            db_id = upsert_product(self.conn, product)

            # Extract structured fields for new products
            if is_new:
                self._extract_and_save(db_id, product)

            # Record price history for every check
            if product.price is not None:
                log_price(self.conn, db_id, product.price)

        self.conn.commit()

        # Log summary
        new_count = sum(1 for c in changes if c.change_type == "new")
        restock_count = sum(1 for c in changes if c.change_type == "restock")
        price_count = sum(1 for c in changes if c.change_type == "price")
        soldout_count = sum(1 for c in changes if c.change_type == "soldout")

        if changes:
            logger.info(
                f"[{site}] Changes: {new_count} new, {restock_count} restocks, "
                f"{price_count} price changes, {soldout_count} newly soldout"
            )
        else:
            logger.info(f"[{site}] No changes detected")

        return changes

    def _extract_and_save(self, db_id: int, product: Product):
        """Run structured extraction on a product and save results.

        Also saves the JAN code from the detail page fetch (if found) so that
        _post_scrape_enrich doesn't need to re-fetch the same page.
        """
        try:
            attrs, method, confidence, page_specs = extract_product_attributes(
                name=product.name,
                site=product.site,
                category=product.category or "",
                manufacturer=product.manufacturer,
                url=product.url,
            )
            save_extraction(self.conn, db_id, attrs.model_dump(), method, confidence)

            # Save JAN code from page fetch right away (avoids duplicate fetch)
            if page_specs and page_specs.get("jan_code"):
                jan = page_specs["jan_code"].strip()
                if len(jan) >= 8:
                    self.conn.execute(
                        "UPDATE products SET jan_code = ? WHERE id = ?",
                        (jan, db_id),
                    )
        except Exception as e:
            logger.warning(f"Extraction failed for {product.name}: {e}")

    def _check_existing(self, product: Product) -> list[Change]:
        """Check an existing product for status and price changes."""
        changes = []
        existing = get_product(self.conn, product.site, product.product_id)
        if not existing:
            return changes

        db_id = existing["id"]
        old_status = existing["status"]
        old_price = existing["price"]

        # Status change detection
        if old_status != product.status:
            if old_status == "soldout" and product.status == "available":
                # Restock!
                changes.append(Change(
                    change_type="restock",
                    product=product,
                    old_value="soldout",
                    new_value="available",
                ))
            elif product.status == "soldout" and old_status != "soldout":
                # Newly soldout
                changes.append(Change(
                    change_type="soldout",
                    product=product,
                    old_value=old_status,
                    new_value="soldout",
                ))
            else:
                # Other status change
                changes.append(Change(
                    change_type="status",
                    product=product,
                    old_value=old_status or "",
                    new_value=product.status,
                ))

            log_status_change(
                self.conn, db_id, "status", old_status or "", product.status
            )

        # Price change detection
        if (
            product.price is not None
            and old_price is not None
            and product.price != old_price
        ):
            changes.append(Change(
                change_type="price",
                product=product,
                old_value=str(old_price),
                new_value=str(product.price),
            ))
            log_status_change(
                self.conn, db_id, "price", str(old_price), str(product.price)
            )

        return changes
