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
    if st.button("매칭 갱신", help="JAN 코드 + 구조화 필드 기반 교차 사이트 매칭"):
        with st.spinner("매칭 중..."):
            n_groups = run_matching()
        st.success(f"{n_groups}개 매칭 그룹 발견")
        st.rerun()

# --- Load matches ---
matches_df = get_saved_matches()

if matches_df.empty:
    st.info("매칭 데이터가 없습니다. '매칭 갱신' 버튼을 눌러주세요.")
    st.stop()

# --- Top metrics ---
n_groups = matches_df["match_key"].nunique()
n_jan = matches_df[matches_df["match_key"].str.startswith("jan_")]["match_key"].nunique()
n_struct = n_groups - n_jan
n_products = len(matches_df)

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 매칭", f"{n_groups}개", help=f"총 {n_products}개 상품")
c2.metric("JAN 매칭", f"{n_jan}개", help="바코드 일치 — 100% 정확")
c3.metric("구조 매칭", f"{n_struct}개", help="필드 기반 매칭")
c4.metric("비교 가능 상품", f"{n_products}개")

st.divider()

# --- Filters ---
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    match_type_filter = st.selectbox(
        "매칭 유형",
        options=["전체", "JAN만 (100% 정확)", "구조 매칭만"],
        index=0,
        key="match_type_filter",
    )
with col_f2:
    search = st.text_input("상품명 / 작품 / 캐릭터 검색", key="price_search")
with col_f3:
    min_diff = st.number_input("최소 가격 차이 (원)", min_value=0, value=0, step=1000)

col_cb1, col_cb2 = st.columns(2)
with col_cb1:
    buyable_only = st.checkbox("🛒 구매 가능한 상품만 보기", value=False, help="품절이 아닌 상품이 2개 사이트 이상에서 판매 중인 매칭만 표시")
with col_cb2:
    hide_suspicious = st.checkbox("⚠️ 가격차 2배 이상 제외", value=False, help="최고가가 최저가의 2배 이상인 매칭 숨기기 (예약금/부분결제 가능성)")

# --- Build comparison table ---
rows = []
for match_key, group in matches_df.groupby("match_key"):
    if len(group) < 2:
        continue

    priced = group[group["price"].notna() & (group["price"] > 0)]
    if priced.empty:
        continue

    # Determine match type
    if match_key.startswith("jan_"):
        match_type = "JAN"
        jan_code = match_key.replace("jan_", "")
    elif match_key.startswith("struct_full"):
        match_type = "구조(정밀)"
        jan_code = ""
    elif match_key.startswith("struct_line"):
        match_type = "구조(라인)"
        jan_code = ""
    else:
        match_type = "구조(캐릭터)"
        jan_code = ""

    # Apply match type filter
    if match_type_filter == "JAN만 (100% 정확)" and match_type != "JAN":
        continue
    if match_type_filter == "구조 매칭만" and match_type == "JAN":
        continue

    # Use structured fields for display
    series = group["series"].dropna().iloc[0] if group["series"].notna().any() else ""
    character = group["character_name"].dropna().iloc[0] if group["character_name"].notna().any() else ""
    mfr = group["extracted_manufacturer"].dropna().iloc[0] if group["extracted_manufacturer"].notna().any() else group["manufacturer"].iloc[0] or ""
    scale = group["scale"].dropna().iloc[0] if group["scale"].notna().any() else ""
    product_line = group["product_line"].dropna().iloc[0] if group["product_line"].notna().any() else ""
    product_type = group["product_type"].dropna().iloc[0] if group["product_type"].notna().any() else ""
    confidence = group["confidence"].iloc[0]

    display_name = ""
    if series:
        display_name = series
    if character:
        display_name = f"{display_name} — {character}" if display_name else character
    if not display_name:
        display_name = group["name"].iloc[0]

    prices_by_site = {}
    urls_by_site = {}
    names_by_site = {}
    status_by_site = {}
    for _, r in group.iterrows():
        prices_by_site[r["site"]] = r["price"]
        urls_by_site[r["site"]] = r["url"]
        names_by_site[r["site"]] = r["name"]
        status_by_site[r["site"]] = r.get("status") or r.get("product_status", "available")

    # Filter: only show groups with 2+ buyable sites
    if buyable_only:
        buyable_sites = [s for s, st_ in status_by_site.items() if st_ != "soldout"]
        if len(buyable_sites) < 2:
            continue

    cheapest_site = priced.loc[priced["price"].idxmin(), "site"]
    cheapest_price = priced["price"].min()
    most_expensive = priced["price"].max()
    price_diff = most_expensive - cheapest_price
    saving_pct = price_diff / most_expensive * 100 if most_expensive > 0 else 0
    is_suspicious = most_expensive >= 2 * cheapest_price

    # Filter: hide suspicious price matches if checkbox checked
    if hide_suspicious and is_suspicious:
        continue

    row = {
        "상품명": display_name,
        "제조사": mfr,
        "유형": product_type,
        "스케일": scale,
        "라인": product_line,
        "매칭": match_type,
        "JAN": jan_code,
        "신뢰도": f"{confidence:.0%}",
        "최저가 사이트": cheapest_site,
        "최저가": cheapest_price,
        "가격차": price_diff,
        "절약%": round(saving_pct, 1),
        "사이트 수": len(group),
        "⚠️": "의심" if is_suspicious else "",
        "_urls": urls_by_site,
        "_names": names_by_site,
        "_status": status_by_site,
    }

    for site in sorted(matches_df["site"].unique()):
        row[site] = prices_by_site.get(site)

    rows.append(row)

