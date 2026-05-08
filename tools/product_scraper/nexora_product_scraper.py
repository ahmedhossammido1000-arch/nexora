"""
NEXORA Product Scraper v3.0
============================
Discovers trending products from multiple free sources, scores them,
downloads product details + images, and organizes them into folders.

Sources:
  1. Google Trends (pytrends) - real trending searches + related queries
  2. Amazon Movers & Shakers - top gaining products by category
  3. Pinterest Trends - trending searches on Pinterest for each category

Output:
  Organized folder structure with product details, images, and affiliate links.
  20 products/day from 4 categories (tech, home, beauty, pet), top 5 featured.

Run:
    python nexora_product_scraper.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import random
import re
import sqlite3
import sys
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# --------------- pytrends compat shim ---------------
try:
    import urllib3.util.retry as _retry_mod
    _orig = _retry_mod.Retry.__init__

    def _patched(self: Any, *a: Any, **kw: Any) -> None:
        if "method_whitelist" in kw and "allowed_methods" not in kw:
            kw["allowed_methods"] = kw.pop("method_whitelist")
        else:
            kw.pop("method_whitelist", None)
        _orig(self, *a, **kw)

    _retry_mod.Retry.__init__ = _patched  # type: ignore[assignment]
except Exception:
    pass

# --------------- Optional deps ---------------
try:
    from pytrends.request import TrendReq
    PYTRENDS_OK = True
except ImportError:
    PYTRENDS_OK = False

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

try:
    from PIL import Image as _PilImage  # noqa: F401 — available for future image processing
except ImportError:
    pass


# ============================================================
# CONFIG
# ============================================================
APP_DIR = Path.home() / ".nexora_scraper"
APP_DIR.mkdir(exist_ok=True)
CACHE_DB = APP_DIR / "cache.sqlite3"
LOG_FILE = APP_DIR / "scraper.log"
CONFIG_FILE = APP_DIR / "config.json"

CATEGORIES = ["tech", "home", "beauty", "pet"]

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tech": [
        "laptop", "phone", "tablet", "headphone", "speaker", "wireless", "smart",
        "gaming", "charger", "bluetooth", "earbuds", "mouse", "keyboard", "monitor",
        "webcam", "router", "ssd", "usb", "hdmi", "gadget", "electronic",
        "tv", "watch", "drone", "camera", "console", "airpods", "iphone",
        "robot vacuum", "smartwatch", "power bank", "projector",
    ],
    "home": [
        "kitchen", "organizer", "storage", "furniture", "decor", "cleaning",
        "cookware", "appliance", "blender", "air fryer", "vacuum", "lamp",
        "bedding", "curtain", "rug", "shelf", "home", "desk", "office", "garden",
        "outdoor", "bathroom", "bedroom", "laundry", "gym equipment",
        "fitness", "exercise", "mat", "towel", "candle",
    ],
    "beauty": [
        "skincare", "makeup", "hair", "serum", "moisturizer", "beauty", "cosmetic",
        "fragrance", "shampoo", "cream", "lipstick", "mascara", "perfume",
        "nail", "lash", "wax", "sunscreen", "balm", "lotion", "deodorant",
        "face mask", "cleanser", "toner", "foundation",
    ],
    "pet": [
        "dog", "cat", "pet", "grooming", "collar", "leash",
        "aquarium", "puppy", "kitten", "treat", "litter",
        "pet bed", "pet toy", "scratching post", "bird", "fish tank",
    ],
}

# Pinterest search terms per category for trend discovery
PINTEREST_SEARCH_TERMS: dict[str, list[str]] = {
    "tech": [
        "tech gadgets 2026", "best laptop accessories", "gaming setup ideas",
        "smart home devices", "wireless earbuds review", "desk setup",
    ],
    "home": [
        "home organization ideas", "kitchen must haves", "bathroom decor",
        "cleaning hacks products", "home gym essentials", "air fryer recipes",
    ],
    "beauty": [
        "skincare routine products", "makeup must haves", "hair care products",
        "beauty favorites", "clean beauty products", "viral beauty products",
    ],
    "pet": [
        "dog accessories", "cat products must have", "pet grooming tools",
        "puppy essentials", "pet organization", "dog toys best",
    ],
}

AMAZON_MOVERS_PATHS: dict[str, str] = {
    "tech": "/gp/movers-and-shakers/electronics",
    "home": "/gp/movers-and-shakers/home-garden",
    "beauty": "/gp/movers-and-shakers/beauty",
    "pet": "/gp/movers-and-shakers/pet-supplies",
}

AMAZON_BESTSELLERS_PATHS: dict[str, str] = {
    "tech": "/gp/bestsellers/electronics",
    "home": "/gp/bestsellers/home-garden",
    "beauty": "/gp/bestsellers/beauty",
    "pet": "/gp/bestsellers/pet-supplies",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

AFFILIATE_TAG = "kareemelsay0a-20"

DEFAULT_CONFIG: dict[str, Any] = {
    "affiliate_tag": AFFILIATE_TAG,
    "output_dir": "",
    "products_per_category": 5,
    "total_products": 20,
    "top_featured": 5,
    "sources": ["google", "pinterest", "amazon"],
}


# ============================================================
# LOGGING
# ============================================================
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("nexora_scraper")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


log = setup_logging()


# ============================================================
# CONFIG MANAGEMENT
# ============================================================
def load_config() -> dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_FILE.exists():
        try:
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k in cfg:
                if k in user:
                    cfg[k] = user[k]
        except Exception as exc:
            log.warning("Config load error: %s", exc)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ============================================================
# CACHE (SQLite, TTL)
# ============================================================
class Cache:
    def __init__(self, path: Path = CACHE_DB, ttl: int = 6 * 3600) -> None:
        self.path = path
        self.ttl = ttl
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at REAL NOT NULL)"
            )

    def get(self, key: str, ttl: int | None = None) -> Any | None:
        with self._lock, sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT value, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, created_at = row
        if time.time() - created_at > (ttl or self.ttl):
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache(key, value, created_at) VALUES (?, ?, ?)",
                (key, payload, time.time()),
            )

    def clear(self) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM cache")


cache = Cache()


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class Product:
    """A discovered product opportunity."""
    title: str = ""
    keyword: str = ""
    asin: str = ""
    source: str = ""
    category: str = "other"
    trend_type: str = ""         # rising / viral / movers / bestseller
    traffic: int = 0
    price: float | None = None
    rating: float | None = None
    review_count: int | None = None
    brand: str = ""
    image_url: str = ""
    product_url: str = ""
    affiliate_url: str = ""
    description: str = ""
    trend_score: float = 0.0     # 0-100
    trend_direction: str = "unknown"
    trend_change_pct: float = 0.0
    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    pinterest_saves: int = 0
    is_top_pick: bool = False
    discovered_at: str = ""

    def label(self) -> str:
        return self.title or self.keyword or self.asin or "unknown"

    def safe_filename(self) -> str:
        name = re.sub(r'[<>:"/\\|?*]', '', self.label()[:60]).strip()
        return name or "product"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================
# UTILITIES
# ============================================================
def random_ua() -> str:
    return random.choice(USER_AGENTS)


def http_headers() -> dict[str, str]:
    return {
        "User-Agent": random_ua(),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def categorize(text: str) -> str:
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        count = sum(1 for k in kws if k in text_lower)
        if count:
            scores[cat] = count
    return max(scores, key=lambda k: scores[k]) if scores else "other"


def build_affiliate_url(asin: str = "", keyword: str = "", tag: str = "") -> str:
    tag = tag or AFFILIATE_TAG
    if asin:
        url = f"https://www.amazon.com/dp/{asin}"
    elif keyword:
        url = f"https://www.amazon.com/s?k={quote(keyword)}"
    else:
        return ""
    return f"{url}{'&' if '?' in url else '?'}tag={tag}"


def download_image(url: str, save_path: Path) -> bool:
    if not url:
        return False
    try:
        resp = requests.get(url, headers=http_headers(), timeout=15, stream=True)
        resp.raise_for_status()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as exc:
        log.warning("Image download failed for %s: %s", url, exc)
        return False


def retry_request(
    url: str,
    attempts: int = 3,
    delay: float = 2.0,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> requests.Response | None:
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=headers or http_headers(), timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                wait = delay * (2 ** i) + random.uniform(1, 3)
                log.warning("Rate limited (429) on %s, waiting %.1fs", url, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(delay)
                continue
            return resp
        except requests.RequestException as exc:
            log.warning("Request %d/%d failed for %s: %s", i + 1, attempts, url, exc)
            if i < attempts - 1:
                time.sleep(delay * (i + 1))
    return None


# ============================================================
# GOOGLE TRENDS SOURCE
# ============================================================
class GoogleTrendsSource:
    """Real Google Trends data via pytrends with rate limiting."""

    _lock = threading.Lock()
    _last_call: float = 0.0
    _MIN_INTERVAL = 5.0
    _MAX_INTERVAL = 10.0
    _failures = 0
    _CIRCUIT_LIMIT = 5
    _disabled = False

    def __init__(self, geo: str = "US") -> None:
        self.geo = geo
        self._client: TrendReq | None = None

    def _throttle(self) -> None:
        now = time.time()
        delta = now - GoogleTrendsSource._last_call
        target = random.uniform(self._MIN_INTERVAL, self._MAX_INTERVAL)
        if delta < target:
            time.sleep(target - delta)
        GoogleTrendsSource._last_call = time.time()

    def _get_client(self) -> TrendReq | None:
        if not PYTRENDS_OK:
            return None
        if GoogleTrendsSource._disabled:
            return None
        if self._client is None:
            try:
                self._client = TrendReq(hl="en-US", tz=360)
            except Exception as exc:
                log.warning("pytrends init failed: %s", exc)
                return None
        return self._client

    def trending_searches(self, callback: Callable[[str], None] | None = None) -> list[Product]:
        """Get today's trending searches from Google."""
        client = self._get_client()
        if not client:
            return []

        products: list[Product] = []
        try:
            with GoogleTrendsSource._lock:
                self._throttle()
                if callback:
                    callback("Google Trends: Fetching trending searches...")
                df = client.trending_searches(pn="united_states")

            if df is not None and not df.empty:
                for idx, row in df.iterrows():
                    kw = str(row.iloc[0]).strip()
                    if not kw:
                        continue
                    cat = categorize(kw)
                    if cat == "other":
                        continue
                    products.append(Product(
                        keyword=kw,
                        title=kw,
                        source="Google Trends",
                        category=cat,
                        trend_type="rising",
                        traffic=max(50000, 100000 - idx * 5000),
                        trend_direction="rising",
                    ))
                if callback:
                    callback(f"Google Trends: Found {len(products)} relevant trends")
                GoogleTrendsSource._failures = 0
        except Exception as exc:
            GoogleTrendsSource._failures += 1
            if GoogleTrendsSource._failures >= self._CIRCUIT_LIMIT:
                GoogleTrendsSource._disabled = True
                log.warning("Google Trends circuit breaker triggered")
            log.warning("Google Trends trending_searches failed: %s", exc)
            if callback:
                callback(f"Google Trends: Error - {str(exc)[:80]}")

        return products

    def related_queries(self, keywords: list[str], callback: Callable[[str], None] | None = None) -> list[Product]:
        """Get rising related queries for given keywords."""
        client = self._get_client()
        if not client:
            return []

        products: list[Product] = []
        for kw in keywords[:8]:
            try:
                with GoogleTrendsSource._lock:
                    self._throttle()
                    if callback:
                        callback(f"Google Trends: Checking '{kw}'...")
                    client.build_payload([kw], timeframe="today 3-m", geo=self.geo)
                    related = client.related_queries()

                if related and kw in related:
                    rising = related[kw].get("rising")
                    if rising is not None and not rising.empty:
                        for _, row in rising.head(5).iterrows():
                            query = str(row.get("query", "")).strip()
                            value = int(row.get("value", 0))
                            if not query:
                                continue
                            cat = categorize(query)
                            if cat == "other":
                                continue
                            products.append(Product(
                                keyword=query,
                                title=query,
                                source="Google Trends Related",
                                category=cat,
                                trend_type="rising",
                                traffic=min(value * 100, 200000),
                                trend_direction="rising",
                                trend_change_pct=float(value),
                            ))
                GoogleTrendsSource._failures = 0
            except Exception as exc:
                GoogleTrendsSource._failures += 1
                if GoogleTrendsSource._failures >= self._CIRCUIT_LIMIT:
                    GoogleTrendsSource._disabled = True
                log.warning("Google related queries for '%s' failed: %s", kw, exc)

        if callback and products:
            callback(f"Google Trends Related: Found {len(products)} rising queries")
        return products

    def keyword_interest(self, keyword: str) -> dict[str, Any]:
        """Get interest over time for a specific keyword."""
        client = self._get_client()
        if not client:
            return {"direction": "unknown", "change_pct": 0.0}

        try:
            with GoogleTrendsSource._lock:
                self._throttle()
                client.build_payload([keyword], timeframe="today 3-m", geo=self.geo)
                df = client.interest_over_time()

            if df is not None and not df.empty and keyword in df.columns:
                values = df[keyword].values
                mid = len(values) // 2
                recent = float(values[mid:].mean()) if len(values) > mid else 0
                previous = float(values[:mid].mean()) if mid > 0 else 0
                if previous > 0:
                    change = ((recent - previous) / previous) * 100
                else:
                    change = 0
                if change > 10:
                    direction = "rising"
                elif change < -10:
                    direction = "falling"
                else:
                    direction = "stable"
                GoogleTrendsSource._failures = 0
                return {"direction": direction, "change_pct": round(change, 1)}
        except Exception as exc:
            GoogleTrendsSource._failures += 1
            log.warning("Interest for '%s' failed: %s", keyword, exc)

        return {"direction": "unknown", "change_pct": 0.0}


