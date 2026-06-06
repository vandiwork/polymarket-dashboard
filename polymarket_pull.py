"""
Polymarket Active Markets Puller (v2 - Events API)
===================================================
Pulls all active markets from Polymarket's Gamma API and exports to CSV.

SETUP (one-time):
    pip install requests pandas

USAGE:
    python polymarket_pull.py

HOW IT WORKS (step by step):
    1. Hits the Gamma /events endpoint (public, no auth needed)
    2. Paginates through all active, non-closed events (100 per request)
    3. Extracts nested markets from each event
    4. Parses each market's key fields (title, prices, volume, liquidity, etc.)
    5. Exports everything to a timestamped CSV file

NOTE: The /events endpoint is the correct way to fetch ALL markets.
      The /markets endpoint only returns a subset. Events contain
      nested market objects with full data.
"""

import requests
import pandas as pd
from datetime import datetime
import time
import sys
import re
import json

print("=" * 60)
print("POLYMARKET PULLER v2 — EVENTS API")
print("If you do NOT see this line, you are running an old version!")
print("=" * 60)

# ---------------------------------------------------------------------------
# STEP 1: Configuration
# ---------------------------------------------------------------------------
# The Gamma API is Polymarket's public metadata API. No API key required.

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
EVENTS_ENDPOINT = f"{GAMMA_API_BASE}/events"

# How many events to fetch per request (max 100)
PAGE_SIZE = 100

