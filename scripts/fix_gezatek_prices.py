#!/usr/bin/env python3
"""Fix Gezatek historical prices that were stored with extra two zeros.

Heuristic: find rows in `scraped_items` with shop_id='gezatek' and price > 1_000_000
and price % 100 == 0. For each candidate, new_price = price // 100.

This script:
 - makes a backup copy of the DB file
 - lists up to 200 candidate rows
 - applies the update (price and scraped_at -> now) and commits
 - prints a summary

Run from repo root: python scripts/fix_gezatek_prices.py
"""
from __future__ import annotations
import shutil
import sqlite3
import sys
from datetime import datetime

import storage.scraper_db as dbm

DB_PATH = dbm.DB_PATH
BACKUP = DB_PATH + ".backup_fix_gezatek_" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

THRESHOLD = 1_000_000
SCALE = 100
LIMIT = 1000

print("DB_PATH:", DB_PATH)
print("Creating backup:", BACKUP)
shutil.copy2(DB_PATH, BACKUP)
print("Backup created")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute(
    """
    SELECT id, product_name, price, product_url, scraped_at
    FROM scraped_items
    WHERE shop_id = 'gezatek'
      AND price > ?
      AND price % ? = 0
    ORDER BY scraped_at DESC
    LIMIT ?
    """,
    (THRESHOLD, SCALE, LIMIT),
)
rows = cur.fetchall()

if not rows:
    print("No candidate rows found. Nothing to do.")
    conn.close()
    sys.exit(0)

print(f"Found {len(rows)} candidate rows (showing up to {LIMIT}). Sample:")
for r in rows[:10]:
    print(f"id={r['id']} price={r['price']} name={r['product_name']}")

# Apply updates
updated = 0
for r in rows:
    old = int(r["price"]) if r["price"] is not None else None
    if old is None:
        continue
    new = old // SCALE
    now = datetime.utcnow().isoformat()
    try:
        cur.execute(
            "UPDATE scraped_items SET price = ?, scraped_at = ? WHERE id = ?",
            (new, now, r["id"]),
        )
        updated += 1
    except Exception as e:
        print("Failed to update id=", r["id"], e)

conn.commit()
conn.close()

print(f"Updated {updated} rows. Backup kept at: {BACKUP}")
print("Done.")
