#!/usr/bin/env python3
"""Listener simple para Telegram: responde a /best <query> y envía la mejor oferta.

Usage: python scripts/telegram_listener.py

El script hace long-polling sobre getUpdates y procesa mensajes entrantes.
Comandos soportados:
 - /best 5060          -> busca modelo 5060 y responde con la mejor oferta
 - /best i7 14         -> busca i7 14ª generación y responde con la mejor oferta
 - /help               -> muestra ayuda

Diseñado para ejecutarse en segundo plano (docker/systemd) o en local.
"""
import time
import requests
import sqlite3
import os
from pathlib import Path
import json
import sys

# Ensure project root is on sys.path when running this file as a script
# so sibling packages like `notifier` and `storage` can be imported.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from notifier import telegram_bot


def load_token():
    env = telegram_bot.load_env('config/telegram.env')
    token = env.get('TELEGRAM_TOKEN')
    if not token:
        raise RuntimeError('Missing TELEGRAM_TOKEN in config/telegram.env')
    return token


def send_text(token: str, chat_id: int, text: str):
    # use notifier send_message for retries/backoff
    env = telegram_bot.load_env('config/telegram.env')
    try:
        # Send as plain text to avoid Markdown/entity parse errors from
        # unescaped user-generated content. Notifier already escapes when
        # composing rich offer messages; for free-form responses send
        # without a parse_mode to prevent 400 errors.
        telegram_bot.send_message(token, str(chat_id), text, parse_mode=None)
    except Exception as e:
        print('Failed to send message:', e)


def find_cheapest_by_code(db_path: str, code: str):
    # simple case-insensitive substring search in product_name
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
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
        (f"%{code.lower()}%",),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"shop_id": row['shop_id'], "shop_name": row['shop_name'], "product_name": row['product_name'], "product_url": row['product_url'], "price": int(row['price']), 'scraped_at': row['scraped_at']}


def find_i7_14(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
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
    conn.close()
    if not row:
        return None
    return {"shop_id": row['shop_id'], "shop_name": row['shop_name'], "product_name": row['product_name'], "product_url": row['product_url'], "price": int(row['price']), 'scraped_at': row['scraped_at']}


def find_cheapest_all_by_code(db_path: str, code: str, limit: int = 5):
    """Return list of best price per product_key containing the code.

    This aggregates by `product_key` and returns the lowest price found for each
    matched key, ordered ascending.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT product_key, MIN(price) AS min_price
        FROM scraped_items
        WHERE product_key IS NOT NULL
          AND lower(product_key) LIKE ?
          AND price IS NOT NULL
          AND stock = 1
        GROUP BY product_key
        ORDER BY min_price ASC
        LIMIT ?
        """,
        (f"%{code.lower()}%", limit),
    )
    rows = cur.fetchall()
    results = []
    for r in rows:
        pk = r['product_key']
        price = int(r['min_price']) if r['min_price'] is not None else None
        # get one representative offer for this product_key (cheapest)
        cur.execute(
            """
            SELECT shop_id, shop_name, product_name, product_url, price, scraped_at
            FROM scraped_items
            WHERE product_key = ? AND price = ? AND stock = 1
            ORDER BY scraped_at DESC
            LIMIT 1
            """,
            (pk, price),
        )
        rep = cur.fetchone()
        if rep:
            results.append({
                'product_key': pk,
                'shop_id': rep['shop_id'],
                'shop_name': rep['shop_name'],
                'product_name': rep['product_name'],
                'product_url': rep['product_url'],
                'price': int(rep['price']),
                'scraped_at': rep['scraped_at'],
            })
    conn.close()
    return results


