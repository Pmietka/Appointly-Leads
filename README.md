# Appointly Leads — Google Maps Scraper

Scrapes Google Maps search results and exports business leads to CSV or JSON.
Built for lead generation — especially home service businesses like insulation contractors.

## What it extracts

| Field | Description |
|-------|-------------|
| `name` | Business name |
| `phone` | Phone number |
| `address` | Full address |
| `website` | Business website URL |
| `rating` | Star rating (e.g. `4.5`) |
| `reviews` | Number of reviews |
| `category` | Business category (e.g. "Insulation contractor") |
| `hours` | Operating hours |
| `maps_url` | Direct Google Maps link |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### Home Insulation Leads

```bash
# Find insulation companies in a specific city
python scraper.py "home insulation companies in Dallas TX"

# Spray foam insulation contractors
python scraper.py "spray foam insulation contractors in Houston TX" --max 50

# Attic insulation — get both CSV and JSON
python scraper.py "attic insulation companies near Chicago IL" --max 40 --format both

# Blown-in insulation
python scraper.py "blown in insulation contractors Phoenix AZ" --output phoenix_insulation
```

### Other Businesses

```bash
python scraper.py "plumbers in Miami" --max 30
python scraper.py "HVAC contractors in Denver CO" --max 50 --format json
python scraper.py "roofing companies in Atlanta GA" --no-headless
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--max N` | `20` | Max listings to scrape |
| `--format` | `csv` | Output format: `csv`, `json`, or `both` |
| `--output` | auto | Base filename (without extension) |
| `--no-headless` | off | Show browser window (for debugging) |

## Search Tips for Insulation Leads

- **Be specific with location**: `"insulation contractors in [City, State]"` works best
- **Try different keywords**: "home insulation", "spray foam insulation", "attic insulation", "insulation contractors", "blown-in insulation"
- **Cover surrounding areas**: Run multiple searches for neighboring cities to build a bigger list
- **Use `--max 50` or higher**: Google Maps typically shows 20-60 results per search area

## Output

Results are saved to the current directory. Example CSV output:

```
name,phone,address,website,rating,reviews,category,hours,maps_url
ABC Insulation Co,(555) 123-4567,123 Main St Dallas TX,https://abcinsulation.com,4.8,142,Insulation contractor,Open ⋅ Closes 5 PM,https://...
```

## How It Works

1. Opens Google Maps with your search query in a headless Chromium browser
2. Scrolls the results panel to load all available listings
3. Visits each listing page to extract business details
4. Uses proven CSS selectors (`data-item-id` attributes) for reliable data extraction
5. Exports to CSV/JSON with a summary table

## Notes

- A ~1.5s delay is added between listings to avoid rate limiting
- Stealth measures are applied to reduce bot detection
- Consent/cookie screens are auto-dismissed
- Service-area businesses (common for insulation) may not show a street address
