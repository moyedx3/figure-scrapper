# Figure Scrapper

한국 피규어 쇼핑몰 5곳을 자동으로 모니터링하여 신상품, 재입고, 가격 변동을 감지하는 스크래퍼.

## 대상 사이트

| 사이트 | URL | 특징 |
|--------|-----|------|
| 피규어프레소 | figurepresso.com | 국내 No.1 피규어샵 |
| 코믹스아트 | comics-art.co.kr | JAN코드, 발매월 등 풍부한 메타데이터 |
| 매니아하우스 | maniahouse.co.kr | 굿스마일 공식 파트너샵 |
| 래빗츠컴퍼니 | rabbits.kr | 도쿄피규어 한국 총판 |
| 따빼몰 | ttabbaemall.co.kr | 게임/애니/한국IP 굿즈 특화 |

5개 사이트 모두 **Cafe24** 이커머스 플랫폼 기반이라 공통 파서 로직으로 대응.

## 작동 방식

```
[Scheduler: 15분 간격]
  → 5개 사이트의 카테고리 페이지 크롤링 (페이지네이션 포함)
    → Cafe24 HTML 파싱 → Product 객체 추출
      → SQLite DB와 비교
        → 신상품: 이전에 없던 product_id → "new" 이벤트
        → 재입고: status가 soldout → available로 변경 → "restock" 이벤트
        → 가격변동: price가 이전과 다름 → "price" 이벤트
      → DB 업데이트 + 이력 기록
```

### 파서 구조

`Cafe24BaseParser`가 공통 로직(HTTP 요청, 가격 파싱, 품절 감지, 페이지네이션)을 처리하고,
각 사이트별 파서가 HTML 구조 차이만 오버라이드:

- **figurepresso** — `ul.prdList.grid7`, 상품명 prefix로 상태 판별 (`[입고완료]`, `[예약]`)
- **comicsart** — `ul.prdList.grid8`, 제조사/마감일/발매월 추가 추출
- **maniahouse** — `div.xans-product-listnormal` (다른 4곳과 다른 레이아웃), 리뷰 수 추출
- **rabbits** — `data-price` 속성으로 가격 추출, 특전포함 뱃지 감지
- **ttabbaemall** — `li[rel="판매가"]` 패턴, 예약 마감일 추출

### 감지 로직

| 이벤트 | 조건 | DB 기록 |
|--------|------|---------|
| 신상품 | DB에 없는 `(site, product_id)` 최초 등장 | `products` 테이블 INSERT |
| 재입고 | 기존 status `soldout` → 새 status `available` | `status_changes` 테이블 기록 |
| 품절 | 기존 status → `soldout` 변경 | `status_changes` + `soldout_at` 타임스탬프 |
| 가격변동 | `price` 값이 이전과 다름 | `status_changes` + `price_history` 기록 |

### DB 스키마

```
products          — 상품 정보 (사이트, ID, 이름, 가격, 상태, 메타데이터)
status_changes    — 상태/가격 변경 이력
price_history     — 가격 추적 (매 스크래핑마다 기록)
product_matches   — 교차 사이트 상품 매칭 (Phase 3)
watchlist         — 관심 상품 재입고 감시 (Phase 2)
```

## 설치

```bash
git clone https://github.com/moyedx3/figure-scrapper.git
cd figure-scrapper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용법

```bash
# 전체 사이트 1회 스크래핑
python scraper.py --once

# 특정 사이트만
python scraper.py --site figurepresso --once

# 15분 간격 스케줄러 실행 (Ctrl+C로 종료)
python scraper.py
```

## DB 조회 예시

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('figures.db')
conn.row_factory = sqlite3.Row

# 사이트별 상품 수
for r in conn.execute('SELECT site, COUNT(*) as cnt FROM products GROUP BY site'):
    print(f'{r[\"site\"]}: {r[\"cnt\"]}')

# 최근 재입고
for r in conn.execute('''
    SELECT p.site, p.name, p.price, sc.changed_at
    FROM status_changes sc JOIN products p ON sc.product_id = p.id
    WHERE sc.change_type = \"status\" AND sc.new_value = \"available\"
    ORDER BY sc.changed_at DESC LIMIT 5
'''):
    print(f'[{r[\"site\"]}] {r[\"name\"][:40]} - {r[\"price\"]}원')
"
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
├── scraper.py          # CLI 진입점 (--once, --site 플래그)
├── scheduler.py        # APScheduler 15분 루프
├── detector.py         # 변경 감지 (신상품/재입고/가격)
├── db.py               # SQLite 스키마 + CRUD
├── models.py           # Product 데이터클래스
├── config.py           # 사이트 설정, URL, 딜레이
├── parsers/
│   ├── base.py         # Cafe24 공통 파서
│   ├── figurepresso.py
│   ├── comicsart.py
│   ├── maniahouse.py
│   ├── rabbits.py
│   └── ttabbaemall.py
└── requirements.txt
```

## 로드맵

- [x] **Phase 1** — Scraper Core (5개 사이트 파서, 변경 감지, 스케줄러)
- [ ] **Phase 2** — OpenClaw 연동 (Telegram 알림, 자연어 쿼리, Vault daily note)
- [ ] **Phase 3** — Analytics (교차 사이트 가격 비교, 품절 속도 분석, 입고 정확도 추적)
