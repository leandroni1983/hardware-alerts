#!/usr/bin/env python3
"""Buscar product_keys y productos por término (usa canonicalizer para coincidencias)."""
from __future__ import annotations
import sys
from typing import List

try:
    import storage.scraper_db as dbm
    from normalizers import matcher
except Exception as e:
    print('Import error:', e)
    raise


def search(query: str, threshold: float = 0.45):
    qcanon = matcher.canonicalize_name(query)
    keys = dbm.get_available_product_keys(limit=2000)
    matches = []
    for k in keys:
        pk = k.get('product_key') or ''
        title = k.get('sample_product_name') or ''
        combined = f"{pk} {title}"
        score = matcher.similarity(query, combined)
        if score >= threshold or qcanon in matcher.canonicalize_name(title) or qcanon in matcher.canonicalize_name(pk):
            matches.append((score, pk, title, k.get('sample_product_url'), k.get('sample_shop_name'), k.get('sample_price')))
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/search_product_keys.py "5060 16gb"')
        raise SystemExit(1)
    query = sys.argv[1]
    results = search(query)
    if not results:
        print('No matches')
        return
    for score, pk, title, url, shop, price in results[:50]:
        print(f'score={score:.2f} | key={pk} | price={price} | shop={shop}\n  {title}\n  {url}\n')


if __name__ == '__main__':
    main()
