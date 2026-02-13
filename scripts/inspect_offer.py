#!/usr/bin/env python3
"""Inspecciona un producto dado su URL y muestra detalles para validar la oferta."""
from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timedelta
import sys

DB_PATH = None
try:
    import storage.scraper_db as dbm
    DB_PATH = dbm.DB_PATH
except Exception:
    print('Cannot import storage.scraper_db'); raise

URL = sys.argv[1] if len(sys.argv) > 1 else None
if not URL:
    print('Usage: python scripts/inspect_offer.py <product_url>')
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute('SELECT * FROM scraped_items WHERE product_url = ?', (URL,))
row = cur.fetchone()
if not row:
    print('No scraped_items row found for URL')
    conn.close()
    raise SystemExit(1)

print('\n== Scraped item ==')
for k in row.keys():
    print(f'{k}: {row[k]}')

pk = row['product_key']
print(f'\nproduct_key: {pk}')

print('\n== Current offers (per shop, min price) ==')
cur.execute(
    '''
    SELECT shop_id, shop_name, MIN(price) AS min_price
    FROM scraped_items
    WHERE product_key = ? AND price IS NOT NULL AND stock = 1
    GROUP BY shop_id, shop_name
    ORDER BY min_price ASC
    ''',
    (pk,)
)
offers = cur.fetchall()
for o in offers:
    print(f"{o['shop_name']} ({o['shop_id']}): {int(o['min_price'])}")

since = datetime.utcnow() - timedelta(days=30)
print(f'\n== Price history summary last 30 days for product_key={pk} ==')
cur.execute(
    '''
    SELECT shop_id, COUNT(*) AS samples, AVG(price) AS avg_price, MIN(price) AS min_price, MAX(price) AS max_price
    FROM scraped_price_history_key
    WHERE product_key = ? AND price IS NOT NULL AND scraped_at >= ?
    GROUP BY shop_id
    ORDER BY samples DESC
    ''',
    (pk, since.isoformat()),
)
hist = cur.fetchall()
if not hist:
    print('No history in last 30 days')
else:
    for h in hist:
        print(f"{h['shop_id']}: samples={h['samples']} avg={int(h['avg_price']) if h['avg_price'] else None} min={h['min_price']} max={h['max_price']}")

print('\n== Recent price history (last 20 entries) ==')
cur.execute(
    '''SELECT shop_id, price, scraped_at FROM scraped_price_history_key WHERE product_key = ? ORDER BY scraped_at DESC LIMIT 20''',
    (pk,)
)
rows = cur.fetchall()
for r in rows:
    print(f"{r['scraped_at']} {r['shop_id']} {r['price']}")

conn.close()
