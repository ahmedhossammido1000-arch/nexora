"""
NEXORA Product Exporter — Professional GUI Edition
====================================================
Standalone tool with a premium dark-mode GUI (Tkinter).
Scrapes all products from the live Nexora website, uploads images to ImgBB,
and produces a styled Excel (.xlsx) spreadsheet for Make.com automation.

Features:
  - Professional dark-mode dashboard
  - Bilingual interface (Arabic + English)
  - Live digital counters: total / scraped / uploaded / remaining
  - Animated progress bar
  - Real-time scrolling log
  - No browser windows opened — all network requests in background

Requirements (auto-installed on first run):
    requests, beautifulsoup4, openpyxl

Usage:
    python nexora_product_exporter.py

Author : Devin (for Kareem Elsayed / Nexora project)
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Auto-install missing dependencies
# ---------------------------------------------------------------------------
_REQUIRED = ["requests", "bs4", "openpyxl"]


def _ensure_deps() -> None:
    missing = []
    for pkg in _REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    pip_names = [p if p != "bs4" else "beautifulsoup4" for p in missing]
    print(f"Installing missing packages: {', '.join(pip_names)} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet"] + pip_names,
    )


_ensure_deps()

import requests  # noqa: E402
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

import tkinter as tk  # noqa: E402
from tkinter import ttk, messagebox  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SITE_URL = "https://nexora-shop-us.netlify.app"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"

# Default API keys — 5 accounts for automatic rotation on rate limit
DEFAULT_IMGBB_KEYS = (
    "9c5a54329d929ce98cde36976412fb23,"
    "74140ca6301c9d99d9c18db9eb50300f,"
    "045024182224b79a64103f33c543c90c,"
    "0eb315e895352245b2ed8d4affa0844e,"
    "bff906780bd0c442e945916049e2cc86"
)


class ImgBBKeyPool:
    """Rotates through multiple ImgBB API keys to avoid rate limits."""

    def __init__(self, keys_csv: str) -> None:
        self.keys = [k.strip() for k in keys_csv.split(",") if k.strip()]
        self._idx = 0

    @property
    def current(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self._idx % len(self.keys)]

    def rotate(self) -> str:
        """Move to next key and return it."""
        if len(self.keys) > 1:
            self._idx = (self._idx + 1) % len(self.keys)
        return self.current

    @property
    def count(self) -> int:
        return len(self.keys)

    def __repr__(self) -> str:
        return f"ImgBBKeyPool({self.count} keys, current={self._idx})"


# Global key pool — initialized with defaults, updated from GUI
_imgbb_pool = ImgBBKeyPool(DEFAULT_IMGBB_KEYS)

REQUEST_TIMEOUT = 30
IMGBB_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2
RATE_LIMIT_DELAY = 0.5

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = str(SCRIPT_DIR / "nexora_products_export.xlsx")

# ---------------------------------------------------------------------------
# Color palette (dark mode)
# ---------------------------------------------------------------------------
BG_DARK = "#0d1117"
BG_CARD = "#161b22"
BG_CARD2 = "#1c2333"
ACCENT = "#e91e63"
ACCENT_HOVER = "#f06292"
GREEN = "#2ea043"
RED = "#f85149"
YELLOW = "#d29922"
BLUE = "#58a6ff"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_DIM = "#484f58"
BORDER_COLOR = "#30363d"
PROGRESS_BG = "#21262d"

# ---------------------------------------------------------------------------
# Bilingual strings
# ---------------------------------------------------------------------------
LANG = {
    "en": {
        "title": "NEXORA Product Exporter",
        "subtitle": "Smart Finds. Better Life.",
        "start_btn": "Start Export",
        "stop_btn": "Running...",
        "done_btn": "Export Complete!",
        "open_file": "Open File",
        "total": "Total Products",
        "scraped": "Scraped",
        "uploaded": "Uploaded to ImgBB",
        "remaining": "Remaining",
        "failed": "Failed",
        "progress": "Progress",
        "status_idle": "Ready — Click 'Start Export' to begin",
        "status_sitemap": "Fetching sitemap...",
        "status_scraping": "Scraping product {i}/{n}: {name}",
        "status_uploading": "Uploading image {i}/{n}: {name}",
        "status_excel": "Generating Excel spreadsheet...",
        "status_done": "Export complete! File saved.",
        "status_error": "Error: {err}",
        "lang_btn": "عربي",
        "api_keys_label": "ImgBB API Keys (comma-separated, up to 5):",
        "api_keys_hint": "key1, key2, key3...",
        "keys_loaded": "{n} API key(s) loaded",
        "log_title": "Live Log",
        "category_breakdown": "Category Breakdown",
        "no_products": "No products found on the website.",
        "scrape_phase": "PHASE 1: Scraping Products",
        "upload_phase": "PHASE 2: Uploading Images",
        "excel_phase": "PHASE 3: Generating Excel",
    },
    "ar": {
        "title": "أداة تصدير منتجات NEXORA",
        "subtitle": "اكتشافات ذكية. حياة أفضل.",
        "start_btn": "ابدأ التصدير",
        "stop_btn": "جاري التشغيل...",
        "done_btn": "تم التصدير بنجاح!",
        "open_file": "فتح الملف",
        "total": "إجمالي المنتجات",
        "scraped": "تم السحب",
        "uploaded": "تم الرفع على ImgBB",
        "remaining": "المتبقي",
        "failed": "فشل",
        "progress": "التقدم",
        "status_idle": "جاهز — اضغط 'ابدأ التصدير' للبدء",
        "status_sitemap": "جاري تحميل خريطة الموقع...",
        "status_scraping": "سحب المنتج {i}/{n}: {name}",
        "status_uploading": "رفع الصورة {i}/{n}: {name}",
        "status_excel": "جاري إنشاء ملف Excel...",
        "status_done": "تم التصدير بنجاح! الملف تم حفظه.",
        "status_error": "خطأ: {err}",
        "lang_btn": "English",
        "api_keys_label": "مفاتيح ImgBB API (مفصولة بفاصلة، حتى 5):",
        "api_keys_hint": "key1, key2, key3...",
        "keys_loaded": "تم تحميل {n} مفتاح API",
        "log_title": "سجل مباشر",
        "category_breakdown": "تقسيم الفئات",
        "no_products": "لم يتم العثور على منتجات في الموقع.",
        "scrape_phase": "المرحلة 1: سحب المنتجات",
        "upload_phase": "المرحلة 2: رفع الصور",
        "excel_phase": "المرحلة 3: إنشاء ملف Excel",
    },
}

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
# HTTP helpers (no browser, just requests)
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
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


def fetch_bytes(url: str, *, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    return None


# ---------------------------------------------------------------------------
# Scraping logic
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
    cleaned = re.sub(r"[^\w\s&]", "", raw).strip()
    key = cleaned.lower()
    return CATEGORY_MAP.get(key, cleaned if cleaned else "Other")


def get_product_urls() -> list[str]:
    xml_text = fetch(SITEMAP_URL)
    if not xml_text:
        return []
    soup = BeautifulSoup(xml_text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/product/" in loc.get_text()]


def scrape_product(url: str) -> Optional[Product]:
    html = fetch(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    product = Product()

    title_el = soup.select_one("h1.prod-title")
    if title_el:
        product.title = title_el.get_text(strip=True)

    cat_el = soup.select_one("span.prod-cat")
    if cat_el:
        product.category = normalize_category(cat_el.get_text(strip=True))

    img_wrap = soup.select_one(".prod-image-wrap img")
    if img_wrap and img_wrap.get("src"):
        product.image_url_original = img_wrap["src"]

    buy_btn = soup.select_one("a.buy-btn")
    if buy_btn and buy_btn.get("href"):
        product.affiliate_link = buy_btn["href"]

    desc_div = soup.select_one(".prod-description")
    if desc_div:
        paragraphs = [p.get_text(strip=True) for p in desc_div.find_all("p")]
        product.description = "\n".join(p for p in paragraphs if p)

    if not product.title:
        return None
    return product


def upload_to_imgbb(image_url: str, name: str = "", log_fn=None) -> Optional[str]:
    """Upload image to ImgBB with automatic key rotation on rate limit."""
    image_data = fetch_bytes(image_url)
    if not image_data:
        return None
    encoded = base64.b64encode(image_data).decode("utf-8")

    base_payload: dict[str, str] = {"image": encoded}
    if name:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "", name.replace(" ", "-"))[:60]
        base_payload["name"] = slug

    # Try each key in the pool (rotate on failure)
    keys_tried = 0
    while keys_tried < _imgbb_pool.count:
        current_key = _imgbb_pool.current
        payload = {**base_payload, "key": current_key}
        key_label = f"Key {(_imgbb_pool._idx % _imgbb_pool.count) + 1}/{_imgbb_pool.count}"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = _session.post(IMGBB_UPLOAD_URL, data=payload, timeout=IMGBB_TIMEOUT)
                result = resp.json()
                if result.get("success"):
                    return result["data"]["url"]
                # Rate limited or forbidden — rotate to next key
                error_msg = result.get("error", {}).get("message", "")
                if "forbidden" in error_msg.lower() or resp.status_code in (429, 403):
                    if log_fn:
                        log_fn(f"{key_label} rate limited, switching...", "warning")
                    break  # break inner loop to rotate key
            except requests.RequestException:
                pass
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
        else:
            # All retries failed for this key without rate limit
            keys_tried += 1
            _imgbb_pool.rotate()
            continue

        # Rate limited — rotate to next key
        keys_tried += 1
        _imgbb_pool.rotate()
        continue

    return None


# ---------------------------------------------------------------------------
# Excel generation
# ---------------------------------------------------------------------------
def build_excel(products: list[Product], output_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Nexora Products"

    headers = ["#", "Title", "Description", "Category", "Affiliate Link", "Image URL", "Status"]
    col_widths = [5, 55, 60, 22, 55, 55, 12]

    header_font = Font(name="Inter", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1a1a2e", end_color="1a1a2e", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    cell_font = Font(name="Inter", size=10)
    cell_align = Alignment(vertical="top", wrap_text=True)
    link_font = Font(name="Inter", size=10, color="0563C1", underline="single")

    ready_fill = PatternFill(start_color="ff0000", end_color="ff0000", fill_type="solid")
    ready_font = Font(name="Inter", size=10, bold=True, color="FFFFFF")

    alt_fill = PatternFill(start_color="f8f9fa", end_color="f8f9fa", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="dee2e6"),
        right=Side(style="thin", color="dee2e6"),
        top=Side(style="thin", color="dee2e6"),
        bottom=Side(style="thin", color="dee2e6"),
    )

    cat_fills = {
        "Tech": PatternFill(start_color="cce5ff", end_color="cce5ff", fill_type="solid"),
        "Home & Kitchen": PatternFill(start_color="fff3cd", end_color="fff3cd", fill_type="solid"),
        "Beauty & Personal Care": PatternFill(start_color="f8d7da", end_color="f8d7da", fill_type="solid"),
        "Pet Supplies": PatternFill(start_color="d4edda", end_color="d4edda", fill_type="solid"),
    }

    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"

    for row_idx, product in enumerate(products, start=2):
        row_num = row_idx - 1

        cell = ws.cell(row=row_idx, column=1, value=row_num)
        cell.font = cell_font
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border

        cell = ws.cell(row=row_idx, column=2, value=product.title)
        cell.font = cell_font
        cell.alignment = cell_align
        cell.border = thin_border

        cell = ws.cell(row=row_idx, column=3, value=product.description)
        cell.font = cell_font
        cell.alignment = cell_align
        cell.border = thin_border

        cell = ws.cell(row=row_idx, column=4, value=product.category)
        cell.font = Font(name="Inter", size=10, bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border
        if product.category in cat_fills:
            cell.fill = cat_fills[product.category]

        cell = ws.cell(row=row_idx, column=5, value=product.affiliate_link)
        cell.font = link_font
        cell.alignment = cell_align
        cell.border = thin_border
        if product.affiliate_link:
            cell.hyperlink = product.affiliate_link

        img_url = product.image_url_imgbb or product.image_url_original
        cell = ws.cell(row=row_idx, column=6, value=img_url)
        cell.font = link_font
        cell.alignment = cell_align
        cell.border = thin_border
        if img_url:
            cell.hyperlink = img_url

        cell = ws.cell(row=row_idx, column=7, value=product.status)
        cell.font = ready_font
        cell.fill = ready_fill
        cell.alignment = Alignment(horizontal="center", vertical="top")
        cell.border = thin_border

        if row_num % 2 == 0:
            for col in [1, 2, 3, 5]:
                ws.cell(row=row_idx, column=col).fill = alt_fill

    ws.auto_filter.ref = f"A1:G{len(products) + 1}"

    ws_summary = wb.create_sheet("Summary")
    ws_summary["A1"] = "Nexora Product Export Summary"
    ws_summary["A1"].font = Font(name="Inter", bold=True, size=14)
    ws_summary["A3"] = "Total Products:"
    ws_summary["B3"] = len(products)
    ws_summary["A4"] = "Export Date:"
    ws_summary["B4"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ws_summary["A5"] = "Site URL:"
    ws_summary["B5"] = SITE_URL

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


# ═══════════════════════════════════════════════════════════════════════════
# GUI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════
class NexoraExporterApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.current_lang = "en"
        self.running = False
        self.products: list[Product] = []

        # Counters
        self.total_count = 0
        self.scraped_count = 0
        self.uploaded_count = 0
        self.failed_count = 0

        self._build_ui()
        self._apply_lang()

    # ── UI construction ──────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = self.root
        root.title("NEXORA Product Exporter")
        root.configure(bg=BG_DARK)
        root.geometry("820x720")
        root.minsize(700, 600)

        # Try to set icon (won't fail if not available)
        try:
            root.iconbitmap(default="")
        except Exception:
            pass

        # ── Header ───────────────────────────────────────────────────────
        header = tk.Frame(root, bg=BG_CARD, pady=12)
        header.pack(fill="x")

        # Logo + Title
        title_frame = tk.Frame(header, bg=BG_CARD)
        title_frame.pack(side="left", padx=20)

        self.logo_label = tk.Label(
            title_frame, text="N", font=("Helvetica", 28, "bold"),
            fg=ACCENT, bg=BG_CARD, width=2,
        )
        self.logo_label.pack(side="left", padx=(0, 10))

        text_frame = tk.Frame(title_frame, bg=BG_CARD)
        text_frame.pack(side="left")

        self.title_label = tk.Label(
            text_frame, text="NEXORA Product Exporter",
            font=("Helvetica", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD,
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = tk.Label(
            text_frame, text="Smart Finds. Better Life.",
            font=("Helvetica", 9), fg=TEXT_SECONDARY, bg=BG_CARD,
        )
        self.subtitle_label.pack(anchor="w")

        # Language toggle button
        self.lang_btn = tk.Button(
            header, text="عربي", font=("Helvetica", 10, "bold"),
            fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=ACCENT,
            activeforeground="white", bd=0, padx=12, pady=4,
            cursor="hand2", command=self._toggle_lang,
        )
        self.lang_btn.pack(side="right", padx=20)

        # ── Separator ───────────────────────────────────────────────────
        tk.Frame(root, bg=ACCENT, height=3).pack(fill="x")

        # ── Main content ────────────────────────────────────────────────
        main = tk.Frame(root, bg=BG_DARK, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        # ── API Keys input ───────────────────────────────────────────────
        api_frame = tk.Frame(main, bg=BG_CARD, padx=12, pady=8,
                             highlightbackground=BORDER_COLOR, highlightthickness=1)
        api_frame.pack(fill="x", pady=(0, 10))

        self.api_keys_label = tk.Label(
            api_frame, text="ImgBB API Keys (comma-separated, up to 5):",
            font=("Helvetica", 9, "bold"), fg=TEXT_SECONDARY, bg=BG_CARD, anchor="w",
        )
        self.api_keys_label.pack(fill="x")

        api_input_frame = tk.Frame(api_frame, bg=BG_CARD)
        api_input_frame.pack(fill="x", pady=(4, 0))

        self.api_keys_entry = tk.Entry(
            api_input_frame, font=("Consolas", 10),
            bg=BG_DARK, fg=TEXT_PRIMARY, insertbackground=ACCENT,
            selectbackground=ACCENT, bd=0, highlightthickness=1,
            highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
        )
        self.api_keys_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        self.api_keys_entry.insert(0, DEFAULT_IMGBB_KEYS)

        self.api_keys_status = tk.Label(
            api_input_frame, text="1 key(s)", font=("Consolas", 9, "bold"),
            fg=GREEN, bg=BG_CARD, width=14,
        )
        self.api_keys_status.pack(side="right")

        self.api_keys_entry.bind("<KeyRelease>", self._on_api_keys_changed)

        # ── Digital counters row ─────────────────────────────────────────
        counters_frame = tk.Frame(main, bg=BG_DARK)
        counters_frame.pack(fill="x", pady=(0, 12))

        self.counter_widgets: dict[str, dict] = {}
        counter_configs = [
            ("total", BLUE, "0"),
            ("scraped", GREEN, "0"),
            ("uploaded", ACCENT, "0"),
            ("remaining", YELLOW, "0"),
            ("failed", RED, "0"),
        ]

        for i, (key, color, default) in enumerate(counter_configs):
            card = tk.Frame(counters_frame, bg=BG_CARD, padx=12, pady=10,
                            highlightbackground=BORDER_COLOR, highlightthickness=1)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            counters_frame.columnconfigure(i, weight=1)

            val_label = tk.Label(
                card, text=default, font=("Consolas", 26, "bold"),
                fg=color, bg=BG_CARD,
            )
            val_label.pack()

            name_label = tk.Label(
                card, text=key.upper(), font=("Helvetica", 8, "bold"),
                fg=TEXT_SECONDARY, bg=BG_CARD,
            )
            name_label.pack()

            self.counter_widgets[key] = {"val": val_label, "name": name_label}

        # ── Phase indicator ──────────────────────────────────────────────
        phase_frame = tk.Frame(main, bg=BG_CARD, pady=8, padx=12,
                               highlightbackground=BORDER_COLOR, highlightthickness=1)
        phase_frame.pack(fill="x", pady=(0, 8))

        self.phase_label = tk.Label(
            phase_frame, text="", font=("Helvetica", 11, "bold"),
            fg=ACCENT, bg=BG_CARD,
        )
        self.phase_label.pack(side="left")

        self.phase_detail = tk.Label(
            phase_frame, text="", font=("Helvetica", 10),
            fg=TEXT_SECONDARY, bg=BG_CARD,
        )
        self.phase_detail.pack(side="right")

        # ── Progress bar ─────────────────────────────────────────────────
        progress_frame = tk.Frame(main, bg=BG_DARK)
        progress_frame.pack(fill="x", pady=(0, 8))

        self.progress_pct_label = tk.Label(
            progress_frame, text="0%", font=("Consolas", 11, "bold"),
            fg=ACCENT, bg=BG_DARK, width=5,
        )
        self.progress_pct_label.pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG, background=ACCENT,
            bordercolor=BORDER_COLOR, lightcolor=ACCENT, darkcolor=ACCENT,
        )

        self.progress_bar = ttk.Progressbar(
            progress_frame, style="Custom.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100,
        )
        self.progress_bar.pack(fill="x", expand=True, side="left", padx=(0, 8))

        # ── Status line ──────────────────────────────────────────────────
        self.status_label = tk.Label(
            main, text="", font=("Helvetica", 10),
            fg=TEXT_SECONDARY, bg=BG_DARK, anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 8))

        # ── Log area ────────────────────────────────────────────────────
        log_frame = tk.Frame(main, bg=BG_CARD2,
                             highlightbackground=BORDER_COLOR, highlightthickness=1)
        log_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.log_title_label = tk.Label(
            log_frame, text="Live Log", font=("Helvetica", 9, "bold"),
            fg=TEXT_SECONDARY, bg=BG_CARD2, anchor="w", padx=10, pady=4,
        )
        self.log_title_label.pack(fill="x")

        self.log_text = tk.Text(
            log_frame, bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Consolas", 9), wrap="word", bd=0,
            insertbackground=TEXT_PRIMARY, selectbackground=ACCENT,
            padx=10, pady=6, height=10,
        )
        self.log_text.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Tag styles for log
        self.log_text.tag_configure("info", foreground=TEXT_PRIMARY)
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=YELLOW)
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("accent", foreground=ACCENT)
        self.log_text.tag_configure("phase", foreground=BLUE, font=("Consolas", 10, "bold"))

        # ── Bottom buttons ───────────────────────────────────────────────
        btn_frame = tk.Frame(main, bg=BG_DARK)
        btn_frame.pack(fill="x")

        self.start_btn = tk.Button(
            btn_frame, text="Start Export", font=("Helvetica", 13, "bold"),
            fg="white", bg=ACCENT, activebackground=ACCENT_HOVER,
            activeforeground="white", bd=0, padx=30, pady=10,
            cursor="hand2", command=self._on_start,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.open_btn = tk.Button(
            btn_frame, text="Open File", font=("Helvetica", 13, "bold"),
            fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=GREEN,
            activeforeground="white", bd=0, padx=30, pady=10,
            cursor="hand2", state="disabled", command=self._open_file,
        )
        self.open_btn.pack(side="right", expand=True, fill="x", padx=(5, 0))

    # ── Language toggle ──────────────────────────────────────────────────
    def _toggle_lang(self) -> None:
        self.current_lang = "ar" if self.current_lang == "en" else "en"
        self._apply_lang()

    def _t(self, key: str) -> str:
        return LANG[self.current_lang].get(key, key)

    def _apply_lang(self) -> None:
        lang = self.current_lang
        t = LANG[lang]

        self.title_label.config(text=t["title"])
        self.subtitle_label.config(text=t["subtitle"])
        self.lang_btn.config(text=t["lang_btn"])
        self.log_title_label.config(text=t["log_title"])
        self.api_keys_label.config(text=t["api_keys_label"])

        if not self.running:
            self.start_btn.config(text=t["start_btn"])
            self.status_label.config(text=t["status_idle"])

        self.open_btn.config(text=t["open_file"])
        self._on_api_keys_changed()

        counter_keys_map = {
            "total": t["total"],
            "scraped": t["scraped"],
            "uploaded": t["uploaded"],
            "remaining": t["remaining"],
            "failed": t["failed"],
        }
        for key, label_text in counter_keys_map.items():
            self.counter_widgets[key]["name"].config(text=label_text)

    # ── API keys input handler ───────────────────────────────────────────
    def _on_api_keys_changed(self, event=None) -> None:
        raw = self.api_keys_entry.get()
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        n = min(len(keys), 5)
        label = self._t("keys_loaded").format(n=n)
        color = GREEN if n > 0 else RED
        self.api_keys_status.config(text=label, fg=color)

    # ── Logging ──────────────────────────────────────────────────────────
    def _log(self, msg: str, tag: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_text.see("end")

    # ── Counter updates ──────────────────────────────────────────────────
    def _update_counter(self, key: str, value: int) -> None:
        self.counter_widgets[key]["val"].config(text=str(value))

    def _update_progress(self, current: int, total: int) -> None:
        if total == 0:
            return
        pct = int((current / total) * 100)
        self.progress_bar["value"] = pct
        self.progress_pct_label.config(text=f"{pct}%")

    def _set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def _set_phase(self, phase: str, detail: str = "") -> None:
        self.phase_label.config(text=phase)
        self.phase_detail.config(text=detail)

    # ── Start button handler ─────────────────────────────────────────────
    def _on_start(self) -> None:
        if self.running:
            return
        self.running = True
        self.start_btn.config(text=self._t("stop_btn"), state="disabled", bg=TEXT_DIM)
        self.open_btn.config(state="disabled")
        self.api_keys_entry.config(state="disabled")
        self.log_text.delete("1.0", "end")

        # Update key pool from the entry
        global _imgbb_pool
        keys_csv = self.api_keys_entry.get()
        _imgbb_pool = ImgBBKeyPool(keys_csv)
        self._log(f"Loaded {_imgbb_pool.count} ImgBB API key(s)", "accent")

        # Reset counters
        self.total_count = 0
        self.scraped_count = 0
        self.uploaded_count = 0
        self.failed_count = 0
        for key in ["total", "scraped", "uploaded", "remaining", "failed"]:
            self._update_counter(key, 0)
        self._update_progress(0, 1)

        thread = threading.Thread(target=self._run_export, daemon=True)
        thread.start()

    # ── Export logic (runs in background thread) ─────────────────────────
    def _run_export(self) -> None:
        try:
            self._export_workflow()
        except Exception as exc:
            self.root.after(0, lambda: self._on_error(str(exc)))

    def _export_workflow(self) -> None:
        # Phase 1: Get product URLs
        self.root.after(0, lambda: self._set_phase(self._t("scrape_phase")))
        self.root.after(0, lambda: self._set_status(self._t("status_sitemap")))
        self.root.after(0, lambda: self._log(self._t("status_sitemap"), "accent"))

        product_urls = get_product_urls()

        if not product_urls:
            self.root.after(0, lambda: self._log(self._t("no_products"), "error"))
            self.root.after(0, lambda: self._on_error(self._t("no_products")))
            return

        total = len(product_urls)
        self.total_count = total
        self.root.after(0, lambda: self._update_counter("total", total))
        self.root.after(0, lambda: self._update_counter("remaining", total))
        self.root.after(0, lambda: self._log(f"Found {total} products in sitemap", "success"))

        # Phase 1: Scrape products
        products: list[Product] = []
        for idx, url in enumerate(product_urls, start=1):
            short_name = url.split("/product/")[-1][:45]
            status_msg = self._t("status_scraping").format(i=idx, n=total, name=short_name)
            self.root.after(0, lambda m=status_msg: self._set_status(m))
            self.root.after(0, lambda m=short_name, i=idx, n=total: self._log(
                f"[{i}/{n}] Scraping: {m}", "info"
            ))
            self.root.after(0, lambda i=idx, n=total: self._set_phase(
                self._t("scrape_phase"), f"{i}/{n}"
            ))

            product = scrape_product(url)
            if product:
                products.append(product)
                self.scraped_count += 1
            else:
                self.failed_count += 1
                self.root.after(0, lambda m=short_name: self._log(
                    f"Failed to scrape: {m}", "warning"
                ))

            sc = self.scraped_count
            fc = self.failed_count
            remaining = total - idx
            self.root.after(0, lambda v=sc: self._update_counter("scraped", v))
            self.root.after(0, lambda v=fc: self._update_counter("failed", v))
            self.root.after(0, lambda v=remaining: self._update_counter("remaining", v))
            self.root.after(0, lambda i=idx, n=total: self._update_progress(i, n * 2))

            time.sleep(0.3)

        if not products:
            self.root.after(0, lambda: self._on_error(self._t("no_products")))
            return

        self.root.after(0, lambda: self._log(
            f"Scraped {len(products)}/{total} products successfully", "success"
        ))

        # Phase 2: Upload images to ImgBB
        self.root.after(0, lambda: self._set_phase(self._t("upload_phase")))
        self.root.after(0, lambda: self._log("=" * 50, "accent"))
        self.root.after(0, lambda: self._log(self._t("upload_phase"), "phase"))

        upload_total = len(products)
        for idx, product in enumerate(products, start=1):
            short_name = product.title[:45]
            status_msg = self._t("status_uploading").format(i=idx, n=upload_total, name=short_name)
            self.root.after(0, lambda m=status_msg: self._set_status(m))
            self.root.after(0, lambda i=idx, n=upload_total: self._set_phase(
                self._t("upload_phase"), f"{i}/{n}"
            ))

            if not product.image_url_original:
                self.failed_count += 1
                fc = self.failed_count
                self.root.after(0, lambda v=fc: self._update_counter("failed", v))
                self.root.after(0, lambda m=short_name: self._log(
                    f"No image URL for: {m}", "warning"
                ))
                continue

            imgbb_url = upload_to_imgbb(
                product.image_url_original, name=product.title[:60],
                log_fn=lambda msg, tag: self.root.after(0, lambda m=msg, t=tag: self._log(m, t)),
            )
            if imgbb_url:
                product.image_url_imgbb = imgbb_url
                self.uploaded_count += 1
                uc = self.uploaded_count
                self.root.after(0, lambda v=uc: self._update_counter("uploaded", v))
                self.root.after(0, lambda m=short_name: self._log(
                    f"Uploaded: {m}", "success"
                ))
            else:
                product.image_url_imgbb = product.image_url_original
                self.failed_count += 1
                fc = self.failed_count
                self.root.after(0, lambda v=fc: self._update_counter("failed", v))
                self.root.after(0, lambda m=short_name: self._log(
                    f"Upload failed (using original): {m}", "warning"
                ))

            remaining = total - self.scraped_count + upload_total - idx
            self.root.after(0, lambda v=max(0, upload_total - idx): self._update_counter("remaining", v))

            progress_val = total + idx
            progress_max = total + upload_total
            self.root.after(0, lambda c=progress_val, m=progress_max: self._update_progress(c, m))

            time.sleep(RATE_LIMIT_DELAY)

        # Phase 3: Generate Excel
        self.root.after(0, lambda: self._set_phase(self._t("excel_phase")))
        self.root.after(0, lambda: self._set_status(self._t("status_excel")))
        self.root.after(0, lambda: self._log("=" * 50, "accent"))
        self.root.after(0, lambda: self._log(self._t("excel_phase"), "phase"))

        build_excel(products, OUTPUT_FILE)

        self.root.after(0, lambda: self._log(f"File saved: {OUTPUT_FILE}", "success"))

        # Category breakdown
        cat_counts: dict[str, int] = {}
        for p in products:
            cat_counts[p.category] = cat_counts.get(p.category, 0) + 1

        self.root.after(0, lambda: self._log("=" * 50, "accent"))
        self.root.after(0, lambda: self._log(self._t("category_breakdown"), "phase"))
        for cat, count in sorted(cat_counts.items()):
            self.root.after(0, lambda c=cat, n=count: self._log(f"  {c}: {n}", "info"))

        # Done
        self.root.after(0, lambda: self._on_done(len(products)))

    def _on_done(self, count: int) -> None:
        self.running = False
        self._update_progress(100, 100)
        self._update_counter("remaining", 0)
        self._set_status(self._t("status_done"))
        self._set_phase(self._t("status_done"), f"{count} products")
        self.start_btn.config(text=self._t("start_btn"), state="normal", bg=ACCENT)
        self.open_btn.config(state="normal", bg=GREEN)
        self.api_keys_entry.config(state="normal")
        self._log("=" * 50, "accent")
        self._log(self._t("status_done"), "success")

    def _on_error(self, err: str) -> None:
        self.running = False
        self._set_status(self._t("status_error").format(err=err))
        self.start_btn.config(text=self._t("start_btn"), state="normal", bg=ACCENT)
        self.api_keys_entry.config(state="normal")
        self._log(f"ERROR: {err}", "error")

    def _open_file(self) -> None:
        if os.path.exists(OUTPUT_FILE):
            if sys.platform == "win32":
                os.startfile(OUTPUT_FILE)
            elif sys.platform == "darwin":
                subprocess.call(["open", OUTPUT_FILE])
            else:
                subprocess.call(["xdg-open", OUTPUT_FILE])

    # ── Run ──────────────────────────────────────────────────────────────
    def run(self) -> None:
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = NexoraExporterApp()
    app.run()
