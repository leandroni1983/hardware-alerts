from storage.scraper_db import _get_conn, DB_PATH

def main():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='scraped_items'")
    has = cur.fetchone()[0]
    print('has_table', has)
    if not has:
        return
    cur.execute("SELECT id, product_name, product_key FROM scraped_items WHERE lower(product_name) LIKE '%arc%' OR lower(product_key) LIKE '%arc%' LIMIT 50")
    rows = cur.fetchall()
    print('DB_PATH=', DB_PATH)
    print('rows:', len(rows))
    for r in rows:
        print(r[0], r[1], '->', r[2])
    conn.close()

if __name__ == '__main__':
    main()
