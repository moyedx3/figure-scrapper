"""Soldout velocity analysis page."""

import streamlit as st

from analytics.queries import get_soldout_velocity
from analytics.charts import (
    soldout_velocity_histogram,
    velocity_by_group_bar,
    price_vs_velocity_scatter,
)

st.header("품절 속도")

df = get_soldout_velocity()

if df.empty:
    st.info(
        "품절 데이터가 아직 부족합니다. "
        "스크래퍼를 며칠 운영하면 품절 속도 분석이 가능합니다."
    )
    st.stop()

# --- Filters ---
col1, col2 = st.columns(2)
with col1:
    sites = st.multiselect(
        "사이트", options=sorted(df["site"].unique()), default=None, key="vel_site"
    )
with col2:
    if df["price"].notna().any():
        prices = df["price"].dropna()
        min_p, max_p = int(prices.min()), int(prices.max())
        if min_p < max_p:
            price_range = st.slider(
                "가격 범위", min_p, max_p, (min_p, max_p), step=1000, key="vel_price"
            )
            df = df[(df["price"] >= price_range[0]) & (df["price"] <= price_range[1])]

if sites:
    df = df[df["site"].isin(sites)]

# --- Metrics ---
c1, c2, c3 = st.columns(3)
c1.metric("분석 상품 수", f"{len(df):,}개")
c2.metric("평균 품절 시간", f"{df['hours_to_soldout'].mean():.1f}시간")
c3.metric("중앙값", f"{df['hours_to_soldout'].median():.1f}시간")

st.divider()

# --- Histogram ---
st.plotly_chart(soldout_velocity_histogram(df), use_container_width=True)

st.divider()

# --- Breakdowns ---
col_left, col_right = st.columns(2)

with col_left:
    st.plotly_chart(
        velocity_by_group_bar(df, "manufacturer", "제조사별 평균 품절 시간 (Top 20)"),
        use_container_width=True,
    )

with col_right:
    st.plotly_chart(
        velocity_by_group_bar(df, "site", "사이트별 평균 품절 시간"),
        use_container_width=True,
    )

st.divider()

# --- Price vs Velocity scatter ---
st.plotly_chart(price_vs_velocity_scatter(df), use_container_width=True)
