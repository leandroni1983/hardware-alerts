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
from normalizers import matcher

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


@router.get("/search")
async def search_products(q: str, limit: int = 50, threshold: float = 0.2):
    """Search product keys and sample names by free-text query.

    Query params:
      - `q`: query string (required)
      - `limit`: maximum results to return
      - `threshold`: similarity threshold (0..1) to include a match
    """
    if not q:
        raise HTTPException(status_code=400, detail="query parameter 'q' is required")
    try:
        items = get_available_product_keys(limit=2000)
        results = []
        qcanon = matcher.canonicalize_name(q)
        qtokens = [t for t in qcanon.split() if t]
        numeric_tokens = [t for t in qtokens if any(c.isdigit() for c in t)]

        for it in items:
            pk = it.get("product_key") or ""
            title = it.get("sample_product_name") or ""
            combined = f"{pk} {title}"
            titlecanon = matcher.canonicalize_name(title)
            pkcanon = matcher.canonicalize_name(pk)

            # If the query contains numeric tokens (models, memory), require those
            # to appear in the canonical title or key to avoid false matches.
            if numeric_tokens:
                ok = False
                for nt in numeric_tokens:
                    if nt in titlecanon or nt in pkcanon:
                        ok = True
                        break
                if not ok:
                    continue

            sim = matcher.similarity(q, combined)

            # token match ratio: how many query tokens appear in title/key
            if qtokens:
                matched = sum(1 for t in qtokens if (t in titlecanon or t in pkcanon))
                token_ratio = matched / len(qtokens)
            else:
                token_ratio = 0.0

            # Combined score: weighted similarity + token overlap boost
            score = 0.7 * sim + 0.3 * token_ratio

            if score >= threshold or qcanon in titlecanon or qcanon in pkcanon:
                results.append({
                    "score": round(score, 3),
                    "product_key": pk,
                    "sample_product_name": title,
                    "sample_product_url": it.get("sample_product_url"),
                    "sample_shop_name": it.get("sample_shop_name"),
                    "sample_price": it.get("sample_price"),
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return {"count": len(results[:limit]), "results": results[:limit]}
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



@router.get("/best-offers/best")
async def best_offer_top3(product_key: str | None = None, q: str | None = None, limit: int = 3, threshold: float = 0.2):
    """Return the top cheapest offers for the given `product_key`.

    Query params:
      - `product_key`: required, the normalized key to search for
      - `limit`: number of cheapest offers to return (default 3)
    """
    # allow searching by free-text `q` as an alternative to passing a product_key
    chosen_sample = None
    try:
        if not product_key and q:
            # find candidate keys using same logic as /search
            items = get_available_product_keys(limit=2000)
            qcanon = matcher.canonicalize_name(q)
            qtokens = [t for t in qcanon.split() if t]
            numeric_tokens = [t for t in qtokens if any(c.isdigit() for c in t)]
            candidates = []
            for it in items:
                pk = it.get("product_key") or ""
                title = it.get("sample_product_name") or ""
                titlecanon = matcher.canonicalize_name(title)
                pkcanon = matcher.canonicalize_name(pk)

                if numeric_tokens:
                    ok = False
                    for nt in numeric_tokens:
                        if nt in titlecanon or nt in pkcanon:
                            ok = True
                            break
                    if not ok:
                        continue

                sim = matcher.similarity(q, f"{pk} {title}")
                matched = sum(1 for t in qtokens if (t in titlecanon or t in pkcanon)) if qtokens else 0
                token_ratio = matched / len(qtokens) if qtokens else 0.0
                score = 0.7 * sim + 0.3 * token_ratio
                if score >= threshold or qcanon in titlecanon or qcanon in pkcanon:
                    candidates.append((score, pk, it))
            candidates.sort(key=lambda x: x[0], reverse=True)
            if not candidates:
                raise HTTPException(status_code=404, detail="No product_key matches query")
            # pick top candidate
            _, product_key, chosen_sample = candidates[0]

        if not product_key:
            raise HTTPException(status_code=400, detail="product_key required")

        rows = get_offers_by_key(product_key=product_key, limit=limit)
        if not rows:
            raise HTTPException(status_code=404, detail="No offers found for product_key")
        items = []
        for r in rows:
            items.append({
                "shop_id": r["shop_id"],
                "shop_name": r["shop_name"],
                "price": int(r["min_price"]),
            })
        resp = {"product_key": product_key, "count": len(items), "offers": items}
        if chosen_sample:
            resp.update({
                "sample_product_name": chosen_sample.get("sample_product_name"),
                "sample_product_url": chosen_sample.get("sample_product_url"),
                "sample_shop_name": chosen_sample.get("sample_shop_name"),
                "sample_price": chosen_sample.get("sample_price"),
            })
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-offers/closest-per-shop")
async def closest_per_shop(q: str, limit_keys: int = 2000, threshold: float = 0.2):
    """For a free-text query `q`, return the single best-matching product per shop.

    This finds product_key candidates similar to `q`, then for each shop that
    sells those keys selects the product with highest match score (tie-breaker: lower price).
    """
    if not q:
        raise HTTPException(status_code=400, detail="query parameter 'q' is required")
    try:
        items = get_available_product_keys(limit=limit_keys)
        qcanon = matcher.canonicalize_name(q)
        qtokens = [t for t in qcanon.split() if t]
        numeric_tokens = [t for t in qtokens if any(c.isdigit() for c in t)]

        # build candidate product_key list with scores
        candidates: list[tuple[float, str, dict]] = []
        for it in items:
            pk = it.get("product_key") or ""
            title = it.get("sample_product_name") or ""
            titlecanon = matcher.canonicalize_name(title)
            pkcanon = matcher.canonicalize_name(pk)

            if numeric_tokens:
                ok = False
                for nt in numeric_tokens:
                    if nt in titlecanon or nt in pkcanon:
                        ok = True
                        break
                if not ok:
                    continue

            sim = matcher.similarity(q, f"{pk} {title}")
            matched = sum(1 for t in qtokens if (t in titlecanon or t in pkcanon)) if qtokens else 0
            token_ratio = matched / len(qtokens) if qtokens else 0.0
            score = 0.7 * sim + 0.3 * token_ratio
            if score >= threshold or qcanon in titlecanon or qcanon in pkcanon:
                candidates.append((score, pk, it))

        if not candidates:
            raise HTTPException(status_code=404, detail="No matching products found")

        # For each candidate product_key, get offers by shop and pick best per shop
        best_by_shop: dict = {}
        for score, pk, it in candidates:
            offers = get_offers_by_key(product_key=pk, limit=1000)
            for r in offers:
                shop_id = r["shop_id"]
                shop_name = r["shop_name"]
                price = int(r["min_price"]) if r["min_price"] is not None else None
                existing = best_by_shop.get(shop_id)
                replace = False
                if not existing:
                    replace = True
                else:
                    # prefer higher score; if scores equal prefer lower price
                    if score > existing["score"]:
                        replace = True
                    elif score == existing["score"] and price is not None and (existing.get("price") is None or price < existing.get("price")):
                        replace = True

                if replace:
                    best_by_shop[shop_id] = {
                        "shop_id": shop_id,
                        "shop_name": shop_name,
                        "product_key": pk,
                        "sample_product_name": it.get("sample_product_name"),
                        "sample_product_url": it.get("sample_product_url"),
                        "price": price,
                        "score": round(score, 3),
                    }

        results = list(best_by_shop.values())
        # sort shops by price where available, otherwise by shop_name
        results.sort(key=lambda x: (x["price"] if x["price"] is not None else 999999999, x.get("shop_name") or ""))

        return {"query": q, "count": len(results), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
