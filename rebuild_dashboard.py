"""
Rebuild the Polymarket dashboard from the most recent polymarket_active_*.csv.

USAGE (from VS Code terminal, in the Polymarket folder):
    python rebuild_dashboard.py

What it does:
    1. Finds the newest polymarket_active_YYYYMMDD_HHMMSS.csv in this folder
    2. Reads dashboard.html
    3. Replaces the embedded RAW_DATA array with fresh rows from the CSV
    4. Updates the page title and "Scraped ..." subtitle to today's date
    5. Writes dashboard.html back in place

Field map (CSV -> dashboard JSON keys):
    question            -> q
    category            -> cat
    volume_usd          -> v
    liquidity_usd       -> l
    yes_price           -> y
    no_price            -> n
    moic_yes            -> my
    moic_no             -> mn
    settlement_clarity  -> sc
    market_url          -> url
    end_date            -> dl   (days_left, integer, null if missing)
"""

import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(HERE, "index.html")


def find_latest_csv():
    csvs = sorted(glob.glob(os.path.join(HERE, "polymarket_active_*.csv")))
    if not csvs:
        print("ERROR: no polymarket_active_*.csv files found in", HERE)
        sys.exit(1)
    return csvs[-1]


def parse_float(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def parse_int(x):
    try:
        if x is None or x == "":
            return None
        return int(float(x))
    except (ValueError, TypeError):
        return None


def days_left(end_date_str, today):
    if not end_date_str:
        return None
    try:
        # CSV stores ISO8601 like "2026-12-31T00:00:00Z"
        end = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        delta = end.date() - today.date()
        return delta.days
    except (ValueError, TypeError):
        return None


def build_rows(csv_path, today):
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            row = {
                "q": r.get("question", "") or "",
                "cat": r.get("category", "Other") or "Other",
                "v": parse_float(r.get("volume_usd")) or 0,
                "l": parse_float(r.get("liquidity_usd")) or 0,
                "y": parse_float(r.get("yes_price")),
                "n": parse_float(r.get("no_price")),
                "my": parse_float(r.get("moic_yes")),
                "mn": parse_float(r.get("moic_no")),
                "sc": parse_int(r.get("settlement_clarity")),
                "dl": days_left(r.get("end_date"), today),
                "url": r.get("market_url", "") or "",
                "d": (r.get("description") or "")[:100],  # first 100 chars of description for search
            }
            rows.append(row)
    # Drop expired and same-day-expiry markets (user policy: never surface dl<=0)
    rows = [r for r in rows if r.get("dl") is None or r.get("dl") > 0]
    # Sort by volume desc, same as the puller
    rows.sort(key=lambda x: x.get("v") or 0, reverse=True)
    return rows


def to_compact_json(rows):
    # Compact, no whitespace, ensure_ascii so it's safe to inline
    return json.dumps(rows, separators=(",", ":"), ensure_ascii=False)


def update_dashboard(rows, scraped_label, scraped_date):
    with open(DASHBOARD, "r", encoding="utf-8") as f:
        html = f.read()

    new_data_line = f"let RAW_DATA={to_compact_json(rows)};"

    # Replace the entire RAW_DATA= line. The current file has it on one line,
    # starting with optional whitespace then "let RAW_DATA=" or "const RAW_DATA="
    pattern = re.compile(r"(?:let|const|var)\s+RAW_DATA\s*=\s*\[.*?\];", re.DOTALL)
    if not pattern.search(html):
        print("ERROR: could not locate RAW_DATA assignment in dashboard.html")
        sys.exit(1)
    html = pattern.sub(new_data_line, html, count=1)

    # Update <title>Polymarket Dashboard — YYYY-MM-DD</title>
    html = re.sub(
        r"<title>Polymarket Dashboard\s*&mdash;\s*\d{4}-\d{2}-\d{2}</title>",
        f"<title>Polymarket Dashboard &mdash; {scraped_date}</title>",
        html,
    )
    html = re.sub(
        r"<title>Polymarket Dashboard\s*—\s*\d{4}-\d{2}-\d{2}</title>",
        f"<title>Polymarket Dashboard — {scraped_date}</title>",
        html,
    )

    # Update "Scraped YYYY-MM-DD HH:MM UTC" subtitle
    html = re.sub(
        r"Scraped \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC",
        f"Scraped {scraped_label}",
        html,
    )

    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    csv_path = find_latest_csv()
    csv_name = os.path.basename(csv_path)
    print(f"Source CSV: {csv_name}")

    # Pull the timestamp out of the filename: polymarket_active_YYYYMMDD_HHMMSS.csv
    m = re.search(r"polymarket_active_(\d{8})_(\d{6})\.csv", csv_name)
    if m:
        date_part, time_part = m.group(1), m.group(2)
        stamp = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
        scraped_label = stamp.strftime("%Y-%m-%d %H:%M UTC")
        scraped_date = stamp.strftime("%Y-%m-%d")
        today = stamp
    else:
        today = datetime.now(timezone.utc)
        scraped_label = today.strftime("%Y-%m-%d %H:%M UTC")
        scraped_date = today.strftime("%Y-%m-%d")

    rows = build_rows(csv_path, today)
    print(f"Markets in CSV: {len(rows)}")
    print(f"Top by volume:  {rows[0]['q'][:60]} ... ${rows[0]['v']:,.0f}")
    print(f"Updating dashboard scrape stamp to: {scraped_label}")

    update_dashboard(rows, scraped_label, scraped_date)
    print(f"Wrote dashboard.html with {len(rows)} markets.")


if __name__ == "__main__":
    main()
