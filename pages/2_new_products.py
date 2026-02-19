"""New products feed page."""

import pandas as pd
import streamlit as st

from analytics.queries import get_recent_new_products, get_latest_crawl_time

st.header("신상품 피드")

# --- Filters ---
col1, col2, col3 = st.columns(3)

with col1:
    period = st.selectbox(
        "기간",
        options=[1, 7, 30, 365],
        format_func=lambda x: {1: "24시간", 7: "7일", 30: "30일", 365: "전체"}[x],
        index=1,
    )

df = get_recent_new_products(days=period)

if df.empty:
    st.info("해당 기간에 신상품이 없습니다.")
    st.stop()

with col2:
    sites = st.multiselect("사이트", options=sorted(df["site"].unique()), default=None)

with col3:
    search = st.text_input("상품명 검색")

# --- Apply filters ---
filtered = df.copy()
if sites:
    filtered = filtered[filtered["site"].isin(sites)]
if search:
    filtered = filtered[filtered["name"].str.contains(search, case=False, na=False)]

# Price range slider
if not filtered.empty and filtered["price"].notna().any():
    prices = filtered["price"].dropna()
    if len(prices) > 0:
        min_p, max_p = int(prices.min()), int(prices.max())
        if min_p < max_p:
            price_range = st.slider("가격 범위", min_p, max_p, (min_p, max_p), step=1000)
            filtered = filtered[
                (filtered["price"] >= price_range[0]) & (filtered["price"] <= price_range[1])
            ]

# --- Mark NEW products (from the latest crawl session) ---
latest_crawl = get_latest_crawl_time()
if latest_crawl:
    # Products first seen within 5 minutes of the latest crawl are "new this session"
    cutoff = pd.Timestamp(latest_crawl) - pd.Timedelta(minutes=5)
    filtered["first_seen_ts"] = pd.to_datetime(filtered["first_seen_at"], format="mixed")
    filtered["is_new"] = filtered["first_seen_ts"] >= cutoff
    new_count = filtered["is_new"].sum()
    filtered["상품명"] = filtered.apply(
        lambda r: f"🆕 {r['name']}" if r["is_new"] else r["name"], axis=1
    )
    filtered = filtered.drop(columns=["first_seen_ts"])
else:
    filtered["is_new"] = False
    filtered["상품명"] = filtered["name"]
    new_count = 0

# --- Metrics ---
c1, c2 = st.columns(2)
c1.metric("검색 결과", f"{len(filtered):,}개")
c2.metric("🆕 최근 크롤링 신상품", f"{new_count}개")

# Sort: new products first, then by first_seen_at desc
filtered = filtered.sort_values(["is_new", "first_seen_at"], ascending=[False, False])

# --- Display table ---
st.dataframe(
    filtered,
    use_container_width=True,
    column_config={
        "url": st.column_config.LinkColumn("URL"),
        "image_url": st.column_config.ImageColumn("이미지", width="small"),
        "site": st.column_config.TextColumn("사이트"),
        "상품명": st.column_config.TextColumn("상품명", width="large"),
        "price": st.column_config.NumberColumn("가격", format="₩%d"),
        "status": st.column_config.TextColumn("상태"),
        "category": st.column_config.TextColumn("카테고리"),
        "manufacturer": st.column_config.TextColumn("제조사"),
        "first_seen_at": st.column_config.DatetimeColumn("발견일", format="YYYY-MM-DD HH:mm"),
        "product_id": None,
        "name": None,
        "is_new": None,
    },
    hide_index=True,
)