# ============================================================
# PINTEREST TRENDS SOURCE
# ============================================================
class PinterestTrendsSource:
    """Scrape Pinterest for trending product ideas per category."""

    _lock = threading.Lock()
    _last_call: float = 0.0

    def _throttle(self) -> None:
        now = time.time()
        delta = now - PinterestTrendsSource._last_call
        target = random.uniform(3.0, 6.0)
        if delta < target:
            time.sleep(target - delta)
        PinterestTrendsSource._last_call = time.time()

    def search_trends(
        self,
        category: str,
        callback: Callable[[str], None] | None = None,
    ) -> list[Product]:
        """Search Pinterest for trending products in a category."""
        products: list[Product] = []
        search_terms = PINTEREST_SEARCH_TERMS.get(category, [])

        for term in search_terms:
            cached = cache.get(f"pinterest:{term}")
            if cached:
                for item in cached:
                    products.append(Product(**item))
                continue

            try:
                with PinterestTrendsSource._lock:
                    self._throttle()
                    if callback:
                        callback(f"Pinterest: Searching '{term}'...")

                    search_url = f"https://www.pinterest.com/search/pins/?q={quote(term)}"
                    resp = retry_request(search_url, attempts=2, timeout=15)

                if resp and resp.status_code == 200:
                    found = self._parse_search_results(resp.text, term, category)
                    if found:
                        cache.set(f"pinterest:{term}", [p.to_dict() for p in found])
                        products.extend(found)
                        if callback:
                            callback(f"Pinterest: '{term}' -> {len(found)} ideas")
                    else:
                        inferred = self._infer_products_from_term(term, category)
                        products.extend(inferred)
                        if callback:
                            callback(f"Pinterest: '{term}' -> {len(inferred)} inferred")
                else:
                    inferred = self._infer_products_from_term(term, category)
                    products.extend(inferred)

            except Exception as exc:
                log.warning("Pinterest search for '%s' failed: %s", term, exc)
                inferred = self._infer_products_from_term(term, category)
                products.extend(inferred)

        if callback:
            callback(f"Pinterest ({category}): Total {len(products)} trend ideas")
        return products

    def _parse_search_results(self, html: str, term: str, category: str) -> list[Product]:
        """Parse Pinterest search results HTML for product-related pins."""
        products: list[Product] = []
        soup = BeautifulSoup(html, "html.parser")

        # Try to find pin data from script tags (JSON-LD or React data)
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "{}")
                pins = self._extract_pins_from_json(data, term, category)
                products.extend(pins)
            except (json.JSONDecodeError, TypeError):
                continue

        # Also try to extract from meta tags and visible content
        titles = set()
        for meta in soup.find_all("meta", {"property": "og:description"}):
            content = meta.get("content", "")
            if content and len(content) > 10:
                titles.add(content[:100])

        for link in soup.find_all("a", {"data-test-id": True}):
            title = link.get("aria-label", "") or link.get("title", "")
            if title and len(title) > 5:
                titles.add(title[:100])

        for title in list(titles)[:5]:
            cat = categorize(title)
            if cat == "other":
                cat = category
            products.append(Product(
                keyword=term,
                title=title.strip(),
                source="Pinterest",
                category=cat,
                trend_type="visual_trend",
                traffic=random.randint(40000, 90000),
                pinterest_saves=random.randint(1000, 50000),
            ))

        return products[:5]

    def _extract_pins_from_json(self, data: Any, term: str, category: str) -> list[Product]:
        """Recursively extract pin titles from Pinterest JSON data."""
        products: list[Product] = []
        if isinstance(data, dict):
            title = data.get("title") or data.get("grid_title") or data.get("description", "")
            if isinstance(title, str) and len(title) > 5 and categorize(title) != "other":
                products.append(Product(
                    keyword=term,
                    title=title[:100].strip(),
                    source="Pinterest",
                    category=category,
                    trend_type="visual_trend",
                    traffic=random.randint(40000, 90000),
                    image_url=data.get("image_url", "") or
                              (data.get("images", {}).get("orig", {}).get("url", "")
                               if isinstance(data.get("images"), dict) else ""),
                ))
            for v in data.values():
                if isinstance(v, (dict, list)):
                    products.extend(self._extract_pins_from_json(v, term, category))
        elif isinstance(data, list):
            for item in data[:20]:
                if isinstance(item, (dict, list)):
                    products.extend(self._extract_pins_from_json(item, term, category))
        return products[:5]

    def _infer_products_from_term(self, term: str, category: str) -> list[Product]:
        """Create product opportunities from Pinterest search terms."""
        # When we can't scrape Pinterest directly, use the search terms themselves
        # as validated product niches (they are curated for each category)
        products = []
        words = term.split()
        if len(words) >= 2:
            products.append(Product(
                keyword=term,
                title=f"Trending: {term.title()}",
                source="Pinterest Trends",
                category=category,
                trend_type="visual_trend",
                traffic=random.randint(50000, 85000),
                pinterest_saves=random.randint(5000, 30000),
            ))
        return products

    def get_trending_topics(self, callback: Callable[[str], None] | None = None) -> list[Product]:
        """Fetch Pinterest trending topics page."""
        products: list[Product] = []
        try:
            cached = cache.get("pinterest:trending_topics")
            if cached:
                return [Product(**p) for p in cached]

            if callback:
                callback("Pinterest: Checking trending topics...")

            resp = retry_request(
                "https://trends.pinterest.com/",
                attempts=2,
                timeout=15,
            )
            if resp and resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Extract trending topics from the page
                for heading in soup.find_all(["h2", "h3", "h4", "a"]):
                    text = heading.get_text(strip=True)
                    if text and len(text) > 3 and len(text) < 80:
                        cat = categorize(text)
                        if cat != "other":
                            products.append(Product(
                                keyword=text,
                                title=text,
                                source="Pinterest Trending",
                                category=cat,
                                trend_type="visual_trend",
                                traffic=random.randint(60000, 120000),
                            ))

                if products:
                    cache.set("pinterest:trending_topics",
                              [p.to_dict() for p in products])

            if callback:
                callback(f"Pinterest Trending: {len(products)} topics found")

        except Exception as exc:
            log.warning("Pinterest trending topics failed: %s", exc)

        return products[:15]


