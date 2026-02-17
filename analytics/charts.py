"""Reusable Plotly chart builders for the dashboard."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Consistent color palette
SITE_COLORS = {
    "figurepresso": "#FF6B6B",
    "comicsart": "#4ECDC4",
    "maniahouse": "#45B7D1",
    "rabbits": "#96CEB4",
    "ttabbaemall": "#FFEAA7",
}

STATUS_COLORS = {
    "available": "#2ECC71",
    "soldout": "#E74C3C",
    "preorder": "#3498DB",
}

LAYOUT_DEFAULTS = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="sans-serif"),
    margin=dict(l=20, r=20, t=40, b=20),
)


def status_pie_chart(df: pd.DataFrame) -> go.Figure:
    fig = px.pie(
        df,
        values="count",
        names="status",
        color="status",
        color_discrete_map=STATUS_COLORS,
        hole=0.4,
    )
    fig.update_layout(title="상태별 분포", **LAYOUT_DEFAULTS)
    return fig


def products_by_site_bar(df: pd.DataFrame) -> go.Figure:
    fig = px.bar(
        df,
        x="count",
        y="site",
        orientation="h",
        color="site",
        color_discrete_map=SITE_COLORS,
    )
    fig.update_layout(
        title="사이트별 상품 수",
        showlegend=False,
        yaxis=dict(categoryorder="total ascending"),
        **LAYOUT_DEFAULTS,
    )
    return fig


def price_distribution_histogram(df: pd.DataFrame) -> go.Figure:
    # Filter out corrupted prices (likely concatenated values from scraping)
    q99 = df["price"].quantile(0.99)
    cap = max(q99, 3_000_000)  # at least 3M to keep high-end figures visible
    clean = df[df["price"] <= cap]
    n_outliers = len(df) - len(clean)

    fig = px.histogram(
        clean,
        x="price",
        color="site",
        nbins=50,
        color_discrete_map=SITE_COLORS,
        barmode="overlay",
        opacity=0.7,
    )
    title = "가격 분포"
    if n_outliers > 0:
        title += f" (이상치 {n_outliers}개 제외)"
    fig.update_layout(
        title=title,
        xaxis_title="가격 (원)",
        yaxis_title="상품 수",
        xaxis=dict(tickformat=",d"),
        **LAYOUT_DEFAULTS,
    )
    return fig


def soldout_velocity_histogram(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df,
        x="hours_to_soldout",
        nbins=40,
        color="site",
        color_discrete_map=SITE_COLORS,
        barmode="overlay",
        opacity=0.7,
    )
    fig.update_layout(
        title="품절까지 소요 시간 분포",
        xaxis_title="시간 (hours)",
        yaxis_title="상품 수",
        **LAYOUT_DEFAULTS,
    )
    return fig


def velocity_by_group_bar(df: pd.DataFrame, group_col: str, title: str) -> go.Figure:
    grouped = (
        df.groupby(group_col)["hours_to_soldout"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_hours", "count": "product_count"})
        .sort_values("avg_hours")
    )
    # Only show groups with enough data
    grouped = grouped[grouped["product_count"] >= 3].tail(20)

    fig = px.bar(
        grouped,
        x="avg_hours",
        y=group_col,
        orientation="h",
        text="product_count",
        color="avg_hours",
        color_continuous_scale="RdYlGn_r",
    )
    fig.update_layout(
        title=title,
        xaxis_title="평균 품절 시간 (hours)",
        coloraxis_showscale=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def price_vs_velocity_scatter(df: pd.DataFrame) -> go.Figure:
    fig = px.scatter(
        df,
        x="price",
        y="hours_to_soldout",
        color="site",
        color_discrete_map=SITE_COLORS,
        opacity=0.6,
        hover_data=["name"],
    )
    fig.update_layout(
        title="가격 vs 품절 속도",
        xaxis_title="가격 (원)",
        yaxis_title="품절까지 시간 (hours)",
        **LAYOUT_DEFAULTS,
    )
    return fig


def restock_time_by_site_bar(df: pd.DataFrame) -> go.Figure:
    avg = (
        df[df["soldout_hours"].notna()]
        .groupby("site")["soldout_hours"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_hours", "count": "restock_count"})
        .sort_values("avg_hours")
    )
    fig = px.bar(
        avg,
        x="avg_hours",
        y="site",
        orientation="h",
        color="site",
        color_discrete_map=SITE_COLORS,
        text="restock_count",
    )
    fig.update_layout(
        title="사이트별 평균 재입고 시간",
        xaxis_title="평균 품절 기간 (hours)",
        showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def monthly_restock_line(df: pd.DataFrame) -> go.Figure:
    fig = px.line(
        df,
        x="month",
        y="count",
        color="site",
        color_discrete_map=SITE_COLORS,
        markers=True,
    )
    fig.update_layout(
        title="월별 재입고 횟수",
        xaxis_title="",
        yaxis_title="재입고 횟수",
        **LAYOUT_DEFAULTS,
    )
    return fig


def category_site_heatmap(df: pd.DataFrame) -> go.Figure:
    pivot = df.pivot_table(
        values="count", index="category", columns="site", fill_value=0
    )
    fig = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale="Blues",
        aspect="auto",
    )
    fig.update_layout(
        title="카테고리 x 사이트 상품 수",
        **LAYOUT_DEFAULTS,
    )
    return fig


def stacked_status_bar(df: pd.DataFrame) -> go.Figure:
    fig = px.bar(
        df,
        x="site",
        y="count",
        color="status",
        color_discrete_map=STATUS_COLORS,
        barmode="stack",
    )
    fig.update_layout(
        title="사이트별 상태 분포",
        xaxis_title="",
        yaxis_title="상품 수",
        **LAYOUT_DEFAULTS,
    )
    return fig
