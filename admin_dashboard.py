"""Admin Analytics Dashboard — password-protected Telegram bot usage metrics."""

import os

import streamlit as st

st.set_page_config(
    page_title="관리자 대시보드",
    page_icon="🔒",
    layout="wide",
)

# ── Password Gate ──────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if not ADMIN_PASSWORD:
    st.error("ADMIN_PASSWORD 환경 변수가 설정되지 않았습니다.")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 관리자 대시보드")
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if password:
        if password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()

# ── Sidebar ────────────────────────────────────────────────────────────────

st.sidebar.title("🔒 관리자 대시보드")
st.sidebar.caption("Telegram 봇 사용 분석")

if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("🚪 로그아웃"):
    st.session_state.authenticated = False
    st.rerun()

# ── Tabs ───────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "👥 사용자 현황",
    "🔔 알림 설정 & 관심",
    "📨 메시지 전송",
    "🛠️ 시스템 상태",
])

# ── Tab 1: User Overview ──────────────────────────────────────────────────

with tab1:
    from analytics.admin_queries import (
        get_user_counts, get_user_growth,
        get_recent_signups, get_churned_users,
    )
    from analytics.admin_charts import user_growth_line

    st.header("사용자 현황")

    counts = get_user_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("전체 사용자", counts["total"])
    c2.metric("활성 사용자", counts["active"])
    c3.metric("비활성 (차단)", counts["inactive"])

    st.divider()

    # Growth chart
    growth_df = get_user_growth()
    if not growth_df.empty:
        st.plotly_chart(user_growth_line(growth_df), use_container_width=True)
    else:
        st.info("사용자 가입 데이터가 없습니다.")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("최근 가입")
        recent_df = get_recent_signups(20)
        if not recent_df.empty:
            st.dataframe(
                recent_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "chat_id": st.column_config.NumberColumn("Chat ID"),
                    "username": st.column_config.TextColumn("사용자명"),
                    "is_active": st.column_config.CheckboxColumn("활성"),
                    "alert_new": st.column_config.CheckboxColumn("신상품"),
                    "alert_restock": st.column_config.CheckboxColumn("재입고"),
                    "alert_price": st.column_config.CheckboxColumn("가격"),
                    "alert_soldout": st.column_config.CheckboxColumn("품절"),
                    "created_at": st.column_config.TextColumn("가입일시"),
                    "updated_at": st.column_config.TextColumn("최근 활동"),
                },
            )
        else:
            st.info("가입 사용자가 없습니다.")

    with col_right:
        st.subheader("이탈 사용자")
        churned_df = get_churned_users()
        if not churned_df.empty:
            st.dataframe(
                churned_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "chat_id": st.column_config.NumberColumn("Chat ID"),
                    "username": st.column_config.TextColumn("사용자명"),
                    "created_at": st.column_config.TextColumn("가입일시"),
                    "churned_at": st.column_config.TextColumn("이탈일시"),
                },
            )
        else:
            st.info("이탈 사용자가 없습니다.")

# ── Tab 2: Alert Preferences & Watches ────────────────────────────────────

with tab2:
    from analytics.admin_queries import (
        get_alert_preference_counts, get_top_watch_keywords,
        get_watches_per_user_distribution, get_watch_adoption_rate,
    )
    from analytics.admin_charts import (
        alert_preference_bar, top_keywords_bar,
        watches_distribution_bar,
    )

    st.header("알림 설정 & 관심 키워드")

    adoption = get_watch_adoption_rate()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("활성 사용자", adoption["total"])
    c2.metric("관심 키워드 사용자", adoption["with_watches"])
    c3.metric("채택률", f"{adoption['pct']}%")
    c4.metric("총 키워드 등록", adoption["total_watches"])

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        pref_df = get_alert_preference_counts()
        if not pref_df.empty:
            st.plotly_chart(alert_preference_bar(pref_df), use_container_width=True)
        else:
            st.info("알림 설정 데이터가 없습니다.")

    with col_right:
        dist_df = get_watches_per_user_distribution()
        if not dist_df.empty:
            st.plotly_chart(watches_distribution_bar(dist_df), use_container_width=True)
        else:
            st.info("관심 키워드 분포 데이터가 없습니다.")

    st.divider()

    st.subheader("인기 관심 키워드")
    keywords_df = get_top_watch_keywords(30)
    if not keywords_df.empty:
        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            st.plotly_chart(top_keywords_bar(keywords_df), use_container_width=True)
        with col_table:
            st.dataframe(
                keywords_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "keyword": st.column_config.TextColumn("키워드"),
                    "user_count": st.column_config.NumberColumn("사용자 수"),
                },
            )
    else:
        st.info("등록된 관심 키워드가 없습니다.")

# ── Tab 3: Message Delivery ───────────────────────────────────────────────

