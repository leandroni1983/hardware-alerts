"""Telegram notifier using Bot API via simple HTTP requests.

Provides `send_offer` which composes a Markdown message and sends it.
"""

import os
import requests
from typing import Optional

TELEGRAM_TOKEN_FILE = os.getenv("TELEGRAM_TOKEN_FILE", "config/telegram.env")


def load_env(path: str) -> dict:
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    data[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return data


def send_message(token: str, chat_id: str, text: str, parse_mode: str = 'Markdown') -> dict:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    resp = requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode})
    return resp.json()


def format_offer_message(product: dict, price: int, avg30: float) -> str:
    title = product.get('title')
    shop = product.get('shop')
    url = product.get('url')
    diff_pct = 0
    if avg30:
        diff_pct = round((1 - (price / avg30)) * 100, 1)

    text = (
        f"*Oferta REAL*\n"
        f"*{title}*\n"
        f"Precio: *${price:,}* (≈ ARS) — {diff_pct}% por debajo del promedio 30d\n"
        f"Tienda: {shop}\n"
        f"{url}"
    )
    return text


def send_offer(product: dict, price: int, avg30: float, telegram_env_path: Optional[str] = None) -> dict:
    env_path = telegram_env_path or TELEGRAM_TOKEN_FILE
    env = load_env(env_path)
    token = env.get('TELEGRAM_TOKEN')
    chat_id = env.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError('Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID in telegram.env')

    text = format_offer_message(product, price, avg30)
    return send_message(token, chat_id, text)


if __name__ == '__main__':
    # quick smoke test
    p = {'title': 'RTX 3060 12GB XYZ', 'shop': 'compra_gamer', 'url': 'https://...'}
    try:
        print(send_offer(p, 900000, 1100000, 'config/telegram.env'))
    except Exception as e:
        print('Notifier error:', e)
