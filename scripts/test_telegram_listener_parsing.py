#!/usr/bin/env python3
"""Quick tests for `scripts/telegram_listener.py` functions.

Creates a small SQLite DB under `./data/test_data.db`, inserts sample rows
and exercises `find_cheapest_by_code` and `find_cheapest_all_by_code`.
Run: `python scripts/test_telegram_listener_parsing.py`
"""
import sqlite3
import os
from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parent
MODULE_PATH = ROOT / 'telegram_listener.py'

spec = importlib.util.spec_from_file_location('telegram_listener', str(MODULE_PATH))
tl = importlib.util.module_from_spec(spec)
sys.modules['telegram_listener'] = tl
spec.loader.exec_module(tl)


DB_DIR = Path(__file__).resolve().parent.parent / 'data'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'test_data.db'

if DB_PATH.exists():
    DB_PATH.unlink()

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()

cur.execute('''
CREATE TABLE scraped_items (
    id INTEGER PRIMARY KEY,
    shop_id TEXT,
    shop_name TEXT,
    product_name TEXT,
    product_url TEXT,
    price INTEGER,
    scraped_at TEXT,
    product_key TEXT,
    stock INTEGER
)
''')

# Insert sample rows
rows = [
    ('s1', 'ShopA', 'Intel i5 12400 6-core', 'http://a/1', 120000, '2026-02-01', 'i5 12400', 1),
    ('s2', 'ShopB', 'Intel i5 12400 boxed', 'http://b/1', 110000, '2026-02-02', 'i5 12400', 1),
    ('s3', 'ShopC', 'Intel i5 generic', 'http://c/1', 90000, '2026-02-03', 'i5', 1),
    ('s4', 'ShopD', 'Strange 1512400 listing', 'http://d/1', 50000, '2026-02-04', '1512400', 1),
]
cur.executemany(
    'INSERT INTO scraped_items (shop_id, shop_name, product_name, product_url, price, scraped_at, product_key, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    rows,
)
conn.commit()
conn.close()

print('DB created at', DB_PATH)

# Tests
print('\n-- find_cheapest_by_code("i5 12400") --')
res = tl.find_cheapest_by_code(str(DB_PATH), 'i5 12400')
print(res)

print('\n-- find_cheapest_by_code("i5") --')
res = tl.find_cheapest_by_code(str(DB_PATH), 'i5')
print(res)

print('\n-- find_cheapest_by_code("15 12400") -- (should not match i5 12400)')
res = tl.find_cheapest_by_code(str(DB_PATH), '15 12400')
print(res)

print('\n-- find_cheapest_all_by_code("i5", limit=10) --')
res_list = tl.find_cheapest_all_by_code(str(DB_PATH), 'i5', limit=10)
for r in res_list:
    print(r)

print('\nTests completed.')
