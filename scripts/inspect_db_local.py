import sqlite3
import sys
p = sys.argv[1] if len(sys.argv) > 1 else 'tmp_datadev_from_container.db'
conn = sqlite3.connect(p)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='scraped_items'")
print('has_table', cur.fetchone()[0])
cur.execute("SELECT count(*) FROM scraped_items WHERE lower(product_name) LIKE '%arc%'")
print('product_name like %arc%:', cur.fetchone()[0])
cur.execute("SELECT count(*) FROM scraped_items WHERE lower(line)='arc'")
print('line=arc:', cur.fetchone()[0])
cur.execute("SELECT DISTINCT model FROM scraped_items WHERE (lower(line)='arc' OR lower(product_key) LIKE '%arc%' OR lower(product_name) LIKE '%arc%') AND model IS NOT NULL")
rows = [r[0] for r in cur.fetchall()]
print('models:', rows)
conn.close()
