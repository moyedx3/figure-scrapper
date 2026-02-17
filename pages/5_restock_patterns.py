"""Restock patterns analysis page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.queries import (
    get_restock_events,
    get_restock_with_duration,
    get_monthly_restock_counts,
    get_price_change_on_restock,
)
from analytics.charts import (
    LAYOUT_DEFAULTS,
    SITE_COLORS,
    restock_time_by_site_bar,
    monthly_restock_line,
)

st.header("재입고 패턴")

restock_df = get_restock_with_duration()

if restock_df.empty:
    st.info(
        "재입고 데이터가 아직 없습니다. "
        "스크래퍼를 운영하며 품절→재입고 전환이 감지되면 여기에 표시됩니다."
    )
    st.stop()

# --- Metrics ---
c1, c2, c3 = st.columns(3)
c1.metric("총 재입고 횟수", f"{len(restock_df):,}회")

with_duration = restock_df[restock_df["soldout_hours"].notna()]
if not with_duration.empty:
    c2.metric("평균 품절 기간", f"{with_duration['soldout_hours'].mean():.1f}시간")
    c3.metric("중앙값", f"{with_duration['soldout_hours'].median():.1f}시간")

st.divider()

# --- Recent restocks table ---
st.subheader("최근 재입고 상품")
st.dataframe(
    restock_df.head(50),
    use_container_width=True,
    column_config={
        "url": st.column_config.LinkColumn("URL"),
        "site": st.column_config.TextColumn("사이트"),
        "name": st.column_config.TextColumn("상품명"),
        "price": st.column_config.NumberColumn("가격", format="₩%d"),
        "manufacturer": st.column_config.TextColumn("제조사"),
        "restock_at": st.column_config.DatetimeColumn("재입고 일시", format="YYYY-MM-DD HH:mm"),
        "soldout_hours": st.column_config.NumberColumn("품절 기간 (시간)", format="%.1f"),
        "soldout_at": None,
    },
    hide_index=True,
)

st.divider()

# --- Avg restock time by site ---
col_left, col_right = st.columns(2)

with col_left:
    if not with_duration.empty:
        st.plotly_chart(restock_time_by_site_bar(restock_df), use_container_width=True)
    else:
        st.info("품절 기간 데이터가 부족합니다.")

# --- Monthly trend ---
with col_right:
    monthly_df = get_monthly_restock_counts()
    if not monthly_df.empty:
        st.plotly_chart(monthly_restock_line(monthly_df), use_container_width=True)
    else:
        st.info("월별 데이터가 부족합니다.")

st.divider()

# --- Price changes around restocks ---
st.subheader("재입고 시 가격 변동")
price_change_df = get_price_change_on_restock()

if not price_change_df.empty:
    price_change_df["가격변동"] = price_change_df["new_price"] - price_change_df["old_price"]
    price_change_df["변동률"] = (
        (price_change_df["가격변동"] / price_change_df["old_price"]) * 100
    ).round(1)

    c1, c2, c3 = st.columns(3)
    avg_change = price_change_df["가격변동"].mean()
    increases = (price_change_df["가격변동"] > 0).sum()
    decreases = (price_change_df["가격변동"] < 0).sum()

    c1.metric("평균 가격 변동", f"₩{avg_change:,.0f}")
    c2.metric("가격 인상", f"{increases}건")
    c3.metric("가격 인하", f"{decreases}건")

    fig = px.histogram(
        price_change_df,
        x="변동률",
        nbins=30,
        color="site",
        color_discrete_map=SITE_COLORS,
        barmode="overlay",
        opacity=0.7,
    )
    fig.update_layout(
        title="가격 변동률 분포 (%)",
        xaxis_title="변동률 (%)",
        yaxis_title="건수",
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("가격 변동 데이터가 아직 없습니다.")
