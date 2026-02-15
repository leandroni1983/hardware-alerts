import sqlite3
import os
base = os.path.join(os.path.dirname(__file__), '..', 'data')
files = ['products.db', 'data.db', 'conversations.db']
for fname in files:
    f = os.path.join(base, fname)
    print('FILE:', f)
    if not os.path.exists(f):
        print('  MISSING')
        continue
    try:
        conn = sqlite3.connect(f)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        rows = [r[0] for r in cur.fetchall()]
        print('  TABLES:', rows)
        if 'scraped_items' in rows:
            cur.execute('SELECT product_name, shop_name, category, price, stock, product_url FROM scraped_items LIMIT 5')
            for r in cur.fetchall():
                print('   SAMPLE scraped_items:', r)
        if 'productos' in rows:
            cur.execute('SELECT nombre, tienda_nombre, categoria, precio, stock, link FROM productos LIMIT 5')
            for r in cur.fetchall():
                print('   SAMPLE productos:', r)
        conn.close()
    except Exception as e:
        print('  ERR', e)