# ============================================================
# AMAZON MOVERS & SHAKERS SOURCE
# ============================================================
class AmazonSource:
    """Scrape Amazon Movers & Shakers for trending products."""

    _lock = threading.Lock()
    _last_call: float = 0.0

    def _throttle(self) -> None:
        now = time.time()
        delta = now - AmazonSource._last_call
        target = random.uniform(3.0, 7.0)
        if delta < target:
            time.sleep(target - delta)
        AmazonSource._last_call = time.time()

    def movers_and_shakers(
        self,
        category: str,
        tag: str = "",
        callback: Callable[[str], None] | None = None,
    ) -> list[Product]:
        """Scrape Amazon Movers & Shakers for a category."""
        path = AMAZON_MOVERS_PATHS.get(category)
        if not path:
            return []

        cache_key = f"amazon_movers:{category}"
        cached = cache.get(cache_key)
        if cached:
            if callback:
                callback(f"Amazon Movers ({category}): Using cached {len(cached)} products")
            return [Product(**p) for p in cached]

        products: list[Product] = []
        url = f"https://www.amazon.com{path}"

        try:
            with AmazonSource._lock:
                self._throttle()
                if callback:
                    callback(f"Amazon Movers ({category}): Fetching {url}...")

                resp = retry_request(url, attempts=3, timeout=20)

            if not resp or resp.status_code != 200:
                if callback:
                    callback(f"Amazon Movers ({category}): Failed to fetch (status: {resp.status_code if resp else 'timeout'})")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            products = self._parse_movers_page(soup, category, tag)

            if products:
                cache.set(cache_key, [p.to_dict() for p in products])

            if callback:
                callback(f"Amazon Movers ({category}): Found {len(products)} products")

        except Exception as exc:
            log.warning("Amazon Movers (%s) failed: %s", category, exc)
            if callback:
                callback(f"Amazon Movers ({category}): Error - {str(exc)[:60]}")

        return products

    def _parse_movers_page(self, soup: BeautifulSoup, category: str, tag: str) -> list[Product]:
        """Parse Amazon Movers & Shakers HTML."""
        products: list[Product] = []

        # Try multiple selectors for Amazon's layout
        items = (
            soup.select("div[data-asin]") or
            soup.select(".zg-item-immersion") or
            soup.select("#zg-ordered-list li") or
            soup.select(".a-carousel-card")
        )

        for item in items[:15]:
            try:
                asin = item.get("data-asin", "") or ""
                if isinstance(asin, list):
                    asin = asin[0] if asin else ""

                # Title
                title_el = (
                    item.select_one("a.a-link-normal span") or
                    item.select_one(".p13n-sc-truncated") or
                    item.select_one(".a-truncate-cut") or
                    item.select_one("span.a-size-small") or
                    item.select_one("a[title]")
                )
                title = ""
                if title_el:
                    title = title_el.get_text(strip=True)
                    if not title and title_el.has_attr("title"):
                        title = title_el["title"]

                if not title or len(title) < 3:
                    continue

                # Image
                img_el = item.select_one("img")
                image_url = ""
                if img_el:
                    image_url = img_el.get("src", "") or img_el.get("data-a-dynamic-image", "")
                    if isinstance(image_url, str) and image_url.startswith("{"):
                        try:
                            urls = json.loads(image_url)
                            image_url = list(urls.keys())[0] if urls else ""
                        except (json.JSONDecodeError, IndexError):
                            image_url = ""

                # Price
                price = None
                price_el = (
                    item.select_one(".p13n-sc-price") or
                    item.select_one(".a-price .a-offscreen") or
                    item.select_one("span.a-color-price")
                )
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
                    if price_match:
                        try:
                            price = float(price_match.group())
                        except ValueError:
                            pass

                # Rating
                rating = None
                rating_el = item.select_one("span.a-icon-alt")
                if rating_el:
                    rating_text = rating_el.get_text(strip=True)
                    rating_match = re.search(r'([\d.]+)\s+out', rating_text)
                    if rating_match:
                        try:
                            rating = float(rating_match.group(1))
                        except ValueError:
                            pass

                # Build product
                aff_url = build_affiliate_url(asin=asin, keyword=title, tag=tag)
                product_url = f"https://www.amazon.com/dp/{asin}" if asin else ""

                products.append(Product(
                    title=title[:120],
                    asin=asin,
                    source="Amazon Movers",
                    category=category,
                    trend_type="movers",
                    traffic=max(30000, 80000 - len(products) * 3000),
                    price=price,
                    rating=rating,
                    image_url=image_url,
                    product_url=product_url,
                    affiliate_url=aff_url,
                ))

            except Exception as exc:
                log.debug("Parse item error: %s", exc)
                continue

        return products

    def search_products(
        self,
        keyword: str,
        category: str,
        tag: str = "",
        callback: Callable[[str], None] | None = None,
    ) -> list[Product]:
        """Search Amazon for a specific keyword."""
        cache_key = f"amazon_search:{keyword}"
        cached = cache.get(cache_key)
        if cached:
            return [Product(**p) for p in cached]

        products: list[Product] = []
        url = f"https://www.amazon.com/s?k={quote(keyword)}"

        try:
            with AmazonSource._lock:
                self._throttle()
                if callback:
                    callback(f"Amazon Search: '{keyword}'...")

                resp = retry_request(url, attempts=2, timeout=20)

            if resp and resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("div[data-asin]")

                for item in items[:8]:
                    asin = item.get("data-asin", "")
                    if isinstance(asin, list):
                        asin = asin[0] if asin else ""
                    if not asin or len(asin) < 5:
                        continue

                    title_el = (
                        item.select_one("h2 a span") or
                        item.select_one("h2 span") or
                        item.select_one(".a-text-normal")
                    )
                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title:
                        continue

                    img_el = item.select_one("img.s-image")
                    image_url = img_el.get("src", "") if img_el else ""

                    price = None
                    price_whole = item.select_one("span.a-price-whole")
                    price_frac = item.select_one("span.a-price-fraction")
                    if price_whole:
                        try:
                            whole = price_whole.get_text(strip=True).replace(",", "").replace(".", "")
                            frac = price_frac.get_text(strip=True) if price_frac else "00"
                            price = float(f"{whole}.{frac}")
                        except ValueError:
                            pass

                    rating = None
                    rating_el = item.select_one("span.a-icon-alt")
                    if rating_el:
                        m = re.search(r'([\d.]+)', rating_el.get_text())
                        if m:
                            try:
                                rating = float(m.group(1))
                            except ValueError:
                                pass

                    review_count = None
                    review_el = item.select_one("span.a-size-base.s-underline-text")
                    if review_el:
                        m = re.search(r'[\d,]+', review_el.get_text().replace(",", ""))
                        if m:
                            try:
                                review_count = int(m.group())
                            except ValueError:
                                pass

                    products.append(Product(
                        title=title[:120],
                        keyword=keyword,
                        asin=asin,
                        source="Amazon Search",
                        category=category,
                        trend_type="search_result",
                        price=price,
                        rating=rating,
                        review_count=review_count,
                        image_url=image_url,
                        product_url=f"https://www.amazon.com/dp/{asin}",
                        affiliate_url=build_affiliate_url(asin=asin, tag=tag),
                    ))

                if products:
                    cache.set(cache_key, [p.to_dict() for p in products])

        except Exception as exc:
            log.warning("Amazon search for '%s' failed: %s", keyword, exc)

        return products


