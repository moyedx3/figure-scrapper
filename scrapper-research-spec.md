# Figure Website Scraper Research

## Overview

5개 피규어 쇼핑몰을 분석하여 신상품 알림 및 재입고 감지 스크래퍼를 설계하기 위한 리서치 문서.

### 대상 사이트
| # | 사이트 | URL | 특징 |
|---|--------|-----|------|
| 1 | 피규어프레소 | figurepresso.com | 국내 No.1 피규어샵, 자체 굿즈 제작 |
| 2 | 코믹스아트 | comics-art.co.kr | 풍부한 메타데이터 (JAN코드, 발매월) |
| 3 | 매니아하우스 | maniahouse.co.kr | 굿스마일 공식 파트너샵, 리뷰 활발 |
| 4 | 래빗츠컴퍼니 | rabbits.kr | 도쿄피규어 한국 총판, 분기별 입고 분류 |
| 5 | 따빼몰 | ttabbaemall.co.kr | 게임/애니/한국IP 굿즈 특화, 오프라인 매장 |

**핵심 발견: 5개 사이트 모두 Cafe24 이커머스 플랫폼 기반** — 동일한 HTML 구조와 URL 패턴을 공유하므로, 하나의 공통 스크래퍼 로직으로 전부 대응 가능.

---

## 1. figurepresso.com (피규어프레소)

### Platform
- **Cafe24** 기반 쇼핑몰
- Server-side rendered HTML (SPA 아님)
- 별도 public API 없음 — HTML 파싱 필요

### URL Patterns

| 용도 | URL |
|------|-----|
| 예약상품 (전체) | `/product/preorder.html?cate_no=24` |
| 예약마감임박 | `/product/list.html?cate_no=1864` |
| 입고상품 (전체) | `/product/list.html?cate_no=25` |
| 신규입고 | `/product/list.html?cate_no=1669` |
| 입고임박 | `/product/list.html?cate_no=1449` |
| 특가세일 | `/product/list.html?cate_no=1532` |
| 작품별 분류 | `/product/listwork.html?cate_no=1382` |
| 제조사별 분류 | `/product/listmaker.html?cate_no=1671` |
| 시리즈별 | `/product/list.html?cate_no=1699` |
| 페이지네이션 | `?cate_no=XXXX&page=N` |
| 정렬 | `?cate_no=XXXX&sort_method=5` (신상품/3=낮은가격/4=높은가격/6=인기) |

### 작품별 카테고리 예시 (cate_no)
- 체인소맨: 1602, 블루 아카이브: 1777, 원신: 1781, 치이카와: 1633
- 주술회전: 1291, 원피스: 27, 봇치 더 록: 1775, SPY×FAMILY: 1445

### Product Card HTML Structure

각 상품은 `<ul>` > `<li>` 구조:

```
<li>
  <!-- 좋아요 버튼 -->
  <button>...</button>

  <!-- 상품 링크 + 이미지 -->
  <a href="/product/SLUG/PRODUCT_ID/category/CATE_NO/display/1/">
    <img alt="[상태태그][제조사][작품명] 상품명" />
  </a>

  <!-- 상품명 -->
  <a href="...">
    <span class="상품명">상품명</span>
    <span>"[입고완료][피규어프레소/공식라이센스][먼작귀/치이카와] 키캡 키링 단품 (랜덤)"</span>
  </a>

  <!-- 가격 -->
  <ul>
    <li>
      <span>"판매가"</span>
      <span>"9,900원"</span>
    </li>
  </ul>

  <!-- 품절 시: 장바구니 아이콘 대신 "품절" 이미지 표시 -->
  <img alt="품절" />        <!-- 품절일 때 -->
  <img alt="장바구니 담기" /> <!-- 구매 가능할 때 -->
</li>
```

### Stock Status Detection

상품명 prefix로 상태를 판별할 수 있음:

| Prefix | 의미 |
|--------|------|
| `[입고완료]` | 입고 완료 (재고 있음, 단 품절일 수도 있음) |
| `[26년 2분기 입고예정]` | 예약 상품 (아직 미입고) |
| `[예약마감임박]` | 예약 마감 곧 종료 |
| (없음) | 일반 판매 상품 |