if not rows:
    st.info("비교 가능한 매칭 상품이 없습니다.")
    st.stop()

compare_df = pd.DataFrame(rows)

# Apply text search filter
if search:
    compare_df = compare_df[
        compare_df["상품명"].str.contains(search, case=False, na=False)
        | compare_df["제조사"].str.contains(search, case=False, na=False)
    ]
if min_diff > 0:
    compare_df = compare_df[compare_df["가격차"] >= min_diff]

compare_df = compare_df.sort_values("가격차", ascending=False)

st.metric("비교 결과", f"{len(compare_df)}개 상품")

# --- Top match groups with clickable links ---
st.subheader("매칭 그룹 (가격차 순)")

site_cols = sorted(matches_df["site"].unique())

type_emoji = {
    "scale_figure": "🗿", "prize_figure": "🎰", "nendoroid": "🧸",
    "figma": "🦾", "action_figure": "💪", "plushie": "🧶",
    "acrylic": "💎", "keychain": "🔑", "badge": "📌",
    "sticker": "🏷️", "model_kit": "🔧", "goods_other": "📦",
    "blanket": "🧣",
}

for idx, row in compare_df.head(30).iterrows():
    cheapest = row["최저가 사이트"]
    diff_str = f"₩{int(row['가격차']):,}" if row["가격차"] > 0 else "동일"
    saving_str = f" ({row['절약%']:.0f}% 절약)" if row["절약%"] > 0 else ""
    t_emoji = type_emoji.get(row.get("유형", ""), "")
    match_badge = "🔗" if row["매칭"] == "JAN" else "🔍"

    with st.expander(
        f"{match_badge} {t_emoji} **{row['상품명']}** — {row['제조사'] or ''} "
        f"| {diff_str}{saving_str} | {int(row['사이트 수'])}개 사이트"
    ):
        # Price comparison columns
        cols = st.columns(len(site_cols))
        urls = row.get("_urls", {})
        names = row.get("_names", {})
        statuses = row.get("_status", {})
        for i, site in enumerate(site_cols):
            price = row.get(site)
            url = urls.get(site)
            site_status = statuses.get(site, "")
            with cols[i]:
                if pd.notna(price) and price:
                    is_soldout = site_status == "soldout"
                    price_str = f"₩{int(price):,}"
                    is_cheapest = site == cheapest and not is_soldout
                    st.markdown(f"**{site}**")
                    if is_soldout:
                        st.markdown(f"~~{price_str}~~ 품절")
                    elif url:
                        label = f"{'🏷️ ' if is_cheapest else ''}{price_str}"
                        st.markdown(f"[{label}]({url})")
                    else:
                        st.markdown(f"{'🏷️ ' if is_cheapest else ''}{price_str}")
                else:
                    st.markdown(f"**{site}**")
                    st.markdown("—")

        # Match info footer
        info_parts = []
        if row.get("JAN"):
            info_parts.append(f"JAN: `{row['JAN']}`")
        if row.get("유형"):
            info_parts.append(f"유형: {row['유형']}")
        if row.get("스케일"):
            info_parts.append(f"스케일: {row['스케일']}")
        if row.get("라인"):
            info_parts.append(f"라인: {row['라인']}")
        info_parts.append(f"매칭: {row['매칭']} ({row['신뢰도']})")
        st.caption(" | ".join(info_parts))

