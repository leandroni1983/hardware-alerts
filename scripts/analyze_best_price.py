#!/usr/bin/env python3
"""Small CLI to analyze best price for a product.

Usage:
  python scripts/analyze_best_price.py --key <product_key>
  python scripts/analyze_best_price.py --name "ASUS RTX 3060"

If given a name, the script will try to build a `product_key` using available normalizers.
"""
import argparse
import sys
from typing import Optional

from storage.scraper_db import get_best_price_by_store

# Try new unified normalizers package first, fallback to older locations
try:
    from normalizers import gpu as _gpu, cpu as _cpu, ram as _ram
    from normalizers.normalize_product import normalize as _normalize_title
except Exception:
    try:
        from storage.normalizers import gpu as _gpu, cpu as _cpu, ram as _ram
        from normalizer.normalize_product import normalize as _normalize_title
    except Exception:
        _gpu = _cpu = _ram = None
        _normalize_title = None


def build_key_from_name(name: str) -> Optional[str]:
    if not name:
        return None
    if _normalize_title:
        try:
            norm = _normalize_title({"title": name})
            category = (norm.get("category") or "").upper()
        except Exception:
            category = ""
    else:
        category = ""

    # pick normalizer by category, fallback to trying all
    if category == "GPU" and _gpu:
        return _gpu.build_product_key(name)
    if category == "CPU" and _cpu:
        return _cpu.build_product_key(name)
    if category == "RAM" and _ram:
        return _ram.build_product_key(name)

    for mod in (_gpu, _cpu, _ram):
        if not mod:
            continue
        try:
            k = mod.build_product_key(name)
        except Exception:
            k = ""
        if k:
            return k
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--key", help="product_key to analyze")
    g.add_argument("--name", help="product name to normalize and analyze")
    p.add_argument("--days", type=int, default=7, help="lookback days for best price")
    args = p.parse_args()

    product_key = args.key
    if not product_key and args.name:
        product_key = build_key_from_name(args.name)
        if not product_key:
            print("Could not build a product_key from the provided name.")
            return 2

    result = get_best_price_by_store(product_key, days=args.days)
    if not result:
        print("No sufficient data to determine best price for key:", product_key)
        return 1

    print("Best price analysis for:", product_key)
    print("Best shop:", result["best_shop_id"], "-", result["best_shop_name"]) 
    print("Best price:", result["best_price"]) 
    print("Second best price:", result["second_best_price"]) 
    print("Price diff:", result["price_diff"], "(", result["price_diff_percent"], "% )")
    print("Deal strength:", result["deal_strength"])
    print("By shop:")
    for sid, pr in result["by_shop"].items():
        print("  ", sid, ":", pr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
