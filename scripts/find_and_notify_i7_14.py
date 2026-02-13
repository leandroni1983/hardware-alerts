import sqlite3
import json
import os
from pathlib import Path

# DB path from storage.scraper_db if available
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

# Look for i7 14th gen: require 'i7' and '14' near model number
# This heuristic searches for rows containing 'i7' and '14' anywhere in the product_name.
cur.execute(
    """
    SELECT shop_id, shop_name, product_name, product_url, price, scraped_at
    FROM scraped_items
    WHERE lower(product_name) LIKE ?
      AND (lower(product_name) LIKE ? OR lower(product_name) LIKE ?)
      AND price IS NOT NULL
      AND stock = 1
    ORDER BY price ASC
    LIMIT 1
    """,
    ("%i7%", "%14%", "%14700%"),
)
row = cur.fetchone()

if not row:
    print(json.dumps({"found": False}))
    conn.close()
    raise SystemExit(0)

best = {
    "shop_id": row["shop_id"],
    "shop_name": row["shop_name"],
    "product_name": row["product_name"],
    "product_url": row["product_url"],
    "price": int(row["price"]),
    "scraped_at": row["scraped_at"],
}
conn.close()

# Compose message
price_txt = f"${best['price']:,}"
text = (
    f"*Mejor i7 14ª generación encontrada*\n"
    f"{best['product_name']}\n"
    f"Precio: *{price_txt}*\n"
    f"Tienda: {best['shop_name']}\n"
    f"{best['product_url']}"
)

# Send via notifier
try:
    from notifier import telegram_bot
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
