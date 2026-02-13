#!/usr/bin/env python3
"""Small harness to validate AI classifier with sample contexts."""
import sys
from pathlib import Path
# ensure project root is on sys.path when running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai import analyze_offer

EXAMPLES = [
    {
        "title": "RTX 5060 TI 8GB MSI GAMING OC",
        "price": 740999,
        "avg30": 914491,
        "avg7": 900000,
        "shop": "mexx",
        "url": "https://...",
    },
    {
        "title": "Auriculares Gamer XYZ con microfono",
        "price": 19999,
        "avg30": 22000,
        "shop": "fullh4rd",
        "url": "https://...",
    },
]

for ex in EXAMPLES:
    r = analyze_offer.analyze(ex)
    print("Context:", ex["title"])
    print("Result:", r)
    print("---")