**품절 감지**: `<img alt="품절">` 이미지 존재 여부로 판별
**재입고 감지**: 이전에 `품절`이었던 상품이 `장바구니 담기`로 변경되면 재입고

### Product Detail URL
```
/product/SLUG/PRODUCT_ID/category/CATE_NO/display/1/
```
예: `/product/입고완료피규어프레소공식라이센스먼작귀치이카와-키캡-키링-단품-랜덤/72069/category/1634/display/1/`

**Product ID는 URL에서 추출 가능** (숫자 부분: `72069`)

---

## 2. comics-art.co.kr (코믹스아트)

### Platform
- **Cafe24** 기반 쇼핑몰 (figurepresso와 동일 플랫폼)
- `xans-product` 클래스 시스템 사용
- Server-side rendered HTML

### URL Patterns

| 용도 | URL |
|------|-----|
| 신작/당일입고 | `/product/list.html?cate_no=3132` |
| 상품분류(타이틀) | `/product/list.html?cate_no=1815` |
| 미소녀(그 외) | `/msf/msf_index.html?cate_no=3208` |
| 넨도로이드(미니피규어) | `/good_smile/good_smile_index.html?cate_no=1797` |
| 세일/중고제품 | `/add_made/used_product_only.html?cate_no=1194` |
| 입고 일정 안내 | `/product/list.html?cate_no=4023` |
| 페이지네이션 | `?cate_no=XXXX&page=N` |

### Product Card HTML Structure

`xans-product-listnormal` 클래스 기반 `<li>` 구조:

```
<li>
  <!-- 상품 링크 -->
  <a href="/product/SLUG/PRODUCT_ID/category/CATE_NO/display/1/">
    <img />
  </a>

  <!-- 상품명 -->
  <a href="...">
    <span>"상품명"</span>
    <span>"(공식 파트너샵) 스파이럴 스튜디오..."</span>
  </a>

  <!-- 메타데이터 -->
  <ul>
    <li><span>"제조사"</span><span>"스파이럴 스튜디오"</span></li>
    <li><span>"판매가"</span><span>"725,000원"</span></li>
    <li><span>"주문 마감일"</span><span>"02월 27일 오전"</span></li>
    <li><span>"발매월"</span><span>"26년 4분기"</span></li>
  </ul>
</li>
```

### Product Detail Page Fields
- **JAN CODE**: 제품 고유코드 (예: `HOF-CLGZ021`)
- **제조사**: 제조사명
- **원작명**: 원작 시리즈명
- **발매월**: 출시 예정월
- **주문 마감일**: 예약 주문 마감 날짜
- **재질**: 소재
- **크기**: 실물 크기
- **구매 버튼**: `바로 구매하기` + `장바구니` (구매 가능 시), 품절 시 버튼 비활성화

### Stock Status Detection
- 상품 리스트에서 `당일발송` 태그 → 즉시 배송 가능 (재고 있음)
- `해외 유통분` 태그 → 해외 유통 상품
- 입고예정제품 섹션 별도 존재
- 품절 시 구매 버튼 비활성화 또는 "품절" 표시

### Sub-tabs on Listing
- `신작상품 (15172)` — 신작 상품 수
- `입고완료/당일발송 (11988)` — 입고완료 상품 수

---

## 3. maniahouse.co.kr (매니아하우스)

### Platform
- **Cafe24** 기반 쇼핑몰
- Good Smile Company 공식 파트너샵 (2024년 선정)
- Server-side rendered HTML
- 좌측 사이드바 카테고리 네비게이션

### URL Patterns

| 용도 | URL |
|------|-----|
| 예약 상품 | `/product/list.html?cate_no=45` |
| 입고 대기 | `/product/list.html?cate_no=104` |
| 입고 완료 | `/product/list.html?cate_no=46` |
| 넨도로이드 | `/product/list.html?cate_no=108` |
| figma | `/product/list.html?cate_no=51` |
| 미소녀 | `/product/list.html?cate_no=63` |
| 메카닉 | `/product/list.html?cate_no=48` |
| 캐릭터 | `/product/list.html?cate_no=49` |
| 프라모델 | `/product/list.html?cate_no=60` |
| 페이지네이션 | `?cate_no=XXXX&page=N` |

