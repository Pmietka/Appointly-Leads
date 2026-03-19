# Appointly Leads — Google Maps Scraper

Scrapes Google Maps search results and exports business leads to CSV or JSON.

## What it extracts

| Field | Description |
|-------|-------------|
| `name` | Business name |
| `phone` | Phone number |
| `address` | Full address |
| `website` | Business website URL |
| `rating` | Star rating (e.g. `4.5`) |
| `reviews` | Number of reviews |
| `category` | Business category |
| `hours` | Current open/close status |
| `maps_url` | Direct Google Maps link |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Basic — scrapes 20 results, saves leads_<query>.csv
python scraper.py "plumbers in Chicago"

# Get 50 results as JSON
python scraper.py "dentists in New York" --max 50 --format json

# Save both CSV and JSON with a custom filename
python scraper.py "coffee shops London" --max 100 --format both --output london_coffee

# Run with visible browser (useful for debugging)
python scraper.py "lawyers in Austin TX" --no-headless
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--max N` | `20` | Max listings to scrape |
| `--format` | `csv` | Output format: `csv`, `json`, or `both` |
| `--output` | auto | Base filename (without extension) |
| `--no-headless` | off | Show browser window |

## Notes

- Results are saved to the current directory.
- The scraper scrolls the results panel automatically to load more listings.
- A ~1.5 s delay is added between listings to avoid rate limiting.
- If Google shows a consent screen (EU), it is dismissed automatically.
