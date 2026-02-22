"""Plotly chart builders for the admin analytics dashboard."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from analytics.charts import LAYOUT_DEFAULTS, SITE_COLORS

# Admin-specific color constants
ALERT_TYPE_COLORS = {
    "new": "#2ECC71",
    "restock": "#3498DB",
    "price": "#F39C12",
    "soldout": "#E74C3C",
}

ALERT_TYPE_LABELS = {
    "new": "신상품",
    "restock": "재입고",
    "price": "가격변동",
    "soldout": "품절",
}


def user_growth_line(df: pd.DataFrame) -> go.Figure:
    """Cumulative user growth with daily new signups overlay."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["cumulative"],
        mode="lines+markers",
        name="누적 사용자",
        fill="tozeroy",
        line=dict(color="#3498DB"),
    ))
    fig.add_trace(go.Bar(
        x=df["date"], y=df["new_users"],
        name="일별 신규",
        marker_color="#2ECC71",
        opacity=0.5,
        yaxis="y2",
    ))
    fig.update_layout(
        title="사용자 성장 추이",
        xaxis_title="",
        yaxis_title="누적 사용자 수",
        yaxis2=dict(title="일별 신규", overlaying="y", side="right"),
        **LAYOUT_DEFAULTS,
    )
    return fig


def alert_preference_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar of alert type subscription counts."""
    fig = px.bar(
        df, x="사용자수", y="알림유형",
        orientation="h",
        color="알림유형",
        color_discrete_map={
            "신상품": ALERT_TYPE_COLORS["new"],
            "재입고": ALERT_TYPE_COLORS["restock"],
            "가격변동": ALERT_TYPE_COLORS["price"],
            "품절": ALERT_TYPE_COLORS["soldout"],
        },
    )
    fig.update_layout(
        title="알림 유형별 구독 현황",
        showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def top_keywords_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar of most popular watch keywords."""
    display = df.head(20).sort_values("user_count")
    fig = px.bar(
        display, x="user_count", y="keyword",
        orientation="h",
        color="user_count",
        color_continuous_scale="Blues",
    )
    fig.update_layout(
        title="인기 관심 키워드 TOP 20",
        xaxis_title="사용자 수",
        yaxis_title="",
        coloraxis_showscale=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def watches_distribution_bar(df: pd.DataFrame) -> go.Figure:
    """Bar chart of watch count distribution per user."""
    fig = px.bar(
        df, x="watch_count", y="user_count",
        labels={"watch_count": "관심 키워드 수", "user_count": "사용자 수"},
    )
    fig.update_layout(
        title="사용자별 관심 키워드 분포",
        **LAYOUT_DEFAULTS,
    )
    return fig


def alert_volume_over_time_area(df: pd.DataFrame) -> go.Figure:
    """Stacked area chart of daily alert volume by type."""
    df = df.copy()
    df["change_type"] = df["change_type"].map(ALERT_TYPE_LABELS).fillna(df["change_type"])
    fig = px.area(
        df, x="date", y="count", color="change_type",
        color_discrete_map={v: ALERT_TYPE_COLORS[k] for k, v in ALERT_TYPE_LABELS.items()},
    )
    fig.update_layout(
        title="일별 알림 발송량",
        xaxis_title="",
        yaxis_title="알림 수",
        **LAYOUT_DEFAULTS,
    )
    return fig


def alert_volume_by_site_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar of alert counts per site."""
    fig = px.bar(
        df.sort_values("count"),
        x="count", y="site",
        orientation="h",
        color="site",
        color_discrete_map=SITE_COLORS,
    )
    fig.update_layout(
        title="사이트별 알림 발송량",
        showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


def delivery_latency_histogram(df: pd.DataFrame) -> go.Figure:
    """Histogram of delivery latency in seconds."""
    fig = px.histogram(
        df, x="latency_seconds",
        nbins=50,
        labels={"latency_seconds": "지연 시간 (초)"},
        barmode="overlay",
        opacity=0.7,
    )
    fig.update_layout(
        title="알림 전송 지연 분포",
        xaxis_title="지연 시간 (초)",
        yaxis_title="건수",
        **LAYOUT_DEFAULTS,
    )
    return fig


def scrape_activity_heatmap(df: pd.DataFrame) -> go.Figure:
    """Heatmap of scrape activity by date and hour."""
    pivot = df.pivot_table(values="count", index="hour", columns="date", fill_value=0)
    fig = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale="Blues",
        aspect="auto",
        labels=dict(x="날짜", y="시간 (KST)", color="업데이트 수"),
    )
    fig.update_layout(
        title="스크래핑 활동 히트맵 (최근 14일)",
        **LAYOUT_DEFAULTS,
    )
    return fig
