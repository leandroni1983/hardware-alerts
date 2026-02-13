#!/usr/bin/env python3
"""Detecta ofertas usando la DB y notifica por Telegram.

Uso:
  python scripts/notify_offers.py [--days 30] [--min-samples 5] [--threshold 15] [--send]

Por defecto corre en modo prueba (no envía). Pase `--send` para enviar.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict

import storage.scraper_db as dbm
from notifier import telegram_bot
from ai import analyze_offer as ai_analyze
from normalizers import matcher

# Keywords to exclude from offer detection (common peripherals / non-target items)
EXCLUDE_KEYWORDS = [
    "auricular",
    "auriculares",
    "audifono",
    "audífono",
    "audifonos",
    "microfono",
    "micrófono",
    "micro",
    "mic",
    "headset",
    "headphones",
    "headphone",
    "mouse",
    "mause",
    "teclado",
    "keyboard",
    "monitor",
    "camara",
    "cámara",
    "webcam",
    "parlante",
    "speaker",
    "impresora",
    "cargador",
    "cable",
]

# Whitelist tokens that indicate CPUs/GPUs/PC parts we care about even if they contain
# ambiguous substrings like 'micro' (e.g. 'micro ATX' or product titles mentioning 'micro').
WHITELIST_TOKENS = [
    "ryzen",
    "intel",
    "core",
    "i3",
    "i5",
    "i7",
    "i9",
    "athlon",
    "pentium",
    "xeon",
    "threadripper",
    "rx",
    "rtx",
    "gtx",
    "radeon",
    "rx",
    "vram",
    "ddr",
    "ddr4",
    "ddr5",
    "ssd",
    "nvme",
    "m.2",
]


def avg_price_for_key_shop(conn: sqlite3.Connection, product_key: str, shop_id: str, days: int) -> float:
    since = datetime.utcnow() - timedelta(days=days)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT price FROM scraped_price_history_key
        WHERE product_key = ? AND shop_id = ? AND price IS NOT NULL AND scraped_at >= ?
        """,
        (product_key, shop_id, since.isoformat()),
    )
    rows = cur.fetchall()
    prices = [r[0] for r in rows if r[0] is not None]
    if not prices:
        return 0.0
    return sum(prices) / len(prices)


