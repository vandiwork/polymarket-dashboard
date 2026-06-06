# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Polymarket (prediction market) analytics toolkit that pulls live market data, categorizes markets, and generates dashboards for market research and portfolio tracking.

**Core workflow**: Polymarket Gamma API → Data puller → CSV export → Dashboard generator → HTML dashboard

## Architecture & Data Flow

### 1. **Market Data Puller** (`polymarket_pull.py` / `polymarket_pull_nopandas.py`)
- Fetches all active markets from Polymarket's Gamma API via the `/events` endpoint
- Key insight: `/events` returns nested markets within events (not `/markets` which is incomplete)
- Automatically classifies markets into categories: Sports, Earnings, AI/Tech, Entertainment, Legal/Crime, Economics, Geopolitics, Politics, Esports, Other
- Filters by configurable thresholds: minimum liquidity ($1000) and volume ($5000)
- Calculates MOIC (multiplier on investment) for YES and NO outcomes
- Assigns settlement clarity scores (1-5 scale, based on outcome clarity and description)
- Exports timestamped CSV with full market metadata

**Two versions**: 
- `polymarket_pull.py` uses pandas (faster, more readable)
- `polymarket_pull_nopandas.py` uses stdlib+csv (workaround for Windows Application Control blocking numpy DLLs)

### 2. **Dashboard Rebuilder** (`rebuild_dashboard.py`)
- Reads the latest `polymarket_active_*.csv` and embeds it in `dashboard.html`
- Compresses CSV data into JSON format for browser-side filtering
- Drops expired markets (deadline ≤ 0 days)
- Maintains interactive dashboard with category/volume/liquidity filters

### 3. **Inspection Utility** (`inspect_other.py`)
- Analyzes the latest CSV to show top uncategorized ("Other") markets
- Helps identify new categories to add to the classifier rules

### 4. **Key Data Files**
- `watchlist.md`: manually tracked markets with trading positions (positions, entry dates, notes)
- `jaro_polymarket_pnl_2026-04-08.xlsx`: PnL tracking spreadsheet
- `polymarket_active_*.csv`: timestamped market snapshots (output of puller)
- `dashboard.html`: interactive browser-based market dashboard

## Common Commands

### Pull fresh market data
```powershell
python polymarket_pull.py
# or (if pandas/numpy fails):
python polymarket_pull_nopandas.py
```
Output: `polymarket_active_YYYYMMDD_HHMMSS.csv`

### Rebuild dashboard with latest data
```powershell
python rebuild_dashboard.py
```
Updates `dashboard.html` with the most recent CSV data.

### Inspect uncategorized markets
```powershell
python inspect_other.py
```
Shows top "Other" category markets by volume. Use to identify new categorization rules.

### View the dashboard
Open `dashboard.html` in a browser. Features:
- Sort/filter by category, volume, liquidity
- Shows YES/NO prices and MOIC
- Settlement clarity score (1-5)
- Days until market deadline
- Direct Polymarket links

## Setup

### One-time setup
```powershell
pip install requests pandas
```

If pandas fails due to Windows Application Control, use the no-pandas version which only needs:
```powershell
pip install requests
```

## Configuration & Customization

In `polymarket_pull.py` / `polymarket_pull_nopandas.py`, adjust these at the top:

- **`MIN_LIQUIDITY`** (default 1000): Minimum liquidity in USD to include market
- **`MIN_VOLUME`** (default 5000): Minimum volume in USD to include market
- **`MAX_EVENTS`** (default None): Cap on events to fetch (None = unlimited)
- **`EXCLUDED_KEYWORDS`** (default []): List of keywords to filter out
- **`CATEGORY_RULES`**: Regex patterns for market classification (note: Crypto category is always dropped)

## Key Design Notes

1. **Events vs Markets API**: The puller uses `/events` with nested markets, not `/markets` endpoint. The API design requires pagination through events to get complete market coverage.

2. **Crypto filtering**: All Crypto-tagged markets are automatically dropped before CSV export and dashboard generation (user policy).

3. **Settlement clarity heuristic**: Score ranges 1-5, based on: presence of end_date, outcome clarity, and description length. Higher = clearer settlement criteria.

4. **MOIC calculation**: Multiplier = 1 / price. Only calculated for prices > 0.01 (avoids division noise).

5. **URL construction**: Market links are built as `https://polymarket.com/event/{event_slug}/{market_slug}`, falling back to event_slug if market_slug unavailable.

6. **Dashboard performance**: HTML embedding keeps data in-browser; no API calls from dashboard. Useful for offline browsing.

## Frequent Iterations

- **Add new category**: Add pattern rules to `CATEGORY_RULES` in the puller, then re-run pull and rebuild dashboard
- **Adjust filtering thresholds**: Change `MIN_LIQUIDITY` / `MIN_VOLUME`, re-pull, rebuild
- **Update watchlist**: Edit `watchlist.md` manually (format: market slug, position, entry date, notes)
