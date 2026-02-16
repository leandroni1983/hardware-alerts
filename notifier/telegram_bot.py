"""Telegram notifier using Bot API via simple HTTP requests.

Provides `send_offer` which composes a Markdown message and sends it.
"""

import os
import requests
import logging
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


def _escape_markdown_v2(text: str) -> str:
    """Escape text for Telegram MarkdownV2 (only user-provided content)."""
    if not text:
        return ""
    # Characters that must be escaped in MarkdownV2
    special = "_()*[]~`>#+-=|{}.!"
    return ''.join(('\\' + c) if c in special else c for c in text)


def send_message(token: str, chat_id: str, text: str, parse_mode: str = 'MarkdownV2', reply_markup: dict | None = None, retries: int = 3, backoff: float = 1.5, timeout: int = 15) -> dict:
    """Send message with simple retries and exponential backoff.

    Parameters configurable per-call. Returns Telegram JSON response on success
    or raises the last exception on failure.
    """
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    logger = logging.getLogger("notifier.telegram")
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            payload = {'chat_id': chat_id, 'text': text}
            if parse_mode:
                payload['parse_mode'] = parse_mode
            if reply_markup is not None:
                payload['reply_markup'] = reply_markup
            resp = requests.post(url, json=payload, timeout=timeout)
            # raise for non-200 statuses to trigger retries
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as he:
            # Try to log response body for diagnosis
            resp = getattr(he, 'response', None)
            body = None
            try:
                if resp is not None:
                    body = resp.text
            except Exception:
                body = None
            logger.error('Telegram HTTPError status=%s body=%s', getattr(resp, 'status_code', None), body)
            # If Bad Request (400) and it looks like a Markdown/entities error,
            # retry once without parse_mode to avoid entity parsing failures.
            if resp is not None and resp.status_code == 400 and parse_mode is not None:
                logger.info('Retrying send_message without parse_mode due to 400 error')
                try:
                    resp2 = requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=timeout)
                    resp2.raise_for_status()
                    return resp2.json()
                except Exception as e2:
                    last_exc = e2
                    logger.exception('Retry without parse_mode failed')
            last_exc = he
            # if we can retry, sleep then continue
        except Exception as e:
            last_exc = e
            logger.exception('Telegram send_message exception')

        if attempt < retries:
            try:
                sleep_time = backoff ** (attempt - 1)
                time_to_sleep = sleep_time if sleep_time > 0 else backoff
                import time as _t
                _t.sleep(time_to_sleep)
            except Exception:
                pass
    # fallback: re-raise last exception with context
    if last_exc:
        raise last_exc
    return {}


def format_offer_message(product: dict, price: int, avg30: float, best_shop: str | None = None, best_price: int | None = None) -> str:
    title = product.get('title')
    shop = product.get('shop')
    url = product.get('url')
    diff_pct = 0
    if avg30:
        diff_pct = round((1 - (price / avg30)) * 100, 1)

    best_line = ""
    # Escape user-provided fields for MarkdownV2
    try:
        esc_title = _escape_markdown_v2(str(title)) if title else ''
        esc_shop = _escape_markdown_v2(str(shop)) if shop else ''
    except Exception:
        esc_title = str(title or '')
        esc_shop = str(shop or '')

    if best_shop and best_price is not None:
        esc_best_shop = _escape_markdown_v2(str(best_shop))
        best_line = f"\nMejor oferta hoy: {esc_best_shop} a *${best_price:,}*"

    # Wrap URL in angle brackets to avoid entity parsing issues
    url_part = f"<{url}>" if url else ''

    text = (
        f"*Oferta REAL*\n"
        f"*{esc_title}*\n"
        f"Precio: *${price:,}* (≈ ARS) — {diff_pct}% por debajo del promedio {int(avg30 and 30 or 0)}d\n"
        f"Tienda: {esc_shop}"
        f"{best_line}\n"
        f"{url_part}"
    )
    return text


def send_offer(product: dict, price: int, avg30: float, best_shop: str | None = None, best_price: int | None = None, telegram_env_path: Optional[str] = None) -> dict:
    env_path = telegram_env_path or TELEGRAM_TOKEN_FILE
    env = load_env(env_path)
    token = env.get('TELEGRAM_TOKEN')
    chat_id = env.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError('Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID in telegram.env')

    text = format_offer_message(product, price, avg30, best_shop=best_shop, best_price=best_price)
    return send_message(token, chat_id, text)


def make_keyboard(button_rows: list[list[str]]) -> dict:
    """Return a Telegram reply_markup keyboard given rows of button labels."""
    return {
        'keyboard': button_rows,
        'one_time_keyboard': True,
        'resize_keyboard': True,
    }


def send_with_keyboard(token: str, chat_id: str, text: str, button_rows: list[list[str]], parse_mode: str = None) -> dict:
    rm = make_keyboard(button_rows)
    return send_message(token, chat_id, text, parse_mode=parse_mode, reply_markup=rm)


if __name__ == '__main__':
    # quick smoke test
    p = {'title': 'RTX 3060 12GB XYZ', 'shop': 'compra_gamer', 'url': 'https://...'}
    try:
        print(send_offer(p, 900000, 1100000, 'config/telegram.env'))
    except Exception as e:
        print('Notifier error:', e)
