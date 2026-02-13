from storage import scraper_db as dbm
import sqlite3

URL = 'https://www.gezatek.com.ar/tienda/procesadores-intel/98378-micro-intel-core-ultra-7-265kf-55ghz-20-nucleos-lga1851.html'

def run():
    conn = sqlite3.connect(dbm.DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print('== scraped_items for URL ==')
    cur.execute('SELECT id, shop_id, shop_name, product_name, product_key, price, scraped_at, stock, product_url FROM scraped_items WHERE product_url = ?', (URL,))
    rows = cur.fetchall()
    for r in rows:
        print(dict(r))

    print('\n== price history for URL ==')
    cur.execute('SELECT price, scraped_at FROM scraped_price_history WHERE product_url = ? ORDER BY scraped_at DESC LIMIT 50', (URL,))
    for r in cur.fetchall():
        print(dict(r))

    product_key = rows[0]['product_key'] if rows else None
    print('\nproduct_key:', product_key)

    if product_key:
        print('\n== offers by key (aggregated min per shop) ==')
        offers = dbm.get_offers_by_key(product_key, limit=50)
        for o in offers:
            print(dict(o))

        print('\n== price history key (last 200) ==')
        cur.execute('SELECT price, scraped_at, shop_id, product_key FROM scraped_price_history_key WHERE product_key = ? ORDER BY scraped_at DESC LIMIT 200', (product_key,))
        for r in cur.fetchall():
            print(dict(r))

        print('\n== scraped_best_offers for key ==')
        cur.execute('SELECT * FROM scraped_best_offers WHERE product_key = ? ORDER BY recorded_at DESC LIMIT 50', (product_key,))
        for r in cur.fetchall():
            print(dict(r))

    # search for any rows with small prices that could leak (e.g., 32350)
    print('\n== any scraped_items with price < 50000 ==')
    cur.execute('SELECT id, shop_id, shop_name, product_name, product_key, price, product_url, scraped_at FROM scraped_items WHERE price < 50000 ORDER BY price ASC LIMIT 50')
    for r in cur.fetchall():
        print(dict(r))

    conn.close()

if __name__ == '__main__':
    run()
