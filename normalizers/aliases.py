"""Simple alias mappings for product keys.

Keep this small and explicit: map common numeric-only codes to families.
"""

ALIASES = {
    # GPU numeric code -> family + code
    "5060": "rx 5060",
    "7060": "rx 7060",
    # Add others as needed
}


def apply_aliases(pk: str, title: str = "") -> str:
    if not pk:
        return pk
    # If pk is numeric or short code, map explicitly
    key = pk.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    # If title contains known code and pk doesn't include family, try to map
    for k, v in ALIASES.items():
        if k in title.lower() and k not in pk:
            return v
    return pk
