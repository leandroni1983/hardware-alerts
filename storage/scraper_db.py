import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Default DB path: prefer host Windows path under D:/Leandro/basesdedatos when running locally (Windows),
# otherwise use the container path /opt/scraper/data.db. Can be overridden with SCRAPER_DB_PATH env var.
if os.environ.get("SCRAPER_DB_PATH"):
    DB_PATH = os.environ.get("SCRAPER_DB_PATH")
else:
    if os.name == "nt":
        DB_PATH = r"D:/Leandro/basesdedatos/data.db"
    else:
        DB_PATH = "/opt/scraper/data.db"


def _ensure_db_dir() -> None:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS scraped_items (
            id INTEGER PRIMARY KEY,
            shop_id TEXT NOT NULL,
            shop_name TEXT NOT NULL,
            category TEXT,
            product_name TEXT NOT NULL,
            price INTEGER,
            stock INTEGER,
            product_url TEXT NOT NULL UNIQUE,
            scraped_at TEXT NOT NULL,
            summary TEXT,
            processed INTEGER NOT NULL DEFAULT 0,
            processed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scraped_items_processed
            ON scraped_items (processed);

        CREATE INDEX IF NOT EXISTS idx_scraped_items_scraped_at
            ON scraped_items (scraped_at);

        CREATE TABLE IF NOT EXISTS scraped_price_history (
            id INTEGER PRIMARY KEY,
            product_url TEXT NOT NULL,
            price INTEGER,
            scraped_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scraped_price_history_url
            ON scraped_price_history (product_url);

        CREATE INDEX IF NOT EXISTS idx_scraped_price_history_scraped_at
            ON scraped_price_history (scraped_at);

        CREATE TRIGGER IF NOT EXISTS trg_scraped_items_price_insert
        AFTER INSERT ON scraped_items
        BEGIN
            INSERT INTO scraped_price_history (product_url, price, scraped_at)
            VALUES (new.product_url, new.price, new.scraped_at);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_scraped_items_price_update
        AFTER UPDATE OF price ON scraped_items
        WHEN new.price IS NOT old.price
        BEGIN
            INSERT INTO scraped_price_history (product_url, price, scraped_at)
            VALUES (new.product_url, new.price, new.scraped_at);
        END;

        CREATE TABLE IF NOT EXISTS scraped_price_history_key (
            id INTEGER PRIMARY KEY,
            product_key TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            price INTEGER,
            scraped_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scraped_price_history_key
            ON scraped_price_history_key (product_key, shop_id);

        CREATE INDEX IF NOT EXISTS idx_scraped_price_history_key_scraped_at
            ON scraped_price_history_key (scraped_at);

        CREATE TRIGGER IF NOT EXISTS trg_scraped_items_key_price_insert
        AFTER INSERT ON scraped_items
        WHEN new.product_key IS NOT NULL AND new.price IS NOT NULL
        BEGIN
            INSERT INTO scraped_price_history_key (product_key, shop_id, price, scraped_at)
            VALUES (new.product_key, new.shop_id, new.price, new.scraped_at);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_scraped_items_key_price_update
        AFTER UPDATE OF price ON scraped_items
        WHEN new.product_key IS NOT NULL AND new.price IS NOT old.price
        BEGIN
            INSERT INTO scraped_price_history_key (product_key, shop_id, price, scraped_at)
            VALUES (new.product_key, new.shop_id, new.price, new.scraped_at);
        END;
        """
    )

    # Table to store computed best offers per product_key
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS scraped_best_offers (
            id INTEGER PRIMARY KEY,
            product_key TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            shop_name TEXT,
            product_url TEXT,
            price INTEGER,
            scraped_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scraped_best_offers_key ON scraped_best_offers (product_key);
        CREATE INDEX IF NOT EXISTS idx_scraped_best_offers_shop ON scraped_best_offers (shop_id);
        """
    )

    cur.execute("PRAGMA table_info(scraped_items)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if "product_key" not in existing_cols:
        cur.execute("ALTER TABLE scraped_items ADD COLUMN product_key TEXT")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_scraped_items_product_key ON scraped_items (product_key)"
    )

    conn.commit()
    conn.close()


def insert_items(items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Inserts items using product_url as UNIQUE key.
    Returns (inserted_count, skipped_count).
    """
    conn = _get_conn()
    cur = conn.cursor()
    inserted = 0
    skipped = 0

    logger = logging.getLogger("storage.scraper_db")
    try:
        logger.debug("DB_PATH=%s exists=%s", DB_PATH, os.path.exists(DB_PATH))
    except Exception:
        pass

    for item in items:
        try:
            # Normalize certain shop price quirks before inserting.
            # Gezatek historically saved prices with two extra zeros (cents multiplied),
            # heuristically fix values > 1_000_000 that are divisible by 100.
            price_val = item.get("price")
            try:
                if item.get("shop_id") == "gezatek" and price_val is not None:
                    pv = int(price_val)
                    if pv > 1_000_000 and pv % 100 == 0:
                        price_val = pv // 100
            except Exception:
                price_val = item.get("price")

            cur.execute(
                """
                INSERT INTO scraped_items (
                    product_key, shop_id, shop_name, category, product_name, price, stock,
                    product_url, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_url) DO UPDATE SET
                    product_key = COALESCE(excluded.product_key, scraped_items.product_key),
                    shop_id = excluded.shop_id,
                    shop_name = excluded.shop_name,
                    category = excluded.category,
                    product_name = excluded.product_name,
                    price = excluded.price,
                    stock = excluded.stock,
                    scraped_at = excluded.scraped_at,
                    processed = 0,
                    processed_at = NULL,
                    summary = NULL
                WHERE excluded.price IS NOT scraped_items.price
                   OR excluded.stock IS NOT scraped_items.stock
                   OR (excluded.product_key IS NOT NULL AND scraped_items.product_key IS NULL)
                """,
                (
                    item.get("product_key"),
                    item["shop_id"],
                    item["shop_name"],
                    item.get("category"),
                    item["product_name"],
                    price_val,
                    1 if item.get("stock") else 0,
                    item["product_url"],
                    item["scraped_at"],
                ),
            )
            # Log the upsert for debugging; don't rely on rowcount across SQLite versions
            logger.debug(
                "Upserted product_url=%s product_key=%s price=%s",
                item.get("product_url"),
                item.get("product_key"),
                item.get("price"),
            )
            inserted += 1
        except Exception as e:
            logger.exception("Failed to insert item %s: %s", item.get("product_url"), e)
            skipped += 1
            continue

    try:
        conn.commit()
    except Exception as e:
        logger.exception("Failed to commit to DB: %s", e)
    finally:
        conn.close()

    return inserted, skipped


def get_price_history(product_url: str, limit: int = 50) -> List[sqlite3.Row]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT price, scraped_at
        FROM scraped_price_history
        WHERE product_url = ?
        ORDER BY scraped_at DESC
        LIMIT ?
        """,
        (product_url, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_min_price(product_url: str, days: int = 30) -> Optional[int]:
    conn = _get_conn()
    cur = conn.cursor()
    since = datetime.utcnow() - timedelta(days=days)
    cur.execute(
        """
        SELECT MIN(price) AS min_price
        FROM scraped_price_history
        WHERE product_url = ?
          AND scraped_at >= ?
        """,
        (product_url, since.isoformat()),
    )
    row = cur.fetchone()
    conn.close()
    if row and row["min_price"] is not None:
        return int(row["min_price"])
    return None


def is_candidate_promo(
    product_key: str,
    shop_id: str,
    current_price: int,
    days: int = 30,
    min_samples: int = 5,
    threshold_pct: float = 15.0,
) -> tuple[bool, str]:
    if not product_key or not shop_id or current_price is None:
        return False, "insufficient_data"

    conn = _get_conn()
    cur = conn.cursor()
    since = datetime.utcnow() - timedelta(days=days)
    cur.execute(
        """
        SELECT price
        FROM scraped_price_history_key
        WHERE product_key = ?
          AND shop_id = ?
          AND scraped_at >= ?
          AND price IS NOT NULL
        """,
        (product_key, shop_id, since.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()

    if len(rows) < min_samples:
        return False, "insufficient_data"

    prices = [int(r["price"]) for r in rows if r["price"] is not None]
    if not prices:
        return False, "insufficient_data"

    avg_price = sum(prices) / max(len(prices), 1)
    min_price = min(prices)

    threshold_value = avg_price * (1 - threshold_pct / 100.0)
    if current_price <= threshold_value:
        return True, "below_avg"

    if current_price <= (min_price * 0.98):
        return True, "near_min"

    return False, "no_promo"


def get_best_price_by_store(product_key: str, days: int = 7) -> Dict | None:
    if not product_key:
        return None

    conn = _get_conn()
    cur = conn.cursor()
    since = datetime.utcnow() - timedelta(days=days)
    cur.execute(
        """
        SELECT shop_id, shop_name, MIN(price) AS min_price
        FROM scraped_items
        WHERE product_key = ?
          AND stock = 1
          AND price IS NOT NULL
          AND scraped_at >= ?
        GROUP BY shop_id, shop_name
        """,
        (product_key, since.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()

    if len(rows) < 2:
        return None

    by_shop = {r["shop_id"]: int(r["min_price"]) for r in rows}
    sorted_rows = sorted(rows, key=lambda r: int(r["min_price"]))

    best = sorted_rows[0]
    second = sorted_rows[1]

    best_price = int(best["min_price"])
    second_price = int(second["min_price"])
    price_diff = max(second_price - best_price, 0)

    if second_price == 0:
        percent = 0.0
    else:
        percent = (price_diff / second_price) * 100.0

    if percent >= 10.0:
        deal_strength = "strong_deal"
    elif percent >= 3.0:
        deal_strength = "weak_deal"
    else:
        deal_strength = "no_real_difference"

    return {
        "best_shop_id": best["shop_id"],
        "best_shop_name": best["shop_name"],
        "best_price": best_price,
        "second_best_price": second_price,
        "price_diff": price_diff,
        "price_diff_percent": round(percent, 2),
        "deal_strength": deal_strength,
        "by_shop": by_shop,
    }


def get_unprocessed(limit: int = 100) -> List[sqlite3.Row]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM scraped_items
        WHERE processed = 0
        ORDER BY scraped_at ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def compute_and_store_best_offers(days: int = 7) -> int:
    """Compute the best (minimum) price per product_key across shops in the last `days`
    and store the results in `scraped_best_offers` table. Returns number of inserted rows.
    """
    conn = _get_conn()
    cur = conn.cursor()
    # Ensure table exists for older DBs
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS scraped_best_offers (
            id INTEGER PRIMARY KEY,
            product_key TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            shop_name TEXT,
            product_url TEXT,
            price INTEGER,
            scraped_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scraped_best_offers_key ON scraped_best_offers (product_key);
        CREATE INDEX IF NOT EXISTS idx_scraped_best_offers_shop ON scraped_best_offers (shop_id);
        """
    )
    since = datetime.utcnow() - timedelta(days=days)

    # Find product_keys with available prices in timeframe
    cur.execute(
        """
        SELECT product_key, MIN(price) AS min_price
        FROM scraped_items
        WHERE product_key IS NOT NULL
          AND product_key != ''
          AND price IS NOT NULL
          AND stock = 1
          AND scraped_at >= ?
        GROUP BY product_key
        """,
        (since.isoformat(),),
    )
    keys = cur.fetchall()

    inserted = 0
    recorded_at = datetime.utcnow().isoformat()

    # Clear previous best offers in the timeframe to avoid duplicates
    cur.execute("DELETE FROM scraped_best_offers WHERE scraped_at >= ?", (since.isoformat(),))

    for row in keys:
        pk = row["product_key"]
        # select single shop with lowest price for this product_key; tie-break by shop_id
        cur.execute(
            """
            SELECT shop_id, shop_name, product_url, price, scraped_at
            FROM scraped_items
            WHERE product_key = ?
              AND price IS NOT NULL
              AND stock = 1
              AND scraped_at >= ?
            ORDER BY price ASC, shop_id ASC
            LIMIT 1
            """,
            (pk, since.isoformat()),
        )
        w = cur.fetchone()
        if w:
            cur.execute(
                "INSERT INTO scraped_best_offers (product_key, shop_id, shop_name, product_url, price, scraped_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pk,
                    w["shop_id"],
                    w["shop_name"],
                    w["product_url"],
                    w["price"],
                    w["scraped_at"],
                    recorded_at,
                ),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted


def get_best_offers(product_key: Optional[str] = None, limit: int = 100) -> List[sqlite3.Row]:
    conn = _get_conn()
    cur = conn.cursor()
    if product_key:
        cur.execute(
            "SELECT * FROM scraped_best_offers WHERE product_key = ? ORDER BY recorded_at DESC LIMIT ?",
            (product_key, limit),
        )
    else:
        cur.execute(
            "SELECT * FROM scraped_best_offers ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_available_product_keys(prefix: Optional[str] = None, limit: int = 200) -> List[Dict[str, str]]:
    """Return a list of distinct product_key entries with a sample product name/url.

    Each item is a dict: {"product_key", "sample_product_name", "sample_product_url"}.
    If `prefix` is provided, filter keys containing the prefix.
    """
    conn = _get_conn()
    cur = conn.cursor()

    # Subquery returns last scraped row per product_key; join to obtain sample name/url
    if prefix:
        cur.execute(
            """
            SELECT s.product_key, s.product_name AS sample_product_name, s.product_url AS sample_product_url, s.shop_name AS sample_shop_name, s.price AS sample_price
            FROM scraped_items s
            JOIN (
                SELECT product_key, MAX(scraped_at) AS last_scraped
                FROM scraped_items
                WHERE product_key IS NOT NULL
                  AND product_key != ''
                  AND product_key LIKE ?
                GROUP BY product_key
            ) m ON s.product_key = m.product_key AND s.scraped_at = m.last_scraped
            ORDER BY s.product_key
            LIMIT ?
            """,
            (f"%{prefix}%", limit),
        )
    else:
                cur.execute(
                        """
                        SELECT s.product_key, s.product_name AS sample_product_name, s.product_url AS sample_product_url, s.shop_name AS sample_shop_name, s.price AS sample_price
                        FROM scraped_items s
                        JOIN (
                                SELECT product_key, MAX(scraped_at) AS last_scraped
                                FROM scraped_items
                                WHERE product_key IS NOT NULL
                                    AND product_key != ''
                                GROUP BY product_key
                        ) m ON s.product_key = m.product_key AND s.scraped_at = m.last_scraped
                        ORDER BY s.product_key
                        LIMIT ?
                        """,
                        (limit,),
                )

    rows = cur.fetchall()
    conn.close()
    results: List[Dict[str, str]] = []
    for r in rows:
        results.append(
            {
                "product_key": r[0],
                "sample_product_name": r[1] or "",
                "sample_product_url": r[2] or "",
                "sample_shop_name": r[3] or "",
                "sample_price": int(r[4]) if r[4] is not None else None,
            }
        )
    return results


def get_latest_best_offer_per_key(product_key: Optional[str] = None, limit: int = 100) -> List[sqlite3.Row]:
    """Return one best-offer row per product_key (the most recently recorded best offer).

    If `product_key` is provided, return that key's best offers (single or multiple if tied).
    Otherwise returns up to `limit` distinct product_keys with their latest best-offer row.
    """
    conn = _get_conn()
    cur = conn.cursor()

    if product_key:
        cur.execute(
            "SELECT * FROM scraped_best_offers WHERE product_key = ? ORDER BY recorded_at DESC LIMIT ?",
            (product_key, limit),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    # Subquery: get latest recorded_at per product_key
    cur.execute(
        """
        SELECT b.*
        FROM scraped_best_offers b
        JOIN (
            SELECT product_key, MAX(recorded_at) AS last_rec
            FROM scraped_best_offers
            GROUP BY product_key
        ) m ON b.product_key = m.product_key AND b.recorded_at = m.last_rec
        ORDER BY b.recorded_at DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_offers_by_key(product_key: str, limit: int = 100) -> List[sqlite3.Row]:
    """Return aggregated offers for a product_key: one row per shop with the minimum price,
    ordered by price ascending.
    """
    if not product_key:
        return []
    conn = _get_conn()
    cur = conn.cursor()
    since = None  # include all recent entries; callers may filter by timeframe if needed
    cur.execute(
        """
        SELECT shop_id, shop_name, MIN(price) AS min_price
        FROM scraped_items
        WHERE product_key = ?
          AND price IS NOT NULL
          AND stock = 1
        GROUP BY shop_id, shop_name
        ORDER BY min_price ASC
        LIMIT ?
        """,
        (product_key, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_processed(item_id: int, summary: str) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE scraped_items
        SET processed = 1,
            processed_at = ?,
            summary = ?
        WHERE id = ?
        """,
        (datetime.utcnow().isoformat(), summary, item_id),
    )
    conn.commit()
    conn.close()


def generate_summary(item: sqlite3.Row) -> str:
    """
    Simple deterministic summary (no external APIs).
    """
    price = item["price"]
    price_txt = f"${price}" if price is not None else "sin precio"
    stock_txt = "en stock" if item["stock"] else "sin stock"
    return f"{item['product_name']} ({item['shop_name']}): {price_txt}, {stock_txt}."


def process_unprocessed(limit: int = 100) -> int:
    """
    Fetches unprocessed items, generates a summary, marks them as processed.
    Returns count of processed items.
    """
    rows = get_unprocessed(limit=limit)
    for row in rows:
        summary = generate_summary(row)
        mark_processed(row["id"], summary)
    return len(rows)
