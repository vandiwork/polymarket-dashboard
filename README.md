# Polymarket Dashboard

Interactive dashboard for Polymarket prediction markets. Automatically pulls live market data every 3 hours and publishes to GitHub Pages.

## Live Site

Once deployed: `https://vandiwork.github.io/polymarket-dashboard/`

## Quick Start

### Local Development

1. Install dependencies:
   ```bash
   pip install requests pandas  # or just 'requests' if pandas fails
   ```

2. Pull fresh market data:
   ```bash
   python polymarket_pull.py
   # or (no pandas):
   python polymarket_pull_nopandas.py
   ```

3. Rebuild the dashboard:
   ```bash
   python rebuild_dashboard.py
   ```

4. Open `index.html` in a browser.

### Publishing to GitHub Pages

#### 1. Create a GitHub Repository

```bash
git remote add origin https://github.com/YOUR_USERNAME/polymarket-dashboard.git
git branch -M main
git push -u origin main
```

#### 2. Configure GitHub Pages

1. Go to **Settings → Pages**
2. Under **Source**, select **GitHub Actions**
3. Go to **Settings → Actions → General**
4. Under **Workflow permissions**, select **Read and write permissions**

#### 3. Done

The site will be live at `https://YOUR_USERNAME.github.io/polymarket-dashboard/`

- Automatic data refreshes run every 3 hours (UTC)
- Trigger a manual refresh from the **Actions** tab

## How It Works

### Components

- **`polymarket_pull.py`** — Fetch markets from Polymarket Gamma API, categorize, filter by liquidity/volume
- **`rebuild_dashboard.py`** — Embed CSV data into `index.html` as compact JSON
- **`index.html`** — Self-contained dashboard (no external dependencies, works offline)

### GitHub Actions Workflows

- **`refresh.yml`** — Every 3 hours: pull data → rebuild dashboard → commit
- **`deploy-site.yml`** — On any `index.html` push: deploy to GitHub Pages

### Data Flow

```
Polymarket API → polymarket_pull_nopandas.py → index.html ↓
                                                  (refresh every 3h)
                                                      ↓
                                           GitHub Pages (live site)
```

## Customization

Adjust these in `polymarket_pull.py` / `polymarket_pull_nopandas.py`:

- `MIN_LIQUIDITY` — Minimum liquidity threshold (default: $1,000)
- `MIN_VOLUME` — Minimum volume threshold (default: $5,000)
- `MAX_EVENTS` — Cap events to fetch (default: unlimited)
- `EXCLUDED_KEYWORDS` — Keywords to filter out (default: empty)
- `CATEGORY_RULES` — Market classification patterns

Then re-pull and rebuild:
```bash
python polymarket_pull.py && python rebuild_dashboard.py
```

## Dashboard Features

- **Live prices** — YES / NO outcome prices
- **MOIC** — Multiplier on investment (1 / price)
- **Settlement clarity** — 1–5 score (higher = clearer settlement criteria)
- **Filtering** — By category, volume, liquidity, expiry date, outcome prices
- **Sorting** — Click column headers to sort
- **Direct links** — Each market links to Polymarket.com

## Notes

- Crypto markets are automatically excluded (user policy)
- All monetary values in USD
- No external CDN dependencies — dashboard works offline
- Scheduled data pulls use `polymarket_pull_nopandas.py` (no numpy DLL issues in GitHub Actions)

## Troubleshooting

**Dashboard not updating?**
- Check the **Actions** tab for workflow errors
- Manually trigger `refresh.yml` from Actions > Workflows > Refresh Market Data

**Markets missing from dashboard?**
- Adjust `MIN_LIQUIDITY` and `MIN_VOLUME` thresholds
- Re-run `polymarket_pull.py` and `rebuild_dashboard.py`

**Deploy failed?**
- Confirm **Pages → Source** is set to **GitHub Actions**
- Confirm **Actions → Workflow permissions** is set to **Read and write**
