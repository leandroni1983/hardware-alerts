#!/usr/bin/env python3
"""Mark existing scraped_items rows that look like peripherals as processed.

This script is non-destructive: it sets `processed=1` and `summary='excluded_peripheral'`
so you can review later. If you prefer deletion, modify the script accordingly.

Usage:
  python scripts/cleanup_peripherals.py [--dry-run]
"""
from __future__ import annotations
import argparse
import sqlite3
from datetime import datetime

# Ensure project root is on sys.path so `import storage` works when running from other CWDs
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import storage.scraper_db as dbm

EXCLUDE_KEYWORDS = [
    "auricular",
    "auriculares",
    "audifono",
    "audífono",
    "audifonos",
    "microfono",
    "micrófono",
    "micro",
    "mic",
    "headset",
    "headphones",
    "headphone",
    "mouse",
    "mause",
    "teclado",
    "keyboard",
    "monitor",
    "camara",
    "cámara",
    "webcam",
    "parlante",
    "speaker",
    "impresora",
    "cargador",
    "cable",
    "sd",
    "microsd",
    "sdcard",
]

WHITELIST = [
    "ryzen",
    "intel",
    "rtx",
    "gtx",
    "ddr",
    "nvme",
    "ssd",
    "m.2",
    "m2",
]


def looks_peripheral(title: str | None) -> bool:
    if not title:
        return False
    tl = title.lower()
    # whitelist override
    for w in WHITELIST:
        if w in tl:
            return False
    for ex in EXCLUDE_KEYWORDS:
        if ex in tl:
            return True
    return False


def main(dry_run: bool):
    conn = sqlite3.connect(dbm.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, product_name, shop_name, product_url FROM scraped_items WHERE processed = 0")
    rows = cur.fetchall()
    to_mark = []
    for r in rows:
        if looks_peripheral(r["product_name"]):
            to_mark.append(r)

    print(f"Found {len(to_mark)} candidate peripheral rows (unprocessed).")
    for r in to_mark:
        print(r["id"], r["shop_name"], r["product_name"], r["product_url"])

    if dry_run:
        print("Dry-run mode, not marking rows.")
        return

    now = datetime.utcnow().isoformat()
    for r in to_mark:
        cur.execute(
            "UPDATE scraped_items SET processed = 1, processed_at = ?, summary = ? WHERE id = ?",
            (now, "excluded_peripheral", r["id"]),
        )
    conn.commit()
    conn.close()
    print(f"Marked {len(to_mark)} rows as excluded_peripheral.")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