### Product Card Structure
```
[예약판매][총판] 상품명 제조사코드
예약접수 👍N        ← 상태 배지 + 리뷰 수
판매가 : XXX,XXX원
제조사 : 제조사명
```

### Stock Status Detection
- **상품명 prefix**: `[예약판매]`, `[입고완료]`, `[총판]`, `[독점유통]`, `[공식]`
- **배지**: `예약접수` (예약중), `입고완료` (재고 있음)
- **"Last One" 서브카테고리**: 입고완료 내 잔여 1개 상품 (cate_no별 별도)
- 품절 시: Cafe24 표준 — 구매 버튼 비활성화 or 품절 이미지
- 입고완료 상품: 15,172개 / Last One: 4,670개

### Product Detail URL
```
/product/detail.html?product_no=XXXXX&cate_no=XX&display_group=1
```

---

## 4. rabbits.kr (래빗츠컴퍼니)

### Platform
- **Cafe24** 기반 쇼핑몰
- 도쿄피규어 한국 공식 총판
- **Friendly URL 지원**: `/category/카테고리명/ID/` 패턴
- Server-side rendered HTML

### URL Patterns

| 용도 | URL |
|------|-----|
| 예약상품 | `/category/예약상품/24/` |
| 입고완료 | `/category/입고완료/77/` |
| 작품별 | `/category/작품별/196/` |
| 굿즈 | `/category/굿즈/253/` |
| 도쿄 피규어 | `/category/도쿄-피규어/25/` |
| 블로키 | `/category/블로키/1439/` |
| 브랜드 모음 | `/category/브랜드-모음/101/` |
| 경품 피규어 | `/category/경품-피규어/47/` |
| 굿스마일 컴퍼니 | `/category/굿스마일-컴퍼니/45/` |
| 성인 피규어 | `/category/성인-피규어/106/` |
| 페이지네이션 | `/category/NAME/ID/?page=N` |

### 예약상품 서브카테고리 (분기별 입고예정)
`25년 4분기 입고예정`, `26년 1분기 입고예정`, ..., `27년 5월 입고예정` 등 월/분기별 세분화

### Product Card Structure
```
[뱃지 아이콘들 (빨간/검정 상태 표시)]
상품명 (예: SSSS.GRIDMAN 1/7 타카라다 릿카 feat. 토리다모노)
XXX,XXX원
예약기간 : 26년 4월 21일 까지
```

### Product Detail Page Fields
- **판매가**: 가격
- **입고 예정일**: 입고 예상 시점 (예: `26년 12월`)
- **제조사**: 제조사명
- **바코드**: 바코드 번호 (JAN에 해당)
- **사양**: 소재/완성도 (예: `PVC&ABS 도색 완성품`)
- **크기**: 실물 크기
- **예약기간**: 예약 마감일 (예: `26년 4월 15일 까지`)
- **배송비**: 무료 등

### Stock Status Detection
- **`[입고완료]` prefix**: 입고 완료 상품
- **`특전증정` / `특전포함` 배지**: 특전 포함 상품
- **`공식유통` 배지**: 공식 유통 상품
- 품절 시: Cafe24 표준 방식
- 입고완료 상품: 2,710개 / 예약상품: 1,647개

---

## 5. ttabbaemall.co.kr (따빼몰)

### Platform
- **Cafe24** 기반 쇼핑몰
- 게임/애니/한국 IP 굿즈 특화
- 오프라인 매장 병행 (국제전자센터 3층)
- 모던한 UI, 카테고리 탭 구조

### URL Patterns

