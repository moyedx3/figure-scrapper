"""Site configurations for figure scraper."""

REQUEST_DELAY = 1.5  # seconds between requests
REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_PAGES = 3  # max pages to scrape per category
SCRAPE_INTERVAL_MINUTES = 15
DB_PATH = "figures.db"

# AI Extraction settings
EXTRACTION_LLM_ENABLED = True       # Set False to use rules-only
EXTRACTION_CONFIDENCE_THRESHOLD = 0.7  # Below this, use LLM
EXTRACTION_MODEL = "claude-sonnet-4-5-20250929"

SITES = {
    "figurepresso": {
        "name": "figurepresso",
        "display_name": "피규어프레소",
        "base_url": "https://figurepresso.com",
        "categories": {
            "preorder": "/product/preorder.html?cate_no=24",
            "new_arrival": "/product/list.html?cate_no=1669",
            "in_stock": "/product/list.html?cate_no=25",
            "arriving_soon": "/product/list.html?cate_no=1449",
            "sale": "/product/list.html?cate_no=1532",
        },
        "product_url_pattern": "/product/{slug}/{product_id}/category/{cate_no}/display/1/",
    },
    "comicsart": {
        "name": "comicsart",
        "display_name": "코믹스아트",
        "base_url": "https://comics-art.co.kr",
        "categories": {
            "new_daily": "/product/list.html?cate_no=3132",
            "title_list": "/product/list.html?cate_no=1815",
            "arrival_schedule": "/product/list.html?cate_no=4023",
        },
        "product_url_pattern": "/product/detail.html?product_no={product_id}",
    },
    "maniahouse": {
        "name": "maniahouse",
        "display_name": "매니아하우스",
        "base_url": "https://maniahouse.co.kr",
        "categories": {
            "preorder": "/product/list.html?cate_no=45",
            "waiting": "/product/list.html?cate_no=104",
            "in_stock": "/product/list.html?cate_no=46",
            "nendoroid": "/product/list.html?cate_no=108",
            "figma": "/product/list.html?cate_no=51",
        },
        "product_url_pattern": "/product/detail.html?product_no={product_id}",
    },
    "rabbits": {
        "name": "rabbits",
        "display_name": "래빗츠컴퍼니",
        "base_url": "https://rabbits.kr",
        "categories": {
            "preorder": "/category/예약상품/24/",
            "in_stock": "/category/입고완료/77/",
            "by_title": "/category/작품별/196/",
            "goods": "/category/굿즈/253/",
        },
        "product_url_pattern": "/product/detail.html?product_no={product_id}",
    },
    "ttabbaemall": {
        "name": "ttabbaemall",
        "display_name": "따빼몰",
        "base_url": "https://ttabbaemall.co.kr",
        "categories": {
            "new_reservation": "/product/list.html?cate_no=24",
            "new_arrival": "/product/list.html?cate_no=23",
            "anime_figure": "/product/list.html?cate_no=25",
            "goodsmile": "/product/list.html?cate_no=27",
        },
        "product_url_pattern": "/product/detail.html?product_no={product_id}",
    },
}
