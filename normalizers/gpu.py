"""
GPU product key normalizer (moved from storage.normalizers.gpu).
"""

from __future__ import annotations

import re
from typing import List, Set

from normalizers.storage import (
    clean_text,
    extract_tokens,
    to_ascii_lower,
    unique_sorted,
)

STOPWORDS: Set[str] = {
    "placa",
    "tarjeta",
    "video",
    "grafica",
    "edition",
    "pack",
    "con",
    "y",
    "para",
    "gddr6",
    "gddr5",
    "gddr",
}

BRANDS: Set[str] = {
    "asus",
    "gigabyte",
    "msi",
    "zotac",
    "evga",
    "palit",
    "asrock",
    "sapphire",
    "xfx",
    "powercolor",
    "inno3d",
    "pny",
}

FAMILIES: Set[str] = {
    "rtx",
    "gtx",
    "radeon",
    "rx",
    "arc",
}

VARIANTS: Set[str] = {
    "dual",
    "gaming",
    "oc",
    "tuf",
    "ventus",
    "eagle",
    "windforce",
    "phoenix",
    "strix",
    "pulse",
    "nitro",
    "ghost",
    "mini",
    "pro",
}

VRAM_PATTERN = re.compile(r"\b(\d{1,2})\s*gb\b", re.IGNORECASE)
MODEL_PATTERN = re.compile(r"\b\d{3,4}[a-z]{0,6}\b", re.IGNORECASE)


def _extract_family(tokens: List[str]) -> str | None:
    for t in tokens:
        if t in FAMILIES:
            return t
    return None


def _extract_model(tokens: List[str]) -> str | None:
    for t in tokens:
        if MODEL_PATTERN.fullmatch(t):
            return t
    return None


def _extract_vram(text: str) -> str | None:
    match = VRAM_PATTERN.search(text)
    if not match:
        return None
    return f"{match.group(1)}gb"


def build_product_key(product_name: str) -> str:
    if not product_name:
        return ""

    text = to_ascii_lower(product_name)
    text = clean_text(text)
    tokens = extract_tokens(text, STOPWORDS)

    brand = next((t for t in tokens if t in BRANDS), None)
    family = _extract_family(tokens)
    model = _extract_model(tokens)
    vram = _extract_vram(text)
    variants = [t for t in tokens if t in VARIANTS]

    parts: List[str] = []
    if brand:
        parts.append(brand)
    if family:
        parts.append(family)
    if model:
        parts.append(model)
    parts.extend(unique_sorted(variants))
    if vram:
        parts.append(vram)

    return "_".join(parts)
