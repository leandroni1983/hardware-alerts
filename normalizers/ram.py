"""
RAM product key normalizer (moved from storage.normalizers.ram).
"""

from __future__ import annotations

import re
from typing import List, Set

from normalizers.storage import clean_text, extract_tokens, to_ascii_lower

STOPWORDS: Set[str] = {"memoria", "ram", "ddr4", "ddr5", "kit", "para", "con"}

VRAM_PATTERN = re.compile(r"\b(\d{1,2})\s*gb\b", re.IGNORECASE)


def build_product_key(product_name: str) -> str:
    if not product_name:
        return ""

    text = to_ascii_lower(product_name)
    text = clean_text(text)
    tokens = extract_tokens(text, STOPWORDS)

    # try to extract brand/model tokens
    parts: List[str] = []
    for t in tokens:
        if t.isalpha() and len(t) > 1:
            parts.append(t)

    match = VRAM_PATTERN.search(text)
    if match:
        parts.append(f"{match.group(1)}gb")

    return "_".join(parts)
