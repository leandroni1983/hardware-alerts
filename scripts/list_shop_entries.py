#!/usr/bin/env python3
"""List scraped_items rows for a shop and product_key."""
from __future__ import annotations
import sys
import sqlite3
try:
    import storage.scraper_db as dbm
except Exception:
    print('Cannot import storage.scraper_db')
    raise

if len(sys.argv) < 3:
    print('Usage: python scripts/list_shop_entries.py <shop_id> <product_key>')
    raise SystemExit(1)

shop_id = sys.argv[1]
product_key = sys.argv[2]

conn = sqlite3.connect(dbm.DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute('SELECT id, price, product_url, scraped_at FROM scraped_items WHERE shop_id = ? AND product_key = ? ORDER BY scraped_at DESC', (shop_id, product_key))
rows = cur.fetchall()
for r in rows:
    print(r['id'], r['price'], r['scraped_at'], r['product_url'])
conn.close()