| 용도 | URL |
|------|-----|
| 신규예약 | `/product/list.html?cate_no=24` |
| 신규입고 | `/product/list.html?cate_no=23` |
| 애니 피규어/굿즈 | `/product/list.html?cate_no=25` |
| 해외 IP 굿즈 | `/product/list.html?cate_no=335` |
| 한국 IP 굿즈 | `/product/list.html?cate_no=26` |
| 굿스마일제품 | `/product/list.html?cate_no=27` |
| 이치방쿠지 | `/product/list.html?cate_no=132` |
| 잔금결제 | `/product/list.html?cate_no=146` |
| 페이지네이션 | `?cate_no=XXXX&page=N` |

### 작품별 카테고리 예시
- 명일방주: cate_no=61, 원신: 74, 블루아카이브: 75

### 신규예약 서브탭
- `피규어 (1863)` / `굿즈 (1809)` — 총 3,673개

### 신규입고 서브카테고리
- 게임/애니 굿즈 (1893), 캡슐 토이 (9), 피규어(스케일) (235)
- 피규어(프라이즈) (57), 프라모델 (2), 넨도로이드/미니 피규어 (76)
- 도서/OST (24), 명조 1주년 기념 (24) — 총 2,488개

### Product Card Structure
```
[예약]상품명
XX,XXX원
예약 마감일 : 26년 02월 23일
[리스트뷰] [캘린더] [하트] [공유] 아이콘
👍 N
```

### Stock Status Detection
- **`[예약]` prefix**: 예약중 상품
- **예약 마감일**: 마감 기한 표시
- 품절 시: Cafe24 표준 방식 (구매 버튼 비활성화)
- 신규예약: 3,673개 / 신규입고: 2,488개

---

## 6. Scraper Architecture Design

### 공통 Cafe24 파서

5개 사이트 모두 Cafe24이므로 공통 파싱 로직 사용 가능:

```
[Scheduler/Cron]
    |
    v
[URL Queue] -- 5개 사이트 URLs (figurepresso, comics-art, maniahouse, rabbits, ttabbaemall)
    |
    v
[HTTP Fetcher] -- requests / httpx (Python) or cheerio (Node)
    |
    v
[Cafe24 HTML Parser] -- 공통 파서
    |
    v
[Product Data Extractor]
    |
    +-- product_id (URL에서 추출)
    +-- name (상품명)
    +-- price (판매가)
    +-- status (품절/구매가능/예약중)
    +-- category
    +-- manufacturer (코믹스아트, 매니아하우스 등)
    +-- release_date
    +-- order_deadline
    |
    v
[State Store] -- SQLite or JSON file
    |
    v
[Change Detector]
    |
    +-- 신상품 감지: 이전에 없던 product_id 등장
    +-- 재입고 감지: status가 "품절" → "구매가능"으로 변경
    +-- 가격 변동 감지 (optional)
    |
    v
[Alert System] -- Discord webhook / Telegram bot / Email
```

### Tech Stack Options

#### Option A: Python (추천)
```
- requests + BeautifulSoup4 (HTML 파싱)
- SQLite (상태 저장)
- APScheduler or cron (스케줄링)
- Discord.py webhook / Telegram Bot API (알림)
```

#### Option B: Node.js
```
- axios + cheerio (HTML 파싱)
- better-sqlite3 (상태 저장)
- node-cron (스케줄링)
- Discord.js webhook (알림)
```

### Key Scraping Selectors (CSS)

#### figurepresso
```css
/* 상품 리스트 컨테이너 */
ul > li  (product list items 내부)

/* 상품명 */
a > span  (상품명 텍스트)

/* 가격 */
li 내부 "판매가" 옆 span

/* 품절 여부 */
img[alt="품절"]         /* 품절 */
img[alt="장바구니 담기"]  /* 구매 가능 */

/* 상품 URL에서 product_id 추출 */
a[href*="/product/"] → URL에서 숫자 ID 추출
```

#### comics-art
```css
/* 상품 리스트 아이템 */
.xans-product-listnormal li

/* 상품명 */
상품명 span

/* 가격, 제조사, 발매월, 마감일 */
li 내부 메타데이터 리스트

/* Product detail URL */
/product/detail.html?product_no=XXXXX
```

### Monitoring Strategy

