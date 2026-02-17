"""Overview / Summary dashboard page."""

import streamlit as st

from analytics.queries import (
    get_count_by_change_type,
    get_price_distribution,
    get_product_counts,
    get_recent_changes,
    get_status_breakdown,
    get_total_products,
)
from analytics.charts import (
    price_distribution_histogram,
    products_by_site_bar,
    status_pie_chart,
)

st.header("개요")

# --- Top metrics ---
total = get_total_products()
counts_24h = get_count_by_change_type(days=1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("전체 상품", f"{total:,}")
c2.metric("신상품 (24h)", counts_24h["new"])
c3.metric("재입고 (24h)", counts_24h["restocks"])
c4.metric("품절 (24h)", counts_24h["soldouts"])

st.divider()

# --- Charts row ---
col_left, col_right = st.columns(2)

with col_left:
    site_df = get_product_counts()
    if not site_df.empty:
        st.plotly_chart(products_by_site_bar(site_df), use_container_width=True)
    else:
        st.info("사이트별 상품 데이터가 없습니다.")

with col_right:
    status_df = get_status_breakdown()
    if not status_df.empty:
        st.plotly_chart(status_pie_chart(status_df), use_container_width=True)
    else:
        st.info("상태 데이터가 없습니다.")

st.divider()

# --- Price distribution ---
price_df = get_price_distribution()
if not price_df.empty:
    st.plotly_chart(price_distribution_histogram(price_df), use_container_width=True)
else:
    st.info("가격 데이터가 없습니다.")

st.divider()

# --- Recent changes table ---
st.subheader("최근 변경사항 (7일)")
changes_df = get_recent_changes(days=7)
if not changes_df.empty:
    st.dataframe(
        changes_df,
        use_container_width=True,
        column_config={
            "url": st.column_config.LinkColumn("URL"),
            "changed_at": st.column_config.DatetimeColumn("변경일시", format="YYYY-MM-DD HH:mm"),
            "change_type": st.column_config.TextColumn("변경유형"),
            "old_value": st.column_config.TextColumn("이전값"),
            "new_value": st.column_config.TextColumn("새값"),
            "site": st.column_config.TextColumn("사이트"),
            "name": st.column_config.TextColumn("상품명"),
            "price": st.column_config.NumberColumn("가격", format="₩%d"),
        },
    )
else:
    st.info("최근 7일간 변경사항이 없습니다.")
