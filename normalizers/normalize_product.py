"""Normalization utilities: detect category (GPU/CPU), brand, model, VRAM.

Moved from `normalizer/normalize_product.py` into unified package.
"""

import re
from typing import Dict
from normalizers.cpu import build_product_key as build_cpu_key
from normalizers.gpu import build_product_key as build_gpu_key
from normalizers.aliases import apply_aliases
from normalizers.structured import parse_title, build_product_key_from_fields

GPU_KEYS = ["rtx", "gtx", "rx", "radeon", "gt"]
CPU_KEYS = ["ryzen", "intel", "core i", "athlon"]


def normalize(raw_item: Dict) -> Dict:
    title = (raw_item.get("title") or "").lower().strip()

    # Use structured parser to detect brand/line/model/variant
    parsed = parse_title(raw_item.get('title') or '')
    brand = parsed.get('brand')
    category = None
    if parsed.get('line') or any(k in title for k in GPU_KEYS):
        category = 'GPU'
    elif any(k in title for k in CPU_KEYS):
        category = 'CPU'

    # Use parser-detected model and variant
    model = parsed.get('model')
    vram = None
    vr = re.search(r"(\d+)\s?gb", title)
    if vr:
        vram = vr.group(1) + "GB"

    normalized = {
        "title": raw_item.get("title"),
        "price": raw_item.get("price"),
        "currency": raw_item.get("currency", "ARS"),
        "in_stock": raw_item.get("in_stock", True),
        "url": raw_item.get("url"),
        "source_id": raw_item.get("source_id"),
        "shop": raw_item.get("shop"),
        "fetched_at": raw_item.get("fetched_at"),
        "brand": brand,
        "line": parsed.get('line'),
        "series": parsed.get('series'),
        "model": model,
        "variant": parsed.get('variant'),
        "vram": vram,
        "category": category,
    }
    # Build a canonical product_key using more specific normalizers when possible.
    try:
        # Prefer structured product_key construction for stability
        fields = {
            'brand': normalized.get('brand'),
            'line': normalized.get('line'),
            'series': normalized.get('series'),
            'model': normalized.get('model'),
            'variant': normalized.get('variant'),
        }
        pk = build_product_key_from_fields(fields)
        if not pk:
            if category == "GPU":
                pk = build_gpu_key(raw_item.get("title") or "")
            else:
                pk = build_cpu_key(raw_item.get("title") or "")
        # Apply simple alias mappings (e.g. '5060' -> 'rx 5060')
        pk = apply_aliases(pk, raw_item.get("title") or "")
    except Exception:
        pk = ""
    normalized["product_key"] = pk
    return normalized


if __name__ == "__main__":
    print(normalize({"title": "ASUS ROG STRIX RTX 3060 12GB"}))