#### 신상품 감지
1. **신규입고/예약 페이지 모니터링** (가장 효율적)
   - figurepresso: `/product/list.html?cate_no=1669` (신규입고)
   - comics-art: `/product/list.html?cate_no=3132` (신작/당일입고)
   - maniahouse: `/product/list.html?cate_no=45` (예약상품) + `cate_no=46` (입고완료)
   - rabbits: `/category/예약상품/24/` + `/category/입고완료/77/`
   - ttabbaemall: `/product/list.html?cate_no=24` (신규예약) + `cate_no=23` (신규입고)
2. 첫 1-2 페이지만 주기적 크롤링 (신상품순 정렬)
3. 이전 크롤링에 없던 product_id → 신상품 알림

#### 재입고 감지
1. **관심 상품 목록** 유지 (사용자가 등록)
2. 해당 상품 detail page 주기적 확인
3. `품절` → `구매가능` 상태 변화 감지 시 알림
4. 공통 Cafe24 패턴: `img[alt="품절"]` 존재 여부 또는 구매 버튼 비활성화 체크
5. 각 사이트 product detail URL:
   - figurepresso: `/product/SLUG/PRODUCT_ID/category/CATE_NO/display/1/`
   - comics-art: `/product/detail.html?product_no=XXXXX`
   - maniahouse: `/product/detail.html?product_no=XXXXX`
   - rabbits: `/product/detail.html?product_no=XXXXX`
   - ttabbaemall: `/product/detail.html?product_no=XXXXX`

#### 크롤링 주기 (권장)
- 신상품 감지: **30분~1시간** 간격
- 재입고 감지 (관심상품): **5~15분** 간격 (빠른 감지 필요)
- 전체 카탈로그 동기화: **1일 1회**

### Anti-Scraping Considerations
- Cafe24는 일반적으로 **강한 anti-bot 조치 없음** (rate limiting 정도)
- 적절한 요청 간격 유지 (1-2초 딜레이 per request)
- User-Agent 헤더 설정
- 과도한 요청 시 IP 차단 가능 → proxy rotation은 보통 불필요
- robots.txt 확인 필요

---

## 7. Analytics & Data Insights

5개 사이트를 동시에 크롤링하면 단일 사이트에서는 불가능한 비교/분석 인사이트를 얻을 수 있음.

### 7-1. 교차 사이트 가격 비교

동일 상품을 **JAN 코드(바코드)** 또는 **상품명 유사도**로 매칭하여 사이트간 가격 차이를 비교.

| 매칭 키 | 제공 사이트 | 신뢰도 |
|---------|-----------|--------|
| JAN 코드 / 바코드 | comics-art, rabbits | 높음 (고유 식별자) |
| 제조사 + 상품명 fuzzy match | 전체 | 중간 (이름 표기 차이 있음) |
| 제조사코드 (예: `0816`, `9176`) | maniahouse | 높음 (제조사 고유번호) |

**활용**:
- "이 피규어 어디서 사는 게 가장 싸지?" 자동 응답
- 가격 차이 알림 (예: 같은 상품인데 A사이트가 B보다 20% 쌈)
- 특가세일 감지 (평소 가격 대비 할인)

### 7-2. 품절 속도 분석 (Soldout Velocity)

`first_seen_at` (최초 등록) → `soldout_at` (품절 시점) 사이의 시간을 추적.

**분석 축**:
- **제조사별**: 어떤 제조사 제품이 빨리 품절되나? (Myethos? Alter? 굿스마일?)
- **작품/IP별**: 어떤 시리즈가 수요가 높나? (블루아카 > 원신 > 체인소맨?)
- **가격대별**: 고가 스케일 vs 저가 프라이즈 중 뭐가 더 빨리 빠지나?
- **피규어 유형별**: 스케일 피규어 vs 넨도로이드 vs 경품 피규어
- **사이트별**: 어떤 사이트가 재고 소진이 빠른가?

**활용**:
- 인기 피규어 예측 → 예약 알림 우선순위
- "이건 빨리 사야 해" 경고 (유사 상품 품절 속도 기반)

### 7-3. 재입고 패턴

품절 후 재입고까지 걸리는 시간과 빈도를 사이트별로 추적.