def main():
    token = load_token()
    # DB path from storage.scraper_db
    try:
        from storage import scraper_db
        DB_PATH = scraper_db.DB_PATH
    except Exception:
        DB_PATH = r"D:/Leandro/basesdedatos/data.db" if os.name == 'nt' else '/opt/scraper/data.db'

    if not Path(DB_PATH).exists():
        print('DB not found at', DB_PATH)
        return

    offset = None
    print('Telegram listener started. Polling for commands...')
    while True:
        try:
            url = f'https://api.telegram.org/bot{token}/getUpdates'
            params = {'timeout': 30, 'allowed_updates': ['message']}
            if offset:
                params['offset'] = offset
            resp = requests.get(url, params=params, timeout=40)
            data = resp.json()
            if not data.get('ok'):
                time.sleep(5)
                continue
            for upd in data.get('result', []):
                offset = upd['update_id'] + 1
                msg = upd.get('message') or {}
                text = msg.get('text') or ''
                chat = msg.get('chat') or {}
                chat_id = chat.get('id')
                user = msg.get('from', {}).get('username') or msg.get('from', {}).get('first_name')
                if not text or not chat_id:
                    continue
                parts = text.strip().split()
                cmd = parts[0].lower()
                args = parts[1:]
                print('Received', cmd, args, 'from', user)
                if cmd in ('/start', '/help'):
                    help_text = ("Comandos disponibles:\n" "- /best <modelo|codigo>  — devuelve la mejor oferta (ej: /best 5060, /best i7 14)\n")
                    send_text(token, chat_id, help_text)
                    continue
                if cmd == '/best':
                    if not args:
                        send_text(token, chat_id, 'Uso: /best <modelo>. Ej: /best 5060 o /best i7 14')
                        continue
                    # Validate query: if user sends nonsense, return help
                    def is_valid_query(tokens):
                        if not tokens:
                            return False
                        q = ' '.join(tokens).lower()
                        # numeric queries are allowed (model codes)
                        if any(c.isdigit() for c in q):
                            return True
                        # whitelist of common tokens
                        whitelist = {'i3','i5','i7','i9','intel','ryzen','amd','rx','rtx','gtx','radeon','ssd','nvme','kingston','ddr4','ddr5'}
                        for t in tokens:
                            if t.lower() in whitelist:
                                return True
                        return False

                    if not is_valid_query(args):
                        send_text(token, chat_id, 'No entiendo la consulta. Uso: /best <modelo|codigo>. Ej: /best 5060, /best i5 12400')
                        continue
                    query = ' '.join(args).lower()
                    # If query contains digits like 5060 -> use code search
                    if any(c.isdigit() for c in query):
                        # Build a code preserving separation between tokens so
                        # searches like "i5 12400" become "i5 12400" and
                        # not "i512400" which would fail matching.
                        code = ' '.join(''.join(ch for ch in part if ch.isalnum()) for part in args).lower()
                        found = find_cheapest_by_code(DB_PATH, code)
                        if not found:
                            send_text(token, chat_id, f'No encontré ofertas para "{query}"')
                        else:
                            txt = f"*Mejor {query} encontrada*\n{found['product_name']}\nPrecio: *${found['price']:,}*\nTienda: {found['shop_name']}\n{found['product_url']}"
                            send_text(token, chat_id, txt)
                        continue

                    # textual query — support 'i7 14' detection
                    if 'i7' in query and '14' in query:
                        found = find_i7_14(DB_PATH)
                        if not found:
                            send_text(token, chat_id, f'No encontré i7 14ª generación')
                        else:
                            txt = f"*Mejor i7 14ª generación encontrada*\n{found['product_name']}\nPrecio: *${found['price']:,}*\nTienda: {found['shop_name']}\n{found['product_url']}"
                            send_text(token, chat_id, txt)
                    else:
                        # fallback: search by token
                        found = find_cheapest_by_code(DB_PATH, query)
                        if not found:
                            send_text(token, chat_id, f'No encontré ofertas para "{query}"')
                        else:
                            txt = f"*Mejor {query} encontrada*\n{found['product_name']}\nPrecio: *${found['price']:,}*\nTienda: {found['shop_name']}\n{found['product_url']}"
                            send_text(token, chat_id, txt)
                    continue

                if cmd == '/bestall':
                    if not args:
                        send_text(token, chat_id, 'Uso: /bestall <codigo> [n]. Ej: /bestall 5060 5')
                        continue
                    # Validate query: quick check to avoid garbage queries
                    def is_valid_all_query(tokens):
                        if not tokens:
                            return False
                        q = ' '.join(tokens).lower()
                        if any(c.isdigit() for c in q):
                            return True
                        whitelist = {'i3','i5','i7','i9','intel','ryzen','amd','rx','rtx','gtx','radeon','ssd','nvme','kingston','ddr4','ddr5'}
                        # check first token for known families
                        if tokens[0].lower() in whitelist:
                            return True
                        return False

                    if not is_valid_all_query(args):
                        send_text(token, chat_id, 'No entiendo la consulta para /bestall. Uso: /bestall <codigo> [n]. Ej: /bestall i5 12400 5')
                        continue
                    # allow optional limit arg. If the last arg is a number,
                    # treat it as the `limit`. Otherwise join all args as the
                    # product code (preserving token separation), e.g.
                    # `/bestall i5 12400` -> code 'i5 12400'.
                    limit = 5
                    code_parts = args
                    if len(args) > 1:
                        # if last token is a number, use it as limit
                        try:
                            maybe_limit = int(args[-1])
                            limit = maybe_limit
                            code_parts = args[:-1]
                        except Exception:
                            code_parts = args
                    # sanitize each part but keep spaces between parts
                    code = ' '.join(''.join(ch for ch in part.lower() if ch.isalnum()) for part in code_parts)
                    found_list = find_cheapest_all_by_code(DB_PATH, code, limit=limit)
                    if not found_list:
                        send_text(token, chat_id, f'No encontré ofertas para "{code}"')
                    else:
                        lines = [f"Top {len(found_list)} resultados para '{code}':"]
                        for it in found_list:
                            lines.append(f"{it['product_key']}: ${it['price']:,} — {it['shop_name']}\n{it['product_url']}")
                        send_text(token, chat_id, "\n\n".join(lines))
                    # end /best handling
            # short sleep to avoid tight loop
            time.sleep(0.5)
        except Exception as e:
            print('Listener error:', e)
            time.sleep(5)


if __name__ == '__main__':
    main()
