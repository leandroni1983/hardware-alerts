import re
import unicodedata
from difflib import SequenceMatcher
from typing import List


# Keep variant tokens (ti, oc, super, xt, lhr) as significant tokens so they
# are not stripped during canonicalization. This prevents grouping different
# SKUs (e.g. "5060 TI" vs "5060").
STOPWORDS = {
    'con', 'y', 'de', 'la', 'el', 'para', 'edition', 'series', 'gpu', 'ddr', 'gddr',
    'gb', 'pc', 'graphics', 'video', 'venta', 'nuevo', 'gaming', 'pro', 'tienda'
}

# Variant tokens that change product semantics and should be preserved and
# compared strictly (if both sides have a variant and they differ, treat as different products).
VARIANT_TOKENS = {'ti', 'oc', 'super', 'xt', 'lhr'}


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", ' ', s).strip()


def canonicalize_name(text: str) -> str:
    if not text:
        return ''
    # remove accents
    s = unicodedata.normalize('NFKD', text)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # replace common separators
    s = s.replace('-', ' ').replace('/', ' ').replace('_', ' ')
    # remove punctuation
    s = re.sub(r"[^a-z0-9\s]", ' ', s)
    s = _normalize_whitespace(s)
    # remove stopwords but preserve variant tokens
    tokens = [t for t in s.split() if t not in STOPWORDS or t in VARIANT_TOKENS]
    # normalize tokens: move numeric tokens to end, keep model numbers
    nums = [t for t in tokens if re.fullmatch(r"\d{2,}|\d+[a-z]*", t)]
    others = [t for t in tokens if t not in nums]
    canon = ' '.join(others + nums)
    return canon


def jaccard(a_tokens: List[str], b_tokens: List[str]) -> float:
    sa = set(a_tokens)
    sb = set(b_tokens)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_c = canonicalize_name(a)
    b_c = canonicalize_name(b)
    # If both have explicit variant tokens and they differ, return low similarity
    a_vars = [t for t in a_c.split() if t in VARIANT_TOKENS]
    b_vars = [t for t in b_c.split() if t in VARIANT_TOKENS]
    if a_vars and b_vars and set(a_vars) != set(b_vars):
        return 0.0
    a_toks = a_c.split()
    b_toks = b_c.split()
    j = jaccard(a_toks, b_toks)
    # sequence matcher ratio on joined canonical strings
    ratio = SequenceMatcher(None, a_c, b_c).ratio()
    # weighted combination
    return 0.6 * j + 0.4 * ratio


def are_same_product(a: str, b: str, threshold: float = 0.78) -> bool:
    return similarity(a, b) >= threshold
