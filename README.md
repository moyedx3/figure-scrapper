# Figure Scrapper

한국 피규어 쇼핑몰 5곳을 자동으로 모니터링하여 신상품, 재입고, 가격 변동을 감지하고 교차 사이트 가격 비교를 제공하는 스크래퍼 + 분석 대시보드.

## 대상 사이트

| 사이트 | URL | 특징 |
|--------|-----|------|
| 피규어프레소 | figurepresso.com | 국내 No.1 피규어샵 |
| 코믹스아트 | comics-art.co.kr | JAN코드, 발매월 등 풍부한 메타데이터 |
| 매니아하우스 | maniahouse.co.kr | 굿스마일 공식 파트너샵 |
| 래빗츠컴퍼니 | rabbits.kr | 도쿄피규어 한국 총판 |
| 따빼몰 | ttabbaemall.co.kr | 게임/애니/한국IP 굿즈 특화 |

5개 사이트 모두 **Cafe24** 이커머스 플랫폼 기반이라 공통 파서 로직으로 대응.

## 주요 기능

### 스크래핑 & 변경 감지
- 5개 사이트 카테고리 페이지 자동 크롤링 (15분 간격 스케줄러)
- 신상품, 재입고, 품절, 가격 변동 실시간 감지
- 모든 변경 이력 SQLite DB에 기록

### AI 기반 상품 구조화
- **Sonnet 4.5 LLM**으로 상품명에서 시리즈, 캐릭터, 제조사, 스케일, 상품유형 등 추출
- 상품 상세 페이지에서 JAN 코드(바코드), 제조사, 사양 자동 수집
- 신상품 등록 시 자동 추출 (LLM + 페이지 fetch)

### 교차 사이트 매칭 & 가격 비교
- **JAN 코드 매칭** — 바코드 일치로 동일 상품 100% 정확 매칭 (242개 그룹)
- **구조화 필드 매칭** — 시리즈 + 캐릭터 + 제조사 + 상품유형 기반 3단계 매칭 (82개 그룹)
- 사이트별 최저가 비교, 절약률 계산

### Streamlit 분석 대시보드
- 📊 **개요** — 사이트별 상품 수, 상태 분포, 가격 분포
- 🆕 **신상품 피드** — 최근 크롤링 신상품 🆕 배지 표시
- 💰 **가격 비교** — JAN/구조 매칭 기반 교차 사이트 가격 비교, 구매 가능 필터
- ⚡ **품절 속도** — 등록~품절 소요 시간 분석
- 🔄 **재입고 패턴** — 재입고 이력, 품절 기간, 가격 변동
- 🗺️ **사이트 커버리지** — 카테고리/상태별 사이트 비교
- 📅 **예약 정확도** — 발매일 기반 예약 상품 추적
- 🔬 **추출 현황** — LLM 추출 커버리지, 샘플 테스트

## 작동 방식

```
[Scheduler: 15분 간격]
  → 5개 사이트의 카테고리 페이지 크롤링 (페이지네이션 포함)
    → Cafe24 HTML 파싱 → Product 객체 추출
      → SQLite DB와 비교 → 변경 감지 (신상품/재입고/가격/품절)
      → 신상품 발견 시:
        → 상세 페이지 fetch → JAN 코드 + 스펙 수집
        → Sonnet 4.5 LLM → 구조화 필드 추출
        → 교차 사이트 매칭 자동 갱신
```

### 감지 로직

| 이벤트 | 조건 | DB 기록 |
|--------|------|---------|
| 신상품 | DB에 없는 `(site, product_id)` 최초 등장 | `products` INSERT + LLM 추출 |
| 재입고 | 기존 status `soldout` → `available` | `status_changes` 기록 |
| 품절 | 기존 status → `soldout` 변경 | `status_changes` + `soldout_at` |
| 가격변동 | `price` 값이 이전과 다름 | `status_changes` + `price_history` |

### DB 스키마

```
products          — 상품 정보 + 구조화 추출 결과 (시리즈, 캐릭터, 제조사, JAN 등)
status_changes    — 상태/가격 변경 이력
price_history     — 가격 추적 (매 스크래핑마다 기록)
product_matches   — 교차 사이트 상품 매칭 (JAN + 구조화 필드)
watchlist         — 관심 상품 재입고 감시
```