def find_offers(days: int, min_samples: int, threshold_pct: float, limit_keys: int = 500) -> List[Dict]:
    results = []
    # open DB connection for queries
    conn = sqlite3.connect(dbm.DB_PATH)
    conn.row_factory = sqlite3.Row

    keys = dbm.get_available_product_keys(limit=limit_keys)
    # group keys by product_key (fallback to canonical name for generic keys)
    groups: Dict[str, List[str]] = {}
    samples: Dict[str, Dict] = {}
    GENERIC_KEYS = {"amd", "intel", "nvidia", "gpu", "cpu"}
    for k in keys:
        pk = k.get("product_key")
        if not pk:
            continue
        pk_lower = pk.lower() if isinstance(pk, str) else pk
        # If the product_key is too generic (like 'amd') or very short, use canonical name
        if pk_lower in GENERIC_KEYS or (isinstance(pk, str) and len(pk.strip()) < 4):
            group_key = matcher.canonicalize_name(k.get("sample_product_name") or pk)
        else:
            group_key = pk
            # If this product_key maps to multiple distinct product_name entries in DB,
            # it's too coarse — fallback to canonicalizing the sample product name.
            try:
                conn_check = sqlite3.connect(dbm.DB_PATH)
                cur_check = conn_check.cursor()
                cur_check.execute("SELECT COUNT(DISTINCT product_name) FROM scraped_items WHERE product_key = ?", (pk,))
                cnt = cur_check.fetchone()[0]
                conn_check.close()
                if cnt and int(cnt) > 1:
                    group_key = matcher.canonicalize_name(k.get("sample_product_name") or pk)
            except Exception:
                pass
        groups.setdefault(group_key, []).append(pk)
        if group_key not in samples:
            samples[group_key] = {
                "title": k.get("sample_product_name") or pk,
                "url": k.get("sample_product_url"),
            }

    since = datetime.utcnow() - timedelta(days=days)

    for canon, pk_list in groups.items():
        # Skip groups that look like peripherals or unrelated categories
        sample_title = (samples.get(canon, {}).get("title") or "").lower()
        # If any exclude keyword present, consider skipping — but allow if whitelist tokens appear.
        found_exclude = any(ex in sample_title for ex in EXCLUDE_KEYWORDS)
        if found_exclude:
            # If title contains ambiguous 'micro' or 'sd', only allow if whitelist token present
            ambiguous = any(x in sample_title for x in ("micro", "microsd", "micro sd", "sd ", "sdcard"))
            has_whitelist = any(w in sample_title for w in WHITELIST_TOKENS)
            if ambiguous and has_whitelist:
                # allow through (e.g., 'intel micro atx' or 'ryzen micro')
                pass
            else:
                continue

        # offers across all keys in group
        placeholders = ','.join('?' for _ in pk_list)
        cur = conn.cursor()
        # If this group is formed from a very generic product_key that maps to many
        # different product_name entries, skip it to avoid noisy/incorrect promotions.
        try:
            cur.execute(f"SELECT COUNT(DISTINCT product_name) as cnt FROM scraped_items WHERE product_key IN ({placeholders})", tuple(pk_list))
            cnt = cur.fetchone()[0]
            if cnt and int(cnt) > 6 and any((isinstance(pk, str) and pk.lower() in ("amd","intel","nvidia","gpu","cpu")) for pk in pk_list):
                # too ambiguous, skip group
                continue
        except Exception:
            pass
        # try to avoid mixing different models that share a coarse product_key
        sample_title = (samples.get(canon, {}).get("title") or "")
        raw_tokens = __import__('re').findall(r"\w+", sample_title)
        # prefer tokens that look like model identifiers (contain both letters and digits)
        # or short family ids (i5,i9,ryzen). Exclude pure numeric tokens like socket numbers.
        family_tokens = {"i3","i5","i7","i9","ryzen","rx","rtx","gtx"}
        def is_model_token(t: str) -> bool:
            has_digit = any(c.isdigit() for c in t)
            has_alpha = any(c.isalpha() for c in t)
            return len(t) > 2 and ( (has_digit and has_alpha) or (t.lower() in family_tokens) )
        tokens = [t for t in raw_tokens if is_model_token(t)]
        # If the group is derived from a canonical name (generic product_key),
        # search by product_name tokens only to avoid mixing unrelated items that share the same coarse key.
        use_token_only = any((isinstance(pk, str) and pk.lower() in ("amd", "intel", "nvidia", "gpu", "cpu")) for pk in pk_list) or (canon not in pk_list)
        if use_token_only and tokens:
            like_clauses = ' OR '.join('product_name LIKE ?' for _ in tokens)
            params = tuple('%' + t + '%' for t in tokens)
            cur.execute(
                f"""
                SELECT shop_id, shop_name, MIN(price) AS min_price
                FROM scraped_items
                WHERE price IS NOT NULL
                  AND stock = 1
                  AND ({like_clauses})
                GROUP BY shop_id, shop_name
                ORDER BY min_price ASC
                """,
                params,
            )
        else:
            if tokens:
                # refine by tokens and product_key list
                like_clauses = ' OR '.join('product_name LIKE ?' for _ in tokens)
                params = tuple(pk_list) + tuple('%' + t + '%' for t in tokens)
                cur.execute(
                    f"""
                    SELECT shop_id, shop_name, MIN(price) AS min_price
                    FROM scraped_items
                    WHERE product_key IN ({placeholders})
                      AND price IS NOT NULL
                      AND stock = 1
                      AND ({like_clauses})
                    GROUP BY shop_id, shop_name
                    ORDER BY min_price ASC
                    """,
                    params,
                )
            else:
                cur.execute(
                    f"""
                    SELECT shop_id, shop_name, MIN(price) AS min_price
                    FROM scraped_items
                    WHERE product_key IN ({placeholders})
                      AND price IS NOT NULL
                      AND stock = 1
                    GROUP BY shop_id, shop_name
                    ORDER BY min_price ASC
                    """,
                    tuple(pk_list),
                )
        offers_all = cur.fetchall()
        if not offers_all:
            continue

        # for each shop offering this group, compute combined historical prices
        for row in offers_all:
            shop_id = row[0]
            shop_name = row[1]
            price = int(row[2]) if row[2] is not None else None
            if price is None:
                continue

            # get historical prices across all product_keys in group for this shop
            cur.execute(
                f"""
                SELECT price FROM scraped_price_history_key
                WHERE product_key IN ({placeholders})
                  AND shop_id = ?
                  AND price IS NOT NULL
                  AND scraped_at >= ?
                """,
                tuple(pk_list) + (shop_id, since.isoformat()),
            )
            hist_rows = cur.fetchall()
            prices = [r[0] for r in hist_rows if r[0] is not None]
            if len(prices) < min_samples:
                continue
            avg_price = sum(prices) / len(prices)
            min_hist = min(prices)

            # detection rules (same as is_candidate_promo logic)
            threshold_value = avg_price * (1 - threshold_pct / 100.0)
            is_promo = False
            reason = 'no_promo'
            if price <= threshold_value:
                is_promo = True
                reason = 'below_avg'
            elif price <= (min_hist * 0.98):
                is_promo = True
                reason = 'near_min'

            if is_promo:
                best_shop = offers_all[0][1]
                best_shop_price = int(offers_all[0][2]) if offers_all[0][2] is not None else None

                # Resolve the specific product_url/product_name that produced this min price
                detected_url = samples[canon]["url"]
                detected_name = samples[canon]["title"]
                try:
                    if use_token_only and tokens:
                        like_clauses = ' OR '.join('product_name LIKE ?' for _ in tokens)
                        params = tuple('%' + t + '%' for t in tokens) + (price,)
                        cur.execute(
                            f"SELECT product_url, product_name FROM scraped_items WHERE price = ? AND stock = 1 AND ({like_clauses}) ORDER BY scraped_at DESC LIMIT 1",
                            (price,) + tuple('%' + t + '%' for t in tokens),
                        )
                        row = cur.fetchone()
                        if row:
                            detected_url = row['product_url']
                            detected_name = row['product_name']
                    else:
                        if tokens:
                            cur.execute(
                                f"SELECT product_url, product_name FROM scraped_items WHERE product_key IN ({placeholders}) AND price = ? AND stock = 1 AND ({like_clauses}) ORDER BY scraped_at DESC LIMIT 1",
                                tuple(pk_list) + (price,) + tuple('%' + t + '%' for t in tokens),
                            )
                        else:
                            cur.execute(
                                f"SELECT product_url, product_name FROM scraped_items WHERE product_key IN ({placeholders}) AND price = ? AND stock = 1 ORDER BY scraped_at DESC LIMIT 1",
                                tuple(pk_list) + (price,),
                            )
                        row = cur.fetchone()
                        if row:
                            detected_url = row['product_url']
                            detected_name = row['product_name']
                except Exception:
                    pass

                results.append(
                    {
                        "product_key_group": canon,
                        "product_keys": pk_list,
                        "title": detected_name,
                        "url": detected_url,
                        "shop_id": shop_id,
                        "shop_name": shop_name,
                        "price": price,
                        "avg": avg_price,
                        "reason": reason,
                        "best_shop": best_shop,
                        "best_shop_price": best_shop_price,
                    }
                )

    conn.close()
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30, help="window in days for historical avg and detection")
    p.add_argument("--min-samples", type=int, default=5, help="minimum historical samples required")
    p.add_argument("--threshold", type=float, default=15.0, help="threshold percent below avg to consider offer")
    p.add_argument("--limit-keys", type=int, default=500, help="max product keys to check")
    p.add_argument("--send", action="store_true", help="actually send Telegram messages")
    p.add_argument("--ai", action="store_true", help="use AI to analyze each detected offer and include analysis in message")
    p.add_argument("--auto-real-pct", type=float, default=None, help="auto-label as REAL when price is this percent below avg (overrides AUTO_REAL_PCT env)")
    args = p.parse_args()

    offers = find_offers(days=args.days, min_samples=args.min_samples, threshold_pct=args.threshold, limit_keys=args.limit_keys)

    # configure AUTO_REAL_PCT from env or CLI
    import os
    env_auto = None
    try:
        env_auto = float(os.environ.get("AUTO_REAL_PCT")) if os.environ.get("AUTO_REAL_PCT") is not None else None
    except Exception:
        env_auto = None
    AUTO_REAL_PCT = args.auto_real_pct if args.auto_real_pct is not None else (env_auto if env_auto is not None else 15.0)

    if not offers:
        print("No offers detected.")
        return

    print(f"Detected {len(offers)} offers (dry-run={not args.send}).")
    for o in offers:
        print(json.dumps(o, ensure_ascii=False))
        if args.send:
            try:
                product = {"title": o["title"], "shop": o["shop_name"], "url": o["url"]}
                if args.ai:
                    # Build context for AI classifier
                    ctx = {
                        "title": o.get("title"),
                        "price": o.get("price"),
                        "avg30": o.get("avg"),
                        "shop": o.get("shop_name"),
                        "url": o.get("url"),
                        "notes": o.get("reason"),
                    }
                    # Heuristic pre-label: if price is significantly below avg, mark REAL
                    pre_label = None
                    try:
                        if o.get("avg") and AUTO_REAL_PCT is not None:
                            if o["price"] <= o["avg"] * (1 - AUTO_REAL_PCT / 100.0):
                                pre_label = "REAL"
                    except Exception:
                        pre_label = None
                    if pre_label:
                        ctx["pre_label"] = pre_label

                    analysis = ai_analyze.analyze(ctx)
                    label = analysis.get("label", "NORMAL")
                    raw = analysis.get("raw", "")

                    # Build similar-products summary: for each product_key in the group,
                    # fetch its best shop/price and mark which is the overall best.
                    try:
                        conn = sqlite3.connect(dbm.DB_PATH)
                        conn.row_factory = sqlite3.Row
                        similar_rows = []
                        best_overall_price = None
                        best_overall = None
                        for pk in o.get("product_keys", []):
                            cur = conn.cursor()
                            cur.execute(
                                "SELECT product_name, product_url FROM scraped_items WHERE product_key = ? ORDER BY scraped_at DESC LIMIT 1",
                                (pk,),
                            )
                            sample = cur.fetchone()
                            sample_name = sample["product_name"] if sample else pk

                            offers = dbm.get_offers_by_key(pk, limit=5)
                            if offers:
                                top = offers[0]
                                shop = top["shop_name"]
                                price = int(top["min_price"]) if top["min_price"] is not None else None
                            else:
                                shop = None
                                price = None

                            similar_rows.append({"product_key": pk, "sample": sample_name, "shop": shop, "price": price})
                            if price is not None:
                                if best_overall_price is None or price < best_overall_price:
                                    best_overall_price = price
                                    best_overall = pk
                        conn.close()
                    except Exception:
                        similar_rows = []
                        best_overall = None

                    # Format similar-products block
                    similar_block = ""
                    if similar_rows:
                        lines = ["Precios similares por producto (mejor en negrita):"]
                        for r in similar_rows:
                            price_txt = f"${r['price']:,}" if r.get("price") is not None else "sin precio"
                            prefix = "**" if r["product_key"] == best_overall else ""
                            suffix = "**" if r["product_key"] == best_overall else ""
                            lines.append(f"- {prefix}{r['sample']}{suffix} — {price_txt} @ {r.get('shop') or 'N/A'}")
                        similar_block = "\n" + "\n".join(lines)

                    # Percentage vs other shops: compute min price per shop for this group
                    try:
                        conn2 = sqlite3.connect(dbm.DB_PATH)
                        conn2.row_factory = sqlite3.Row
                        cur2 = conn2.cursor()
                        pk_list = o.get("product_keys") or []
                        pct_saving = None
                        avg_other = None
                        if pk_list:
                            placeholders = ','.join('?' for _ in pk_list)
                            cur2.execute(
                                f"""
                                SELECT shop_id, MIN(price) AS min_price
                                FROM scraped_items
                                WHERE product_key IN ({placeholders})
                                  AND price IS NOT NULL
                                  AND stock = 1
                                GROUP BY shop_id
                                """,
                                tuple(pk_list),
                            )
                            shop_rows = cur2.fetchall()
                            prices_by_shop = {r['shop_id']: int(r['min_price']) for r in shop_rows}
                            other_prices = [p for s, p in prices_by_shop.items() if s != o.get('shop_id')]
                            if other_prices:
                                from statistics import mean
                                avg_other = mean(other_prices)
                                try:
                                    pct_saving = round((1 - (o['price'] / avg_other)) * 100, 2)
                                except Exception:
                                    pct_saving = None

                        # Best prices for 8GB / 16GB variants (search product_name for tokens)
                        size_lines = []
                        for size_token in ('8gb', '8 gb', '16gb', '16 gb'):
                            # run a search limited to the same pk_list if available
                            try:
                                if pk_list:
                                    placeholders = ','.join('?' for _ in pk_list)
                                    cur2.execute(
                                        f"""
                                        SELECT shop_name, MIN(price) AS min_price
                                        FROM scraped_items
                                        WHERE product_key IN ({placeholders})
                                          AND lower(product_name) LIKE ?
                                          AND price IS NOT NULL
                                          AND stock = 1
                                        GROUP BY shop_name
                                        ORDER BY min_price ASC
                                        LIMIT 1
                                        """,
                                        tuple(pk_list) + (f"%{size_token}%",),
                                    )
                                else:
                                    cur2.execute(
                                        """
                                        SELECT shop_name, MIN(price) AS min_price
                                        FROM scraped_items
                                        WHERE lower(product_name) LIKE ?
                                          AND price IS NOT NULL
                                          AND stock = 1
                                        GROUP BY shop_name
                                        ORDER BY min_price ASC
                                        LIMIT 1
                                        """,
                                        (f"%{size_token}%",),
                                    )
                                r = cur2.fetchone()
                                if r and r['min_price'] is not None:
                                    size_lines.append((size_token.replace(' ', ''), int(r['min_price']), r['shop_name']))
                            except Exception:
                                continue
                    except Exception:
                        pct_saving = None
                        avg_other = None
                        size_lines = []
                    finally:
                        try:
                            conn2.close()
                        except Exception:
                            pass

                    # Format message
                    diff_pct = 0
                    try:
                        if o.get("avg"):
                            diff_pct = round((1 - (o["price"] / o["avg"])) * 100, 1)
                    except Exception:
                        diff_pct = 0

                    savings_text = ''
                    if pct_saving is not None:
                        savings_text = f"Ahorro vs otras tiendas: {pct_saving}% (promedio otras: ${int(avg_other):,})\n"

                    size_block = ''
                    if size_lines:
                        lines = ["Mejores precios por variante:"]
                        for token, price_val, shopn in size_lines:
                            lines.append(f"- {token.upper()}: ${price_val:,} @ {shopn}")
                        size_block = "\n" + "\n".join(lines)

                    text = (
                        f"*{label}* — {o.get('title')}\n"
                        f"Precio: *${o.get('price'):,}* — {diff_pct}% debajo del promedio\n"
                        f"Tienda: {o.get('shop_name')}\n"
                        f"{o.get('url')}\n\n"
                        f"{savings_text}"
                        f"_AI analysis:_\n{raw}"
                        f"{similar_block}"
                        f"{size_block}"
                    )

                    env = telegram_bot.load_env(telegram_bot.TELEGRAM_TOKEN_FILE)
                    token = env.get("TELEGRAM_TOKEN")
                    chat_id = env.get("TELEGRAM_CHAT_ID")
                    if not token or not chat_id:
                        print("Missing TELEGRAM_TOKEN/CHAT_ID, skipping send")
                    else:
                        telegram_bot.send_message(token, chat_id, text)
                else:
                    telegram_bot.send_offer(product, o["price"], o["avg"]) 
            except Exception as e:
                print("Failed to send offer for", o["product_key"], o["shop_id"], e)


if __name__ == "__main__":
    main()