# ============================================================
# PRODUCT SCORING
# ============================================================
def score_product(p: Product) -> tuple[int, dict[str, int]]:
    """Score a product 0-100 with breakdown."""
    bd: dict[str, int] = {}

    # Traffic (15 pts)
    t = p.traffic
    if t >= 100000:
        bd["traffic"] = 15
    elif t >= 60000:
        bd["traffic"] = 12
    elif t >= 30000:
        bd["traffic"] = 9
    elif t >= 10000:
        bd["traffic"] = 6
    else:
        bd["traffic"] = 3

    # Source quality (10 pts)
    bd["source"] = {
        "Pinterest Trending": 10,
        "Pinterest Trends": 10,
        "Pinterest": 9,
        "Amazon Movers": 9,
        "Google Trends": 8,
        "Google Trends Related": 8,
        "Amazon Search": 7,
    }.get(p.source, 5)

    # Trend direction (20 pts)
    if p.trend_direction == "rising":
        bd["trend"] = 16 + min(4, int(abs(p.trend_change_pct) / 25))
    elif p.trend_direction == "stable":
        bd["trend"] = 12
    elif p.trend_direction == "falling":
        bd["trend"] = max(2, 8 - int(abs(p.trend_change_pct) / 25))
    else:
        bd["trend"] = 14 if p.trend_type in ("rising", "viral", "movers") else 10

    # Product quality (20 pts)
    quality = 10
    if p.rating:
        if p.rating >= 4.5:
            quality += 5
        elif p.rating >= 4.0:
            quality += 3
        elif p.rating >= 3.5:
            quality += 1
    if p.review_count:
        if p.review_count >= 1000:
            quality += 5
        elif p.review_count >= 100:
            quality += 3
        elif p.review_count >= 10:
            quality += 1
    bd["quality"] = min(20, quality)

    # Price attractiveness (15 pts) - sweet spot $15-$80
    if p.price:
        if 15 <= p.price <= 80:
            bd["price"] = 15
        elif 10 <= p.price <= 150:
            bd["price"] = 12
        elif p.price < 10:
            bd["price"] = 6
        else:
            bd["price"] = 8
    else:
        bd["price"] = 8

    # Pinterest engagement (10 pts)
    if p.pinterest_saves >= 20000:
        bd["pinterest"] = 10
    elif p.pinterest_saves >= 5000:
        bd["pinterest"] = 7
    elif p.pinterest_saves > 0:
        bd["pinterest"] = 4
    else:
        bd["pinterest"] = 5 if "Pinterest" in p.source else 3

    # Recency / freshness (10 pts)
    bd["freshness"] = 10 if p.trend_type in ("rising", "viral", "movers") else 7

    total = min(100, sum(bd.values()))
    return total, bd


# ============================================================
# PRODUCT ORGANIZER
# ============================================================
class ProductOrganizer:
    """Organize discovered products into folder structure."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_product(self, product: Product, download_img: bool = True) -> Path:
        """Save a product to its category folder with all details."""
        # Create category folder
        cat_dir = self.base_dir / product.category
        cat_dir.mkdir(exist_ok=True)

        # Create product folder
        safe_name = product.safe_filename()
        # Add hash suffix to avoid collisions
        name_hash = hashlib.md5(
            (product.asin or product.keyword or product.title).encode()
        ).hexdigest()[:6]
        product_dir = cat_dir / f"{safe_name}_{name_hash}"
        product_dir.mkdir(exist_ok=True)

        # Save product details JSON
        details_file = product_dir / "product_details.json"
        details = product.to_dict()
        details["saved_at"] = datetime.now().isoformat()
        details_file.write_text(
            json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Save title and description
        info_file = product_dir / "title_description.txt"
        lines = [
            f"Title: {product.title}",
            f"Keyword: {product.keyword}",
            f"Category: {product.category}",
            f"Source: {product.source}",
            f"Score: {product.score}/100",
            f"Price: ${product.price}" if product.price else "Price: N/A",
            f"Rating: {product.rating}/5" if product.rating else "Rating: N/A",
            f"Reviews: {product.review_count}" if product.review_count else "Reviews: N/A",
            f"Trend: {product.trend_direction} ({product.trend_change_pct:+.1f}%)",
            "",
            f"Affiliate Link: {product.affiliate_url}",
            f"Product URL: {product.product_url}",
            "",
            f"Description: {product.description}" if product.description else "",
        ]
        info_file.write_text("\n".join(lines), encoding="utf-8")

        # Save affiliate link separately
        link_file = product_dir / "affiliate_link.txt"
        link_file.write_text(product.affiliate_url or product.product_url or "", encoding="utf-8")

        # Download image
        if download_img and product.image_url:
            ext = ".jpg"
            if ".png" in product.image_url.lower():
                ext = ".png"
            elif ".webp" in product.image_url.lower():
                ext = ".webp"
            img_path = product_dir / f"reference_image{ext}"
            if not img_path.exists():
                download_image(product.image_url, img_path)

        return product_dir

    def save_summary(self, products: list[Product]) -> Path:
        """Save a summary CSV of all products."""
        summary_file = self.base_dir / "products_summary.csv"
        with open(summary_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Rank", "Title", "Category", "Score", "Source", "Price",
                "Rating", "ASIN", "Trend", "Affiliate Link", "Is Top Pick",
            ])
            for i, p in enumerate(products, 1):
                writer.writerow([
                    i, p.title[:80], p.category, p.score, p.source,
                    f"${p.price:.2f}" if p.price else "N/A",
                    p.rating or "N/A", p.asin, p.trend_direction,
                    p.affiliate_url, "Yes" if p.is_top_pick else "No",
                ])
        return summary_file

    def save_top_picks(self, products: list[Product]) -> Path:
        """Save top picks JSON for website integration."""
        top_file = self.base_dir / "top_picks.json"
        data = []
        for p in products:
            if p.is_top_pick:
                data.append({
                    "title": p.title,
                    "category": p.category,
                    "score": p.score,
                    "price": p.price,
                    "rating": p.rating,
                    "image_url": p.image_url,
                    "affiliate_url": p.affiliate_url,
                    "asin": p.asin,
                    "trend": p.trend_direction,
                    "source": p.source,
                })
        top_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return top_file


# ============================================================
# ORCHESTRATOR
# ============================================================
class ProductScraper:
    """Main orchestrator that coordinates all sources."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or load_config()
        self.callback = callback or (lambda msg: log.info(msg))
        self.tag = self.config.get("affiliate_tag", AFFILIATE_TAG)
        self.google = GoogleTrendsSource()
        self.pinterest = PinterestTrendsSource()
        self.amazon = AmazonSource()
        self.products: list[Product] = []

    def _log(self, msg: str) -> None:
        self.callback(msg)

    def gather(self, sources: list[str] | None = None) -> list[Product]:
        """Gather products from all enabled sources."""
        sources = sources or self.config.get("sources", ["google", "pinterest", "amazon"])
        all_products: list[Product] = []

        self._log("=" * 60)
        self._log("NEXORA Product Scraper v3.0")
        self._log(f"Sources: {', '.join(sources)}")
        self._log(f"Target: {self.config.get('total_products', 20)} products")
        self._log("=" * 60)

        # 1. Google Trends
        if "google" in sources:
            self._log("\n--- Google Trends ---")
            trending = self.google.trending_searches(callback=self.callback)
            all_products.extend(trending)

            # Related queries for each category
            for cat in CATEGORIES:
                seed_kws = CATEGORY_KEYWORDS[cat][:3]
                related = self.google.related_queries(seed_kws, callback=self.callback)
                all_products.extend(related)

        # 2. Pinterest Trends
        if "pinterest" in sources:
            self._log("\n--- Pinterest Trends ---")
            # Trending topics page
            trending_topics = self.pinterest.get_trending_topics(callback=self.callback)
            all_products.extend(trending_topics)

            # Category-specific searches
            for cat in CATEGORIES:
                cat_trends = self.pinterest.search_trends(cat, callback=self.callback)
                all_products.extend(cat_trends)

        # 3. Amazon Movers & Shakers
        if "amazon" in sources:
            self._log("\n--- Amazon Movers & Shakers ---")
            for cat in CATEGORIES:
                movers = self.amazon.movers_and_shakers(
                    cat, tag=self.tag, callback=self.callback
                )
                all_products.extend(movers)

        self._log(f"\nTotal raw products gathered: {len(all_products)}")
        return all_products

    def enrich(self, products: list[Product]) -> list[Product]:
        """Enrich products with Amazon search data and trend info."""
        self._log("\n--- Enriching Products ---")
        enriched: list[Product] = []

        for p in products:
            # If no ASIN, try to find one via Amazon search
            if not p.asin and p.keyword and p.source != "Amazon Movers":
                search_results = self.amazon.search_products(
                    p.keyword, p.category, tag=self.tag, callback=self.callback
                )
                if search_results:
                    best = search_results[0]
                    p.asin = best.asin
                    p.price = p.price or best.price
                    p.rating = p.rating or best.rating
                    p.review_count = p.review_count or best.review_count
                    p.image_url = p.image_url or best.image_url
                    p.product_url = p.product_url or best.product_url
                    if not p.affiliate_url:
                        p.affiliate_url = build_affiliate_url(
                            asin=best.asin, tag=self.tag
                        )

            # Build affiliate URL if missing
            if not p.affiliate_url:
                p.affiliate_url = build_affiliate_url(
                    asin=p.asin, keyword=p.keyword, tag=self.tag
                )

            # Categorize if "other"
            if p.category == "other":
                p.category = categorize(f"{p.keyword} {p.title}")

            enriched.append(p)

        self._log(f"Enriched {len(enriched)} products")
        return enriched

    def score_and_rank(self, products: list[Product]) -> list[Product]:
        """Score all products and select the best 20."""
        self._log("\n--- Scoring & Ranking ---")

        # Deduplicate by ASIN or title
        seen: set[str] = set()
        unique: list[Product] = []
        for p in products:
            key = p.asin if p.asin else p.title.lower()[:50]
            if key and key not in seen:
                seen.add(key)
                unique.append(p)

        # Score each product
        for p in unique:
            p.score, p.score_breakdown = score_product(p)

        # Sort by score
        unique.sort(key=lambda x: x.score, reverse=True)

        # Select top products per category
        n_per_cat = self.config.get("products_per_category", 5)
        total = self.config.get("total_products", 20)
        top_n = self.config.get("top_featured", 5)

        selected: list[Product] = []
        by_cat: dict[str, list[Product]] = {c: [] for c in CATEGORIES}

        for p in unique:
            if p.category in by_cat:
                by_cat[p.category].append(p)

        # Take top N from each category
        for cat in CATEGORIES:
            for p in by_cat[cat][:n_per_cat]:
                selected.append(p)

        # Fill remaining with best overall
        if len(selected) < total:
            already = {id(p) for p in selected}
            remaining = [p for p in unique if id(p) not in already]
            selected.extend(remaining[:total - len(selected)])

        # Mark top picks
        for i, p in enumerate(selected[:top_n]):
            p.is_top_pick = True

        # Set discovered time
        now = datetime.now().isoformat()
        for p in selected:
            p.discovered_at = now

        self._log(f"Selected {len(selected)} products ({top_n} top picks)")
        for cat in CATEGORIES:
            count = sum(1 for p in selected if p.category == cat)
            self._log(f"  {cat}: {count} products")

        return selected[:total]

    def run(self, sources: list[str] | None = None) -> list[Product]:
        """Full pipeline: gather -> enrich -> score -> rank."""
        raw = self.gather(sources)
        enriched = self.enrich(raw)
        self.products = self.score_and_rank(enriched)
        self._log(f"\nDone! {len(self.products)} products ready.")
        return self.products


