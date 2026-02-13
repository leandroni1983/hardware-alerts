#!/usr/bin/env python3
"""Use Playwright to render product page and extract common price selectors."""
from __future__ import annotations
import sys
from playwright.sync_api import sync_playwright

if len(sys.argv) < 2:
    print('Usage: python scripts/render_price.py <url>')
    raise SystemExit(1)

url = sys.argv[1]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_timeout(1000)
    selectors = [".price", ".precio", ".product-price", ".amount", ".price-current", ".price-final"]
    found = []
    for sel in selectors:
        try:
            els = page.query_selector_all(sel)
            for el in els:
                txt = el.inner_text().strip()
                if txt:
                    found.append((sel, txt))
        except Exception:
            continue

    # fallback: search for numbers
    if not found:
        body = page.content()
        import re
        tokens = re.findall(r"(\d{1,3}(?:[\.,\s]\d{3})*(?:[\.,]\d{2})?)", body)
        tokens = tokens[:20]
        found.extend([('token', t) for t in tokens])

    for sel, txt in found[:30]:
        print(sel, '->', txt)

    browser.close()
