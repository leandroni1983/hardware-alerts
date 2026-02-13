#!/usr/bin/env python3
"""Sugerir merges de `product_key` similares.

Salida: lista de pares (key_a, key_b, score) en JSON para revisión.
"""
from __future__ import annotations
import json
import argparse

import storage.scraper_db as dbm
from normalizers import matcher


def collect_keys(limit: int = 1000):
    keys = dbm.get_available_product_keys(limit=limit)
    return [k['product_key'] for k in keys if k.get('product_key')]


def suggest_pairs(keys, threshold: float = 0.78):
    n = len(keys)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a = keys[i]
            b = keys[j]
            score = matcher.similarity(a, b)
            if score >= threshold:
                pairs.append((a, b, score))
    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--threshold", type=float, default=0.78)
    p.add_argument("--out", type=str, default="suggested_key_merges.json")
    args = p.parse_args()

    keys = collect_keys(limit=args.limit)
    pairs = suggest_pairs(keys, threshold=args.threshold)
    print(f"Found {len(pairs)} candidate pairs (threshold={args.threshold}).")
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump([{'a': a, 'b': b, 'score': s} for a, b, s in pairs], f, ensure_ascii=False, indent=2)
    print('Wrote', args.out)


if __name__ == '__main__':
    main()
