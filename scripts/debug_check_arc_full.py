from storage.scraper_db import _get_conn, DB_PATH

def main():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, product_name, product_key, brand, line, model, series FROM scraped_items WHERE lower(product_name) LIKE '%arc%' OR lower(product_key) LIKE '%arc%' LIMIT 50")
    rows = cur.fetchall()
    print('DB_PATH=', DB_PATH)
    print('rows:', len(rows))
    for r in rows:
        print(r['id'], '->', r['product_key'], '| brand=', r['brand'], 'line=', r['line'], 'model=', r['model'], 'series=', r['series'])
    conn.close()

if __name__ == '__main__':
    main()
