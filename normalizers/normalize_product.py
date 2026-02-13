"""Normalization utilities: detect category (GPU/CPU), brand, model, VRAM.

Moved from `normalizer/normalize_product.py` into unified package.
"""

import re
from typing import Dict
from normalizers.cpu import build_product_key as build_cpu_key
from normalizers.gpu import build_product_key as build_gpu_key
from normalizers.aliases import apply_aliases

GPU_KEYS = ["rtx", "gtx", "rx", "radeon", "gt"]
CPU_KEYS = ["ryzen", "intel", "core i", "athlon"]


def normalize(raw_item: Dict) -> Dict:
    title = (raw_item.get("title") or "").lower().strip()

    brand = None
    if "amd" in title or "radeon" in title or any(k in title for k in ["ryzen"]):
        brand = "AMD"
    elif "nvidia" in title or any(k in title for k in ["rtx", "gtx"]):
        brand = "NVIDIA"
    elif "intel" in title or "core" in title:
        brand = "INTEL"

    category = None
    if any(k in title for k in GPU_KEYS):
        category = "GPU"
    elif any(k in title for k in CPU_KEYS):
        category = "CPU"
    else:
        if "tarjeta" in title or "video" in title or "gpu" in title:
            category = "GPU"
        elif "procesador" in title or "cpu" in title:
            category = "CPU"

    model = None
    vram = None

    m = re.search(r"(rtx|gtx|rx)\s*\d{3,4}\w*", title)
    if m:
        model = m.group(0).upper()
        vr = re.search(r"(\d+)\s?gb", title)
        if vr:
            vram = vr.group(1) + "GB"

    if not model:
        m2 = re.search(r"(ryzen\s?\d\s?\d{3,4}|ryzen\s?\d+|core\s*i\s?\d)", title)
        if m2:
            model = m2.group(0).upper()

    # Intel-specific model detection: Pentium/Celeron/G-series (e.g. G4560, G5420, G6900)
    if not model:
        m3 = re.search(r"\b(pentium\s+gold\s+g\d{3,4}|pentium\s+g\d{3,4}|celeron\s+g\d{3,4}|\bg\d{3,4})\b", title)
        if m3:
            model = m3.group(0).upper().replace('\\s+', ' ')

    if not model:
        # Fallback: prefer first token that contains a digit (likely model number),
        # otherwise use the first token.
        tokens = re.findall(r"[A-Za-z0-9\-\+]+", raw_item.get("title", ""))
        if tokens:
            token_with_digit = next((t for t in tokens if any(c.isdigit() for c in t)), None)
            model = (token_with_digit or tokens[0]).upper()

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
        "model": model,
        "vram": vram,
        "category": category,
    }
    # Build a canonical product_key using more specific normalizers when possible.
    try:
        if category == "GPU":
            pk = build_gpu_key(raw_item.get("title") or "")
        else:
            # default to CPU normalizer (covers many cases including intel/amd)
            pk = build_cpu_key(raw_item.get("title") or "")
        # Apply simple alias mappings (e.g. '5060' -> 'rx 5060')
        pk = apply_aliases(pk, raw_item.get("title") or "")
    except Exception:
        pk = ""
    normalized["product_key"] = pk
    return normalized


if __name__ == "__main__":
    print(normalize({"title": "ASUS ROG STRIX RTX 3060 12GB"}))