## 설치

```bash
git clone https://github.com/moyedx3/figure-scrapper.git
cd figure-scrapper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` 파일에 Anthropic API 키 설정 (LLM 추출용):
```
ANTHROPIC_API_KEY=sk-ant-...
```

## 사용법

```bash
# 전체 사이트 1회 스크래핑 (신상품 자동 추출 + 매칭 갱신)
python scraper.py --once

# 특정 사이트만
python scraper.py --site figurepresso --once

# 15분 간격 자동 스케줄러 실행
python scraper.py

# 기존 상품 구조화 추출 (미추출 상품만)
python scraper.py --extract

# 전체 상품 재추출 (LLM)
python scraper.py --re-extract

# 대시보드 실행
streamlit run dashboard.py
```

## 설정

`config.py`에서 조정 가능:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `REQUEST_DELAY` | 1.5초 | 요청 간 딜레이 (polite scraping) |
| `MAX_PAGES` | 3 | 카테고리당 최대 페이지 수 |
| `SCRAPE_INTERVAL_MINUTES` | 15 | 스케줄러 실행 간격 |
| `DB_PATH` | `figures.db` | SQLite DB 파일 경로 |

## 프로젝트 구조

```
figure-scrapper/
├── scraper.py              # CLI 진입점 (--once, --site, --extract)
├── scheduler.py            # APScheduler 15분 루프
├── detector.py             # 변경 감지 (신상품/재입고/가격)
├── db.py                   # SQLite 스키마 + CRUD
├── models.py               # Product 데이터클래스
├── config.py               # 사이트 설정, URL, 딜레이
├── dashboard.py            # Streamlit 대시보드 진입점
├── parsers/
│   ├── base.py             # Cafe24 공통 파서
│   ├── figurepresso.py
│   ├── comicsart.py
│   ├── maniahouse.py
│   ├── rabbits.py
│   └── ttabbaemall.py
├── extraction/
│   ├── extractor.py        # 추출 파이프라인 (규칙 + LLM)
│   ├── llm.py              # Sonnet 4.5 프롬프트 + 호출
│   ├── models.py           # ProductAttributes 스키마
│   └── page_fetcher.py     # 상세 페이지 fetch + JAN 코드 추출
├── analytics/
│   ├── matching.py         # JAN + 구조화 필드 교차 사이트 매칭
│   ├── queries.py          # 대시보드용 SQL 쿼리
│   └── charts.py           # 차트 설정 (색상, 레이아웃)
└── pages/                  # Streamlit 대시보드 페이지 (8개)
```

## 현재 성과

- **2,870+** 상품 모니터링 중 (5개 사이트)
- **2,163** JAN 코드 수집 (91% 커버리지)
- **324** 교차 사이트 매칭 그룹 (242 JAN + 82 구조화)
- **100%** 상품유형 추출률, **93%** 시리즈, **88%** 캐릭터/제조사

## 로드맵

- [x] **Phase 1** — Scraper Core (5개 사이트 파서, 변경 감지, 스케줄러)
- [x] **Phase 2** — AI 추출 & 매칭 (Sonnet 4.5 구조화, JAN 매칭, 가격 비교)
- [x] **Phase 3** — Analytics Dashboard (Streamlit 8개 페이지)
- [ ] **Phase 4** — Telegram 알림 연동
- [ ] **Phase 5** — 중고 마켓 연동

## Future Directions

### Telegram 알림
- 재입고 알림: 품절 상품이 다시 입고되면 즉시 알림
- 신상품 알림: 관심 키워드/시리즈 매칭 시 알림
- 가격 변동 알림: 교차 사이트 최저가 변동 시 알림
- 새로운 매칭 그룹 발견 알림

### 중고 마켓 연동
- **Mercari (메루카리)** — API 기반, 일본 최대 중고 피규어 마켓. JAN 코드로 매칭 가능. 우선순위 1순위
- **번개장터** — API 기반, 한국 중고 마켓
- **Amazon Japan** — Product Advertising API, ASIN 코드 매칭
- **중고나라** — 네이버 카페 구조, 파싱 난이도 높음

중고가 vs 신품가 비교로 "지금 중고로 사는 게 나은가, 신품 최저가를 노리는 게 나은가" 판단 지원.
