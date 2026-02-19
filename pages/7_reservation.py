"""Reservation accuracy analysis page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.queries import get_products_with_release_date
from analytics.charts import LAYOUT_DEFAULTS, SITE_COLORS

st.header("예약 정확도")

df = get_products_with_release_date()

if df.empty:
    st.info("발매일 데이터가 있는 상품이 없습니다.")
    st.stop()

# --- Parse dates and compute delays ---
df["release_date_parsed"] = pd.to_datetime(df["release_date"], errors="coerce")
df["first_seen_parsed"] = pd.to_datetime(df["first_seen_at"], errors="coerce")

# For products that have gone available after being preorder,
# compare release_date vs actual availability
# Use first_seen_at as a proxy when soldout_at is not available
has_dates = df[df["release_date_parsed"].notna()].copy()

if has_dates.empty:
    st.info("발매일을 파싱할 수 있는 상품이 없습니다.")
    st.stop()

# Compute delay: positive = late, negative = early
today = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
has_dates["expected"] = has_dates["release_date_parsed"]
has_dates["delay_days"] = (today - has_dates["release_date_parsed"]).dt.days

# Classify: released (past release date) vs upcoming
has_dates["분류"] = has_dates["delay_days"].apply(
    lambda d: "발매 완료" if d >= 0 else "발매 예정"
)

# --- Metrics ---
released = has_dates[has_dates["delay_days"] >= 0]
upcoming = has_dates[has_dates["delay_days"] < 0]
on_time = released[released["status"] == "available"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("발매일 있는 상품", f"{len(has_dates):,}개")
c2.metric("발매 완료", f"{len(released):,}개")
c3.metric("발매 예정", f"{len(upcoming):,}개")

if not released.empty:
    available_pct = len(on_time) / len(released) * 100
    c4.metric("구매 가능률", f"{available_pct:.1f}%")

st.divider()

# --- Upcoming releases ---
st.subheader("발매 예정 상품")
if not upcoming.empty:
    upcoming_sorted = upcoming.sort_values("release_date_parsed")
    st.dataframe(
        upcoming_sorted[["site", "name", "price", "manufacturer", "release_date", "status"]],
        use_container_width=True,
        column_config={
            "site": st.column_config.TextColumn("사이트"),
            "name": st.column_config.TextColumn("상품명"),
            "price": st.column_config.NumberColumn("가격", format="₩%d"),
            "manufacturer": st.column_config.TextColumn("제조사"),
            "release_date": st.column_config.TextColumn("발매일"),
            "status": st.column_config.TextColumn("상태"),
        },
        hide_index=True,
    )
else:
    st.info("발매 예정 상품이 없습니다.")

st.divider()

# --- Status of released products ---
st.subheader("발매 완료 상품 상태 분석")
if not released.empty:
    status_counts = released["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]

    from analytics.charts import STATUS_COLORS

    fig = px.pie(
        status_counts,
        values="count",
        names="status",
        color="status",
        color_discrete_map=STATUS_COLORS,
        hole=0.4,
    )
    fig.update_layout(title="발매 완료 상품의 현재 상태", **LAYOUT_DEFAULTS)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Delay by manufacturer ---
st.subheader("제조사별 발매 현황")

mfr_stats = (
    has_dates[has_dates["manufacturer"].notna() & (has_dates["manufacturer"] != "")]
    .groupby("manufacturer")
    .agg(
        total=("name", "count"),
        avg_delay=("delay_days", "mean"),
        released_count=("분류", lambda x: (x == "발매 완료").sum()),
    )
    .reset_index()
)
mfr_stats = mfr_stats[mfr_stats["total"] >= 3].sort_values("total", ascending=False).head(20)

if not mfr_stats.empty:
    fig = px.bar(
        mfr_stats,
        x="total",
        y="manufacturer",
        orientation="h",
        color="avg_delay",
        color_continuous_scale="RdYlGn_r",
        text="released_count",
    )
    fig.update_layout(
        title="제조사별 상품 수 (색상: 평균 발매 경과일)",
        xaxis_title="상품 수",
        yaxis=dict(categoryorder="total ascending"),
        coloraxis_colorbar=dict(title="경과일"),
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Delay by site ---
st.subheader("사이트별 발매 현황")

site_stats = (
    has_dates.groupby("site")
    .agg(
        total=("name", "count"),
        upcoming=("분류", lambda x: (x == "발매 예정").sum()),
        released=("분류", lambda x: (x == "발매 완료").sum()),
    )
    .reset_index()
)

if not site_stats.empty:
    melted = site_stats.melt(
        id_vars="site",
        value_vars=["upcoming", "released"],
        var_name="분류",
        value_name="수량",
    )
    melted["분류"] = melted["분류"].map({"upcoming": "발매 예정", "released": "발매 완료"})

    fig = px.bar(
        melted,
        x="site",
        y="수량",
        color="분류",
        barmode="group",
        color_discrete_map={"발매 예정": "#3498DB", "발매 완료": "#2ECC71"},
    )
    fig.update_layout(
        title="사이트별 발매 예정 vs 완료",
        xaxis_title="",
        yaxis_title="상품 수",
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)
