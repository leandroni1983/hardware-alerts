from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

# Configurable mappings for extensibility
BRAND_ALIASES = {
    'nvidia': 'nvidia',
    'geforce': 'nvidia',
    'asus': None,  # vendor tokens ignored for brand-level
    'amd': 'amd',
    'radeon': 'amd',
    'intel': 'intel',
}

LINE_TOKENS = {
    'rtx': 'rtx',
    'gtx': 'gtx',
    'rx': 'rx',
    'radeon': 'rx',
    'arc': 'arc',
}

VARIANT_TOKENS = {'ti', 'super', 'xt', 'oc', 'lhr'}


def _normalize_ascii(text: str) -> str:
    if not text:
        return ''
    s = unicodedata.normalize('NFKD', text)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower()


MODEL_NUM_RE = re.compile(r"\b([ab]?\d{3,4}[a-z]{0,2})\b", re.IGNORECASE)


def parse_title(title: str) -> Dict[str, Optional[str]]:
    """Parse product title into structured fields.

    Returns dict with keys: brand, line, series, model, variant
    """
    t = _normalize_ascii(title or '')
    # replace separators
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    tokens = [tok for tok in t.split() if tok]

    brand = None
    for tok in tokens:
        if tok in ('nvidia', 'geforce'):
            brand = 'nvidia'
            break
        if tok in ('amd', 'radeon'):
            brand = 'amd'
            break
        if tok == 'intel':
            brand = 'intel'
            break

    line = None
    for tok in tokens:
        if tok in LINE_TOKENS:
            line = LINE_TOKENS[tok]
            break

    # model detection: capture tokens like 3060, 4060, a580, b580
    model = None
    for m in MODEL_NUM_RE.finditer(t):
        candidate = m.group(1).lower()
        # avoid year-like numbers (e.g., 2021) by requiring 3 or 4-digit patterns with optional letter prefix
        if re.fullmatch(r'[ab]?\d{3,4}[a-z]{0,2}', candidate):
            model = candidate
            break

    variant = None
    if model:
        # look for variant tokens after model in the raw string
        post = t.split(model, 1)[1] if model in t else ''
        for v in VARIANT_TOKENS:
            if re.search(r'\b' + re.escape(v) + r'\b', post):
                variant = v
                break
    else:
        # standalone variant tokens anywhere may indicate variant-only titles
        for v in VARIANT_TOKENS:
            if v in tokens:
                variant = v
                break

    # derive series for numeric models: 3060 -> 3000, 7600 -> 7000, 4060 -> 4000
    series = None
    if model:
        m_digits = re.search(r'\d{3,4}', model)
        if m_digits:
            try:
                val = int(m_digits.group(0))
                # series resolution: thousands granularity
                series = str((val // 1000) * 1000)
                # if series is 0 (e.g., models <1000) fallback to hundred grouping
                if series == '0':
                    series = str((val // 100) * 100)
            except Exception:
                series = None

    return {
        'brand': brand,
        'line': line,
        'series': series,
        'model': model,
        'variant': variant,
    }


def build_product_key_from_fields(fields: Dict[str, Optional[str]]) -> str:
    """Build canonical product_key like 'nvidia_rtx_4060_ti'"""
    parts = []
    brand = fields.get('brand')
    line = fields.get('line')
    model = fields.get('model')
    variant = fields.get('variant')
    if brand:
        parts.append(brand)
    if line:
        parts.append(line)
    if model:
        parts.append(model)
    if variant:
        parts.append(variant)
    return '_'.join(parts)