# Optional filters — adjust these to narrow your pull
# NOTE: We do NOT filter by active=true here because some high-volume
# events (e.g. "US strikes Iran") may not have the active flag set on
# the event level even though their nested markets are actively trading.
# We filter at the market level instead after extraction.
FILTERS = {
    "closed": "false",      # only non-closed events
    "order": "volume",      # sort by volume so biggest markets come first
    "ascending": "false",   # descending — highest volume first
    "limit": PAGE_SIZE,
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Maximum events to fetch (set to None for unlimited)
MAX_EVENTS = None

# Minimum liquidity threshold (in USD). Markets below this get dropped.
MIN_LIQUIDITY = 1000

# Minimum volume threshold (in USD). Markets below this get dropped.
MIN_VOLUME = 5000

# ---------------------------------------------------------------------------
# Keyword exclusions
# ---------------------------------------------------------------------------
# Markets matching any of these keywords (checked against question, category,
# and description) will be dropped. Case-insensitive.

EXCLUDED_KEYWORDS = []


# ---------------------------------------------------------------------------
# STEP 2: Fetch events with nested markets
# ---------------------------------------------------------------------------
# The /events endpoint returns events, each containing a list of nested
# markets. This is the recommended way to get ALL markets on Polymarket.
# The /markets endpoint only returns a subset.

def fetch_all_events():
    """Fetch all active events using offset pagination."""
    all_events = []
    offset = 0

    print("Fetching active events from Polymarket Gamma API...")
    print("-" * 50)

    while True:
        params = {**FILTERS, "offset": offset}

        try:
            response = requests.get(EVENTS_ENDPOINT, params=params, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"\n[ERROR] API request failed: {e}")
            print("Check your internet connection and try again.")
            sys.exit(1)

        batch = response.json()

        if not batch:
            break

        all_events.extend(batch)
        # Count total markets across events
        total_markets = sum(len(e.get("markets", [])) for e in all_events)
        print(f"  Fetched {len(all_events)} events ({total_markets} markets) so far... (offset={offset})")

        if len(batch) < PAGE_SIZE:
            break

        if MAX_EVENTS and len(all_events) >= MAX_EVENTS:
            all_events = all_events[:MAX_EVENTS]
            print(f"  Reached MAX_EVENTS cap ({MAX_EVENTS}), stopping.")
            break

        offset += PAGE_SIZE
        time.sleep(0.3)

    total_markets = sum(len(e.get("markets", [])) for e in all_events)
    print(f"\nTotal events fetched: {len(all_events)} containing {total_markets} markets")
    return all_events


# ---------------------------------------------------------------------------
# STEP 3: Extract markets from events and structure the data
# ---------------------------------------------------------------------------

# Category classifier
CATEGORY_RULES = [
    ("Sports", [
        r"\b(nba|nfl|mlb|nhl|wnba|mls|ufc|mma|pga|nascar|ipl|epl)\b",
        r"\b(basketball|football|baseball|hockey|soccer|tennis|golf|boxing|cricket|rugby|esports|counter-strike)\b",
        r"\b(lakers|celtics|warriors|chiefs|eagles|cowboys|yankees|dodgers)\b",
        r"\b(premier league|la liga|serie a|champions league|bundesliga|wimbledon)\b",
        r"\b(super bowl|world series|stanley cup|march madness|olympics)\b",
        r"\b(f1|formula 1|grand prix)\b",
        r"\bBO3\b",
        r"\b(ESL|HEROIC|Lilmix)\b",
    ]),
    ("Earnings", [
        r"\bearnings\b", r"\brevenue\b", r"\bEPS\b", r"\bquarterly results\b",
        r"\bearnings call\b", r"\bbeat estimates\b", r"\bmiss estimates\b",
        r"\bfiscal quarter\b", r"\b10-[kq]\b", r"\bannual report\b",
    ]),
    ("AI/Tech", [
        r"\b(ai|artificial intelligence|openai|anthropic|deepmind|gpt|chatgpt|gemini|claude)\b",
        r"\b(tech|silicon valley|apple|google|microsoft|meta|nvidia|tesla|amazon)\b",
        r"\b(agi|llm|machine learning|robotics|semiconductor|chip)\b",
    ]),
    ("Entertainment", [
        r"\b(netflix|disney|hbo|spotify|youtube|tiktok|instagram)\b",
        r"\b(movie|film|oscar|grammy|emmy|tony|golden globe|box office)\b",
        r"\b(album|song|concert|tour|streaming|show|season \d|reality tv)\b",
        r"\b(celebrity|kardashian|taylor swift|drake|beyonce|rihanna)\b",
        r"\btop US Netflix\b",
    ]),
    ("Legal/Crime", [
        r"\b(court|judge|ruling|lawsuit|indictment|convicted|sentenced|charged|verdict)\b",
        r"\b(supreme court|scotus|trial|prosecution|plea|prison|jail)\b",
        r"\b(shooter|shooting|murder|crime|arrest|fbi)\b",
        r"\b(extradite|pardon|clemency)\b",
    ]),
    ("Economics", [
        r"\b(fed|federal reserve|interest rate|inflation|gdp|recession|unemployment)\b",
        r"\b(tariff|trade war|sanctions|treasury|debt ceiling|deficit)\b",
        r"\b(bank of japan|ecb|central bank|monetary policy)\b",
        r"\b(s&p|dow jones|nasdaq|stock market|ipo)\b",
        r"\b(oil price|commodity|housing market|cpi)\b",
    ]),
    ("Geopolitics", [
        r"\b(war|invasion|ceasefire|nato|military|troops|missile|nuclear|nuke)\b",
        r"\b(hamas|hezbollah|ukraine|russia|china|iran|north korea|taiwan)\b",
        r"\b(embassy|diplomat|sanctions|annex|invade|greenland)\b",
        r"\b(ISIS|al.?qaeda|taliban|terrorist)\b",
    ]),
    ("Politics", [
        r"\b(election|president|prime minister|governor|senator|congress|parliament)\b",
        r"\b(democrat|republican|gop|vote|ballot|campaign|candidate|caucus)\b",
        r"\b(mayor|cabinet|impeach|resign|political|party|coalition)\b",
        r"\b(trump|biden|obama|desantis|newsom|pelosi|mcconnell)\b",
        r"\b(fidesz|tisza|by-election|primary election|runoff)\b",
        r"\b(tax|wealth tax|bill passes|legislation)\b",
    ]),
]

def classify_market(question, description=""):
    """Classify a market into a category based on keywords."""
    text = (question + " " + description).lower()
    for cat, patterns in CATEGORY_RULES:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return cat
    return "Other"


def extract_markets_from_events(events):
    """Extract individual markets from nested event objects."""
    rows = []
    skipped_closed = 0

    for event in events:
        event_slug = event.get("slug", "")
        event_title = event.get("title", "")
        nested_markets = event.get("markets", [])

        # If event has no nested markets, try to treat the event itself as a market
        if not nested_markets:
            nested_markets = [event]

        for m in nested_markets:
            # Skip closed/inactive individual markets
            if str(m.get("closed", "false")).lower() == "true":
                skipped_closed += 1
                continue
            # Parse outcome prices
            outcome_prices = m.get("outcomePrices", "[]")
            try:
                prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
            except (json.JSONDecodeError, TypeError):
                prices = []

            yes_price = float(prices[0]) if len(prices) > 0 else None
            no_price = float(prices[1]) if len(prices) > 1 else None

            # Parse outcomes list
            outcomes_raw = m.get("outcomes", "[]")
            if isinstance(outcomes_raw, str):
                try:
                    outcomes = json.loads(outcomes_raw)
                except (json.JSONDecodeError, TypeError):
                    outcomes = []
            else:
                outcomes = outcomes_raw if outcomes_raw else []

            # Build the correct URL: /event/{event_slug}/{market_slug}
            market_slug = m.get("slug", "")
            if event_slug and market_slug and event_slug != market_slug:
                url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
            elif event_slug:
                url = f"https://polymarket.com/event/{event_slug}"
            else:
                url = f"https://polymarket.com/event/{market_slug}"

            question = m.get("question", event_title)
            description = (m.get("description") or event.get("description") or "")[:200]

            rows.append({
                "id": m.get("id", event.get("id")),
                "question": question,
                "slug": market_slug,
                "event_slug": event_slug,
                "yes_price": yes_price,
                "no_price": no_price,
                "spread": round(abs((yes_price or 0) - (1 - (no_price or 1))), 4) if yes_price and no_price else None,
                "volume_usd": float(m.get("volume", 0) or 0),
                "liquidity_usd": float(m.get("liquidity", 0) or 0),
                "outcomes": ", ".join(outcomes) if outcomes else "",
                "start_date": m.get("startDate", event.get("startDate")),
                "end_date": m.get("endDate", event.get("endDate")),
                "description": description,
                "category": classify_market(question, description),
                "market_url": url,
            })

    df = pd.DataFrame(rows)

    # Drop duplicates by market ID (some events may share markets)
    if "id" in df.columns:
        before_dedup = len(df)
        df = df.drop_duplicates(subset=["id"]).reset_index(drop=True)
        if before_dedup > len(df):
            print(f"  Removed {before_dedup - len(df)} duplicate markets")

    print(f"  Skipped {skipped_closed} closed markets")

    # Sort by volume descending
    df = df.sort_values("volume_usd", ascending=False).reset_index(drop=True)

    return df


def filter_excluded(df):
    """Remove markets matching excluded keywords + low liquidity/volume."""
    before = len(df)

    # Filter 1: Minimum liquidity
    df = df[df["liquidity_usd"] >= MIN_LIQUIDITY].reset_index(drop=True)
    low_liq = before - len(df)
    print(f"  Filtered out {low_liq} markets below ${MIN_LIQUIDITY:,} liquidity")

    # Filter 2: Minimum volume
    before_vol = len(df)
    df = df[df["volume_usd"] >= MIN_VOLUME].reset_index(drop=True)
    low_vol = before_vol - len(df)
    print(f"  Filtered out {low_vol} markets below ${MIN_VOLUME:,} volume")

    # Filter 3: Excluded keywords
    if EXCLUDED_KEYWORDS:
        search_col = (
            df["question"].fillna("") + " " +
            df["category"].fillna("") + " " +
            df["description"].fillna("")
        ).str.lower()

        mask = search_col.apply(
            lambda text: not any(kw in text for kw in EXCLUDED_KEYWORDS)
        )

        before2 = len(df)
        df = df[mask].reset_index(drop=True)
        dropped = before2 - len(df)
        print(f"  Filtered out {dropped} markets (excluded keywords)")

    print(f"  Remaining: {len(df)} markets")
    return df


# ---------------------------------------------------------------------------
# STEP 4: Calculate trading metrics
# ---------------------------------------------------------------------------

def add_trading_metrics(df):
    """Add MOIC and a simple settlement clarity heuristic."""

    df["moic_yes"] = df["yes_price"].apply(
        lambda p: round(1.0 / p, 2) if p and p > 0.01 else None
    )

    df["moic_no"] = df["no_price"].apply(
        lambda p: round(1.0 / p, 2) if p and p > 0.01 else None
    )

    def clarity_score(row):
        score = 3
        if row.get("end_date"):
            score += 1
        if row.get("outcomes") and row["outcomes"].lower() in ["yes, no"]:
            score += 1
        if not row.get("description") or len(str(row.get("description", ""))) < 20:
            score -= 1
        return min(max(score, 1), 5)

    df["settlement_clarity"] = df.apply(clarity_score, axis=1)

    return df


# ---------------------------------------------------------------------------
# STEP 5: Export to CSV
# ---------------------------------------------------------------------------

def export_to_csv(df):
    """Save the DataFrame to a timestamped CSV file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"polymarket_active_{timestamp}.csv"
    df.to_csv(filename, index=False)
    print(f"\nExported {len(df)} markets to: {filename}")
    return filename


# ---------------------------------------------------------------------------
# STEP 6: Print a summary
# ---------------------------------------------------------------------------

def print_summary(df):
    """Print a quick overview of what we pulled."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total active markets:    {len(df)}")
    print(f"Total volume (all mkts): ${df['volume_usd'].sum():,.0f}")
    print(f"Avg liquidity:           ${df['liquidity_usd'].mean():,.0f}")

    # Category breakdown
    print(f"\n--- BY CATEGORY ---")
    cat_counts = df["category"].value_counts()
    for cat, count in cat_counts.items():
        print(f"  {cat:20s} {count:4d} markets")

    print(f"\n--- TOP 30 BY VOLUME ---")
    top = df.head(30)[["question", "yes_price", "volume_usd", "moic_yes", "settlement_clarity"]]
    top.columns = ["Question", "YES $", "Volume", "MOIC (YES)", "Clarity"]
    print(top.to_string(index=False))


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Step 1-2: Fetch all events with nested markets
    events = fetch_all_events()

    if not events:
        print("No active events found. Exiting.")
        sys.exit(0)

    # Diagnostic: show top events by nested market count
    print("\n--- TOP 10 EVENTS BY MARKET COUNT ---")
    events_sorted = sorted(events, key=lambda e: len(e.get("markets", [])), reverse=True)
    for e in events_sorted[:10]:
        mkts = e.get("markets", [])
        print(f"  {len(mkts):4d} markets | closed={str(e.get('closed','')):5s} | {e.get('title', '???')[:60]}")

    # Step 3: Extract markets from events
    df = extract_markets_from_events(events)
    print(f"\nExtracted {len(df)} unique markets from {len(events)} events")

    # Diagnostic: check for known big markets
    print("\n--- DIAGNOSTIC: Searching for known big markets ---")
    for keyword in ["2028", "netanyahu", "iran strike", "chelsea clinton", "oprah"]:
        matches = df[df["question"].str.lower().str.contains(keyword, na=False)]
        if len(matches) > 0:
            print(f"  FOUND '{keyword}': {len(matches)} markets (top vol: ${matches['volume_usd'].max():,.0f})")
        else:
            print(f"  MISSING '{keyword}'")

    # Step 3.5: Remove excluded categories
    df = filter_excluded(df)

    # Step 4: Add MOIC and settlement clarity
    df = add_trading_metrics(df)

    # Step 5: Export
    filename = export_to_csv(df)

    # Step 6: Summary
    print_summary(df)

    print(f"\nDone! Open {filename} in Excel or Google Sheets for full data.")