**추적 데이터**:
- 품절 → 재입고 평균 소요 시간 (사이트별)
- 재입고 빈도 (월 N회 재입고하는 사이트 vs 1회성)
- 재입고 시 가격 변동 여부 (재입고 시 인상되는 경우)

**활용**:
- "A 사이트에서 품절이면 B 사이트를 확인해봐" 추천
- 재입고 확률 높은 사이트 우선 알림

### 7-4. 사이트별 커버리지 차이

각 사이트가 강점을 가진 영역을 데이터로 파악.

| 사이트 | 예상 강점 (검증 필요) |
|--------|----------------------|
| figurepresso | 자체 굿즈/복권, 치이카와/먼작귀 등 캐릭터 굿즈 |
| comics-art | 미소녀 피규어, 폭넓은 스케일 피규어 |
| maniahouse | 굿스마일 제품 (공식 파트너), 넨도로이드/figma |
| rabbits | 도쿄피규어 독점, 해외 제조사 직수입 |
| ttabbaemall | 한국 IP 굿즈 (명일방주, 원신, 블루아카), 이치방쿠지 |

**활용**:
- 특정 피규어 타입별 "최적 사이트" 자동 추천
- 사이트 독점 상품 알림

### 7-5. 예약→입고 정확도

예약 시 명시된 `입고예정일`/`발매월`과 실제 `입고완료`된 시점을 비교.

**추적 데이터**:
- 예고된 입고월 vs 실제 입고월 차이 (사이트별)
- 지연 빈도 (어떤 사이트가 자주 늦나?)
- 제조사별 지연 패턴 (어떤 제조사가 잘 밀리나?)

**활용**:
- "이 제조사 예정일은 대체로 N개월 밀린다" 예측
- 실제 입고 예상 시점 보정

### 7-6. 추가 수집 데이터 포인트

기존 수집 항목 외 추가로 수집하면 유용한 필드:

| 데이터 | 출처 | 용도 |
|--------|------|------|
| JAN 코드 / 바코드 | comics-art, rabbits detail page | 교차 사이트 상품 매칭 |
| 제조사코드 | maniahouse 상품명 내 숫자 | 상품 매칭 보조 |
| 리뷰/좋아요 수 | maniahouse (👍N), ttabbaemall (👍N) | 인기도 지표 |
| 피규어 크기 | comics-art, rabbits detail | 스케일 분류 |
| 재질/사양 | rabbits detail (PVC&ABS 등) | 제품 유형 분류 |
| 예약 마감일 | 전체 (표기 방식 상이) | 마감 임박 알림 |
| 서브카테고리 | 전체 | 피규어 유형 분류 (스케일/넨도/프라이즈/굿즈) |
| 입고예정 분기 | rabbits (분기별 탭), figurepresso (월별 카테고리) | 입고 시점 추적 |
| 특전 포함 여부 | rabbits (특전증정 배지), maniahouse (특전포함) | 특전 있는 쇼핑몰 우선 추천 |
| 이미지 URL | 전체 (상품 썸네일) | UI 표시, 상품 식별 보조 |

---

## 8. Database Schema (SQLite)

