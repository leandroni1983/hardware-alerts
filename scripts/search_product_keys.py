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
    # Structured search: parse query and match against structured DB fields when possible
    from normalizers.structured import parse_title as parse_struct

    q = query or ''
    q_struct = parse_struct(q)
    keys = dbm.get_available_product_keys(limit=2000)
    matches = []

    for k in keys:
        pk = k.get('product_key') or ''
        title = k.get('sample_product_name') or ''
        # structured fields from DB (may be None)
        k_brand = (k.get('brand') or '').lower() if k.get('brand') else None
        k_line = (k.get('line') or '').lower() if k.get('line') else None
        k_series = (k.get('series') or '') if k.get('series') else None
        k_model = (k.get('model') or '').lower() if k.get('model') else None
        k_variant = (k.get('variant') or '').lower() if k.get('variant') else None

        matched = False
        score = 0.0

        # Exact model match (e.g. 'a580' or '4060') must match model field to avoid false positives
        if q_struct.get('model'):
            if k_model and q_struct['model'].lower() == k_model:
                matched = True
                score = 1.0

        # Brand + line queries (e.g. 'intel arc')
        if not matched and q_struct.get('brand') and q_struct.get('line'):
            if k_brand == q_struct['brand'] and k_line == q_struct['line']:
                matched = True
                score = 0.95

        # Line + series queries (e.g. 'rtx 5000')
        if not matched and q_struct.get('line') and q_struct.get('series'):
            if k_line == q_struct['line'] and k_series == q_struct['series']:
                matched = True
                score = 0.95

        # Model-only queries: match model exactly
        if not matched and q_struct.get('model'):
            if k_model and k_model == q_struct['model']:
                matched = True
                score = 0.9

        # Fallback: use canonical similarity against stored key and sample title
        if not matched:
            combined = f"{pk} {title}"
            score = matcher.similarity(query, combined)
            if score >= threshold or matcher.canonicalize_name(q) in matcher.canonicalize_name(title) or matcher.canonicalize_name(q) in matcher.canonicalize_name(pk):
                matched = True

        if matched:
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