st.divider()

# --- Summary stats ---
st.subheader("가격 비교 요약")

col_s1, col_s2 = st.columns(2)

with col_s1:
    # Savings distribution
    jan_df = compare_df[compare_df["매칭"] == "JAN"]
    if not jan_df.empty and jan_df["가격차"].sum() > 0:
        fig = px.histogram(
            jan_df[jan_df["가격차"] > 0],
            x="절약%",
            nbins=20,
            color_discrete_sequence=["#4ecdc4"],
        )
        fig.update_layout(
            title="JAN 매칭 절약률 분포",
            xaxis_title="절약률 (%)",
            yaxis_title="상품 수",
            **LAYOUT_DEFAULTS,
        )
        st.plotly_chart(fig, use_container_width=True)

with col_s2:
    # Cheapest site ranking
    if not compare_df.empty:
        cheapest_counts = compare_df["최저가 사이트"].value_counts().reset_index()
        cheapest_counts.columns = ["사이트", "최저가 횟수"]
        fig = px.bar(
            cheapest_counts,
            x="최저가 횟수",
            y="사이트",
            orientation="h",
            color="사이트",
            color_discrete_map=SITE_COLORS,
        )
        fig.update_layout(
            title="사이트별 최저가 횟수",
            showlegend=False,
            **LAYOUT_DEFAULTS,
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Full comparison table ---
st.subheader("전체 비교 테이블")

display_cols = ["상품명", "제조사", "유형", "매칭", "JAN", "최저가 사이트", "최저가", "가격차", "절약%", "사이트 수"] + site_cols
table_df = compare_df[[c for c in display_cols if c in compare_df.columns]]

column_config = {
    "상품명": st.column_config.TextColumn("상품명", width="large"),
    "제조사": st.column_config.TextColumn("제조사"),
    "유형": st.column_config.TextColumn("유형"),
    "매칭": st.column_config.TextColumn("매칭"),
    "JAN": st.column_config.TextColumn("JAN"),
    "최저가 사이트": st.column_config.TextColumn("최저가"),
    "최저가": st.column_config.NumberColumn("최저가", format="₩%d"),
    "가격차": st.column_config.NumberColumn("가격차", format="₩%d"),
    "절약%": st.column_config.NumberColumn("절약%", format="%.1f%%"),
    "사이트 수": st.column_config.NumberColumn("사이트"),
}
for site in site_cols:
    column_config[site] = st.column_config.NumberColumn(site, format="₩%d")

st.dataframe(
    table_df,
    use_container_width=True,
    column_config=column_config,
    hide_index=True,
)

st.divider()

# --- Average price difference by site pair ---
st.subheader("사이트 쌍별 평균 가격 차이")

# Use only JAN matches for most accurate comparison
jan_compare = compare_df[compare_df["매칭"] == "JAN"] if not compare_df[compare_df["매칭"] == "JAN"].empty else compare_df

pair_diffs = []
for _, row in jan_compare.iterrows():
    site_prices = {s: row[s] for s in site_cols if pd.notna(row.get(s))}
    sites = list(site_prices.keys())
    for i, s1 in enumerate(sites):
        for s2 in sites[i + 1:]:
            diff = abs(site_prices[s1] - site_prices[s2])
            cheaper = s1 if site_prices[s1] < site_prices[s2] else s2
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
        title="JAN 매칭 기준 평균 가격 차이",
        xaxis_title="평균 가격 차이 (원)",
        coloraxis_showscale=False,
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("사이트 쌍별 비교 데이터가 부족합니다.")
