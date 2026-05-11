"""
NEXORA Product Exporter
=======================
Scrapes all products from the live Nexora website, uploads each product image
to ImgBB, and produces an Excel (.xlsx) spreadsheet ready for Make.com automation.

Columns: Title | Description | Category | Affiliate Link | Image URL (ImgBB) | Status

Usage:
    python nexora_product_exporter.py

Output:
    nexora_products_export.xlsx   (in current working directory)

Author : Devin (for Kareem Elsayed / Nexora project)
"""
from __future__ import annotations

import base64
import io
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import warnings

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from openpyxl import Workbook

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SITE_URL = "https://nexora-shop-us.netlify.app"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
IMGBB_API_KEY = "9c5a54329d929ce98cde36976412fb23"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"

REQUEST_TIMEOUT = 30
IMGBB_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries
RATE_LIMIT_DELAY = 0.5  # seconds between imgbb uploads

OUTPUT_FILE = "nexora_products_export.xlsx"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexora_exporter")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Product:
    title: str = ""
    description: str = ""
    category: str = ""
    affiliate_link: str = ""
    image_url_original: str = ""
    image_url_imgbb: str = ""
    status: str = "ready"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
})


def fetch(url: str, *, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """GET a URL with retries. Returns response text or None."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


def fetch_bytes(url: str, *, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    """GET a URL and return raw bytes with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


# ---------------------------------------------------------------------------
# Step 1: Discover product URLs from the sitemap
# ---------------------------------------------------------------------------
def get_product_urls() -> list[str]:
    """Parse sitemap.xml and return all product page URLs."""
    log.info("Fetching sitemap from %s", SITEMAP_URL)
    xml_text = fetch(SITEMAP_URL)
    if not xml_text:
        log.error("Could not fetch sitemap.xml")
        return []

    soup = BeautifulSoup(xml_text, "html.parser")
    urls: list[str] = []
    for loc in soup.find_all("loc"):
        url = loc.get_text(strip=True)
        if "/product/" in url:
            urls.append(url)

    log.info("Found %d product URLs in sitemap", len(urls))
    return urls


# ---------------------------------------------------------------------------
# Step 2: Scrape a single product page
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "tech": "Tech",
    "electronics": "Tech",
    "home": "Home & Kitchen",
    "home & kitchen": "Home & Kitchen",
    "beauty": "Beauty & Personal Care",
    "beauty & personal care": "Beauty & Personal Care",
    "pet": "Pet Supplies",
    "pet supplies": "Pet Supplies",
}


def normalize_category(raw: str) -> str:
    """Clean up emoji/whitespace and map to a standard category name."""
    cleaned = re.sub(r"[^\w\s&]", "", raw).strip()
    key = cleaned.lower()
    return CATEGORY_MAP.get(key, cleaned if cleaned else "Other")


def scrape_product(url: str) -> Optional[Product]:
    """Scrape a single product page and return a Product dataclass."""
    html = fetch(url)
    if not html:
        log.error("Failed to fetch product page: %s", url)
        return None

    soup = BeautifulSoup(html, "html.parser")
    product = Product()

    # Title
    title_el = soup.select_one("h1.prod-title")
    if title_el:
        product.title = title_el.get_text(strip=True)

    # Category
    cat_el = soup.select_one("span.prod-cat")
    if cat_el:
        product.category = normalize_category(cat_el.get_text(strip=True))

    # Image
    img_wrap = soup.select_one(".prod-image-wrap img")
    if img_wrap and img_wrap.get("src"):
        product.image_url_original = img_wrap["src"]

    # Affiliate link
    buy_btn = soup.select_one("a.buy-btn")
    if buy_btn and buy_btn.get("href"):
        product.affiliate_link = buy_btn["href"]

    # Description
    desc_div = soup.select_one(".prod-description")
    if desc_div:
        paragraphs = [p.get_text(strip=True) for p in desc_div.find_all("p")]
        product.description = "\n".join(p for p in paragraphs if p)

    if not product.title:
        log.warning("No title found on %s — skipping", url)
        return None

    return product


