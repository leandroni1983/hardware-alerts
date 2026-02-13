#!/usr/bin/env python3
"""Fetch product URL from DB for given shop_id and product_key, then GET the page and try to extract a visible price."""
from __future__ import annotations
import re
import sys
import sqlite3
try:
    import storage.scraper_db as dbm
except Exception:
    print('Cannot import storage.scraper_db')
    raise

import requests

if len(sys.argv) < 3:
    print('Usage: python scripts/fetch_site_price.py <shop_id> <product_key>')
    raise SystemExit(1)

shop_id = sys.argv[1]
product_key = sys.argv[2]

conn = sqlite3.connect(dbm.DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute('SELECT product_url FROM scraped_items WHERE shop_id = ? AND product_key = ? ORDER BY scraped_at DESC LIMIT 1', (shop_id, product_key))
row = cur.fetchone()
if not row:
    print('No URL found for', shop_id, product_key)
    raise SystemExit(1)
url = row['product_url']
print('Found URL:', url)

try:
    r = requests.get(url, timeout=15)
    print('HTTP', r.status_code)
    text = r.text
    # naive price extraction: find largest number-looking token
    cand = re.findall(r"(\d{1,3}(?:[\.,\s]\d{3})*(?:[\.,]\d{2})?)", text)
    if not cand:
        print('No price-like tokens found')
    else:
        # normalize tokens to numbers (take last occurrence likely price)
        def norm(t):
            s = t.replace('\u00A0',' ').replace(' ','').replace('.','').replace(',','.')
            try:
                return float(s)
            except Exception:
                return None
        nums = [(t, norm(t)) for t in cand]
        nums = [x for x in nums if x[1] is not None]
        if not nums:
            print('No numeric prices parsed')
        else:
            # pick largest numeric (often price) and also show last few
            nums_sorted = sorted(nums, key=lambda x: x[1], reverse=True)
            print('Top candidates:')
            for t, v in nums_sorted[:10]:
                print(t, '->', v)
except Exception as e:
    print('HTTP error:', e)

conn.close()
