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
# model token: 2-5 digits, optional 0-3 letter suffix (e.g. 12400f, 245kf)
MODEL_NUM_RE = re.compile(r"^\d{2,5}[a-z0-9]{0,4}$")
# tokens like g7400 or celeron style: optional single letter then 2-5 digits and optional alnum suffix
ALPHA_LEAD_MODEL_RE = re.compile(r"^[a-z]?\d{2,5}[a-z0-9]{0,4}$")


def build_product_key(product_name: str) -> str:
    if not product_name:
        return ""

    text = to_ascii_lower(product_name)
    text = clean_text(text)
    tokens = extract_tokens(text, STOPWORDS)

    brand = next((t for t in tokens if t in BRANDS), None)

    model = None

    # 1) Intel family like `i5 12400f`
    for i, t in enumerate(tokens):
        m = INT_FAMILY_RE.match(t)
        if m:
            family = m.group(1)
            # next token often contains the numeric model
            if i + 1 < len(tokens) and MODEL_NUM_RE.match(tokens[i + 1]):
                model = f"i{family} {tokens[i+1]}"
                break

    # 1b) Intel Core Ultra series: look for 'ultra' + family digit + model (e.g. 'ultra 5 245kf')
    if not model:
        for i, t in enumerate(tokens):
            if t == "ultra":
                # family digit may be the next token
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    family = tokens[i + 1]
                    # model token after family
                    if i + 2 < len(tokens) and ALPHA_LEAD_MODEL_RE.match(tokens[i + 2]):
                        model = f"ultra{family} {tokens[i+2]}"
                        break
                # or model could follow directly
                if i + 1 < len(tokens) and ALPHA_LEAD_MODEL_RE.match(tokens[i + 1]):
                    model = f"ultra {tokens[i+1]}"
                    break

    if not model:
        # 2) AMD Ryzen: look for `ryzen` then family + model (e.g. 'ryzen 5 5600x')
        for i, t in enumerate(tokens):
            if t == "ryzen":
                # try ryzen + family + model
                if i + 2 < len(tokens) and tokens[i + 1].isdigit() and MODEL_NUM_RE.match(tokens[i + 2]):
                    model = f"ryzen {tokens[i+1]} {tokens[i+2]}"
                    break
                # try ryzen + model (e.g. 'ryzen 5600')
                if i + 1 < len(tokens) and MODEL_NUM_RE.match(tokens[i + 1]):
                    model = f"ryzen {tokens[i+1]}"
                    break

    if not model:
        # 3) Pentium/Celeron or generic: look for tokens like 'g7400', 'g6400' or numeric-like model
        for i, t in enumerate(tokens):
            if t in ("pentium", "pentiumgold", "pentium_g", "pentium_gold") and i + 1 < len(tokens):
                if ALPHA_LEAD_MODEL_RE.match(tokens[i + 1]):
                    model = f"pentium {tokens[i+1]}"
                    break
            if t == "celeron" and i + 1 < len(tokens):
                if ALPHA_LEAD_MODEL_RE.match(tokens[i + 1]):
                    model = f"celeron {tokens[i+1]}"
                    break
        # fallback: prefer tokens that look like real model numbers (>=3 digits or have alpha suffix),
        # to avoid picking small numbers like core counts (e.g. '16').
    if not model:
        prefer = None
        for t in tokens:
            if ALPHA_LEAD_MODEL_RE.match(t):
                # has letter prefix like g7400 or suffix like x3d
                prefer = t
                break
            if MODEL_NUM_RE.match(t) and len(re.findall(r"\d+", t)[0]) >= 3:
                prefer = t
                break
        if prefer:
            model = prefer
        else:
            for t in tokens:
                if ALPHA_LEAD_MODEL_RE.match(t) or MODEL_NUM_RE.match(t):
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

    # Use space as separator as per user preference (e.g. 'intel i5 12400')
    return " ".join(parts)
