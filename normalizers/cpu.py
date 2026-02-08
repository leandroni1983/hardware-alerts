"""CPU product key normalizer.

Produces a stable key that includes brand and model/family when possible,
e.g. `intel_i5_12400`, `amd_ryzen_5_5600x`, `intel_4460`.
"""

from __future__ import annotations

import re
from typing import List, Set

from normalizers.storage import clean_text, extract_tokens, to_ascii_lower

STOPWORDS: Set[str] = {"micro", "procesador", "cpu", "para", "y", "con"}

BRANDS: Set[str] = {"intel", "amd"}

# token patterns after `clean_text` (which leaves only a-z0-9 and spaces)
INT_FAMILY_RE = re.compile(r"^i(\d)$")
MODEL_NUM_RE = re.compile(r"^\d{3,5}[a-z]?$")


def build_product_key(product_name: str) -> str:
    if not product_name:
        return ""

    text = to_ascii_lower(product_name)
    text = clean_text(text)
    tokens = extract_tokens(text, STOPWORDS)

    brand = next((t for t in tokens if t in BRANDS), None)

    model = None

    # 1) Intel pattern: look for `i5` followed by numeric token (e.g. 'i5', '12400f')
    for i, t in enumerate(tokens):
        m = INT_FAMILY_RE.match(t)
        if m:
            family = m.group(1)
            if i + 1 < len(tokens) and MODEL_NUM_RE.match(tokens[i + 1]):
                model = f"i{family}_{tokens[i+1]}"
                break

    if not model:
        # 2) AMD Ryzen: look for `ryzen` then family + model (e.g. 'ryzen 5 5600x')
        for i, t in enumerate(tokens):
            if t == "ryzen":
                # try ryzen + family + model
                if i + 2 < len(tokens) and tokens[i + 1].isdigit() and MODEL_NUM_RE.match(tokens[i + 2]):
                    model = f"ryzen_{tokens[i+1]}_{tokens[i+2]}"
                    break
                # try ryzen + model (e.g. 'ryzen 5600')
                if i + 1 < len(tokens) and MODEL_NUM_RE.match(tokens[i + 1]):
                    model = f"ryzen_{tokens[i+1]}"
                    break

    if not model:
        # 3) Generic: first numeric-like token (3-5 digits) is a good candidate
        for t in tokens:
            if MODEL_NUM_RE.match(t):
                model = t
                break

    # fallback: if no numeric model, try family token like 'i5'
    if not model:
        for t in tokens:
            if INT_FAMILY_RE.match(t):
                model = t
                break

    parts: List[str] = []
    if brand:
        parts.append(brand)
    if model:
        parts.append(model)

    return "_".join(parts)
