# Figure Scrapper

한국 피규어 쇼핑몰 5곳을 자동 모니터링하여 신상품, 재입고, 가격 변동을 감지하고 **Telegram 알림** + **교차 사이트 가격 비교**를 제공합니다.

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
- 5개 사이트 카테고리 페이지 자동 크롤링 (15분 간격)
- 신상품, 재입고, 품절, 가격 변동 실시간 감지
- 모든 변경 이력 SQLite DB에 기록

### AI 기반 상품 구조화
- **Claude Sonnet** LLM으로 상품명에서 시리즈, 캐릭터, 제조사, 스케일, 상품유형 추출
- 상품 상세 페이지에서 JAN 코드(바코드), 제조사, 사양 자동 수집
- 신상품 등록 시 자동 추출 (LLM + 페이지 fetch)

### 교차 사이트 매칭 & 가격 비교
- **JAN 코드 매칭** — 바코드 일치로 동일 상품 100% 정확 매칭
- **구조화 필드 매칭** — 시리즈 + 캐릭터 + 제조사 + 상품유형 기반 3단계 매칭
- 사이트별 최저가 비교, 절약률 계산
- 가격차 2배 이상 의심 매칭 자동 플래그 (예약금/부분결제 구분)

### Telegram 알림 봇
- 신상품, 재입고, 품절, 가격 변동 알림 (사진 + 가격 포함)
- `/settings`로 알림 유형별 ON/OFF 설정
- 교차 사이트 가격 비교 정보 알림에 포함
- 대량 알림 시 요약 헤더 + 개별 메시지 구조
- 1시간 이상 밀린 알림은 요약만 발송 (스팸 방지)

### Streamlit 분석 대시보드
- 📊 **개요** — 사이트별 상품 수, 상태 분포, 가격 분포
- 🆕 **신상품 피드** — 최근 크롤링 신상품 표시
- 💰 **가격 비교** — JAN/구조 매칭 기반 교차 사이트 가격 비교
- ⚡ **품절 속도** — 등록~품절 소요 시간 분석
- 🔄 **재입고 패턴** — 재입고 이력, 품절 기간, 가격 변동
- 🗺️ **사이트 커버리지** — 카테고리/상태별 사이트 비교
- 📅 **예약 정확도** — 발매일 기반 예약 상품 추적
- 🔬 **추출 현황** — LLM 추출 커버리지, 샘플 테스트

## 아키텍처

```
[Scraper] 15분 간격 크롤링
    → Cafe24 HTML 파싱 → 변경 감지
    → 신상품: 상세 페이지 fetch + LLM 추출
    → 변경사항 → pending_alerts 테이블에 큐잉
                        ↓
[Telegram Bot] 30초 간격 폴링
    → pending_alerts 읽기 → 사진 + 가격 비교 포맷
    → 구독 유저에게 발송
                        ↓
[Dashboard] Streamlit (별도 프로세스)
    → SQLite 읽기 전용 → 8개 분석 페이지
```

3개 프로세스가 **SQLite WAL 모드**로 동시 접근. 스크래퍼만 쓰기, 나머지는 읽기.

## 설치

```bash
git clone https://github.com/moyedx3/figure-scrapper.git
cd figure-scrapper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` 파일 설정:
```
ANTHROPIC_API_KEY=your-api-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
```

## 사용법

```bash
# 전체 사이트 1회 스크래핑
python scraper.py --once

# 특정 사이트만
python scraper.py --site figurepresso --once

# 15분 간격 자동 스케줄러
python scraper.py

# 기존 상품 구조화 추출 (미추출 상품만)
python scraper.py --extract

# Telegram 봇 실행
python telegram_bot.py

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
├── telegram_bot.py         # Telegram 알림 봇
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
│   ├── llm.py              # Claude LLM 프롬프트 + 호출
│   ├── models.py           # ProductAttributes 스키마
│   └── page_fetcher.py     # 상세 페이지 fetch + JAN 코드 추출
├── analytics/
│   ├── matching.py         # JAN + 구조화 필드 교차 사이트 매칭
│   ├── queries.py          # 대시보드용 SQL 쿼리
│   └── charts.py           # 차트 설정 (색상, 레이아웃)
└── pages/                  # Streamlit 대시보드 페이지 (8개)
```

## DB 스키마

```
products          — 상품 정보 + 구조화 추출 결과 (시리즈, 캐릭터, 제조사, JAN 등)
status_changes    — 상태/가격 변경 이력
price_history     — 가격 추적 (매 스크래핑마다 기록)
product_matches   — 교차 사이트 상품 매칭 (JAN + 구조화 필드)
pending_alerts    — Telegram 알림 큐 (스크래퍼 → 봇)
telegram_users    — 봇 구독자 + 알림 설정
```

## 현재 현황

- **3,100+** 상품 모니터링 중 (5개 사이트)
- **2,400+** JAN 코드 수집 (77% 커버리지)
- **400+** 교차 사이트 매칭 그룹 (JAN + 구조화)
- Telegram 봇 실시간 알림 운영 중

## 로드맵

- [x] **Phase 1** — Scraper Core (5개 사이트 파서, 변경 감지, 스케줄러)
- [x] **Phase 2** — AI 추출 & 매칭 (Claude 구조화, JAN 매칭, 가격 비교)
- [x] **Phase 3** — Analytics Dashboard (Streamlit 8개 페이지)
- [x] **Phase 4** — Telegram 알림 봇
- [ ] **Phase 5** — 중고 마켓 연동 (Mercari, 번개장터)

## License

MIT
