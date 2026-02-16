"""Backfill structured columns (brand,line,series,model,variant) in `scraped_items`.

Run from project root: `python scripts/backfill_structured.py`.
"""
from normalizers.structured import parse_title
from storage.scraper_db import _get_conn


def main():
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, product_name FROM scraped_items")
    rows = cur.fetchall()
    updated = 0
    for r in rows:
        _id = r[0]
        title = r[1] or ''
        parsed = parse_title(title)
        cur.execute(
            "UPDATE scraped_items SET brand = ?, line = ?, series = ?, model = ?, variant = ? WHERE id = ?",
            (
                parsed.get('brand'),
                parsed.get('line'),
                parsed.get('series'),
                parsed.get('model'),
                parsed.get('variant'),
                _id,
            ),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"Backfilled {updated} rows")


if __name__ == '__main__':
    main()
