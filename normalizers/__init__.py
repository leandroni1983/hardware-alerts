"""Unified normalizers package.

This package consolidates the old `normalizer/` and `storage/normalizers/` modules.
"""

__all__ = ["normalize_product", "gpu", "cpu", "ram", "storage"]

# Expose normalize_product at package level for backward compat
from . import normalize_product  # noqa: E402,F401

