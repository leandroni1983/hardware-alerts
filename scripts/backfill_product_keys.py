#!/usr/bin/env python3
"""Backfill `product_key` for existing rows in the SQLite DB.

Usage:
  python scripts/backfill_product_keys.py [--dry-run]

It will update rows where `product_key` IS NULL or empty, computing the
key using `normalizers.normalize_product`.
"""
import argparse
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import scraper_db
from normalizers import normalize_product


def backfill(db_path: str, dry_run: bool = False, batch: int = 200):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, product_name FROM scraped_items WHERE product_key IS NULL OR product_key = ''"
    )
    rows = cur.fetchall()
    total = len(rows)
    print(f"Found {total} rows to update")
    updated = 0
    for i in range(0, total, batch):
        batch_rows = rows[i : i + batch]
        for rid, pname in batch_rows:
            try:
                pk = normalize_product.normalize({"title": pname}).get("product_key") or ""
                if pk:
                    print(f"{rid}: -> {pk}")
                    if not dry_run:
                        cur.execute("UPDATE scraped_items SET product_key = ? WHERE id = ?", (pk, rid))
                        updated += 1
            except Exception as e:
                print("Error normalizing", rid, e)
        if not dry_run:
            conn.commit()
    conn.close()
    print(f"Updated: {updated} rows (dry_run={dry_run})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    DB = scraper_db.DB_PATH
    print("Using DB:", DB)
    backfill(DB, dry_run=args.dry_run)