```sql
-- 상품 테이블 (사이트별 개별 리스팅)
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,              -- 'figurepresso' | 'comics-art' | 'maniahouse' | 'rabbits' | 'ttabbaemall'
    product_id TEXT NOT NULL,        -- 사이트 내 상품 ID
    name TEXT NOT NULL,
    price INTEGER,                   -- 원 단위
    status TEXT,                     -- 'available' | 'soldout' | 'preorder'
    category TEXT,                   -- 사이트 내 카테고리
    figure_type TEXT,                -- 'scale' | 'nendoroid' | 'prize' | 'goods' | 'popup_parade' | 'figma' | etc
    manufacturer TEXT,
    jan_code TEXT,                   -- JAN코드/바코드 (교차 매칭 키)
    release_date TEXT,               -- 발매월/입고예정일
    order_deadline TEXT,             -- 예약 마감일
    size TEXT,                       -- 피규어 크기
    material TEXT,                   -- 재질/사양
    has_bonus BOOLEAN DEFAULT 0,     -- 특전 포함 여부
    image_url TEXT,                  -- 썸네일 이미지
    review_count INTEGER DEFAULT 0,  -- 리뷰/좋아요 수
    url TEXT,
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_checked_at DATETIME,
    soldout_at DATETIME,             -- 최초 품절 시점 (품절 속도 분석용)
    UNIQUE(site, product_id)
);

-- 상태 변경 이력 (품절/재입고/가격 변동 추적)
CREATE TABLE status_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    change_type TEXT,                -- 'status' | 'price'
    old_value TEXT,
    new_value TEXT,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 교차 매칭 테이블 (동일 상품의 여러 사이트 리스팅을 그룹핑)
CREATE TABLE product_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_key TEXT NOT NULL,         -- JAN코드 또는 생성된 매칭 키
    product_id INTEGER REFERENCES products(id),
    confidence REAL DEFAULT 1.0,     -- 매칭 신뢰도 (1.0=JAN 정확매칭, 0.x=fuzzy)
    UNIQUE(product_id)
);

-- 가격 히스토리 (가격 변동 추세 분석용)
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    price INTEGER,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 관심 상품 (재입고 감시 대상)
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id),
    notify_restock BOOLEAN DEFAULT 1,
    notify_price_drop BOOLEAN DEFAULT 0,
    target_price INTEGER,            -- 목표 가격 (이하로 내리면 알림)
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. Deployment: VPS + OpenClaw Integration

기존 VPS에서 운영 중인 OpenClaw 에이전트와 연동하여, 단순 알림 봇이 아닌 대화형 피규어 어시스턴트로 확장.

### Architecture

```
VPS (기존 인프라)
│
├── figure-scraper/           ← 새로 구축
│   ├── scraper.py            # 5개 사이트 크롤러 (cron 실행)
│   ├── db.py                 # SQLite 읽기/쓰기
│   ├── parsers/              # 사이트별 파서
│   └── figures.db            # SQLite DB (공유 데이터)
│
├── openclaw/                 ← 기존 에이전트
│   ├── figures.db 접근       # scraper DB를 읽어서 응답
│   ├── Telegram 인터페이스    # 사용자 ↔ 에이전트 대화
│   └── Obsidian vault 쓰기   # 알림/리포트를 vault에 기록
│
└── cron
    ├── */15 * * * * scraper  # 15분마다 크롤링
    └── 0 7 * * * report      # 매일 아침 7시 데일리 리포트
```

### 데이터 흐름

```
[Cron: 15분마다]
    → scraper가 5개 사이트 크롤링
    → 신상품/재입고/가격변동 감지
    → SQLite DB 업데이트
    → 변경사항 있으면 → OpenClaw에 이벤트 전달
                        → Telegram으로 즉시 알림
                        → Vault daily note에 기록

[사용자 → Telegram]
    "블루아카 신상품 있어?"
    → OpenClaw이 figures.db 쿼리
    → 결과 응답

    "이거 watchlist에 넣어줘" + URL
    → OpenClaw이 watchlist 테이블에 추가
    → 재입고 감시 시작

    "figurepresso랑 rabbits 가격 비교해줘"
    → product_matches 테이블로 교차 조회
    → 가격 비교 결과 응답
```

### OpenClaw이 처리할 수 있는 명령 예시

| 명령 (자연어) | 동작 |
|-------------|------|
| "새로 들어온 거 있어?" | 최근 24h 신상품 리스트 조회 |
| "재입고된 거 알려줘" | 최근 status_changes에서 soldout→available 필터 |
| "이거 watchlist 추가" + URL | watchlist 테이블에 INSERT |
| "블루아카 예약 상품 보여줘" | products WHERE name LIKE '%블루아카%' AND status='preorder' |
| "이 피규어 제일 싼 데 어디야?" | product_matches JOIN products → MIN(price) |
| "이번 달 입고 예정 뭐 있어?" | release_date 기반 필터 |
| "지난주 품절된 거 뭐야?" | soldout_at >= 7일 전 |
| "예약 마감 임박한 거 알려줘" | order_deadline <= 3일 후 |

### Vault 연동 (Daily Note)

OpenClaw이 매일 아침 daily note에 피규어 섹션을 자동 추가:

```markdown
## 🎯 Figure Updates (자동 생성)

