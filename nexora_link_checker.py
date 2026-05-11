"""
NEXORA Link Checker — Professional GUI Edition
================================================
Standalone tool that checks all Amazon affiliate product links in your
products JS file and identifies removed/unavailable products.

Features:
  - Professional dark-mode dashboard (same style as Product Exporter)
  - Bilingual interface (Arabic + English)
  - File picker to select your products JS file
  - Strips affiliate tag before checking (safe for your account)
  - Shows removed products with "Remove" button to delete from file
  - Live progress with digital counters
  - Rate-limited requests (safe for Amazon)

Requirements (auto-installed on first run):
    requests

Usage:
    python nexora_link_checker.py

Author : Devin (for Kareem Elsayed / Nexora project)
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Auto-install missing dependencies
# ---------------------------------------------------------------------------
_REQUIRED = ["requests"]


def _ensure_deps() -> None:
    missing = []
    for pkg in _REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    print(f"Installing missing packages: {', '.join(missing)} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
    )


_ensure_deps()

import requests  # noqa: E402
import tkinter as tk  # noqa: E402
from tkinter import ttk, filedialog, messagebox  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 20
CHECK_DELAY_MIN = 3.0   # minimum seconds between Amazon checks
CHECK_DELAY_MAX = 6.0   # maximum seconds (random human-like delay)
MAX_RETRIES = 3          # retry ambiguous / bot-blocked responses

# ---------------------------------------------------------------------------
# Color palette (dark mode — same as Product Exporter)
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
ORANGE = "#f0883e"
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
        "title": "NEXORA Link Checker",
        "subtitle": "Amazon Product Link Validator",
        "start_btn": "Start Check",
        "stop_btn": "Checking...",
        "select_file": "Select Products File",
        "file_label": "Products JS File:",
        "file_hint": "Click 'Select Products File' to choose your products.js",
        "total": "Total Products",
        "active": "Active",
        "removed": "Removed",
        "remaining": "Remaining",
        "errors": "Errors",
        "status_idle": "Ready — Select your products file and click 'Start Check'",
        "status_loading": "Loading products file...",
        "status_checking": "Checking {i}/{n}: {name}",
        "status_done": "Check complete! {active} active, {removed} removed.",
        "status_error": "Error: {err}",
        "lang_btn": "عربي",
        "log_title": "Live Log",
        "removed_title": "Removed Products (click 'Remove' to delete from file)",
        "remove_btn": "Remove from File",
        "remove_all_btn": "Remove All Unavailable",
        "no_removed": "All products are active!",
        "removed_count": "{n} product(s) removed from file",
        "safe_note": "Affiliate tag stripped — checking original Amazon links (safe)",
        "product_active": "ACTIVE",
        "product_removed": "REMOVED",
        "product_error": "ERROR",
    },
    "ar": {
        "title": "فاحص روابط NEXORA",
        "subtitle": "أداة فحص روابط منتجات أمازون",
        "start_btn": "ابدأ الفحص",
        "stop_btn": "جاري الفحص...",
        "select_file": "اختر ملف المنتجات",
        "file_label": "ملف المنتجات JS:",
        "file_hint": "اضغط 'اختر ملف المنتجات' لاختيار ملف products.js",
        "total": "إجمالي المنتجات",
        "active": "نشط",
        "removed": "متشال",
        "remaining": "المتبقي",
        "errors": "أخطاء",
        "status_idle": "جاهز — اختر ملف المنتجات واضغط 'ابدأ الفحص'",
        "status_loading": "جاري تحميل ملف المنتجات...",
        "status_checking": "فحص {i}/{n}: {name}",
        "status_done": "تم الفحص! {active} نشط، {removed} متشال.",
        "status_error": "خطأ: {err}",
        "lang_btn": "English",
        "log_title": "سجل مباشر",
        "removed_title": "المنتجات المتشالة (اضغط 'شيل' لحذفها من الملف)",
        "remove_btn": "شيل من الملف",
        "remove_all_btn": "شيل كل المنتجات المتاحة",
        "no_removed": "كل المنتجات نشطة!",
        "removed_count": "تم حذف {n} منتج من الملف",
        "safe_note": "تم إزالة الـ affiliate tag — الفحص على الرابط الأصلي (آمن)",
        "product_active": "نشط",
        "product_removed": "متشال",
        "product_error": "خطأ",
    },
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class ProductCheck:
    title: str = ""
    link_original: str = ""
    link_clean: str = ""
    category: str = ""
    slug: str = ""
    status: str = ""  # "active", "removed", "error"
    http_code: int = 0


# ---------------------------------------------------------------------------
# Rotating User-Agents (simulate different real browsers)
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    return s


_session = _make_session()


def _human_delay() -> None:
    """Sleep a random duration to simulate human browsing."""
    time.sleep(random.uniform(CHECK_DELAY_MIN, CHECK_DELAY_MAX))


def strip_affiliate_tag(url: str) -> str:
    """Remove the affiliate tag parameter from an Amazon URL."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    params.pop("tag", None)
    clean_query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=clean_query))


