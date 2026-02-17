"""Cross-site product matching engine (JAN code + structured fields)."""

import sqlite3

import pandas as pd
import streamlit as st

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


@st.cache_data(ttl=300)
def get_products_for_matching() -> pd.DataFrame:
    """All products with fields needed for matching."""
    conn = get_conn()
    df = pd.read_sql_query(
        """SELECT id, site, product_id, name, price, status,
                  manufacturer, jan_code, category,
                  series, character_name, extracted_manufacturer,
                  scale, version, product_line,
                  extraction_confidence
           FROM products""",
        conn,
    )
    conn.close()
    return df


def match_by_jan_code(df: pd.DataFrame) -> dict[str, list[int]]:
    """Exact match products sharing a JAN/barcode across sites.

    Returns {match_key: [product db ids]}.
    """
    with_jan = df[df["jan_code"].notna() & (df["jan_code"] != "")]
    groups: dict[str, list[int]] = {}

    for jan, group in with_jan.groupby("jan_code"):
        if group["site"].nunique() < 2:
            continue
        key = f"jan_{jan}"
        groups[key] = group["id"].tolist()

    return groups


def match_by_structured_fields(df: pd.DataFrame) -> dict[str, tuple[list[int], float]]:
    """Match products by extracted structured fields.

    Tier 1 (full): series + character_name + manufacturer + scale  → high confidence
    Tier 2 (partial): series + character_name  → lower confidence

    Returns {match_key: (product_ids, confidence)}.
    """
    groups: dict[str, tuple[list[int], float]] = {}
    group_counter = 0
    matched_ids: set[int] = set()

    # Filter to products with at least series and character_name
    has_fields = df[
        df["series"].notna() & (df["series"] != "")
        & df["character_name"].notna() & (df["character_name"] != "")
    ].copy()

    if has_fields.empty:
        return groups

    # Tier 1: Full structured match (series + character + manufacturer + scale)
    full_cols = ["series", "character_name", "extracted_manufacturer", "scale"]
    has_full = has_fields[
        has_fields["extracted_manufacturer"].notna()
        & (has_fields["extracted_manufacturer"] != "")
    ]

    if not has_full.empty:
        for keys, group in has_full.groupby(full_cols):
            if group["site"].nunique() < 2:
                continue
            ids = group["id"].tolist()
            # Average extraction confidence of the group
            avg_conf = group["extraction_confidence"].mean()
            confidence = round(min(avg_conf or 0.8, 1.0), 2)
            group_counter += 1
            groups[f"struct_full_{group_counter}"] = (ids, confidence)
            matched_ids.update(ids)

    # Tier 2: Partial match (series + character only, for remaining products)
    remaining = has_fields[~has_fields["id"].isin(matched_ids)]
    if not remaining.empty:
        partial_cols = ["series", "character_name"]
        for keys, group in remaining.groupby(partial_cols):
            if group["site"].nunique() < 2:
                continue
            ids = group["id"].tolist()
            group_counter += 1
            groups[f"struct_partial_{group_counter}"] = (ids, 0.6)
            matched_ids.update(ids)

    return groups


def build_match_groups(df: pd.DataFrame) -> dict[str, tuple[list[int], float]]:
    """Combine JAN and structured matches. JAN matches take priority.

    Returns {match_key: (product_ids, confidence)}.
    """
    jan_groups = match_by_jan_code(df)
    jan_with_conf = {k: (ids, 1.0) for k, ids in jan_groups.items()}

    jan_matched_ids: set[int] = set()
    for ids in jan_groups.values():
        jan_matched_ids.update(ids)

    remaining = df[~df["id"].isin(jan_matched_ids)]
    structured_groups = match_by_structured_fields(remaining)

    all_groups = {**jan_with_conf, **structured_groups}
    return all_groups


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
                  p.scale, p.version, p.product_line
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
