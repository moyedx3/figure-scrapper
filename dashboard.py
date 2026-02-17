"""Figure Scraper Analytics Dashboard — Streamlit entrypoint."""

import streamlit as st

st.set_page_config(
    page_title="피규어 스크래퍼 대시보드",
    page_icon="📊",
    layout="wide",
)

# --- Sidebar ---
st.sidebar.title("피규어 분석 대시보드")

# --- Navigation ---
pages = [
    st.Page("pages/1_overview.py", title="개요", icon="📊", default=True),
    st.Page("pages/2_new_products.py", title="신상품 피드", icon="🆕"),
    st.Page("pages/3_price_compare.py", title="가격 비교", icon="💰"),
    st.Page("pages/4_soldout_velocity.py", title="품절 속도", icon="⚡"),
    st.Page("pages/5_restock_patterns.py", title="재입고 패턴", icon="🔄"),
    st.Page("pages/6_site_coverage.py", title="사이트 커버리지", icon="🗺️"),
    st.Page("pages/7_reservation.py", title="예약 정확도", icon="📅"),
    st.Page("pages/8_extraction.py", title="추출 현황", icon="🔬"),
]

pg = st.navigation(pages)
pg.run()
