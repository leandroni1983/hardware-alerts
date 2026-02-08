from fastapi import APIRouter, HTTPException
from services.scraper_runner import (
    get_supported_shops,
    validate_shop_id,
    run_scraper,
    run_all_scrapers,
)
from storage.scraper_db import (
    compute_and_store_best_offers,
    get_best_offers,
    get_available_product_keys,
    get_latest_best_offer_per_key,
    get_offers_by_key,
)

router = APIRouter()

@router.get("/shops")
async def list_shops():
    return {"shops": get_supported_shops()}

@router.get("/scrape/{shop_id}")
async def scrape_shop(shop_id: str):
    if not validate_shop_id(shop_id):
        raise HTTPException(status_code=404, detail="Shop not supported")
    try:
        items = await run_scraper(shop_id)
        return {
            "shop": shop_id,
            "count": len(items),
            "items": items,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scrape/all")
async def scrape_all():
    try:
        results = await run_all_scrapers()
        return {
            "results": [
                {"shop": shop, "count": len(items), "items": items}
                for shop, items in results.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/best-offers")
async def best_offers(
    product_key: str | None = None,
    days: int = 7,
    recompute: bool = False,
    limit: int = 100,
    unique: bool = False,
):
    """Return best offers stored in `scraped_best_offers`.

    Query params:
      - `product_key` (optional): filter by product_key
      - `days` (default 7): lookback window when recomputing
      - `recompute` (bool): if true, recompute best offers before returning
      - `limit` (int): max rows to return
    """
    try:
        recomputed = 0
        if recompute:
            recomputed = compute_and_store_best_offers(days=days)
        # If a product_key is provided, return all shop offers for that key ordered by price (asc).
        # If no product_key, behave as previously (list recent best_offers rows).
        if product_key:
            # return aggregated offers per shop (min price) ordered asc
            rows = get_offers_by_key(product_key=product_key, limit=limit)
            # convert aggregated rows to dicts with consistent keys
            items = [
                {"shop_id": r["shop_id"], "shop_name": r["shop_name"], "price": int(r["min_price"])}
                for r in rows
            ]
            return {"count": len(items), "recomputed": recompute, "recomputed_rows": 0, "offers": items}
        else:
            if unique:
                rows = get_latest_best_offer_per_key(product_key=product_key, limit=limit)
            else:
                rows = get_best_offers(product_key=product_key, limit=limit)
            items = [dict(r) for r in rows]
            return {"count": len(items), "recomputed": recompute, "recomputed_rows": recomputed, "best_offers": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-offers/keys")
async def best_offer_keys(q: str | None = None, limit: int = 200):
    """Return a list of available `product_key` values with a sample product name/url.

    Query params:
      - `q`: optional substring filter
      - `limit`: max keys to return
    """
    try:
        items = get_available_product_keys(prefix=q, limit=limit)
        return {"count": len(items), "product_keys": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-offers/best")
async def best_offer_single(product_key: str | None = None):
    """Return the single best offer (lowest price) for the given `product_key`.

    Query params:
      - `product_key`: required, the normalized key to search for
    """
    if not product_key:
        raise HTTPException(status_code=400, detail="product_key required")
    try:
        rows = get_offers_by_key(product_key=product_key, limit=1)
        if not rows:
            raise HTTPException(status_code=404, detail="No offers found for product_key")
        r = rows[0]
        return {
            "product_key": product_key,
            "shop_id": r["shop_id"],
            "shop_name": r["shop_name"],
            "price": int(r["min_price"]),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
