"""
Shared normalization helpers for product name parsing (moved from storage.normalizers.storage).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Set


def to_ascii_lower(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_tokens(text: str, stopwords: Set[str] | None = None) -> List[str]:
    if not text:
        return []
    tokens = text.split()
    if not stopwords:
        return tokens
    return [t for t in tokens if t and t not in stopwords]


def unique_sorted(tokens: Iterable[str]) -> List[str]:
    return sorted(set(t for t in tokens if t))
