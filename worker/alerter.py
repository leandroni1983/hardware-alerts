#!/usr/bin/env python3
"""Worker that periodically finds offers, analyses with AI and sends Telegram messages.

Behavior:
 - Runs in a loop with interval `ALERT_INTERVAL_MIN` (default 10).
 - Calls `scripts.notify_offers.find_offers` to get candidate offers.
 - For each offer, checks DB (`storage.scraper_db.has_been_notified`) to avoid duplicates.
 - If `AI_ENABLED` is true, calls `ai.analyze_offer.analyze` and may filter sends by `SEND_ONLY_REAL`.
 - Sends message via `notifier.telegram_bot.send_message` and marks the offer as notified via DB helper.

Environment variables:
 - ALERT_INTERVAL_MIN (int, default 10)
 - NOTIFY_SEND (true/false, default false) — whether to actually send Telegram messages
 - AI_ENABLED (true/false, default true)
 - SEND_ONLY_REAL (true/false, default true) — if true, only send when AI label == REAL
 - OLLAMA_URL is read by `ai.analyze_offer` if needed
 - SCRAPER_DB_PATH and TELEGRAM_TOKEN_FILE honored via existing modules
"""
from __future__ import annotations
import os
import time
import logging
from typing import Any
import sys
from pathlib import Path

# Ensure project root is on sys.path when running this file as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from notifier import telegram_bot
import storage.scraper_db as dbm
from ai import analyze_offer as ai_analyze
import scripts.notify_offers as notifier_script

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alerter")

ALERT_INTERVAL_MIN = int(os.getenv("ALERT_INTERVAL_MIN", "10"))
NOTIFY_SEND = os.getenv("NOTIFY_SEND", "false").lower() in ("1", "true", "yes")
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() in ("1", "true", "yes")
SEND_ONLY_REAL = os.getenv("SEND_ONLY_REAL", "true").lower() in ("1", "true", "yes")
LIMIT_KEYS = int(os.getenv("NOTIFY_LIMIT_KEYS", "500"))
MIN_SAMPLES = int(os.getenv("NOTIFY_MIN_SAMPLES", "5"))
THRESHOLD_PCT = float(os.getenv("NOTIFY_THRESHOLD_PCT", "15"))
AUTO_REAL_PCT = float(os.getenv("AUTO_REAL_PCT", "15"))


def process_offer(o: dict[str, Any]):
    product = {"title": o["title"], "shop": o["shop_name"], "url": o["url"]}
    product_key = None
    if o.get("product_keys"):
        # group-based detection uses groups; prefer first key if present
        product_key = o["product_keys"][0] if isinstance(o["product_keys"], list) and o["product_keys"] else None

    # Check duplicate by product_url/shop/price
    if dbm.has_been_notified(o.get("url"), o.get("shop_id"), o.get("price")):
        logger.info("Skipping already-notified: %s %s %s", o.get("url"), o.get("shop_name"), o.get("price"))
        return

    label = None
    raw = None

    # Heuristic pre-check: if price is sufficiently below avg30, mark REAL without calling AI
    try:
        price = o.get("price")
        avg = o.get("avg")
        if price is not None and avg is not None:
            try:
                price = float(price)
                avg = float(avg)
                if avg > 0 and price <= avg * (1.0 - AUTO_REAL_PCT / 100.0):
                    label = "REAL"
                    raw = f"heuristic: price <= avg * (1 - {AUTO_REAL_PCT}% )"
            except Exception:
                pass
    except Exception:
        pass

    # If heuristic didn't decide, use AI if enabled
    if label is None and AI_ENABLED:
        try:
            ctx = {
                "title": o.get("title"),
                "price": o.get("price"),
                "avg30": o.get("avg"),
                "avg7": None,
                "shop": o.get("shop_name"),
                "url": o.get("url"),
                "notes": o.get("reason"),
            }
            analysis = ai_analyze.analyze(ctx)
            label = analysis.get("label")
            raw = analysis.get("raw")
        except Exception as e:
            logger.exception("AI analyze failed: %s", e)
            label = None
            raw = None

    # Decide to send
    should_send = NOTIFY_SEND
    if AI_ENABLED and SEND_ONLY_REAL:
        should_send = should_send and (label == "REAL")

    if should_send:
        try:
            # Compose message similar to notifier but include AI label
            diff_pct = 0
            try:
                if o.get("avg"):
                    diff_pct = round((1 - (o["price"] / o["avg"])) * 100, 1)
            except Exception:
                diff_pct = 0

            text = (
                f"*{label or 'OFFER'}* — {o.get('title')}\n"
                f"Precio: *${o.get('price'):,}* — {diff_pct}% debajo del promedio\n"
                f"Tienda: {o.get('shop_name')}\n"
                f"{o.get('url')}\n\n"
                f"_AI analysis:_\n{(raw or '')}"
            )

            env = telegram_bot.load_env(telegram_bot.TELEGRAM_TOKEN_FILE)
            token = env.get("TELEGRAM_TOKEN")
            chat_id = env.get("TELEGRAM_CHAT_ID")
            if not token or not chat_id:
                logger.error("Missing TELEGRAM_TOKEN/CHAT_ID, skipping send")
            else:
                telegram_bot.send_message(token, chat_id, text)
                logger.info("Sent notification for %s %s", o.get("url"), o.get("shop_name"))
                dbm.mark_notified_offer(product_key, o.get("shop_id"), o.get("shop_name"), o.get("url"), o.get("price"), label=label, raw_ai=raw)
        except Exception as e:
            logger.exception("Failed sending notification: %s", e)
    else:
        # Dry-run or not allowed to send — still record decision if AI said REAL and dry-run requested? we don't mark as notified.
        logger.info("Dry-run/Not sending: %s %s label=%s", o.get("url"), o.get("shop_name"), label)


def main_loop():
    logger.info("Alerter starting: interval=%dmin ai=%s send=%s send_only_real=%s", ALERT_INTERVAL_MIN, AI_ENABLED, NOTIFY_SEND, SEND_ONLY_REAL)
    while True:
        try:
            offers = notifier_script.find_offers(days=30, min_samples=MIN_SAMPLES, threshold_pct=THRESHOLD_PCT, limit_keys=LIMIT_KEYS)
            logger.info("Found %d candidate offers", len(offers))
            for o in offers:
                try:
                    process_offer(o)
                except Exception:
                    logger.exception("Processing offer failed: %s", o)
        except Exception:
            logger.exception("Alerter loop error")
        logger.info("Sleeping %d minutes...", ALERT_INTERVAL_MIN)
        time.sleep(ALERT_INTERVAL_MIN * 60)


if __name__ == '__main__':
    main_loop()