def _is_bot_blocked(text: str) -> bool:
    """Detect if Amazon served a bot-detection / CAPTCHA / throttle page."""
    markers = [
        "sorry, we just need to make sure",
        "enter the characters you see below",
        "type the characters you see in this image",
        "to discuss automated access",
        "automated access to amazon",
        "api-services-support@amazon",
    ]
    lower = text.lower()
    return any(m in lower for m in markers)


def _is_dog_page(text: str) -> bool:
    """Detect Amazon's 'dog page' which means the product truly doesn't exist."""
    lower = text.lower()
    # The real dog/404 page has specific patterns
    has_sorry = "sorry" in lower and "couldn" in lower and "find" in lower
    has_dog_img = "g/img/illustrations" in lower
    return has_sorry and has_dog_img


def check_amazon_link(url: str, log_fn=None) -> tuple[str, int]:
    """
    Check if an Amazon product is still available.
    Returns (status, http_code).
    status: 'active', 'removed', or 'error'
    """
    global _session

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Rotate User-Agent each attempt
            _session.headers["User-Agent"] = random.choice(_USER_AGENTS)

            resp = _session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            code = resp.status_code
            text = resp.text

            if code == 200:
                # 1. Check for bot block / CAPTCHA — NOT a real result
                if _is_bot_blocked(text):
                    if log_fn:
                        log_fn(f"  Bot blocked (attempt {attempt}/{MAX_RETRIES}), waiting...", "warning")
                    if attempt < MAX_RETRIES:
                        # Recreate session with new User-Agent and wait longer
                        _session = _make_session()
                        time.sleep(random.uniform(8, 15))
                        continue
                    return "error", code

                # 2. Check for dog page (true 404 / product removed)
                if _is_dog_page(text):
                    return "removed", 404

                lower = text.lower()

                # 3. Product page indicators (product exists)
                product_indicators = [
                    '<div id="dp"',
                    'id="productTitle"',
                    'id="add-to-cart-button"',
                    '"add to cart"',
                    '"buy now"',
                    'id="priceblock_ourprice"',
                    'id="price_inside_buybox"',
                    'id="acrPopover"',
                    'data-asin',
                ]
                for indicator in product_indicators:
                    if indicator in lower:
                        return "active", code

                # 4. Check for "currently unavailable" (product page exists
                #    but item is out of stock — still counts as active listing)
                if "currently unavailable" in lower and 'id="productTitle"' in lower:
                    return "active", code

                # 5. Generic "currently unavailable" without product page = removed
                if "currently unavailable" in lower:
                    return "removed", code

                # 6. Page not found patterns (actual removal)
                if "looking for something?" in lower and "try searching" in lower:
                    return "removed", code

                # 7. If 200 but no clear signal, retry once then assume active
                if attempt < MAX_RETRIES:
                    if log_fn:
                        log_fn(f"  Ambiguous response (attempt {attempt}), retrying...", "warning")
                    time.sleep(random.uniform(5, 10))
                    continue
                return "active", code

            elif code == 404:
                return "removed", code

            elif code in (301, 302, 303, 307, 308):
                return "active", code

            elif code == 503:
                if log_fn:
                    log_fn(f"  Amazon throttling (503), waiting... (attempt {attempt})", "warning")
                if attempt < MAX_RETRIES:
                    _session = _make_session()
                    time.sleep(random.uniform(10, 20))
                    continue
                return "error", code

            elif code == 429:
                if log_fn:
                    log_fn(f"  Rate limited (429), long wait... (attempt {attempt})", "warning")
                if attempt < MAX_RETRIES:
                    _session = _make_session()
                    time.sleep(random.uniform(15, 30))
                    continue
                return "error", code

            else:
                return "error", code

        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(random.uniform(3, 6))
                continue
            return "error", 0

    return "error", 0


