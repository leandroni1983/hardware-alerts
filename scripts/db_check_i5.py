import sqlite3
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import storage.scraper_db as s

print('DB_PATH=', s.DB_PATH)
conn = sqlite3.connect(s.DB_PATH)
cur = conn.cursor()
cur.execute("select product_key, product_name, price, shop_name from scraped_items where lower(product_name) like ? limit 20", ("%i5%",))
rows = cur.fetchall()
print('rows count=', len(rows))
for r in rows[:20]:
    print(r)
conn.close()