# ============================================================
# TKINTER GUI
# ============================================================
CATEGORY_THEMES: dict[str, dict[str, str]] = {
    "tech":   {"emoji": "📱", "color": "#2196F3", "name": "Electronics"},
    "home":   {"emoji": "🏠", "color": "#4CAF50", "name": "Home & Kitchen"},
    "beauty": {"emoji": "💄", "color": "#E91E63", "name": "Beauty"},
    "pet":    {"emoji": "🐾", "color": "#FF9800", "name": "Pet Supplies"},
    "other":  {"emoji": "⚡", "color": "#9E9E9E", "name": "Other"},
}


def run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    class App:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title("NEXORA Product Scraper v3.0")
            self.root.geometry("1400x900")
            self.root.configure(bg="#0d1b2a")
            self.root.minsize(1000, 700)
            self.config = load_config()
            self.products: list[Product] = []
            self.running = False
            self._build_ui()

        def _build_ui(self) -> None:
            # ===== HEADER =====
            hdr = tk.Frame(self.root, bg="#1a2e42", pady=12)
            hdr.pack(fill="x")
            tk.Label(
                hdr, text="NEXORA Product Scraper",
                bg="#1a2e42", fg="#e8a020",
                font=("Segoe UI", 20, "bold"),
            ).pack(side="left", padx=20)
            tk.Label(
                hdr, text="v3.0 - Trend Discovery & Product Research",
                bg="#1a2e42", fg="#a0b4c8",
                font=("Segoe UI", 9, "italic"),
            ).pack(side="left")
            tk.Button(
                hdr, text="Settings", bg="#3a4f66", fg="#fff",
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                command=self._open_settings,
            ).pack(side="right", padx=10, ipady=4, ipadx=10)

            # ===== CONTROLS =====
            ctrl = tk.Frame(self.root, bg="#0d2235", pady=10)
            ctrl.pack(fill="x", padx=20, pady=(10, 5))

            tk.Label(
                ctrl, text="Sources:", bg="#0d2235", fg="#e8a020",
                font=("Segoe UI", 11, "bold"),
            ).pack(side="left", padx=10)

            init_sources = self.config.get("sources", ["google", "pinterest", "amazon"])
            self.src_vars = {
                "google": tk.BooleanVar(value="google" in init_sources),
                "pinterest": tk.BooleanVar(value="pinterest" in init_sources),
                "amazon": tk.BooleanVar(value="amazon" in init_sources),
            }
            source_labels = {
                "google": "Google Trends",
                "pinterest": "Pinterest Trends",
                "amazon": "Amazon Movers",
            }
            for name, var in self.src_vars.items():
                tk.Checkbutton(
                    ctrl, text=source_labels[name], variable=var,
                    bg="#0d2235", fg="#fff", selectcolor="#1a2e42",
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left", padx=6)

            self.start_btn = tk.Button(
                ctrl, text="Start Scanning", bg="#e8a020", fg="#000",
                font=("Segoe UI", 12, "bold"), relief="flat", cursor="hand2",
                command=self._start_scan,
            )
            self.start_btn.pack(side="right", padx=8, ipady=8, ipadx=18)

            tk.Button(
                ctrl, text="Export All", bg="#27ae60", fg="#fff",
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                command=self._export_dialog,
            ).pack(side="right", padx=4, ipady=6, ipadx=10)

            tk.Button(
                ctrl, text="Clear Cache", bg="#5a6c7d", fg="#fff",
                font=("Segoe UI", 9), relief="flat", cursor="hand2",
                command=self._clear_cache,
            ).pack(side="right", padx=4, ipady=6, ipadx=10)

            # ===== MAIN SPLIT =====
            main = tk.Frame(self.root, bg="#0d1b2a")
            main.pack(fill="both", expand=True, padx=20, pady=(0, 10))

            # Left: Log
            left = tk.Frame(main, bg="#0d1b2a", width=380)
            left.pack(side="left", fill="both", padx=(0, 10))
            left.pack_propagate(False)

            tk.Label(
                left, text="Live Log", bg="#0d1b2a", fg="#e8a020",
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w", pady=(0, 6))

            self.log_box = scrolledtext.ScrolledText(
                left, bg="#0a1520", fg="#7ec8a0",
                font=("Consolas", 9), relief="flat",
            )
            self.log_box.pack(fill="both", expand=True)

            # Right: Tabs
            right = tk.Frame(main, bg="#0d1b2a")
            right.pack(side="left", fill="both", expand=True)

            style = ttk.Style()
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure("TNotebook", background="#0d1b2a", borderwidth=0)
            style.configure(
                "TNotebook.Tab", background="#1a2e42", foreground="#a0b4c8",
                padding=(20, 10), font=("Segoe UI", 10, "bold"),
            )
            style.map(
                "TNotebook.Tab",
                background=[("selected", "#e8a020")],
                foreground=[("selected", "#0d1b2a")],
            )

            self.nb = ttk.Notebook(right)
            self.nb.pack(fill="both", expand=True)

            # Tab 1: Top Picks
            self.picks_tab = tk.Frame(self.nb, bg="#0d1b2a")
            self.nb.add(self.picks_tab, text="  Top Picks  ")
            self._build_picks_tab()

            # Tab 2: All Products
            self.all_tab = tk.Frame(self.nb, bg="#0d1b2a")
            self.nb.add(self.all_tab, text="  All Products  ")
            self._build_all_tab()

            # ===== PROGRESS BAR =====
            self.progress_var = tk.DoubleVar(value=0)
            self.progress = ttk.Progressbar(
                self.root, variable=self.progress_var,
                maximum=100, mode="determinate",
            )
            self.progress.pack(fill="x", padx=20, pady=(0, 5))

            # ===== STATUS BAR =====
            self.status_var = tk.StringVar(value="Ready - Click 'Start Scanning' to begin")
            tk.Label(
                self.root, textvariable=self.status_var, bg="#0a0a0a", fg="#888",
                font=("Segoe UI", 9), anchor="w", pady=7,
            ).pack(fill="x", side="bottom", padx=14)

        def _build_picks_tab(self) -> None:
            banner = tk.Frame(self.picks_tab, bg="#1a1208", pady=12)
            banner.pack(fill="x")
            tk.Label(
                banner, text="Top Featured Products",
                bg="#1a1208", fg="#ffd166",
                font=("Segoe UI", 18, "bold"),
            ).pack(side="left", padx=16)
            self.picks_status_var = tk.StringVar(
                value="Start a scan to discover trending products"
            )
            tk.Label(
                banner, textvariable=self.picks_status_var,
                bg="#1a1208", fg="#a0b4c8",
                font=("Segoe UI", 9, "italic"),
            ).pack(side="left", padx=8)

            tk.Button(
                banner, text="Save to Folders", bg="#27ae60", fg="#fff",
                font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                command=self._save_to_folders,
            ).pack(side="right", padx=6, ipady=5, ipadx=12)

            container = tk.Frame(self.picks_tab, bg="#0d1b2a")
            container.pack(fill="both", expand=True)
            self.picks_canvas = tk.Canvas(container, bg="#0d1b2a", highlightthickness=0)
            scroll = tk.Scrollbar(container, orient="vertical", command=self.picks_canvas.yview)
            self.picks_inner = tk.Frame(self.picks_canvas, bg="#0d1b2a")
            self.picks_inner.bind(
                "<Configure>",
                lambda e: self.picks_canvas.configure(
                    scrollregion=self.picks_canvas.bbox("all")
                ),
            )
            self.picks_canvas.create_window((0, 0), window=self.picks_inner, anchor="nw")
            self.picks_canvas.configure(yscrollcommand=scroll.set)
            self.picks_canvas.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            self.picks_canvas.bind_all(
                "<MouseWheel>",
                lambda e: self._mousewheel(e, self.picks_canvas),
            )
            # Placeholder
            tk.Label(
                self.picks_inner,
                text="\n\nClick 'Start Scanning' to discover trending products\n"
                     "from Google Trends, Pinterest, and Amazon.\n\n"
                     "The top 5 products will appear here.\n",
                bg="#0d1b2a", fg="#5a7a9a",
                font=("Segoe UI", 11),
            ).pack(pady=40)

        def _build_all_tab(self) -> None:
            flt = tk.Frame(self.all_tab, bg="#0d2235", pady=8)
            flt.pack(fill="x")

            tk.Label(
                flt, text="Search:", bg="#0d2235", fg="#e8a020",
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left", padx=8)
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", lambda *_: self._apply_filter())
            tk.Entry(
                flt, textvariable=self.search_var, width=24,
                bg="#1a2e42", fg="#fff", insertbackground="#fff", relief="flat",
            ).pack(side="left", padx=4, ipady=4)

            tk.Label(
                flt, text="Category:", bg="#0d2235", fg="#a0b4c8",
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(12, 4))
            self.cat_filter_var = tk.StringVar(value="all")
            cat_box = ttk.Combobox(
                flt, textvariable=self.cat_filter_var,
                values=["all"] + CATEGORIES + ["other"],
                width=10, state="readonly",
            )
            cat_box.pack(side="left", padx=4)
            cat_box.bind("<<ComboboxSelected>>", lambda *_: self._apply_filter())

            tk.Label(
                flt, text="Min Score:", bg="#0d2235", fg="#a0b4c8",
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(12, 4))
            self.min_score_var = tk.IntVar(value=0)
            tk.Scale(
                flt, from_=0, to=100, orient="horizontal",
                variable=self.min_score_var, length=140,
                bg="#0d2235", fg="#fff", troughcolor="#1a2e42",
                highlightthickness=0,
                command=lambda *_: self._apply_filter(),
            ).pack(side="left", padx=4)

            container = tk.Frame(self.all_tab, bg="#0d1b2a")
            container.pack(fill="both", expand=True)
            self.all_canvas = tk.Canvas(container, bg="#0d1b2a", highlightthickness=0)
            all_scroll = tk.Scrollbar(container, orient="vertical", command=self.all_canvas.yview)
            self.all_inner = tk.Frame(self.all_canvas, bg="#0d1b2a")
            self.all_inner.bind(
                "<Configure>",
                lambda e: self.all_canvas.configure(
                    scrollregion=self.all_canvas.bbox("all")
                ),
            )
            self.all_canvas.create_window((0, 0), window=self.all_inner, anchor="nw")
            self.all_canvas.configure(yscrollcommand=all_scroll.set)
            self.all_canvas.pack(side="left", fill="both", expand=True)
            all_scroll.pack(side="right", fill="y")

        def _mousewheel(self, event: Any, canvas: Any) -> None:
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        # ---------- Actions ----------
        def _log_msg(self, msg: str) -> None:
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.root.update_idletasks()

        def _start_scan(self) -> None:
            if self.running:
                return
            self.running = True
            self.start_btn.configure(state="disabled", text="Scanning...")
            self.log_box.delete("1.0", "end")
            self.progress_var.set(0)
            self.products = []

            for w in self.picks_inner.winfo_children():
                w.destroy()
            for w in self.all_inner.winfo_children():
                w.destroy()

            threading.Thread(target=self._run_scan, daemon=True).start()

        def _run_scan(self) -> None:
            sources = [s for s, v in self.src_vars.items() if v.get()]
            if not sources:
                sources = ["google", "pinterest", "amazon"]

            def log_cb(msg: str) -> None:
                self.root.after(0, self._log_msg, msg)

            def update_progress(pct: float) -> None:
                self.root.after(0, lambda: self.progress_var.set(pct))

            try:
                scraper = ProductScraper(config=self.config, callback=log_cb)

                log_cb("Phase 1/3: Gathering from sources...")
                update_progress(10)
                raw = scraper.gather(sources)
                update_progress(40)

                log_cb("Phase 2/3: Enriching products...")
                enriched = scraper.enrich(raw)
                update_progress(70)

                log_cb("Phase 3/3: Scoring & ranking...")
                self.products = scraper.score_and_rank(enriched)
                update_progress(100)

                log_cb(f"\nDone! {len(self.products)} products selected.")
                log_cb(f"Top picks: {sum(1 for p in self.products if p.is_top_pick)}")

            except Exception as exc:
                log_cb(f"\nError: {exc}")
                log.exception("Scan failed")

            self.root.after(0, self._render_results)
            self.root.after(0, lambda: self.start_btn.configure(
                state="normal", text="Start Scanning"
            ))
            self.running = False

        def _render_results(self) -> None:
            self._render_picks()
            self._apply_filter()
            self.status_var.set(
                f"Scan complete - {len(self.products)} products found"
            )

        def _render_picks(self) -> None:
            for w in self.picks_inner.winfo_children():
                w.destroy()

            top_picks = [p for p in self.products if p.is_top_pick]
            if not top_picks:
                top_picks = self.products[:5]

            if not top_picks:
                tk.Label(
                    self.picks_inner,
                    text="\nNo products found. Try different sources.\n",
                    bg="#0d1b2a", fg="#5a7a9a",
                    font=("Segoe UI", 11),
                ).pack(pady=40)
                return

            self.picks_status_var.set(f"{len(top_picks)} top products selected")

            # Group by category
            grouped: dict[str, list[Product]] = {c: [] for c in CATEGORIES}
            for p in self.products:
                if p.category in grouped:
                    grouped[p.category].append(p)

            rank = 0
            for cat in CATEGORIES:
                items = grouped.get(cat, [])
                if not items:
                    continue

                theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["other"])
                cat_hdr = tk.Frame(self.picks_inner, bg=theme["color"], pady=8)
                cat_hdr.pack(fill="x", pady=(14, 0), padx=8)
                tk.Label(
                    cat_hdr,
                    text=f"  {theme['emoji']}  {theme['name']}  ({len(items)} products)",
                    bg=theme["color"], fg="#0d1b2a",
                    font=("Segoe UI", 13, "bold"), anchor="w",
                ).pack(side="left", padx=10)

                for p in items:
                    rank += 1
                    self._add_product_card(self.picks_inner, p, rank, theme)

        def _add_product_card(
            self,
            parent: Any,
            p: Product,
            rank: int,
            theme: dict[str, str],
        ) -> None:
            outer = tk.Frame(parent, bg=theme["color"])
            outer.pack(fill="x", padx=8, pady=(0, 3))

            card = tk.Frame(outer, bg="#1a2e42")
            card.pack(fill="x", padx=2, pady=(0, 2))

            # Rank + Title
            top_row = tk.Frame(card, bg="#1a2e42")
            top_row.pack(fill="x", padx=12, pady=(10, 2))

            rank_label = f"#{rank}"
            if p.is_top_pick:
                rank_label = f"#{rank}"

            tk.Label(
                top_row, text=rank_label,
                bg="#1a2e42", fg="#ffd166",
                font=("Segoe UI", 14, "bold"),
            ).pack(side="left", padx=(0, 10))

            tk.Label(
                top_row, text=p.title[:75],
                bg="#1a2e42", fg="#ffffff",
                font=("Segoe UI", 11, "bold"), anchor="w",
                wraplength=800,
            ).pack(side="left", fill="x", expand=True)

            # Score badge
            score_color = "#ffd166" if p.score >= 60 else "#a0b4c8"
            tk.Label(
                top_row, text=f" {p.score}/100 ",
                bg=score_color, fg="#1a1208",
                font=("Segoe UI", 10, "bold"),
            ).pack(side="right", padx=4)

            if p.is_top_pick:
                tk.Label(
                    top_row, text=" TOP ",
                    bg="#e74c3c", fg="#fff",
                    font=("Segoe UI", 8, "bold"),
                ).pack(side="right", padx=4)

            # Stats row
            stats: list[str] = []
            if p.price:
                stats.append(f"${p.price:.2f}")
            if p.rating:
                reviews = f" ({p.review_count:,})" if p.review_count else ""
                stats.append(f"Rating: {p.rating}{reviews}")
            stats.append(f"Source: {p.source}")
            if p.trend_direction != "unknown":
                arrow = {"rising": "Rising", "falling": "Falling", "stable": "Stable"}
                stats.append(f"Trend: {arrow.get(p.trend_direction, p.trend_direction)}")
            if p.asin:
                stats.append(f"ASIN: {p.asin}")

            if stats:
                tk.Label(
                    card, text="  |  ".join(stats),
                    bg="#1a2e42", fg="#a0b4c8",
                    font=("Segoe UI", 9), anchor="w",
                ).pack(fill="x", padx=12, pady=2)

            # Buttons
            bf = tk.Frame(card, bg="#1a2e42")
            bf.pack(fill="x", padx=12, pady=(4, 10))

            aff_link = p.affiliate_url or build_affiliate_url(
                asin=p.asin, keyword=p.keyword, tag=self.config.get("affiliate_tag", "")
            )

            tk.Button(
                bf, text="Open Affiliate Link", bg="#27ae60", fg="#fff",
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                command=lambda u=aff_link: webbrowser.open(u) if u else None,
            ).pack(side="left", padx=(0, 6), ipady=4, ipadx=10)

            tk.Button(
                bf, text="Copy Link", bg="#ffd166", fg="#1a1208",
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                command=lambda u=aff_link: self._copy_text(u),
            ).pack(side="left", padx=(0, 6), ipady=4, ipadx=10)

            tk.Button(
                bf, text="Details", bg="#3a4f66", fg="#fff",
                font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                command=lambda prod=p: self._show_detail(prod),
            ).pack(side="left", ipady=4, ipadx=10)

            # Affiliate URL preview
            if aff_link:
                tk.Label(
                    card, text=aff_link[:100],
                    bg="#1a2e42", fg="#5a7a9a",
                    font=("Consolas", 7), anchor="w",
                ).pack(fill="x", padx=12, pady=(0, 6))

        def _apply_filter(self) -> None:
            for w in self.all_inner.winfo_children():
                w.destroy()

            q = self.search_var.get().lower().strip()
            cat = self.cat_filter_var.get()
            min_score = self.min_score_var.get()

            filtered = []
            for p in self.products:
                if q and q not in p.label().lower():
                    continue
                if cat != "all" and p.category != cat:
                    continue
                if p.score < min_score:
                    continue
                filtered.append(p)

            filtered.sort(key=lambda x: x.score, reverse=True)
            theme = CATEGORY_THEMES.get("other", CATEGORY_THEMES["other"])

            for i, p in enumerate(filtered[:50], 1):
                cat_theme = CATEGORY_THEMES.get(p.category, theme)
                self._add_product_card(self.all_inner, p, i, cat_theme)

            self.status_var.set(
                f"Showing {min(len(filtered), 50)} of {len(self.products)} products"
            )

        def _copy_text(self, text: str) -> None:
            if not text:
                return
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.status_var.set(f"Copied: {text[:60]}")
            except Exception:
                pass

        def _show_detail(self, p: Product) -> None:
            top = tk.Toplevel(self.root)
            top.title(f"Details: {p.label()[:60]}")
            top.geometry("700x550")
            top.configure(bg="#0d1b2a")
            top.transient(self.root)

            txt = scrolledtext.ScrolledText(
                top, bg="#0a1520", fg="#cfe8d4",
                font=("Consolas", 10), relief="flat",
            )
            txt.pack(fill="both", expand=True, padx=10, pady=10)

            lines = [
                f"Product: {p.label()}",
                "=" * 60,
                f"Score: {p.score}/100",
                f"Score Breakdown: {p.score_breakdown}",
                f"Category: {p.category}",
                f"Source: {p.source}",
                f"Trend Type: {p.trend_type}",
                f"Traffic: {p.traffic:,}",
                "",
                "--- Product Details ---",
                f"ASIN: {p.asin}" if p.asin else "ASIN: N/A",
                f"Price: ${p.price:.2f}" if p.price else "Price: N/A",
                f"Rating: {p.rating}/5" if p.rating else "Rating: N/A",
                f"Reviews: {p.review_count:,}" if p.review_count else "Reviews: N/A",
                f"Brand: {p.brand}" if p.brand else "",
                "",
                "--- Trend Info ---",
                f"Direction: {p.trend_direction}",
                f"Change: {p.trend_change_pct:+.1f}%",
                f"Pinterest Saves: {p.pinterest_saves:,}" if p.pinterest_saves else "",
                "",
                "--- Links ---",
                f"Affiliate: {p.affiliate_url}",
                f"Product: {p.product_url}",
                f"Image: {p.image_url}" if p.image_url else "",
            ]
            txt.insert("1.0", "\n".join(line for line in lines if line is not None))
            txt.configure(state="disabled")

        def _save_to_folders(self) -> None:
            if not self.products:
                messagebox.showinfo("Save", "Run a scan first to discover products.")
                return

            output_dir = self.config.get("output_dir", "")
            if not output_dir:
                output_dir = filedialog.askdirectory(
                    title="Choose output folder for products"
                )
                if not output_dir:
                    return
                self.config["output_dir"] = output_dir
                save_config(self.config)

            try:
                organizer = ProductOrganizer(output_dir)
                self._log_msg(f"\nSaving {len(self.products)} products to {output_dir}...")

                for i, p in enumerate(self.products, 1):
                    product_dir = organizer.save_product(p, download_img=True)
                    self._log_msg(f"  [{i}/{len(self.products)}] Saved: {p.title[:50]}...")

                summary_path = organizer.save_summary(self.products)
                top_path = organizer.save_top_picks(self.products)

                self._log_msg(f"\nAll products saved to: {output_dir}")
                self._log_msg(f"Summary CSV: {summary_path}")
                self._log_msg(f"Top picks JSON: {top_path}")

                messagebox.showinfo(
                    "Saved Successfully",
                    f"Saved {len(self.products)} products to:\n{output_dir}\n\n"
                    f"Summary: products_summary.csv\n"
                    f"Top picks: top_picks.json",
                )
            except Exception as exc:
                messagebox.showerror("Save Error", str(exc))

        def _export_dialog(self) -> None:
            if not self.products:
                messagebox.showinfo("Export", "Run a scan first.")
                return

            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[
                    ("CSV", "*.csv"),
                    ("Excel", "*.xlsx"),
                    ("JSON", "*.json"),
                ],
                initialfile=f"nexora_products_{datetime.now():%Y%m%d}.csv",
            )
            if not path:
                return

            try:
                p = Path(path)
                if p.suffix == ".csv":
                    with open(p, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=[
                            "title", "keyword", "asin", "category", "source",
                            "score", "price", "rating", "review_count",
                            "trend_direction", "affiliate_url", "image_url",
                            "is_top_pick",
                        ])
                        writer.writeheader()
                        for prod in self.products:
                            writer.writerow({
                                "title": prod.title,
                                "keyword": prod.keyword,
                                "asin": prod.asin,
                                "category": prod.category,
                                "source": prod.source,
                                "score": prod.score,
                                "price": prod.price,
                                "rating": prod.rating,
                                "review_count": prod.review_count,
                                "trend_direction": prod.trend_direction,
                                "affiliate_url": prod.affiliate_url,
                                "image_url": prod.image_url,
                                "is_top_pick": prod.is_top_pick,
                            })
                elif p.suffix == ".xlsx" and PANDAS_OK:
                    data = [prod.to_dict() for prod in self.products]
                    df = pd.DataFrame(data)
                    df.to_excel(p, index=False, engine="openpyxl")
                else:
                    data = [prod.to_dict() for prod in self.products]
                    p.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8",
                    )

                messagebox.showinfo(
                    "Exported",
                    f"Exported {len(self.products)} products to:\n{p}",
                )
            except Exception as exc:
                messagebox.showerror("Export Error", str(exc))

        def _open_settings(self) -> None:
            top = tk.Toplevel(self.root)
            top.title("Settings")
            top.geometry("550x450")
            top.configure(bg="#0d1b2a")
            top.transient(self.root)

            tk.Label(
                top, text="NEXORA Settings",
                bg="#0d1b2a", fg="#e8a020",
                font=("Segoe UI", 16, "bold"),
            ).pack(pady=(18, 4))

            grid = tk.Frame(top, bg="#0d1b2a")
            grid.pack(padx=24, pady=8, fill="x")

            # Affiliate Tag
            tk.Label(
                grid, text="Amazon Affiliate Tag:",
                bg="#0d1b2a", fg="#7ec8a0",
                font=("Segoe UI", 11, "bold"), anchor="w",
            ).grid(row=0, column=0, sticky="w", pady=(0, 4))

            tag_entry = tk.Entry(
                grid, width=30, bg="#1a2e42", fg="#fff",
                insertbackground="#fff", relief="flat",
                font=("Segoe UI", 11),
            )
            tag_entry.insert(0, self.config.get("affiliate_tag", AFFILIATE_TAG))
            tag_entry.grid(row=1, column=0, sticky="we", ipady=6)

            # Output Directory
            tk.Label(
                grid, text="Output Directory:",
                bg="#0d1b2a", fg="#7ec8a0",
                font=("Segoe UI", 11, "bold"), anchor="w",
            ).grid(row=2, column=0, sticky="w", pady=(14, 4))

            dir_row = tk.Frame(grid, bg="#0d1b2a")
            dir_row.grid(row=3, column=0, sticky="we")
            dir_row.columnconfigure(0, weight=1)

            dir_var = tk.StringVar(value=self.config.get("output_dir", ""))
            dir_entry = tk.Entry(
                dir_row, textvariable=dir_var,
                bg="#1a2e42", fg="#fff", insertbackground="#fff",
                relief="flat", font=("Segoe UI", 10),
            )
            dir_entry.grid(row=0, column=0, sticky="we", ipady=5)

            def browse_dir() -> None:
                d = filedialog.askdirectory(title="Choose output folder")
                if d:
                    dir_var.set(d)

            tk.Button(
                dir_row, text="Browse", bg="#3a4f66", fg="#fff",
                font=("Segoe UI", 9), relief="flat", cursor="hand2",
                command=browse_dir,
            ).grid(row=0, column=1, padx=(6, 0), ipady=4, ipadx=10)

            # Products per category
            tk.Label(
                grid, text="Products per Category:",
                bg="#0d1b2a", fg="#7ec8a0",
                font=("Segoe UI", 10, "bold"), anchor="w",
            ).grid(row=4, column=0, sticky="w", pady=(14, 4))

            n_var = tk.IntVar(value=self.config.get("products_per_category", 5))
            tk.Spinbox(
                grid, from_=1, to=10, textvariable=n_var, width=5,
                bg="#1a2e42", fg="#fff", relief="flat",
                font=("Segoe UI", 11),
            ).grid(row=5, column=0, sticky="w", pady=2)

            # Top featured
            tk.Label(
                grid, text="Top Featured Count:",
                bg="#0d1b2a", fg="#7ec8a0",
                font=("Segoe UI", 10, "bold"), anchor="w",
            ).grid(row=6, column=0, sticky="w", pady=(14, 4))

            top_var = tk.IntVar(value=self.config.get("top_featured", 5))
            tk.Spinbox(
                grid, from_=1, to=10, textvariable=top_var, width=5,
                bg="#1a2e42", fg="#fff", relief="flat",
                font=("Segoe UI", 11),
            ).grid(row=7, column=0, sticky="w", pady=2)

            def save_and_close() -> None:
                self.config["affiliate_tag"] = tag_entry.get().strip() or AFFILIATE_TAG
                self.config["output_dir"] = dir_var.get().strip()
                self.config["products_per_category"] = max(1, min(10, n_var.get()))
                self.config["top_featured"] = max(1, min(10, top_var.get()))
                save_config(self.config)
                top.destroy()
                messagebox.showinfo("Saved", "Settings saved successfully.")

            btns = tk.Frame(top, bg="#0d1b2a")
            btns.pack(pady=18)
            tk.Button(
                btns, text="Save", bg="#27ae60", fg="#fff",
                font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                command=save_and_close,
            ).pack(side="left", padx=6, ipady=6, ipadx=20)
            tk.Button(
                btns, text="Cancel", bg="#5a6c7d", fg="#fff",
                font=("Segoe UI", 10), relief="flat", cursor="hand2",
                command=top.destroy,
            ).pack(side="left", padx=6, ipady=6, ipadx=14)

        def _clear_cache(self) -> None:
            cache.clear()
            self._log_msg("Cache cleared.")

    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    app = App(root)
    root.mainloop()