def parse_products_js(filepath: str) -> list[dict]:
    """Parse a products-showcase.js file and extract the product array."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the JSON array from the JS file
    # Pattern: const products = [ ... ];
    match = re.search(r"(?:const|let|var)\s+\w+\s*=\s*(\[[\s\S]*\])\s*;?", content)
    if not match:
        # Try to find just a JSON array
        match = re.search(r"(\[[\s\S]*\])", content)

    if not match:
        raise ValueError("Could not find a product array in the file.")

    json_str = match.group(1)

    # Fix JS-specific syntax for JSON parsing:
    # Remove trailing commas before ] or }
    json_str = re.sub(r",\s*([\]}])", r"\1", json_str)
    # Handle unquoted keys (JS allows them, JSON doesn't)
    # This is a basic fix — covers most cases
    json_str = re.sub(r'(?<=\{|,)\s*(\w+)\s*:', r' "\1":', json_str)
    # Handle single quotes → double quotes (if any)
    # Only do this carefully to avoid breaking strings with apostrophes
    # We'll rely on the JS file using double quotes (which it does)

    # Fix boolean values (JS true/false without quotes)
    json_str = re.sub(r':\s*true\b', ': true', json_str)
    json_str = re.sub(r':\s*false\b', ': false', json_str)

    products = json.loads(json_str)
    return products


def save_products_js(filepath: str, products: list[dict]) -> None:
    """Save products back to the JS file in the original format."""
    with open(filepath, "r", encoding="utf-8") as f:
        original = f.read()

    # Find the variable name
    var_match = re.match(r"(.*?(?:const|let|var)\s+(\w+)\s*=\s*)", original, re.DOTALL)
    if var_match:
        prefix = var_match.group(1)
        # Check if file ends with semicolon
        has_semicolon = original.rstrip().endswith(";")
    else:
        prefix = "const products = "
        has_semicolon = True

    # Format the JSON nicely
    json_str = json.dumps(products, indent=2, ensure_ascii=False)

    suffix = ";\n" if has_semicolon else "\n"
    new_content = prefix + json_str + suffix

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)


# ═══════════════════════════════════════════════════════════════════════════
# GUI APPLICATION
# ═══════════════════════════════════════════════════════════════════════════
class NexoraLinkCheckerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.current_lang = "en"
        self.running = False
        self.file_path = ""
        self.raw_products: list[dict] = []
        self.check_results: list[ProductCheck] = []
        self.removed_indices: list[int] = []  # indices into raw_products

        # Counters
        self.total_count = 0
        self.active_count = 0
        self.removed_count = 0
        self.error_count = 0

        self._build_ui()
        self._apply_lang()

    def _build_ui(self) -> None:
        root = self.root
        root.title("NEXORA Link Checker")
        root.configure(bg=BG_DARK)
        root.geometry("880x780")
        root.minsize(750, 650)

        try:
            root.iconbitmap(default="")
        except Exception:
            pass

        # ── Header ───────────────────────────────────────────────────────
        header = tk.Frame(root, bg=BG_CARD, pady=12)
        header.pack(fill="x")

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
            text_frame, text="NEXORA Link Checker",
            font=("Helvetica", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD,
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = tk.Label(
            text_frame, text="Amazon Product Link Validator",
            font=("Helvetica", 9), fg=TEXT_SECONDARY, bg=BG_CARD,
        )
        self.subtitle_label.pack(anchor="w")

        self.lang_btn = tk.Button(
            header, text="عربي", font=("Helvetica", 10, "bold"),
            fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=ACCENT,
            activeforeground="white", bd=0, padx=12, pady=4,
            cursor="hand2", command=self._toggle_lang,
        )
        self.lang_btn.pack(side="right", padx=20)

        # ── Separator ────────────────────────────────────────────────────
        tk.Frame(root, bg=ACCENT, height=3).pack(fill="x")

        # ── Main content ─────────────────────────────────────────────────
        main = tk.Frame(root, bg=BG_DARK, padx=20, pady=12)
        main.pack(fill="both", expand=True)

        # ── File picker ──────────────────────────────────────────────────
        file_frame = tk.Frame(main, bg=BG_CARD, padx=12, pady=8,
                              highlightbackground=BORDER_COLOR, highlightthickness=1)
        file_frame.pack(fill="x", pady=(0, 8))

        self.file_label = tk.Label(
            file_frame, text="Products JS File:",
            font=("Helvetica", 9, "bold"), fg=TEXT_SECONDARY, bg=BG_CARD, anchor="w",
        )
        self.file_label.pack(fill="x")

        file_input_frame = tk.Frame(file_frame, bg=BG_CARD)
        file_input_frame.pack(fill="x", pady=(4, 0))

        self.file_entry = tk.Entry(
            file_input_frame, font=("Consolas", 10),
            bg=BG_DARK, fg=TEXT_PRIMARY, insertbackground=ACCENT,
            selectbackground=ACCENT, bd=0, highlightthickness=1,
            highlightbackground=BORDER_COLOR, highlightcolor=ACCENT,
        )
        self.file_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))

        self.browse_btn = tk.Button(
            file_input_frame, text="Select Products File",
            font=("Helvetica", 9, "bold"),
            fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=ACCENT,
            activeforeground="white", bd=0, padx=12, pady=4,
            cursor="hand2", command=self._browse_file,
        )
        self.browse_btn.pack(side="right")

        # ── Safety note ──────────────────────────────────────────────────
        self.safe_note_label = tk.Label(
            main, text="", font=("Helvetica", 8, "italic"),
            fg=GREEN, bg=BG_DARK, anchor="w",
        )
        self.safe_note_label.pack(fill="x", pady=(0, 6))

        # ── Digital counters ─────────────────────────────────────────────
        counters_frame = tk.Frame(main, bg=BG_DARK)
        counters_frame.pack(fill="x", pady=(0, 8))

        self.counter_widgets: dict[str, dict] = {}
        counter_configs = [
            ("total", BLUE, "0"),
            ("active", GREEN, "0"),
            ("removed", RED, "0"),
            ("remaining", YELLOW, "0"),
            ("errors", ORANGE, "0"),
        ]

        for i, (key, color, default) in enumerate(counter_configs):
            card = tk.Frame(counters_frame, bg=BG_CARD, padx=12, pady=8,
                            highlightbackground=BORDER_COLOR, highlightthickness=1)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            counters_frame.columnconfigure(i, weight=1)

            val_label = tk.Label(
                card, text=default, font=("Consolas", 24, "bold"),
                fg=color, bg=BG_CARD,
            )
            val_label.pack()

            name_label = tk.Label(
                card, text=key.upper(), font=("Helvetica", 8, "bold"),
                fg=TEXT_SECONDARY, bg=BG_CARD,
            )
            name_label.pack()

            self.counter_widgets[key] = {"val": val_label, "name": name_label}

        # ── Progress bar ─────────────────────────────────────────────────
        progress_frame = tk.Frame(main, bg=BG_DARK)
        progress_frame.pack(fill="x", pady=(0, 6))

        self.progress_pct_label = tk.Label(
            progress_frame, text="0%", font=("Consolas", 11, "bold"),
            fg=ACCENT, bg=BG_DARK, width=5,
        )
        self.progress_pct_label.pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Checker.Horizontal.TProgressbar",
            troughcolor=PROGRESS_BG, background=ACCENT,
            bordercolor=BORDER_COLOR, lightcolor=ACCENT, darkcolor=ACCENT,
        )

        self.progress_bar = ttk.Progressbar(
            progress_frame, style="Checker.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100,
        )
        self.progress_bar.pack(fill="x", expand=True, side="left", padx=(0, 8))

        # ── Status line ──────────────────────────────────────────────────
        self.status_label = tk.Label(
            main, text="", font=("Helvetica", 10),
            fg=TEXT_SECONDARY, bg=BG_DARK, anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 6))

        # ── Notebook (tabs): Log + Removed Products ──────────────────────
        style.configure("Dark.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=BG_CARD2, foreground=TEXT_SECONDARY,
                        padding=[12, 4], font=("Helvetica", 9, "bold"))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", ACCENT)])

        self.notebook = ttk.Notebook(main, style="Dark.TNotebook")
        self.notebook.pack(fill="both", expand=True, pady=(0, 8))

        # Tab 1: Live Log
        log_tab = tk.Frame(self.notebook, bg=BG_CARD2)
        self.notebook.add(log_tab, text="  Live Log  ")

        self.log_text = tk.Text(
            log_tab, bg=BG_DARK, fg=TEXT_PRIMARY,
            font=("Consolas", 9), wrap="word", bd=0,
            insertbackground=TEXT_PRIMARY, selectbackground=ACCENT,
            padx=10, pady=6, height=8,
        )
        self.log_text.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.tag_configure("info", foreground=TEXT_PRIMARY)
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=YELLOW)
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("accent", foreground=ACCENT)
        self.log_text.tag_configure("phase", foreground=BLUE, font=("Consolas", 10, "bold"))

        # Tab 2: Removed Products
        removed_tab = tk.Frame(self.notebook, bg=BG_CARD2)
        self.notebook.add(removed_tab, text="  Removed Products  ")

        self.removed_frame_outer = tk.Frame(removed_tab, bg=BG_DARK)
        self.removed_frame_outer.pack(fill="both", expand=True)

        # Scrollable frame for removed products
        self.removed_canvas = tk.Canvas(
            self.removed_frame_outer, bg=BG_DARK, bd=0,
            highlightthickness=0,
        )
        removed_scroll = ttk.Scrollbar(
            self.removed_frame_outer, orient="vertical",
            command=self.removed_canvas.yview,
        )
        self.removed_inner = tk.Frame(self.removed_canvas, bg=BG_DARK)

        self.removed_inner.bind(
            "<Configure>",
            lambda e: self.removed_canvas.configure(
                scrollregion=self.removed_canvas.bbox("all")
            ),
        )

        self.removed_canvas.create_window((0, 0), window=self.removed_inner, anchor="nw")
        self.removed_canvas.configure(yscrollcommand=removed_scroll.set)

        self.removed_canvas.pack(side="left", fill="both", expand=True)
        removed_scroll.pack(side="right", fill="y")

        # ── Bottom buttons ───────────────────────────────────────────────
        btn_frame = tk.Frame(main, bg=BG_DARK)
        btn_frame.pack(fill="x")

        self.start_btn = tk.Button(
            btn_frame, text="Start Check", font=("Helvetica", 13, "bold"),
            fg="white", bg=ACCENT, activebackground=ACCENT_HOVER,
            activeforeground="white", bd=0, padx=30, pady=10,
            cursor="hand2", command=self._on_start,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.remove_all_btn = tk.Button(
            btn_frame, text="Remove All Unavailable",
            font=("Helvetica", 13, "bold"),
            fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=RED,
            activeforeground="white", bd=0, padx=30, pady=10,
            cursor="hand2", state="disabled", command=self._remove_all,
        )
        self.remove_all_btn.pack(side="right", expand=True, fill="x", padx=(5, 0))

    # ── Language ─────────────────────────────────────────────────────────
    def _toggle_lang(self) -> None:
        self.current_lang = "ar" if self.current_lang == "en" else "en"
        self._apply_lang()

    def _t(self, key: str) -> str:
        return LANG[self.current_lang].get(key, key)

    def _apply_lang(self) -> None:
        t = LANG[self.current_lang]
        self.title_label.config(text=t["title"])
        self.subtitle_label.config(text=t["subtitle"])
        self.lang_btn.config(text=t["lang_btn"])
        self.file_label.config(text=t["file_label"])
        self.browse_btn.config(text=t["select_file"])
        self.safe_note_label.config(text=t["safe_note"])

        if not self.running:
            self.start_btn.config(text=t["start_btn"])
            self.status_label.config(text=t["status_idle"])

        self.remove_all_btn.config(text=t["remove_all_btn"])

        counter_map = {
            "total": t["total"],
            "active": t["active"],
            "removed": t["removed"],
            "remaining": t["remaining"],
            "errors": t["errors"],
        }
        for key, label in counter_map.items():
            self.counter_widgets[key]["name"].config(text=label)

        if not self.file_path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, t["file_hint"])

    # ── Helpers ──────────────────────────────────────────────────────────
    def _log(self, msg: str, tag: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_text.see("end")

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

    # ── File picker ──────────────────────────────────────────────────────
    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title=self._t("select_file"),
            filetypes=[
                ("JavaScript files", "*.js"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_path = path
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, path)

    # ── Start ────────────────────────────────────────────────────────────
    def _on_start(self) -> None:
        if self.running:
            return

        # Get file path from entry (user might have typed it)
        path = self.file_entry.get().strip()
        if not path or path == self._t("file_hint"):
            messagebox.showwarning("NEXORA", self._t("file_hint"))
            return

        if not os.path.isfile(path):
            messagebox.showerror("NEXORA", f"File not found: {path}")
            return

        self.file_path = path
        self.running = True
        self.start_btn.config(text=self._t("stop_btn"), state="disabled", bg=TEXT_DIM)
        self.remove_all_btn.config(state="disabled")
        self.browse_btn.config(state="disabled")
        self.file_entry.config(state="disabled")
        self.log_text.delete("1.0", "end")

        # Clear removed products list
        for widget in self.removed_inner.winfo_children():
            widget.destroy()

        # Reset
        self.check_results.clear()
        self.removed_indices.clear()
        self.total_count = 0
        self.active_count = 0
        self.removed_count = 0
        self.error_count = 0
        for key in ["total", "active", "removed", "remaining", "errors"]:
            self._update_counter(key, 0)
        self._update_progress(0, 1)

        thread = threading.Thread(target=self._run_check, daemon=True)
        thread.start()

    # ── Check logic ──────────────────────────────────────────────────────
    def _run_check(self) -> None:
        try:
            self._check_workflow()
        except Exception as exc:
            self.root.after(0, lambda: self._on_error(str(exc)))

    def _check_workflow(self) -> None:
        self.root.after(0, lambda: self._set_status(self._t("status_loading")))
        self.root.after(0, lambda: self._log(self._t("status_loading"), "accent"))

        # Parse file
        try:
            self.raw_products = parse_products_js(self.file_path)
        except Exception as exc:
            self.root.after(0, lambda: self._on_error(f"Failed to parse file: {exc}"))
            return

        total = len(self.raw_products)
        self.total_count = total
        self.root.after(0, lambda: self._update_counter("total", total))
        self.root.after(0, lambda: self._update_counter("remaining", total))
        self.root.after(0, lambda: self._log(f"Loaded {total} products from file", "success"))
        self.root.after(0, lambda: self._log(self._t("safe_note"), "success"))
        self.root.after(0, lambda: self._log("=" * 50, "accent"))

        # Check each product
        for idx, product in enumerate(self.raw_products):
            title = product.get("title", "Unknown")[:50]
            link = product.get("link", "")

            if not link:
                self.error_count += 1
                ec = self.error_count
                self.root.after(0, lambda v=ec: self._update_counter("errors", v))
                self.root.after(0, lambda t=title: self._log(f"No link: {t}", "warning"))
                self.check_results.append(ProductCheck(
                    title=title, link_original=link, status="error",
                ))
                continue

            # Strip affiliate tag
            clean_link = strip_affiliate_tag(link)

            status_msg = self._t("status_checking").format(
                i=idx + 1, n=total, name=title,
            )
            self.root.after(0, lambda m=status_msg: self._set_status(m))

            # Check the link (with log callback for retry info)
            def _thread_log(msg, tag):
                self.root.after(0, lambda m=msg, t=tag: self._log(m, t))
            status, http_code = check_amazon_link(clean_link, log_fn=_thread_log)

            result = ProductCheck(
                title=product.get("title", ""),
                link_original=link,
                link_clean=clean_link,
                category=product.get("category", ""),
                slug=product.get("slug", ""),
                status=status,
                http_code=http_code,
            )
            self.check_results.append(result)

            if status == "active":
                self.active_count += 1
                ac = self.active_count
                self.root.after(0, lambda v=ac: self._update_counter("active", v))
                self.root.after(0, lambda t=title: self._log(
                    f"ACTIVE: {t}", "success"
                ))
            elif status == "removed":
                self.removed_count += 1
                rc = self.removed_count
                self.removed_indices.append(idx)
                self.root.after(0, lambda v=rc: self._update_counter("removed", v))
                self.root.after(0, lambda t=title, c=http_code: self._log(
                    f"REMOVED (HTTP {c}): {t}", "error"
                ))
                # Add to removed products UI
                self.root.after(0, lambda i=idx, t=product.get("title", ""),
                                cat=product.get("category", ""),
                                lnk=product.get("link", ""): self._add_removed_card(i, t, cat, lnk))
            else:
                self.error_count += 1
                ec = self.error_count
                self.root.after(0, lambda v=ec: self._update_counter("errors", v))
                self.root.after(0, lambda t=title, c=http_code: self._log(
                    f"ERROR (HTTP {c}): {t}", "warning"
                ))

            remaining = total - (idx + 1)
            self.root.after(0, lambda v=remaining: self._update_counter("remaining", v))
            self.root.after(0, lambda c=idx + 1, t=total: self._update_progress(c, t))

            _human_delay()

        # Done
        self.root.after(0, lambda: self._on_done())

    def _add_removed_card(self, product_idx: int, title: str, category: str,
                          link: str = "") -> None:
        """Add a card for a removed product with Amazon link and Remove button."""
        card = tk.Frame(
            self.removed_inner, bg=BG_CARD, padx=10, pady=8,
            highlightbackground=RED, highlightthickness=1,
        )
        card.pack(fill="x", padx=5, pady=3)

        # Product info
        info_frame = tk.Frame(card, bg=BG_CARD)
        info_frame.pack(side="left", fill="x", expand=True)

        title_short = title[:70] + ("..." if len(title) > 70 else "")
        tk.Label(
            info_frame, text=title_short,
            font=("Helvetica", 9, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD,
            anchor="w", wraplength=500,
        ).pack(anchor="w")

        tk.Label(
            info_frame, text=f"Category: {category}",
            font=("Helvetica", 8), fg=TEXT_SECONDARY, bg=BG_CARD, anchor="w",
        ).pack(anchor="w")

        # Show the clean Amazon link (without affiliate tag) for manual verification
        if link:
            clean = strip_affiliate_tag(link)
            link_label = tk.Label(
                info_frame, text=clean,
                font=("Consolas", 8, "underline"), fg=BLUE, bg=BG_CARD,
                anchor="w", cursor="hand2",
            )
            link_label.pack(anchor="w", pady=(2, 0))
            link_label.bind("<Button-1>", lambda e, url=clean: self._open_url(url))

        # Buttons frame
        btn_frame = tk.Frame(card, bg=BG_CARD)
        btn_frame.pack(side="right", padx=(10, 0))

        # Open link button
        if link:
            open_btn = tk.Button(
                btn_frame, text="Open Link",
                font=("Helvetica", 8, "bold"),
                fg=TEXT_PRIMARY, bg=BG_CARD2, activebackground=BLUE,
                activeforeground="white", bd=0, padx=8, pady=3,
                cursor="hand2",
                command=lambda url=strip_affiliate_tag(link): self._open_url(url),
            )
            open_btn.pack(pady=(0, 4))

        # Remove button
        remove_btn = tk.Button(
            btn_frame, text=self._t("remove_btn"),
            font=("Helvetica", 9, "bold"),
            fg="white", bg=RED, activebackground="#da3633",
            activeforeground="white", bd=0, padx=10, pady=4,
            cursor="hand2",
            command=lambda idx=product_idx, c=card: self._remove_single(idx, c),
        )
        remove_btn.pack()

    def _open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        import webbrowser
        webbrowser.open(url)

    def _remove_single(self, product_idx: int, card_widget: tk.Frame) -> None:
        """Remove a single product from the file."""
        if not self.file_path or not os.path.isfile(self.file_path):
            return

        try:
            title = self.raw_products[product_idx].get("title", "")[:50]
            del self.raw_products[product_idx]
            save_products_js(self.file_path, self.raw_products)

            # Remove the card from UI
            card_widget.destroy()

            # Update removed indices (shift down)
            self.removed_indices = [i if i < product_idx else i - 1
                                    for i in self.removed_indices if i != product_idx]

            self._log(f"Removed from file: {title}", "accent")
            self.total_count -= 1
            self.removed_count -= 1
            self._update_counter("total", self.total_count)
            self._update_counter("removed", self.removed_count)

        except Exception as exc:
            self._log(f"Error removing product: {exc}", "error")

    def _remove_all(self) -> None:
        """Remove all unavailable products from the file."""
        if not self.file_path or not os.path.isfile(self.file_path):
            return

        if not self.removed_indices:
            return

        # Sort in reverse order so deleting doesn't shift indices
        count = 0
        for idx in sorted(self.removed_indices, reverse=True):
            if idx < len(self.raw_products):
                del self.raw_products[idx]
                count += 1

        save_products_js(self.file_path, self.raw_products)

        # Clear removed UI
        for widget in self.removed_inner.winfo_children():
            widget.destroy()

        self.removed_indices.clear()
        self.total_count -= count
        self.removed_count = 0
        self._update_counter("total", self.total_count)
        self._update_counter("removed", 0)

        msg = self._t("removed_count").format(n=count)
        self._log(msg, "accent")
        self._set_status(msg)
        self.remove_all_btn.config(state="disabled")

    def _on_done(self) -> None:
        self.running = False
        self._update_progress(100, 100)
        self._update_counter("remaining", 0)

        done_msg = self._t("status_done").format(
            active=self.active_count, removed=self.removed_count,
        )
        self._set_status(done_msg)
        self.start_btn.config(text=self._t("start_btn"), state="normal", bg=ACCENT)
        self.browse_btn.config(state="normal")
        self.file_entry.config(state="normal")

        if self.removed_count > 0:
            self.remove_all_btn.config(state="normal", bg=RED)
            self.notebook.select(1)  # Switch to removed tab
        else:
            self._log(self._t("no_removed"), "success")

        self._log("=" * 50, "accent")
        self._log(done_msg, "success")

    def _on_error(self, err: str) -> None:
        self.running = False
        self._set_status(self._t("status_error").format(err=err))
        self.start_btn.config(text=self._t("start_btn"), state="normal", bg=ACCENT)
        self.browse_btn.config(state="normal")
        self.file_entry.config(state="normal")
        self._log(f"ERROR: {err}", "error")

    def run(self) -> None:
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = NexoraLinkCheckerApp()
    app.run()
