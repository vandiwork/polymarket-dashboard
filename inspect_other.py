"""
Inspect the latest polymarket CSV and print the top 50 markets currently
labeled "Other" (sorted by volume). Reads the `category` column written by
the puller — so this reflects the actual hybrid classifier output (API tags
first, regex fallback). Re-run the puller before this for fresh data.

USAGE:
    python inspect_other.py
"""

import csv
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_latest_csv():
    csvs = sorted(glob.glob(os.path.join(HERE, "polymarket_active_*.csv")))
    if not csvs:
        print("No polymarket_active_*.csv found.")
        sys.exit(1)
    return csvs[-1]


def main():
    csv_path = find_latest_csv()
    print(f"Source: {os.path.basename(csv_path)}\n")

    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["volume_usd_f"] = float(r.get("volume_usd") or 0)
            except (ValueError, TypeError):
                r["volume_usd_f"] = 0.0
            rows.append(r)

    # Category counts (the puller already drops Crypto, so they shouldn't appear)
    counts = {}
    for r in rows:
        cat = r.get("category", "Other") or "Other"
        counts[cat] = counts.get(cat, 0) + 1
    print("=== CATEGORY COUNTS ===")
    for cat in sorted(counts, key=lambda c: -counts[c]):
        print(f"  {cat:20s} {counts[cat]:5d}")
    print()

    # Top 50 Other by volume
    others = [r for r in rows if (r.get("category") or "Other") == "Other"]
    others.sort(key=lambda r: r["volume_usd_f"], reverse=True)
    print(f"=== TOP 50 'OTHER' BY VOLUME (of {len(others)} total) ===")
    print(f"{'Vol':>14}  {'Question':<80}  {'Event slug':<40}")
    print("-" * 140)
    for r in others[:50]:
        q = (r.get("question") or "")[:80]
        es = (r.get("event_slug") or "")[:40]
        v = r["volume_usd_f"]
        print(f"${v:>13,.0f}  {q:<80}  {es:<40}")


if __name__ == "__main__":
    main()