with tab3:
    from analytics.admin_queries import (
        get_alert_volume_by_type, get_alert_volume_over_time,
        get_delivery_latency, get_pending_queue_depth,
        get_alert_volume_by_site,
    )
    from analytics.admin_charts import (
        alert_volume_over_time_area, alert_volume_by_site_bar,
        delivery_latency_histogram, ALERT_TYPE_LABELS,
    )

    st.header("메시지 전송 현황")
    st.caption("⚠️ 봇이 전송 완료된 알림은 7일 후 자동 삭제됩니다.")

    # Queue depth warning
    queue = get_pending_queue_depth()
    if queue["pending"] > 0:
        st.warning(
            f"⚠️ 미전송 알림: {queue['pending']}건 "
            f"(최초 생성: {queue['oldest'] or 'N/A'})"
        )

    # Volume metrics
    vol_df = get_alert_volume_by_type()
    if not vol_df.empty:
        total_sent = int(vol_df["count"].sum())
        cols = st.columns(len(vol_df) + 1)
        cols[0].metric("총 전송", f"{total_sent:,}")
        for i, (_, row) in enumerate(vol_df.iterrows()):
            label = ALERT_TYPE_LABELS.get(row["change_type"], row["change_type"])
            cols[i + 1].metric(label, f"{int(row['count']):,}")
    else:
        st.info("전송된 알림이 없습니다.")

    st.divider()

    # Volume over time
    time_df = get_alert_volume_over_time(days=30)
    if not time_df.empty:
        st.plotly_chart(alert_volume_over_time_area(time_df), use_container_width=True)

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        site_df = get_alert_volume_by_site()
        if not site_df.empty:
            st.plotly_chart(alert_volume_by_site_bar(site_df), use_container_width=True)
        else:
            st.info("사이트별 알림 데이터가 없습니다.")

    with col_right:
        latency_df = get_delivery_latency()
        if not latency_df.empty:
            avg_latency = latency_df["latency_seconds"].mean()
            p95_latency = latency_df["latency_seconds"].quantile(0.95)
            lc1, lc2 = st.columns(2)
            lc1.metric("평균 전송 지연", f"{avg_latency:.1f}초")
            lc2.metric("P95 전송 지연", f"{p95_latency:.1f}초")
            st.plotly_chart(
                delivery_latency_histogram(latency_df), use_container_width=True
            )
        else:
            st.info("전송 지연 데이터가 없습니다.")

# ── Tab 4: System Health ──────────────────────────────────────────────────

with tab4:
    from analytics.admin_queries import (
        get_last_scrape_per_site, get_recent_status_changes,
        get_db_table_sizes, get_db_file_size_mb,
        get_scrape_activity_heatmap,
    )
    from analytics.admin_charts import scrape_activity_heatmap

    st.header("시스템 상태")

    db_size = get_db_file_size_mb()
    table_sizes = get_db_table_sizes()
    total_rows = int(table_sizes["rows"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("DB 파일 크기", f"{db_size} MB")
    c2.metric("총 행 수", f"{total_rows:,}")
    c3.metric("테이블 수", len(table_sizes))

    st.divider()

    # Last scrape per site
    st.subheader("사이트별 마지막 스크래핑")
    scrape_df = get_last_scrape_per_site()
    if not scrape_df.empty:
        st.dataframe(
            scrape_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "site": st.column_config.TextColumn("사이트"),
                "last_scrape": st.column_config.TextColumn("마지막 스크래핑"),
                "product_count": st.column_config.NumberColumn("상품 수", format="%d"),
            },
        )
    else:
        st.info("스크래핑 데이터가 없습니다.")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("테이블별 행 수")
        st.dataframe(
            table_sizes,
            use_container_width=True,
            hide_index=True,
            column_config={
                "table": st.column_config.TextColumn("테이블"),
                "rows": st.column_config.NumberColumn("행 수", format="%d"),
            },
        )

    with col_right:
        heatmap_df = get_scrape_activity_heatmap(days=14)
        if not heatmap_df.empty:
            st.plotly_chart(
                scrape_activity_heatmap(heatmap_df), use_container_width=True
            )
        else:
            st.info("스크래핑 활동 데이터가 없습니다.")

    st.divider()

    st.subheader("최근 상태 변경 (50건)")
    changes_df = get_recent_status_changes(50)
    if not changes_df.empty:
        st.dataframe(
            changes_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "site": st.column_config.TextColumn("사이트"),
                "name": st.column_config.TextColumn("상품명"),
                "change_type": st.column_config.TextColumn("변경유형"),
                "old_value": st.column_config.TextColumn("이전값"),
                "new_value": st.column_config.TextColumn("새값"),
                "changed_at": st.column_config.TextColumn("변경일시"),
            },
        )
    else:
        st.info("최근 상태 변경이 없습니다.")
