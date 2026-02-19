#!/usr/bin/env python3
"""Analyze Naver Smartstore page structure for scraping feasibility.

Run locally (not from blocked IPs):
    python analyze_naver.py https://smartstore.naver.com/monkey-gk/products/13069360675
"""

import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def analyze_product_page(url: str):
    print(f"=== Fetching product page: {url} ===\n")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Content-Length: {len(resp.text)} chars\n")

    if resp.status_code != 200:
        print(f"ERROR: Got {resp.status_code}. Naver may be blocking this IP.")
        return

    soup = BeautifulSoup(resp.text, "lxml")

    # 1. Extract channelUid
    channel_uid = None
    matches = re.findall(r'"channelUid"\s*:\s*"([^"]+)"', resp.text)
    if matches:
        channel_uid = matches[0]
        print(f"channelUid: {channel_uid}")
    else:
        print("channelUid: NOT FOUND in HTML")

    # 2. Extract storeId / channelNo
    store_ids = re.findall(r'"(?:storeId|channelNo|smartstoreChannelId)"\s*:\s*"?(\d+)"?', resp.text)
    if store_ids:
        print(f"storeId/channelNo: {store_ids[:3]}")

    # 3. Extract product ID
    product_ids = re.findall(r'"(?:productId|productNo)"\s*:\s*"?(\d+)"?', resp.text)
    if product_ids:
        print(f"productId/productNo: {product_ids[:3]}")

    # 4. Look for __PRELOADED_STATE__ or similar JSON data
    print("\n=== Embedded JSON data ===")
    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        if "__PRELOADED_STATE__" in text or "__NEXT_DATA__" in text:
            # Extract the JSON
            for var_name in ["__PRELOADED_STATE__", "__NEXT_DATA__"]:
                if var_name in text:
                    print(f"\nFound {var_name}!")
                    # Try to extract JSON
                    match = re.search(rf'{var_name}\s*=\s*(\{{.*?\}});?\s*$', text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            print(f"  Top-level keys: {list(data.keys())[:20]}")
                            # Dump first 2000 chars for analysis
                            dump = json.dumps(data, ensure_ascii=False, indent=2)
                            print(f"  Total size: {len(dump)} chars")
                            print(f"\n  First 3000 chars:\n{dump[:3000]}")
                        except json.JSONDecodeError as e:
                            print(f"  Failed to parse JSON: {e}")
                            print(f"  First 2000 chars of raw: {text[:2000]}")

    # 5. Look for product info in meta tags
    print("\n=== Meta tags ===")
    for meta in soup.find_all("meta"):
        name = meta.get("property", meta.get("name", ""))
        content = meta.get("content", "")
        if any(k in name.lower() for k in ["title", "description", "price", "product", "image", "og:"]):
            print(f"  {name}: {content[:200]}")

    # 6. Look for structured data (JSON-LD)
    print("\n=== JSON-LD structured data ===")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        except (json.JSONDecodeError, TypeError):
            print("  Failed to parse JSON-LD")

    # 7. Try the internal JSON API if we have channelUid
    if channel_uid:
        product_id = url.rstrip("/").split("/")[-1]
        api_url = f"https://smartstore.naver.com/i/v2/channels/{channel_uid}/products/{product_id}?withWindow=false"
        print(f"\n=== Trying JSON API: {api_url} ===")
        time.sleep(2)
        api_resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        print(f"Status: {api_resp.status_code}")
        if api_resp.status_code == 200:
            try:
                data = api_resp.json()
                print(f"Top-level keys: {list(data.keys())[:20]}")
                dump = json.dumps(data, ensure_ascii=False, indent=2)
                print(f"Total size: {len(dump)} chars")
                print(f"\nFirst 5000 chars:\n{dump[:5000]}")
            except json.JSONDecodeError:
                print(f"Not JSON. First 1000 chars: {api_resp.text[:1000]}")
        else:
            print(f"API returned {api_resp.status_code}: {api_resp.text[:500]}")

    # 8. Try product listing API
    if channel_uid:
        list_url = f"https://smartstore.naver.com/i/v1/stores/{channel_uid}/categories/ALL/products?page=1&pageSize=20&sortType=RECENT"
        print(f"\n=== Trying product list API: {list_url} ===")
        time.sleep(2)
        list_resp = requests.get(list_url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        print(f"Status: {list_resp.status_code}")
        if list_resp.status_code == 200:
            try:
                data = list_resp.json()
                print(f"Top-level keys: {list(data.keys())[:20]}")
                dump = json.dumps(data, ensure_ascii=False, indent=2)
                print(f"Total size: {len(dump)} chars")
                print(f"\nFirst 5000 chars:\n{dump[:5000]}")
            except json.JSONDecodeError:
                print(f"Not JSON. First 500 chars: {list_resp.text[:500]}")

    # 9. Check for tables with product specs (like Cafe24 sites)
    print("\n=== Product spec tables ===")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if rows:
            print(f"\nTable with {len(rows)} rows:")
            for row in rows[:10]:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    print(f"  {th.get_text(strip=True)}: {td.get_text(strip=True)[:100]}")

    print("\n=== Done ===")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://smartstore.naver.com/monkey-gk/products/13069360675"
    analyze_product_page(url)
