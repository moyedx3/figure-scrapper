"""Cross-site product matching engine (JAN code + structured fields)."""

import re
import sqlite3

import pandas as pd
import streamlit as st

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _normalize_character(name: str | None) -> str:
    """Normalize character name for matching.

    Strips product codes, extra whitespace, and standardizes formatting
    so the same character matches across sites.
    """
    if not name:
        return ""
    s = name.strip()
    # Strip leading product codes like "2968", "No.681"
    s = re.sub(r"^(?:No\.?\s*)?\d{3,5}\s+", "", s)
    # Strip trailing product codes like "3786", "8333"
    s = re.sub(r"\s+\d{4,5}$", "", s)
    # Remove product line names that leaked in
    s = re.sub(r"^(피그마|넨도로이드|figma|nendoroid)\s+", "", s, flags=re.IGNORECASE)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


@st.cache_data(ttl=300)
def get_products_for_matching() -> pd.DataFrame:
    """All products with fields needed for matching."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT id, site, product_id, name, price, status,
                  manufacturer, jan_code, category,
                  series, character_name, extracted_manufacturer,
                  scale, version, product_line, product_type,
                  extraction_confidence
           FROM products""",
        conn,
    )
    conn.close()
    return df


def match_by_jan_code(df: pd.DataFrame) -> dict[str, list[int]]:
    """Exact match products sharing a JAN/barcode across sites.

    Skips JAN codes that appear multiple times within the same site,
    as that indicates bad data (e.g., CDN caching during scraping).
    """
    with_jan = df[df["jan_code"].notna() & (df["jan_code"] != "")]

    # Find and exclude same-site duplicate JANs (bad data signal)
    site_jan_counts = with_jan.groupby(["site", "jan_code"]).size().reset_index(name="cnt")
    bad_jans = set(site_jan_counts[site_jan_counts["cnt"] > 1]["jan_code"])
    if bad_jans:
        with_jan = with_jan[~with_jan["jan_code"].isin(bad_jans)]

    groups: dict[str, list[int]] = {}
    for jan, group in with_jan.groupby("jan_code"):
        if group["site"].nunique() < 2:
            continue
        groups[f"jan_{jan}"] = group["id"].tolist()

    return groups


def match_by_structured_fields(df: pd.DataFrame) -> dict[str, tuple[list[int], float]]:
    """Match products by extracted structured fields.

    Tier 1: series + normalized character + manufacturer + scale (high confidence)
    Tier 2: series + normalized character + product_line (medium confidence)
    Tier 3: series + normalized character (lower confidence, fuzzy substring)
    """
    groups: dict[str, tuple[list[int], float]] = {}
    group_counter = 0
    matched_ids: set[int] = set()

    has_fields = df[
        df["series"].notna() & (df["series"] != "")
        & df["character_name"].notna() & (df["character_name"] != "")
    ].copy()

    if has_fields.empty:
        return groups

    # Normalize character names for matching
    has_fields["_norm_char"] = has_fields["character_name"].apply(_normalize_character)
    has_fields = has_fields[has_fields["_norm_char"] != ""]

    # --- Tier 1: Full match (series + character + manufacturer + product_type + scale/version) ---
    has_mfr = has_fields[
        has_fields["extracted_manufacturer"].notna()
        & (has_fields["extracted_manufacturer"] != "")
        & has_fields["product_type"].notna()
    ]
    if not has_mfr.empty:
        for _, group in has_mfr.groupby(
            ["series", "_norm_char", "extracted_manufacturer", "product_type", "scale", "version"]
        ):
            if group["site"].nunique() < 2:
                continue
            ids = group["id"].tolist()
            avg_conf = group["extraction_confidence"].mean()
            group_counter += 1
            groups[f"struct_full_{group_counter}"] = (ids, round(min(avg_conf or 0.85, 1.0), 2))
            matched_ids.update(ids)

    # --- Tier 2: series + character + product_type + product_line ---
    remaining = has_fields[~has_fields["id"].isin(matched_ids)]
    has_line = remaining[
        remaining["product_line"].notna() & (remaining["product_line"] != "")
        & remaining["product_type"].notna()
    ]
    if not has_line.empty:
        for _, group in has_line.groupby(["series", "_norm_char", "product_type", "product_line"]):
            if group["site"].nunique() < 2:
                continue
            ids = group["id"].tolist()
            group_counter += 1
            groups[f"struct_line_{group_counter}"] = (ids, 0.75)
            matched_ids.update(ids)

    # --- Tier 3: series + character + product_type (exact character match) ---
    remaining = has_fields[~has_fields["id"].isin(matched_ids)]
    has_type = remaining[remaining["product_type"].notna()]
    if not has_type.empty:
        for _, group in has_type.groupby(["series", "_norm_char", "product_type"]):
            if group["site"].nunique() < 2:
                continue
            ids = group["id"].tolist()
            group_counter += 1
            groups[f"struct_char_{group_counter}"] = (ids, 0.6)
            matched_ids.update(ids)

    return groups


def build_match_groups(df: pd.DataFrame) -> dict[str, tuple[list[int], float]]:
    """Combine JAN and structured matches. JAN matches take priority."""
    jan_groups = match_by_jan_code(df)
    jan_with_conf = {k: (ids, 1.0) for k, ids in jan_groups.items()}

    jan_matched_ids: set[int] = set()
    for ids in jan_groups.values():
        jan_matched_ids.update(ids)

    remaining = df[~df["id"].isin(jan_matched_ids)]
    structured_groups = match_by_structured_fields(remaining)

    return {**jan_with_conf, **structured_groups}


def save_matches_to_db(groups: dict[str, tuple[list[int], float]]):
    """Persist match groups to product_matches table."""
    conn = get_conn()
    conn.execute("DELETE FROM product_matches")
    for match_key, (product_ids, confidence) in groups.items():
        for pid in product_ids:
            conn.execute(
                """INSERT OR REPLACE INTO product_matches (match_key, product_id, confidence)
                   VALUES (?, ?, ?)""",
                (match_key, pid, confidence),
            )
    conn.commit()
    conn.close()


@st.cache_data(ttl=300)
def get_saved_matches() -> pd.DataFrame:
    """Load persisted matches joined with product info."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT pm.match_key, pm.confidence,
                  p.id, p.site, p.name, p.price, p.status,
                  p.manufacturer, p.jan_code, p.url,
                  p.series, p.character_name, p.extracted_manufacturer,
                  p.scale, p.version, p.product_line, p.product_type,
                  p.status as product_status
           FROM product_matches pm
           JOIN products p ON pm.product_id = p.id
           ORDER BY pm.match_key, p.site""",
        conn,
    )
    conn.close()
    return df


def run_matching() -> int:
    """Run full matching pipeline. Returns number of match groups found."""
    df = get_products_for_matching()
    groups = build_match_groups(df)
    save_matches_to_db(groups)
    get_saved_matches.clear()
    return len(groups)