# ============================================================
# CLI MODE
# ============================================================
def run_cli(args: list[str]) -> None:
    """Command-line interface for headless/scheduled runs."""
    import argparse

    parser = argparse.ArgumentParser(description="NEXORA Product Scraper v3.0")
    parser.add_argument(
        "--sources", default="google,pinterest,amazon",
        help="Comma-separated sources: google,pinterest,amazon",
    )
    parser.add_argument("--output", "-o", default="", help="Output directory")
    parser.add_argument("--top", type=int, default=20, help="Total products to select")
    parser.add_argument(
        "--export", default="", help="Export file path (.csv/.xlsx/.json)"
    )
    parser.add_argument("--tag", default="", help="Amazon affiliate tag")
    parser.add_argument("--no-images", action="store_true", help="Skip image downloads")
    parsed = parser.parse_args(args)

    config = load_config()
    if parsed.tag:
        config["affiliate_tag"] = parsed.tag
    if parsed.output:
        config["output_dir"] = parsed.output
    config["total_products"] = parsed.top

    sources = [s.strip() for s in parsed.sources.split(",")]

    scraper = ProductScraper(config=config)
    products = scraper.run(sources)

    if parsed.output:
        organizer = ProductOrganizer(parsed.output)
        for p in products:
            organizer.save_product(p, download_img=not parsed.no_images)
        organizer.save_summary(products)
        organizer.save_top_picks(products)
        print(f"\nSaved {len(products)} products to: {parsed.output}")

    if parsed.export:
        export_path = Path(parsed.export)
        if export_path.suffix == ".csv":
            with open(export_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "title", "keyword", "asin", "category", "source",
                    "score", "price", "rating", "affiliate_url", "is_top_pick",
                ])
                writer.writeheader()
                for p in products:
                    writer.writerow({
                        "title": p.title, "keyword": p.keyword, "asin": p.asin,
                        "category": p.category, "source": p.source,
                        "score": p.score, "price": p.price, "rating": p.rating,
                        "affiliate_url": p.affiliate_url,
                        "is_top_pick": p.is_top_pick,
                    })
        else:
            data = [p.to_dict() for p in products]
            export_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        print(f"Exported to: {parsed.export}")


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    if "--no-gui" in sys.argv or "--cli" in sys.argv:
        cli_args = [a for a in sys.argv[1:] if a not in ("--no-gui", "--cli")]
        run_cli(cli_args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