# ---------------------------------------------------------------------------
# Step 3: Upload image to ImgBB
# ---------------------------------------------------------------------------
def upload_to_imgbb(image_url: str, name: str = "") -> Optional[str]:
    """Download an image and upload it to ImgBB. Returns the hosted URL."""
    image_data = fetch_bytes(image_url)
    if not image_data:
        log.error("Could not download image: %s", image_url)
        return None

    encoded = base64.b64encode(image_data).decode("utf-8")
    payload = {
        "key": IMGBB_API_KEY,
        "image": encoded,
    }
    if name:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "", name.replace(" ", "-"))[:60]
        payload["name"] = slug

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.post(
                IMGBB_UPLOAD_URL,
                data=payload,
                timeout=IMGBB_TIMEOUT,
            )
            result = resp.json()
            if result.get("success"):
                hosted_url = result["data"]["url"]
                log.info("Uploaded to ImgBB: %s", hosted_url)
                return hosted_url
            else:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                log.warning(
                    "ImgBB upload attempt %d/%d failed: %s",
                    attempt, MAX_RETRIES, error_msg,
                )
        except requests.RequestException as exc:
            log.warning(
                "ImgBB upload attempt %d/%d error: %s",
                attempt, MAX_RETRIES, exc,
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * attempt)

    log.error("All ImgBB upload attempts failed for: %s", image_url)
    return None


