import asyncio
import logging
from typing import Any, Dict, List

from services.scraper_runner import run_all_scrapers
from storage.scraper_db import (
    generate_summary,
    get_min_price,
    get_price_history,
    get_unprocessed,
    init_db,
    insert_items,
    mark_processed,
)

# Normalization: use normalize_product to detect category and try specialized
# normalizers (gpu/cpu/ram) to build a stable `product_key`.
from normalizers.normalize_product import normalize as _normalize_title
try:
    from normalizers import gpu as _gpu_norm
    from normalizers import cpu as _cpu_norm
    from normalizers import ram as _ram_norm
except Exception:
    _gpu_norm = _cpu_norm = _ram_norm = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("runner")


async def _run() -> None:
    init_db()

    logger.info("Running scrapers...")
    results: Dict[str, List[Dict[str, Any]]] = await run_all_scrapers()

    all_items: List[Dict[str, Any]] = []
    for shop_id, items in results.items():
        logger.info("Scraped %d items from %s", len(items), shop_id)
        all_items.extend(items)

    # Generate product_key for each scraped item before inserting.
    for item in all_items:
        title = item.get("product_name") or ""
        try:
            normalized = _normalize_title({"title": title})
        except Exception:
            normalized = None

        category = (normalized.get("category") if normalized else None) or ""
        category = category.upper() if isinstance(category, str) else ""

        key = ""
        if category == "GPU" and _gpu_norm:
            key = _gpu_norm.build_product_key(title)
        elif category == "CPU" and _cpu_norm:
            key = _cpu_norm.build_product_key(title)
        elif category == "RAM" and _ram_norm:
            key = _ram_norm.build_product_key(title)
        else:
            # Fallback: try each normalizer until one yields a key
            for mod in (_gpu_norm, _cpu_norm, _ram_norm):
                if not mod:
                    continue
                try:
                    k = mod.build_product_key(title)
                except Exception:
                    k = ""
                if k:
                    key = k
                    break

        item["product_key"] = key or None

    inserted, skipped = insert_items(all_items)
    logger.info("Inserted %d items, skipped %d duplicates", inserted, skipped)

    rows = get_unprocessed(limit=500)
    for row in rows:
        history = get_price_history(row["product_url"], limit=5)
        min_price_30d = get_min_price(row["product_url"], days=30)
        summary = generate_summary(row)
        mark_processed(row["id"], summary)

        if min_price_30d is not None:
            logger.info(
                "Price history %s last=%s min30d=%s entries=%d",
                row["product_url"],
                row["price"],
                min_price_30d,
                len(history),
            )

    logger.info("Processed %d items", len(rows))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
