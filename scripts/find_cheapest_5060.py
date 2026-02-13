import sqlite3
import json
import os
from pathlib import Path

# Import DB path from storage.scraper_db if available
DB_PATH = None
try:
    from storage import scraper_db
    DB_PATH = scraper_db.DB_PATH
except Exception:
    # fallback to default used in scraper_db
    if os.name == 'nt':
        DB_PATH = r"D:/Leandro/basesdedatos/data.db"
    else:
        DB_PATH = "/opt/scraper/data.db"

if not Path(DB_PATH).exists():
    print(json.dumps({"error": "db_not_found", "db_path": DB_PATH}))
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Case-insensitive search for '5060' in product_name
cur.execute(
    """
    SELECT shop_id, shop_name, product_name, product_url, price, scraped_at
    FROM scraped_items
    WHERE lower(product_name) LIKE ?
      AND price IS NOT NULL
      AND stock = 1
    ORDER BY price ASC
    LIMIT 1
    """,
    ("%5060%",),
)
row = cur.fetchone()
conn.close()

if not row:
    print(json.dumps({"found": False}))
else:
    out = {"found": True, "shop_id": row['shop_id'], "shop_name": row['shop_name'], "product_name": row['product_name'], "product_url": row['product_url'], "price": int(row['price']), "scraped_at": row['scraped_at']}
    print(json.dumps(out, ensure_ascii=False))