# ---------------------------------------------------------------------------
# Step 4: Generate styled Excel workbook
# ---------------------------------------------------------------------------
def build_excel(products: list[Product], output_path: str) -> None:
    """Create a professionally formatted Excel file from the product list."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Nexora Products"

    # Column headers
    headers = ["#", "Title", "Description", "Category", "Affiliate Link", "Image URL", "Status"]
    col_widths = [5, 55, 60, 22, 55, 55, 12]

    # Styles
    header_font = Font(name="Inter", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1a1a2e", end_color="1a1a2e", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    cell_font = Font(name="Inter", size=10)
    cell_align = Alignment(vertical="top", wrap_text=True)
    link_font = Font(name="Inter", size=10, color="0563C1", underline="single")

    ready_fill = PatternFill(start_color="d4edda", end_color="d4edda", fill_type="solid")
    ready_font = Font(name="Inter", size=10, bold=True, color="155724")

    alt_fill = PatternFill(start_color="f8f9fa", end_color="f8f9fa", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="dee2e6"),
        right=Side(style="thin", color="dee2e6"),
        top=Side(style="thin", color="dee2e6"),
        bottom=Side(style="thin", color="dee2e6"),
    )

    # Category color mapping
    cat_fills = {
        "Tech": PatternFill(start_color="cce5ff", end_color="cce5ff", fill_type="solid"),
        "Home & Kitchen": PatternFill(start_color="fff3cd", end_color="fff3cd", fill_type="solid"),
        "Beauty & Personal Care": PatternFill(start_color="f8d7da", end_color="f8d7da", fill_type="solid"),
        "Pet Supplies": PatternFill(start_color="d4edda", end_color="d4edda", fill_type="solid"),
    }

    # Write headers
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # Set column widths
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    # Write product rows
    for row_idx, product in enumerate(products, start=2):
        row_num = row_idx - 1

        # Row number
        cell = ws.cell(row=row_idx, column=1, value=row_num)
        cell.font = cell_font
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border

        # Title
        cell = ws.cell(row=row_idx, column=2, value=product.title)
        cell.font = cell_font
        cell.alignment = cell_align
        cell.border = thin_border

        # Description
        cell = ws.cell(row=row_idx, column=3, value=product.description)
        cell.font = cell_font
        cell.alignment = cell_align
        cell.border = thin_border

        # Category
        cell = ws.cell(row=row_idx, column=4, value=product.category)
        cell.font = Font(name="Inter", size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border
        if product.category in cat_fills:
            cell.fill = cat_fills[product.category]

        # Affiliate Link
        cell = ws.cell(row=row_idx, column=5, value=product.affiliate_link)
        cell.font = link_font
        cell.alignment = cell_align
        cell.border = thin_border
        if product.affiliate_link:
            cell.hyperlink = product.affiliate_link

        # Image URL (ImgBB)
        img_url = product.image_url_imgbb or product.image_url_original
        cell = ws.cell(row=row_idx, column=6, value=img_url)
        cell.font = link_font
        cell.alignment = cell_align
        cell.border = thin_border
        if img_url:
            cell.hyperlink = img_url

        # Status
        cell = ws.cell(row=row_idx, column=7, value=product.status)
        cell.font = ready_font
        cell.fill = ready_fill
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border

        # Alternate row shading (skip category & status which have their own fill)
        if row_num % 2 == 0:
            for col in [1, 2, 3, 5]:
                ws.cell(row=row_idx, column=col).fill = alt_fill

    # Add auto-filter
    ws.auto_filter.ref = f"A1:G{len(products) + 1}"

    # Add summary sheet
    ws_summary = wb.create_sheet("Summary")
    ws_summary["A1"] = "Nexora Product Export Summary"
    ws_summary["A1"].font = Font(name="Inter", bold=True, size=14)

    ws_summary["A3"] = "Total Products:"
    ws_summary["B3"] = len(products)
    ws_summary["A4"] = "Export Date:"
    ws_summary["B4"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ws_summary["A5"] = "Site URL:"
    ws_summary["B5"] = SITE_URL

    # Category breakdown
    ws_summary["A7"] = "Category Breakdown:"
    ws_summary["A7"].font = Font(name="Inter", bold=True, size=11)
    cat_counts: dict[str, int] = {}
    for p in products:
        cat_counts[p.category] = cat_counts.get(p.category, 0) + 1
    for i, (cat, count) in enumerate(sorted(cat_counts.items()), start=8):
        ws_summary[f"A{i}"] = cat
        ws_summary[f"B{i}"] = count

    ws_summary.column_dimensions["A"].width = 30
    ws_summary.column_dimensions["B"].width = 40

    wb.save(output_path)
    log.info("Excel file saved: %s", output_path)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("NEXORA Product Exporter — Starting")
    log.info("=" * 60)

    # Step 1: Get product URLs
    product_urls = get_product_urls()
    if not product_urls:
        log.error("No product URLs found. Exiting.")
        sys.exit(1)

    # Step 2: Scrape each product
    products: list[Product] = []
    total = len(product_urls)
    for idx, url in enumerate(product_urls, start=1):
        log.info("[%d/%d] Scraping: %s", idx, total, url.split("/product/")[-1][:60])
        product = scrape_product(url)
        if product:
            products.append(product)
        time.sleep(0.3)  # polite delay between page fetches

    log.info("Successfully scraped %d / %d products", len(products), total)

    if not products:
        log.error("No products scraped successfully. Exiting.")
        sys.exit(1)

    # Step 3: Upload images to ImgBB
    log.info("=" * 60)
    log.info("Uploading %d product images to ImgBB...", len(products))
    log.info("=" * 60)

    success_count = 0
    fail_count = 0
    for idx, product in enumerate(products, start=1):
        if not product.image_url_original:
            log.warning("[%d/%d] No image URL for: %s", idx, len(products), product.title[:50])
            fail_count += 1
            continue

        log.info("[%d/%d] Uploading image for: %s", idx, len(products), product.title[:50])
        imgbb_url = upload_to_imgbb(product.image_url_original, name=product.title[:60])

        if imgbb_url:
            product.image_url_imgbb = imgbb_url
            success_count += 1
        else:
            log.error("[%d/%d] ImgBB upload failed — using original URL", idx, len(products))
            product.image_url_imgbb = product.image_url_original
            fail_count += 1

        time.sleep(RATE_LIMIT_DELAY)  # rate limit protection

    log.info("ImgBB uploads: %d success, %d failed", success_count, fail_count)

    # Step 4: Generate Excel
    log.info("=" * 60)
    log.info("Generating Excel spreadsheet...")
    log.info("=" * 60)
    build_excel(products, OUTPUT_FILE)

    # Final summary
    log.info("=" * 60)
    log.info("EXPORT COMPLETE")
    log.info("  Products exported : %d", len(products))
    log.info("  Images on ImgBB   : %d", success_count)
    log.info("  Output file       : %s", OUTPUT_FILE)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
