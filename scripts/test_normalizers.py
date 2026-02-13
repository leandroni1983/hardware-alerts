#!/usr/bin/env python3
"""Quick tests for normalization functions.

Run: python scripts/test_normalizers.py
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path when running this script directly
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from normalizers import normalize_product
from normalizers.cpu import build_product_key as cpu_key
from normalizers.gpu import build_product_key as gpu_key


cases = [
    ("Intel i5 12400 boxed", "intel i5 12400"),
    ("Intel i5-12400F", "intel i5 12400f"),
    ("AMD Ryzen 5 5600X", "amd ryzen 5 5600x"),
    ("ASUS ROG STRIX RTX 3060 12GB", None),
    ("Gigabyte RTX 3060 12GB Gaming OC", None),
]

print('Testing CPU normalizer:')
for title, expect in cases:
    k = cpu_key(title)
    print(title, '->', k)

print('\nTesting GPU normalizer:')
for title, expect in cases:
    k = gpu_key(title)
    print(title, '->', k)

print('\nTesting normalize_product.normalize:')
for title, expect in cases:
    n = normalize_product.normalize({'title': title})
    print(title, '=> product_key=', n.get('product_key'))

print('\nDone')
