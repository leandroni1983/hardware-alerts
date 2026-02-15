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
from storage import conversations


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

                # Guided `/buscar` flow: start when user issues /buscar, or continue when state exists
                state = conversations.get_state(chat_id)
                if cmd in ('/buscar', '/browse', '/browser'):
                    conversations.set_state(chat_id, 'AWAIT_CATEGORY', {})
                    send_text(token, chat_id, 'Iniciando búsqueda guiada. Responde con: "Procesadores" o "Placas de video". Escribe "Cancelar" para salir.')
                    continue
                # If we're in a guided state and the user sent non-command text,
                # handle it according to the stage.
                if state and not text.strip().startswith('/'):
                    stage = state.get('stage')
                    data = state.get('data') or {}
                    ut = text.strip()
                    lcu = ut.lower()

                    # Helpers
                    def send_options(msg, buttons: list[list[str]] | None = None):
                        if buttons:
                            try:
                                telegram_bot.send_with_keyboard(token, str(chat_id), msg, buttons, parse_mode=None)
                                return
                            except Exception:
                                # fallback to plain text
                                pass
                        send_text(token, chat_id, msg)

                    if stage == 'AWAIT_CATEGORY':
                        if lcu in ('procesadores', 'procesador', 'cpu'):
                            conversations.set_state(chat_id, 'AWAIT_CPU_BRAND', {'category': 'cpu'})
                            send_options('Has elegido Procesadores. Elige marca:', buttons=[['Intel','AMD'],['Volver','Cancelar']])
                        elif lcu in ('placas de video', 'placa de video', 'gpu', 'placas'):
                            conversations.set_state(chat_id, 'AWAIT_GPU_BRAND', {'category': 'gpu'})
                            send_options('Has elegido Placas de video. Elige marca:', buttons=[['AMD','Intel','Radeon'],['Volver','Cancelar']])
                        elif lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                        else:
                            send_options('Opción no reconocida. Responde: "Procesadores" o "Placas de video" o "Cancelar".')
                        continue

                    if stage == 'AWAIT_CPU_BRAND':
                        if lcu in ('intel', 'amd'):
                            data['brand'] = lcu
                            # Ask for CPU family/generation next
                            conversations.set_state(chat_id, 'AWAIT_CPU_FAMILY', data)
                            if lcu == 'intel':
                                # generations + Pentium/Celeron
                                send_options('Elige generación o tipo Intel:', buttons=[['14','13','12'],['11','Pentium','Celeron'],['Otro','Volver']])
                            else:
                                # AMD families (Ryzen series)
                                send_options('Elige familia AMD/Ryzen:', buttons=[['Ryzen 7000','Ryzen 5000'],['Ryzen 3000','Otro'],['Volver']])
                        elif lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_CATEGORY', {})
                            send_options('Elige categoría:', buttons=[['Procesadores','Placas de video'],['Cancelar']])
                        elif lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                        else:
                            # re-send brand keyboard to avoid forcing typing
                            send_options('Respuesta no válida. Elige marca:', buttons=[['Intel','AMD'],['Volver','Cancelar']])
                        continue

                    if stage == 'AWAIT_CPU_MODEL':
                        if lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_CPU_BRAND', {'category': 'cpu'})
                            send_options('¿Intel o AMD?')
                            continue
                        if lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                            continue
                        # perform aggregated search and return top results
                        # Support buttons that may contain a placeholder like
                        # '{fam}600' when the family wasn't formatted client-side.
                        resolved = ut.replace('{fam}', data.get('family', ''))
                        # If the user sent only the numeric part (e.g. '12400' or '600'),
                        # prepend the family prefix (e.g. 'i5' or 'rx') to improve matching.
                        fam = data.get('family', '') or ''
                        fam_prefix = fam.split()[0] if fam else ''
                        if fam_prefix and fam_prefix not in resolved.lower() and any(ch.isdigit() for ch in resolved):
                            query = f"{fam_prefix} {resolved}"
                        else:
                            query = resolved
                        # log resolved query for debugging
                        print('Resolved CPU model query:', query)
                        code = ' '.join(''.join(ch for ch in part if ch.isalnum()) for part in query.split())
                        found_list = find_cheapest_all_by_code(DB_PATH, code, limit=5)
                        conversations.clear_state(chat_id)
                        if not found_list:
                            # Fallback: try single-item name search in product_name
                            single = find_cheapest_by_code(DB_PATH, code)
                            if single:
                                txt = f"*Mejor {query} encontrada*\n{single['product_name']}\nPrecio: *${single['price']:,}*\nTienda: {single['shop_name']}\n{single['product_url']}"
                                send_text(token, chat_id, txt)
                            else:
                                send_text(token, chat_id, f'No encontré ofertas para "{query}"')
                        else:
                            lines = [f"Top {len(found_list)} resultados para '{query}':"]
                            for it in found_list:
                                lines.append(f"{it.get('product_key') or it.get('product_name')}: ${it['price']:,} — {it['shop_name']}\n{it['product_url']}")
                            send_text(token, chat_id, "\n\n".join(lines))
                        continue
                    if stage == 'AWAIT_CPU_FAMILY':
                        if lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_CPU_BRAND', {'category': 'cpu'})
                            send_options('Elige marca:', buttons=[['Intel','AMD'],['Cancelar']])
                            continue
                        if lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                            continue
                        # record family/generation and prompt example models as buttons
                        data['family'] = lcu
                        conversations.set_state(chat_id, 'AWAIT_CPU_MODEL', data)
                        fam = lcu.lower()
                        # Intel generations (numeric) or Pentium/Celeron
                        if fam in ('14','13','12','11'):
                            send_options('Elige modelo (ej):', buttons=[[f'i9 {fam}900','i7 {fam}700','i5 {fam}600'],['Otro','Volver','Cancelar']])
                        elif fam in ('pentium','celeron'):
                            send_options('Elige modelo Pentium/Celeron (ej):', buttons=[['Pentium G6400','Celeron G6900','Otro'],['Volver','Cancelar']])
                        elif 'ryzen' in fam or 'amd' in fam:
                            send_options('Elige modelo (ej):', buttons=[['Ryzen 9 7950','Ryzen 7 7700','Ryzen 5 7600'],['Otro','Volver','Cancelar']])
                        else:
                            send_options('Elige modelo o selecciona "Otro" para escribir uno:', buttons=[['Otro','Volver','Cancelar']])
                        continue

                    if stage == 'AWAIT_GPU_BRAND':
                        if lcu in ('amd', 'intel', 'radeon', 'nvidia'):
                            data['brand'] = lcu
                            # Ask for GPU family next (e.g., RTX 40, RX 7000, Arc A7)
                            conversations.set_state(chat_id, 'AWAIT_GPU_FAMILY', data)
                            brand = lcu
                            if brand in ('nvidia', 'nvidia'):
                                send_options('Elige familia NVIDIA:', buttons=[['RTX 40','RTX 30'],['GTX','Otro'],['Volver','Cancelar']])
                            elif brand in ('amd', 'radeon'):
                                send_options('Elige familia AMD/Radeon:', buttons=[['RX 7000','RX 6000'],['RX 500','Otro'],['Volver','Cancelar']])
                            else:
                                # Intel
                                send_options('Elige familia Intel Arc:', buttons=[['Arc A7','Arc A5'],['Otro'],['Volver','Cancelar']])
                        elif lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_CATEGORY', {})
                            send_options('Elige categoría:', buttons=[['Procesadores','Placas de video'],['Cancelar']])
                        elif lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                        else:
                            # resend the GPU brand keyboard to avoid typing
                            send_options('Respuesta no válida. Elige marca:', buttons=[['AMD','Intel','Radeon'],['Volver','Cancelar']])
                        continue

                    if stage == 'AWAIT_GPU_MODEL':
                        if lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_GPU_BRAND', {'category': 'gpu'})
                            send_options('¿AMD, Intel o Radeon?')
                            continue
                        if lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                            continue
                        # Replace placeholder tokens if present (e.g. '{fam}600')
                        resolved = ut.replace('{fam}', data.get('family', ''))
                        # Prepend family prefix if user entered only numeric model
                        fam = data.get('family', '') or ''
                        fam_prefix = fam.split()[0] if fam else ''
                        if fam_prefix and fam_prefix not in resolved.lower() and any(ch.isdigit() for ch in resolved):
                            query = f"{fam_prefix} {resolved}"
                        else:
                            query = resolved
                        print('Resolved GPU model query:', query)
                        code = ' '.join(''.join(ch for ch in part if ch.isalnum()) for part in query.split())
                        found_list = find_cheapest_all_by_code(DB_PATH, code, limit=5)
                        conversations.clear_state(chat_id)
                        if not found_list:
                            single = find_cheapest_by_code(DB_PATH, code)
                            if single:
                                txt = f"*Mejor {query} encontrada*\n{single['product_name']}\nPrecio: *${single['price']:,}*\nTienda: {single['shop_name']}\n{single['product_url']}"
                                send_text(token, chat_id, txt)
                            else:
                                send_text(token, chat_id, f'No encontré ofertas para "{query}"')
                        else:
                            lines = [f"Top {len(found_list)} resultados para '{query}':"]
                            for it in found_list:
                                lines.append(f"{it.get('product_key') or it.get('product_name')}: ${it['price']:,} — {it['shop_name']}\n{it['product_url']}")
                            send_text(token, chat_id, "\n\n".join(lines))
                        continue
                    if stage == 'AWAIT_GPU_FAMILY':
                        # user selected a GPU family (e.g., 'RTX 40' or 'RX 7000')
                        if lcu in ('volver', 'atrás', 'atras'):
                            conversations.set_state(chat_id, 'AWAIT_GPU_BRAND', {'category': 'gpu'})
                            send_options('¿AMD, Intel o Radeon?', buttons=[['AMD','Intel','Radeon'],['Cancelar']])
                            continue
                        if lcu in ('cancelar', 'salir'):
                            conversations.clear_state(chat_id)
                            send_options('Búsqueda cancelada.')
                            continue
                        # Accept family selection or 'Otro'
                        data['family'] = lcu
                        conversations.set_state(chat_id, 'AWAIT_GPU_MODEL', data)
                        fam = lcu
                        # Provide example models for common families
                        if 'rtx' in fam:
                            send_options('Elige modelo (ej):', buttons=[['rtx 4090','rtx 4080','rtx 4070'],['Otro','Volver','Cancelar']])
                        elif 'rx 7000' in fam or 'rx7000' in fam or 'rx' in fam:
                            send_options('Elige modelo (ej):', buttons=[['rx 7900','rx 7800','rx 7700'],['Otro','Volver','Cancelar']])
                        elif 'arc' in fam:
                            send_options('Elige modelo (ej):', buttons=[['arc a770','arc a750','arc a580'],['Otro','Volver','Cancelar']])
                        elif 'gtx' in fam:
                            send_options('Elige modelo (ej):', buttons=[['gtx 1660','gtx 1650','Otro'],['Volver','Cancelar']])
                        else:
                            send_options('Escribe el modelo o selecciona "Otro" para escribirlo.', buttons=[['Otro','Volver','Cancelar']])
                        continue
                if cmd in ('/start', '/help'):
                    help_text = (
                        "Hola — comandos disponibles:\n"
                        "/best <modelo|codigo> - Devuelve la mejor oferta para un modelo o código.\n"
                        "  Ejemplos: /best 5060, /best i5 12400, /best i7 14\n"
                        "/bestall <codigo> [n] - Devuelve los mejores resultados por producto (top n).\n"
                        "  Ejemplo: /bestall 5060 5\n"
                        "/buscar - Flujo guiado para buscar productos paso a paso.\n"
                        "  Flujo: 1) Elige categoría: 'Procesadores' o 'Placas de video'\n"
                        "         2) Elige marca: (Procesadores) 'Intel'/'AMD' ; (Placas) 'AMD'/'Intel'/'Radeon'\n"
                        "         3) Escribe modelo (ej: 'i5 12400', 'rtx 4060', 'rx 7600')\n"
                        "  Dentro del flujo puedes escribir 'Volver' para retroceder o 'Cancelar' para salir.\n"
                        "Alias: /buscar -> /best (entrada guiada), /buscarall -> /bestall\n"
                        "Más ayuda: /help\n"
                    )
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
