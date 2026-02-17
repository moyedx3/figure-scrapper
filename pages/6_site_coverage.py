"""Site coverage comparison page."""

import pandas as pd
import streamlit as st

from analytics.queries import (
    get_products_by_category_site,
    get_status_by_site,
    get_product_counts,
)
from analytics.charts import (
    category_site_heatmap,
    stacked_status_bar,
    SITE_COLORS,
)
from analytics.matching import get_saved_matches

st.header("사이트 커버리지")

# --- Category x Site heatmap ---
cat_site_df = get_products_by_category_site()

if cat_site_df.empty:
    st.info("카테고리 데이터가 없습니다.")
    st.stop()

st.plotly_chart(category_site_heatmap(cat_site_df), use_container_width=True)

st.divider()

# --- Unique vs Shared products ---
st.subheader("사이트별 독점 vs 공유 상품")

matches_df = get_saved_matches()
site_counts = get_product_counts()

if not matches_df.empty and not site_counts.empty:
    matched_ids_by_site: dict[str, int] = {}
    for site in matches_df["site"].unique():
        matched_ids_by_site[site] = matches_df[matches_df["site"] == site]["id"].nunique()

    rows = []
    for _, row in site_counts.iterrows():
        site = row["site"]
        total = row["count"]
        shared = matched_ids_by_site.get(site, 0)
        unique = total - shared
        rows.append({"사이트": site, "독점": unique, "공유": shared})

    coverage_df = pd.DataFrame(rows)

    col_left, col_right = st.columns(2)
    with col_left:
        import plotly.express as px
        from analytics.charts import LAYOUT_DEFAULTS

        melted = coverage_df.melt(
            id_vars="사이트", value_vars=["독점", "공유"], var_name="유형", value_name="수량"
        )
        fig = px.bar(
            melted,
            x="사이트",
            y="수량",
            color="유형",
            barmode="stack",
            color_discrete_map={"독점": "#3498DB", "공유": "#E67E22"},
        )
        fig.update_layout(
            title="사이트별 독점/공유 상품",
            xaxis_title="",
            yaxis_title="상품 수",
            **LAYOUT_DEFAULTS,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.dataframe(
            coverage_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "사이트": st.column_config.TextColumn("사이트"),
                "독점": st.column_config.NumberColumn("독점 상품"),
                "공유": st.column_config.NumberColumn("공유 상품"),
            },
        )
else:
    st.info("매칭 데이터가 없습니다. '가격 비교' 페이지에서 매칭을 먼저 실행하세요.")

st.divider()

# --- Site strengths ---
st.subheader("사이트별 강점 카테고리")

strengths = (
    cat_site_df.sort_values("count", ascending=False)
    .groupby("site")
    .head(3)
    .sort_values(["site", "count"], ascending=[True, False])
)

for site in sorted(strengths["site"].unique()):
    site_data = strengths[strengths["site"] == site]
    cats = ", ".join(
        f"{r['category']} ({r['count']}개)" for _, r in site_data.iterrows()
    )
    st.write(f"**{site}**: {cats}")

st.divider()

# --- Status distribution per site ---
st.subheader("사이트별 상태 분포")

status_df = get_status_by_site()
if not status_df.empty:
    st.plotly_chart(stacked_status_bar(status_df), use_container_width=True)

    # Show percentage table
    pivot = status_df.pivot_table(
        values="count", index="site", columns="status", fill_value=0
    )
    pivot["합계"] = pivot.sum(axis=1)
    for col in pivot.columns[:-1]:
        pivot[f"{col}%"] = (pivot[col] / pivot["합계"] * 100).round(1)

    st.dataframe(pivot, use_container_width=True)
else:
    st.info("상태 데이터가 없습니다.")
