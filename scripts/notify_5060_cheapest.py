import sqlite3
import json
import os
from pathlib import Path
from statistics import mean

# reuse DB path from storage.scraper_db
DB_PATH = None
try:
    from storage import scraper_db
    DB_PATH = scraper_db.DB_PATH
except Exception:
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

# get cheapest row for 5060 (already implemented in find_cheapest_5060.py logic)
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
best = cur.fetchone()

if not best:
    print(json.dumps({"found": False}))
    conn.close()
    raise SystemExit(0)

best_shop = best['shop_id']
best_price = int(best['price'])
product_name = best['product_name']
product_url = best['product_url']

# get minimum price per shop for this model
cur.execute(
    """
    SELECT shop_id, MIN(price) AS min_price
    FROM scraped_items
    WHERE lower(product_name) LIKE ?
      AND price IS NOT NULL
      AND stock = 1
    GROUP BY shop_id
    """,
    ("%5060%",),
)
rows = cur.fetchall()
conn.close()

prices_by_shop = {r['shop_id']: int(r['min_price']) for r in rows}
other_prices = [p for s, p in prices_by_shop.items() if s != best_shop]

if other_prices:
    avg_other = mean(other_prices)
    pct_saving = round((1 - (best_price / avg_other)) * 100, 2)
else:
    avg_other = None
    pct_saving = None

# Compose message
title = product_name
shop_name = best['shop_name']
price_txt = f"${best_price:,}"
if avg_other:
    avg_txt = f"${int(avg_other):,}"
    pct_txt = f"{pct_saving}%"
    savings_line = f"Ahorro respecto al promedio de otras tiendas: {pct_txt} (promedio {avg_txt})"
else:
    savings_line = "No hay otras tiendas para comparar"

text = (
    "*Oferta encontrada:*\n"
    f"*{title}*\n"
    f"Precio: *{price_txt}*\n"
    f"Tienda: {shop_name}\n"
    f"{savings_line}\n"
    f"{product_url}"
)

# Send via notifier
try:
    from notifier import telegram_bot
    env = telegram_bot.load_env('config/telegram.env')
    token = env.get('TELEGRAM_TOKEN')
    chat_id = env.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        # try default path
        env = telegram_bot.load_env('config/telegram.env')
        token = env.get('TELEGRAM_TOKEN')
        chat_id = env.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print(json.dumps({"error": "missing_telegram_config"}))
        raise SystemExit(1)
    resp = telegram_bot.send_message(token, chat_id, text, parse_mode='Markdown')
    print(json.dumps({"sent": True, "resp": resp}))
except Exception as e:
    print(json.dumps({"sent": False, "error": str(e)}))
