"""Cross-site price comparison page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.charts import LAYOUT_DEFAULTS, SITE_COLORS
from analytics.matching import get_saved_matches, run_matching

st.header("가격 비교")

# --- Run matching button ---
col_btn, col_info = st.columns([1, 3])
with col_btn:
    if st.button("매칭 갱신", help="구조화된 필드 기반 교차 사이트 매칭 실행"):
        with st.spinner("매칭 중..."):
            n_groups = run_matching()
        st.success(f"{n_groups}개 매칭 그룹 발견")
        st.rerun()

# --- Load matches ---
matches_df = get_saved_matches()

if matches_df.empty:
    st.info("매칭 데이터가 없습니다. '매칭 갱신' 버튼을 눌러주세요.")
    st.stop()

with col_info:
    n_groups = matches_df["match_key"].nunique()
    n_products = len(matches_df)
    st.metric("매칭 그룹", f"{n_groups}개", help=f"총 {n_products}개 상품")

# --- Filters ---
col1, col2 = st.columns(2)
with col1:
    search = st.text_input("상품명 / 작품 / 캐릭터 검색", key="price_search")
with col2:
    min_diff = st.number_input("최소 가격 차이 (원)", min_value=0, value=0, step=1000)

# --- Build comparison table ---
rows = []
for match_key, group in matches_df.groupby("match_key"):
    if len(group) < 2:
        continue

    priced = group[group["price"].notna() & (group["price"] > 0)]
    if priced.empty:
        continue

    # Use structured fields for display when available
    series = group["series"].dropna().iloc[0] if group["series"].notna().any() else ""
    character = group["character_name"].dropna().iloc[0] if group["character_name"].notna().any() else ""
    mfr = group["extracted_manufacturer"].dropna().iloc[0] if group["extracted_manufacturer"].notna().any() else group["manufacturer"].iloc[0] or ""
    scale = group["scale"].dropna().iloc[0] if group["scale"].notna().any() else ""
    product_line = group["product_line"].dropna().iloc[0] if group["product_line"].notna().any() else ""
    confidence = group["confidence"].iloc[0]

    # Build display name from structured fields
    display_name = ""
    if series:
        display_name = series
    if character:
        display_name = f"{display_name} — {character}" if display_name else character
    if not display_name:
        display_name = group["name"].iloc[0]

    prices_by_site = {}
    urls_by_site = {}
    for _, r in group.iterrows():
        prices_by_site[r["site"]] = r["price"]
        urls_by_site[r["site"]] = r["url"]

    cheapest_site = priced.loc[priced["price"].idxmin(), "site"]
    cheapest_price = priced["price"].min()
    most_expensive = priced["price"].max()
    price_diff = most_expensive - cheapest_price

    # Determine match type
    if match_key.startswith("jan_"):
        match_type = "JAN"
    elif match_key.startswith("struct_full"):
        match_type = "구조"
    else:
        match_type = "부분"

    row = {
        "상품명": display_name,
        "제조사": mfr,
        "스케일": scale,
        "라인": product_line,
        "매칭": match_type,
        "신뢰도": f"{confidence:.0%}",
        "최저가 사이트": cheapest_site,
        "최저가": cheapest_price,
        "가격차": price_diff,
        "사이트 수": len(group),
    }

    for site in sorted(matches_df["site"].unique()):
        row[site] = prices_by_site.get(site)

    rows.append(row)

if not rows:
    st.info("비교 가능한 매칭 상품이 없습니다.")
    st.stop()

compare_df = pd.DataFrame(rows)

# Apply filters
if search:
    compare_df = compare_df[
        compare_df["상품명"].str.contains(search, case=False, na=False)
        | compare_df["제조사"].str.contains(search, case=False, na=False)
    ]
if min_diff > 0:
    compare_df = compare_df[compare_df["가격차"] >= min_diff]

compare_df = compare_df.sort_values("가격차", ascending=False)

st.metric("비교 결과", f"{len(compare_df)}개 상품")

# --- Display comparison table ---
site_cols = sorted(matches_df["site"].unique())
column_config = {
    "상품명": st.column_config.TextColumn("상품명", width="large"),
    "제조사": st.column_config.TextColumn("제조사"),
    "스케일": st.column_config.TextColumn("스케일"),
    "라인": st.column_config.TextColumn("라인"),
    "매칭": st.column_config.TextColumn("매칭"),
    "신뢰도": st.column_config.TextColumn("신뢰도"),
    "최저가 사이트": st.column_config.TextColumn("최저가"),
    "최저가": st.column_config.NumberColumn("최저가", format="₩%d"),
    "가격차": st.column_config.NumberColumn("가격차", format="₩%d"),
    "사이트 수": st.column_config.NumberColumn("사이트 수"),
}
for site in site_cols:
    column_config[site] = st.column_config.NumberColumn(site, format="₩%d")

st.dataframe(
    compare_df,
    use_container_width=True,
    column_config=column_config,
    hide_index=True,
)

st.divider()

# --- Average price difference by site pair ---
st.subheader("사이트 쌍별 평균 가격 차이")

pair_diffs = []
for _, row in compare_df.iterrows():
    site_prices = {s: row[s] for s in site_cols if pd.notna(row.get(s))}
    sites = list(site_prices.keys())
    for i, s1 in enumerate(sites):
        for s2 in sites[i + 1 :]:
            diff = abs(site_prices[s1] - site_prices[s2])
            pair_diffs.append({"사이트 쌍": f"{s1} vs {s2}", "가격차": diff})

if pair_diffs:
    pair_df = pd.DataFrame(pair_diffs)
    avg_pair = pair_df.groupby("사이트 쌍")["가격차"].mean().reset_index()
    avg_pair = avg_pair.sort_values("가격차", ascending=True)

    fig = px.bar(
        avg_pair,
        x="가격차",
        y="사이트 쌍",
        orientation="h",
        color="가격차",
        color_continuous_scale="RdYlGn_r",
    )
    fig.update_layout(
        xaxis_title="평균 가격 차이 (원)",
        coloraxis_showscale=False,
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("사이트 쌍별 비교 데이터가 부족합니다.")
