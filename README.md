# Caitlin Clark WNBA Data Scraper

Modular scraper for FanbaseHQ to collect Caitlin Clark milestones, shoes, and tunnel fits from social media.

## Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

2. **Set up API keys:**
   - Copy `deployment/.env.production.example` to `config/.env`
   - Add your OpenAI API key
   - Add your TwitterAPI.io API key
   - Configure SMTP settings for email notifications

## Usage

### Basic milestone scraping:
```bash
python main.py --player "caitlin clark" --type milestones
```

### With custom date range:
```bash
python main.py --player "caitlin clark" --start-date 2024-04-01 --end-date 2024-08-27
```

### With custom output file:
```bash
python main.py --player "caitlin clark" --output custom_milestones.csv --limit 200
```

### Dry run (see what would be scraped):
```bash
python main.py --player "caitlin clark" --dry-run
```

## Configuration

- **Players**: `config/players.json` - Player name variations
- **Accounts**: `config/accounts.json` - Twitter accounts to scrape
- **Environment**: `config/.env` - API keys and SMTP settings
- **Settings**: `config/settings.py` - Configuration management

## Output

Generates CSV files matching FanbaseHQ schema in the `output/` directory:
- `milestones.csv` - Player milestone submissions
- `shoes.csv` - Shoe submissions with game stats
- `tunnel_fits.csv` - Tunnel fit submissions

## Architecture

- **Service layer design** - Clean separation of concerns with dependency injection
- **AI-powered parsing** - Uses OpenAI GPT-4o-mini to extract structured data
- **Multi-source data** - TwitterAPI.io for tweets, KixStats.com for shoes, SportDataverse for game validation
- **Semantic deduplication** - Fuzzy matching to eliminate duplicate milestones across sources
- **Production ready** - Email notifications, monitoring, error alerts, cron automation
- **CSV output** - Matches exact FanbaseHQ Supabase schema

## Development

- Add new players to `config/players.json`
- Add new Twitter accounts to `config/accounts.json`
- Extend with new scrapers in `scrapers/` directory
- See `PRODUCTION_GUIDE.md` for deployment instructions