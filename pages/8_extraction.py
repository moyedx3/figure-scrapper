"""Extraction status and monitoring page."""

import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from analytics.charts import LAYOUT_DEFAULTS, SITE_COLORS
from config import DB_PATH, EXTRACTION_MODEL

st.header("추출 현황")


@st.cache_data(ttl=300)
def get_extraction_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    stats = {}

    # Overall counts
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN extracted_at IS NOT NULL THEN 1 ELSE 0 END) as extracted,
            SUM(CASE WHEN extraction_method = 'rules' THEN 1 ELSE 0 END) as rules_count,
            SUM(CASE WHEN extraction_method = 'llm' THEN 1 ELSE 0 END) as llm_count,
            AVG(CASE WHEN extraction_confidence IS NOT NULL THEN extraction_confidence END) as avg_confidence
        FROM products
    """).fetchone()
    stats["total"] = row[0]
    stats["extracted"] = row[1]
    stats["rules_count"] = row[2]
    stats["llm_count"] = row[3]
    stats["avg_confidence"] = row[4]

    # Per-site extraction
    stats["by_site"] = pd.read_sql_query("""
        SELECT site,
               COUNT(*) as total,
               SUM(CASE WHEN extracted_at IS NOT NULL THEN 1 ELSE 0 END) as extracted,
               SUM(CASE WHEN series IS NOT NULL THEN 1 ELSE 0 END) as has_series,
               SUM(CASE WHEN character_name IS NOT NULL THEN 1 ELSE 0 END) as has_character,
               SUM(CASE WHEN extracted_manufacturer IS NOT NULL THEN 1 ELSE 0 END) as has_manufacturer,
               SUM(CASE WHEN scale IS NOT NULL THEN 1 ELSE 0 END) as has_scale,
               SUM(CASE WHEN product_line IS NOT NULL THEN 1 ELSE 0 END) as has_product_line,
               AVG(extraction_confidence) as avg_confidence
        FROM products
        GROUP BY site
        ORDER BY site
    """, conn)

    # Field coverage
    stats["field_coverage"] = pd.read_sql_query("""
        SELECT
            SUM(CASE WHEN series IS NOT NULL THEN 1 ELSE 0 END) as series,
            SUM(CASE WHEN character_name IS NOT NULL THEN 1 ELSE 0 END) as character_name,
            SUM(CASE WHEN extracted_manufacturer IS NOT NULL THEN 1 ELSE 0 END) as manufacturer,
            SUM(CASE WHEN scale IS NOT NULL THEN 1 ELSE 0 END) as scale,
            SUM(CASE WHEN version IS NOT NULL THEN 1 ELSE 0 END) as version,
            SUM(CASE WHEN product_line IS NOT NULL THEN 1 ELSE 0 END) as product_line,
            COUNT(*) as total
        FROM products WHERE extracted_at IS NOT NULL
    """, conn)

    # Confidence distribution
    stats["confidence_dist"] = pd.read_sql_query("""
        SELECT extraction_confidence as confidence
        FROM products
        WHERE extraction_confidence IS NOT NULL
    """, conn)

    # Top series
    stats["top_series"] = pd.read_sql_query("""
        SELECT series, COUNT(*) as count, COUNT(DISTINCT site) as sites
        FROM products
        WHERE series IS NOT NULL
        GROUP BY series
        ORDER BY count DESC
        LIMIT 20
    """, conn)

    # Unextracted products
    stats["unextracted"] = pd.read_sql_query("""
        SELECT site, name, category
        FROM products
        WHERE extracted_at IS NULL
        LIMIT 50
    """, conn)

    conn.close()
    return stats


stats = get_extraction_stats()

# --- Top metrics ---
c1, c2, c3, c4 = st.columns(4)
pct = stats["extracted"] / stats["total"] * 100 if stats["total"] else 0
c1.metric("추출 완료", f"{stats['extracted']:,} / {stats['total']:,}", f"{pct:.1f}%")
c2.metric("규칙 기반", f"{stats['rules_count']:,}")
c3.metric("LLM 추출", f"{stats['llm_count']:,}")
c4.metric("평균 신뢰도", f"{stats['avg_confidence']:.1%}" if stats['avg_confidence'] else "N/A")

st.divider()

# --- Field coverage ---
st.subheader("필드 커버리지")
field_df = stats["field_coverage"]
if not field_df.empty:
    total = field_df["total"].iloc[0]
    fields = ["series", "character_name", "manufacturer", "scale", "version", "product_line"]
    labels = ["작품명", "캐릭터", "제조사", "스케일", "버전", "상품라인"]
    values = [field_df[f].iloc[0] for f in fields]
    pcts = [v / total * 100 if total else 0 for v in values]

    fig = go.Figure(go.Bar(
        x=pcts,
        y=labels,
        orientation="h",
        text=[f"{v:,} ({p:.1f}%)" for v, p in zip(values, pcts)],
        textposition="auto",
        marker_color=["#4ecdc4", "#45b7d1", "#f9ca24", "#f0932b", "#eb4d4b", "#6c5ce7"],
    ))
    fig.update_layout(
        xaxis_title="커버리지 (%)",
        xaxis=dict(range=[0, 100]),
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Per-site extraction ---
st.subheader("사이트별 추출 현황")
site_df = stats["by_site"]
if not site_df.empty:
    site_df["coverage"] = (site_df["extracted"] / site_df["total"] * 100).round(1)

    fig = go.Figure()
    for _, row in site_df.iterrows():
        fig.add_trace(go.Bar(
            name=row["site"],
            x=["추출율", "작품명", "캐릭터", "제조사", "스케일", "상품라인"],
            y=[
                row["coverage"],
                row["has_series"] / row["total"] * 100,
                row["has_character"] / row["total"] * 100,
                row["has_manufacturer"] / row["total"] * 100,
                row["has_scale"] / row["total"] * 100,
                row["has_product_line"] / row["total"] * 100,
            ],
            marker_color=SITE_COLORS.get(row["site"], "#999"),
        ))
    fig.update_layout(
        barmode="group",
        yaxis_title="커버리지 (%)",
        **LAYOUT_DEFAULTS,
    )
    st.plotly_chart(fig, use_container_width=True)

# --- Confidence distribution ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("신뢰도 분포")
    conf_df = stats["confidence_dist"]
    if not conf_df.empty:
        fig = px.histogram(
            conf_df, x="confidence", nbins=20,
            color_discrete_sequence=["#4ecdc4"],
        )
        fig.update_layout(
            xaxis_title="추출 신뢰도",
            yaxis_title="상품 수",
            **LAYOUT_DEFAULTS,
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("인기 작품 (시리즈)")
    series_df = stats["top_series"]
    if not series_df.empty:
        st.dataframe(
            series_df.rename(columns={
                "series": "작품명",
                "count": "상품 수",
                "sites": "사이트 수",
            }),
            hide_index=True,
            use_container_width=True,
        )

# --- Unextracted products ---
unextracted_df = stats["unextracted"]
if not unextracted_df.empty:
    st.divider()
    st.subheader(f"미추출 상품 (상위 50개)")
    st.dataframe(
        unextracted_df.rename(columns={
            "site": "사이트",
            "name": "상품명",
            "category": "카테고리",
        }),
        hide_index=True,
        use_container_width=True,
    )

# --- Sonnet extraction sample test ---
st.divider()
st.subheader(f"🧪 추출 샘플 테스트 ({EXTRACTION_MODEL})")

col_sample_btn, col_sample_n = st.columns([1, 2])
with col_sample_n:
    sample_n = st.slider("사이트당 샘플 수", 2, 20, 10)

with col_sample_btn:
    run_sample = st.button("샘플 추출 실행", type="primary")

if run_sample:
    from extraction.page_fetcher import fetch_product_detail
    from extraction.llm import extract_with_llm

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sample_products = []
    for site in ["figurepresso", "comicsart", "maniahouse", "rabbits", "ttabbaemall"]:
        rows = conn.execute(
            "SELECT id, site, name, manufacturer, category, price, url "
            "FROM products WHERE site = ? ORDER BY RANDOM() LIMIT ?",
            (site, sample_n),
        ).fetchall()
        sample_products.extend([dict(r) for r in rows])
    conn.close()

    total = len(sample_products)
    progress = st.progress(0, text="추출 중...")
    results = []

    for i, p in enumerate(sample_products):
        # Hybrid: try fetching product detail page first
        page_detail = None
        if p.get("url"):
            try:
                page_detail = fetch_product_detail(p["url"], p["site"])
            except Exception:
                pass

        attrs = extract_with_llm(
            p["name"], p["site"], p["category"] or "", p["manufacturer"],
            page_detail=page_detail,
        )
        method = "llm+page" if page_detail else "llm"
        results.append({**p, **attrs.model_dump(), "_method": method, "_page_detail": page_detail})
        progress.progress((i + 1) / total, text=f"추출 중... {i+1}/{total}")

    progress.empty()

    page_count = sum(1 for r in results if r["_method"] == "llm+page")
    st.success(f"{total}개 상품 추출 완료 (페이지 활용: {page_count}/{total})")

    # Store in session for display
    st.session_state["sample_results"] = results

if "sample_results" in st.session_state:
    results = st.session_state["sample_results"]

    # Filter controls
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        type_filter = st.multiselect(
            "유형 필터",
            options=sorted({r["product_type"] for r in results if r.get("product_type")}),
            default=None,
            key="sample_type_filter",
        )
    with col_f2:
        site_filter = st.multiselect(
            "사이트 필터",
            options=sorted({r["site"] for r in results}),
            default=None,
            key="sample_site_filter",
        )
    with col_f3:
        method_filter = st.multiselect(
            "추출 방법",
            options=sorted({r.get("_method", "llm") for r in results}),
            default=None,
            key="sample_method_filter",
        )

    filtered = results
    if type_filter:
        filtered = [r for r in filtered if r.get("product_type") in type_filter]
    if method_filter:
        filtered = [r for r in filtered if r.get("_method", "llm") in method_filter]
    if site_filter:
        filtered = [r for r in filtered if r["site"] in site_filter]

    for i, r in enumerate(filtered):
        price_str = f"₩{int(r['price']):,}" if r.get("price") else "?"
        type_emoji = {
            "scale_figure": "🗿", "prize_figure": "🎰", "nendoroid": "🧸",
            "figma": "🦾", "action_figure": "💪", "plushie": "🧶",
            "acrylic": "💎", "keychain": "🔑", "badge": "📌",
            "sticker": "🏷️", "model_kit": "🔧", "goods_other": "📦",
            "blanket": "🧣",
        }.get(r.get("product_type", ""), "❓")

        method = r.get("_method", "llm")
        method_badge = "📄+🤖" if method == "llm+page" else "🤖"
        with st.expander(
            f"{type_emoji} {method_badge} **[{r['site']}]** {r['name']}  —  {price_str}"
        ):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**추출 결과**")
                st.markdown(f"- **유형**: `{r.get('product_type')}`")
                st.markdown(f"- **작품**: {r.get('series') or '—'}")
                st.markdown(f"- **캐릭터**: {r.get('character_name') or '—'}")
                st.markdown(f"- **제조사**: {r.get('manufacturer') or '—'}")
            with col_b:
                st.markdown("**상세**")
                st.markdown(f"- **스케일**: {r.get('scale') or '—'}")
                st.markdown(f"- **라인**: {r.get('product_line') or '—'}")
                st.markdown(f"- **버전**: {r.get('version') or '—'}")
                if r.get("url"):
                    st.markdown(f"- 🔗 [상품 페이지 열기]({r['url']})")

            # Show page detail info if available
            page_detail = r.get("_page_detail")
            if page_detail:
                st.markdown("---")
                st.markdown(f"**📄 페이지 추출 데이터** (`{method}`)")
                detail_parts = []
                for k, v in page_detail.items():
                    detail_parts.append(f"`{k}`: {v}")
                st.markdown(" · ".join(detail_parts))

    # Summary stats
    st.divider()
    types = [r.get("product_type") for r in results if r.get("product_type")]
    if types:
        from collections import Counter
        type_counts = Counter(types).most_common()
        st.markdown("**유형 분포**: " + " · ".join(
            f"`{t}` ({c})" for t, c in type_counts
        ))
