from storage import scraper_db as dbm
import sqlite3, re

def run():
    pk = 'intel_1700'
    conn = sqlite3.connect(dbm.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT product_name FROM scraped_items WHERE product_key = ? ORDER BY scraped_at DESC LIMIT 1", (pk,))
    row = cur.fetchone()
    sample_title = row['product_name'] if row else ''
    print('sample_title:', sample_title)
    raw_tokens = re.findall(r"\w+", sample_title)
    family_tokens = {"i3","i5","i7","i9","ryzen","rx","rtx","gtx"}
    def is_model_token(t: str) -> bool:
        has_digit = any(c.isdigit() for c in t)
        has_alpha = any(c.isalpha() for c in t)
        return len(t) > 2 and ( (has_digit and has_alpha) or (t.lower() in family_tokens) )
    tokens = [t for t in raw_tokens if is_model_token(t)]
    print('tokens:', tokens)
    placeholders = ','.join('?' for _ in [pk])
    if tokens:
        like_clauses = ' OR '.join('product_name LIKE ?' for _ in tokens)
        params = tuple([pk]) + tuple('%' + t + '%' for t in tokens)
        sql = f"SELECT shop_id, shop_name, product_name, price FROM scraped_items WHERE product_key IN ({placeholders}) AND price IS NOT NULL AND stock = 1 AND ({like_clauses}) ORDER BY price ASC"
        print('SQL:', sql)
        print('params:', params)
        cur.execute(sql, params)
    else:
        sql = f"SELECT shop_id, shop_name, product_name, price FROM scraped_items WHERE product_key IN ({placeholders}) AND price IS NOT NULL AND stock = 1 ORDER BY price ASC"
        print('SQL:', sql)
        cur.execute(sql, (pk,))
    rows = cur.fetchall()
    print('matching rows:')
    for r in rows:
        print(dict(r))

    print('\nall rows for key:')
    cur.execute('SELECT shop_id, shop_name, product_name, price FROM scraped_items WHERE product_key = ? ORDER BY price ASC', (pk,))
    for r in cur.fetchall():
        print(dict(r))

    conn.close()

if __name__ == '__main__':
    run()
