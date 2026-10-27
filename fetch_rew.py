#!/usr/bin/env python3
"""
Pull active Vancouver listings from REW.ca's public search pages into data/listings_raw.csv,
then run match_listings.py to link them to parcels.

    python fetch_rew.py            # ~10 minutes at a polite pace
    python match_listings.py
    python score.py && python build_dashboard.py

Notes
- REW caps any single search at ~500 results, so houses are pulled per sub-area (47 slugs below);
  duplex / land / multi-family / fourplex / triplex fit in one search each.
- Requests are spaced ~4.5 s apart. REW returns HTTP 429 and then a Cloudflare bot check if you go
  faster; this script backs off for a minute on 429 and stops on a challenge page rather than trying
  to get around it. If that happens, wait 15 minutes and rerun -- it resumes from the cache.
- Listing cards carry schema.org JSON-LD (address, postal code, lat/lon, URL); price is read from the card text.
- This reads public web pages for personal research. Check REW's terms of use before redistributing the data.
"""
import csv, json, os, re, sys, time
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "rew_cache.json")
BASE = "https://www.rew.ca"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
      "Accept-Language": "en-CA,en;q=0.9"}
PACE = 4.5

SUBAREAS = ["arbutus", "cambie", "champlain-heights", "coal-harbour", "collingwood", "downtown-east", "downtown-west", "dunbar",
            "fairview", "false-creek", "fraser-east", "fraserview-east", "grandview-east", "hastings", "hastings-sunrise", "kerrisdale",
            "killarney", "kitsilano", "knight", "mackenzie-heights", "main", "marpole", "mount-pleasant-east", "mount-pleasant-west",
            "oakridge", "point-grey", "quilchena", "renfrew", "renfrew-heights", "shaughnessy", "south-cambie", "south-granville",
            "southlands", "south-marine", "south-vancouver", "southwest-marine", "strathcona", "victoria-east", "west-end", "yaletown",
            "mount-pleasant", "kensington", "cedar-cottage", "sunset", "riley-park", "oakridge-vancouver", "killarney-east"]
SINGLE_TYPES = ["duplex", "land-lot", "multifamily", "fourplex", "triplex"]


def parse_cards(html, typ, default_locality=""):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.select("article.displaycard"):
        ld = {}
        s = c.select_one('script[type="application/ld+json"]')
        if s:
            try:
                arr = json.loads(s.string or "[]")
                ld = arr[0] if isinstance(arr, list) and arr else (arr if isinstance(arr, dict) else {})
            except Exception:
                pass
        a = c.select_one('a[href*="/properties/"]')
        url = (BASE + a["href"]) if a and a["href"].startswith("/") else (a["href"] if a else ld.get("url", ""))
        if not url:
            continue
        txt = re.sub(r"\s+", " ", c.get_text(" "))
        pm = re.search(r"\$(\d{1,3}(?:,\d{3})+)", txt)
        lm = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*ft", txt, re.I)
        ad = ld.get("address", {}) or {}
        geo = ld.get("geo", {}) or {}
        out.append({"type": typ, "address": ad.get("streetAddress") or (a.get_text(strip=True) if a else ""),
                    "postal": ad.get("postalCode", ""), "locality": ad.get("addressLocality", default_locality),
                    "price": pm.group(1).replace(",", "") if pm else "", "floor_sf": "",
                    "lot_ft": f"{lm.group(1)}x{lm.group(2)}" if lm else "",
                    "lat": geo.get("latitude", ""), "lon": geo.get("longitude", ""), "url": url})
    return out


def fetch(session, path):
    for attempt in range(3):
        r = session.get(BASE + path, headers=UA, timeout=60)
        if r.status_code == 429:
            print("  429 rate-limited; sleeping 60 s", flush=True)
            time.sleep(60)
            continue
        if "Just a moment" in r.text[:2000] or "Performing security verification" in r.text:
            raise SystemExit("REW served a bot-verification page. Wait ~15 min and rerun (progress is cached).")
        return r
    return r


def crawl(session, path_prefix, typ, cache, locality=""):
    key = path_prefix
    if key in cache:
        return cache[key]
    rows, seen = [], set()
    for p in range(1, 30):
        r = fetch(session, f"{path_prefix}?page={p}")
        if r.status_code == 404 or not r.ok:
            break
        cards = parse_cards(r.text, typ, locality)
        new = [c for c in cards if c["url"] not in seen]
        for c in new:
            seen.add(c["url"])
        rows += new
        if len(cards) < 15 or not new:
            break
        time.sleep(PACE)
    cache[key] = rows
    json.dump(cache, open(CACHE, "w"))
    print(f"  {path_prefix}: {len(rows)}", flush=True)
    time.sleep(1.5)
    return rows


def main():
    os.makedirs(DATA, exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    s = requests.Session()
    all_rows = []
    for area in SUBAREAS:
        all_rows += crawl(s, f"/properties/areas/{area}-vancouver-bc/type/house", "house", cache, area)
    for typ in SINGLE_TYPES:
        all_rows += crawl(s, f"/properties/areas/vancouver-bc/type/{typ}", typ, cache)
    seen, uniq = set(), []
    for r in all_rows:
        if r["url"] not in seen:
            seen.add(r["url"]); uniq.append(r)
    cols = ["type", "address", "postal", "locality", "price", "floor_sf", "lot_ft", "lat", "lon", "url"]
    with open(os.path.join(DATA, "listings_raw.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(uniq)
    print(f"saved {len(uniq):,} unique listings -> data/listings_raw.csv  (delete data/rew_cache.json to force a fresh pull)")


if __name__ == "__main__":
    main()