### 신상품 (3건)
- [예약] 체인소맨 파워 1/7 - 198,000원 (figurepresso) [마감: 03/15]
- [예약] 블루아카 시로코 수영복 - 220,000원 (rabbits) [마감: 03/20]
- [입고] 봇치 더 록 넨도로이드 - 52,000원 (maniahouse)

### 재입고 (1건)
- ⚡ 원신 나히다 1/7 - comics-art (183,000원) ← 품절 해제!

### Watchlist 상태
- ❌ 블루아카 아로나 1/7 - 전 사이트 품절
- ✅ SPY×FAMILY 요르 1/7 - maniahouse 재고 있음 (195,000원)

### 예약 마감 임박
- ⏰ 2일 남음: 젠레스 존 제로 이블린 (rabbits, 225,000원)
```

### 왜 OpenClaw 연동이 좋은가

| 단순 알림 봇 | OpenClaw 연동 |
|-------------|--------------|
| 일방적 push 알림 | 대화형 — 질문하면 답변 |
| 모든 알림 수동 확인 | 에이전트가 우선순위 판단 |
| 별도 UI 필요 | Telegram이 UI |
| 데이터 확인 = DB 직접 쿼리 | 자연어로 질문 |
| Vault 연동 없음 | Daily note 자동 업데이트 |
| Watchlist 관리 = CLI/웹 | "이거 추가해줘"로 끝 |

---

## 10. Alert Message Format (예시)

### 신상품 알림
```
🆕 [피규어프레소] 신상품 등록!
━━━━━━━━━━━━━━━━
상품명: [26년 3분기 입고예정] 체인소맨 파워 1/7 스케일
가격: 198,000원
상태: 예약중
마감일: 03월 15일
━━━━━━━━━━━━━━━━
🔗 https://figurepresso.com/product/...
```

### 재입고 알림
```
🔔 [코믹스아트] 재입고 감지!
━━━━━━━━━━━━━━━━
상품명: 블루 아카이브 1/7 스케일 피규어
가격: 220,000원
상태: 품절 → 구매가능
━━━━━━━━━━━━━━━━
🔗 https://comics-art.co.kr/product/...
```

---

## 11. Next Steps

### Phase 1: Scraper Core
1. [ ] Python 프로젝트 셋업 (venv, requirements.txt)
2. [ ] SQLite DB 스키마 생성
3. [ ] Cafe24 공통 HTML 파서 구현 (5개 사이트 공통 베이스)
4. [ ] 사이트별 파서 어댑터 구현
   - [ ] figurepresso (품절 이미지 감지, 상품명 prefix 파싱)
   - [ ] comics-art (xans 클래스 기반, JAN코드 추출)
   - [ ] maniahouse (배지 파싱, 리뷰 수 추출)
   - [ ] rabbits (friendly URL 대응, 바코드 추출)
   - [ ] ttabbaemall (서브탭/서브카테고리 대응)
5. [ ] 신상품 감지 로직 구현
6. [ ] 재입고 감지 로직 구현
7. [ ] cron 스케줄러 설정 (15분 간격)

### Phase 2: OpenClaw Integration
8. [ ] scraper → OpenClaw 이벤트 연동 (신상품/재입고/가격변동 시 알림 트리거)
9. [ ] OpenClaw에 figures.db 쿼리 기능 추가 (자연어 → SQL)
10. [ ] Telegram 대화형 명령 구현 (watchlist 추가/조회, 가격 비교 등)
11. [ ] Vault daily note 자동 업데이트 (아침 리포트)

### Phase 3: Analytics
12. [ ] 교차 사이트 상품 매칭 (JAN코드 + fuzzy name match)
13. [ ] 품절 속도 분석 대시보드
14. [ ] 예약→입고 정확도 추적
15. [ ] 사이트별 커버리지/강점 분석
