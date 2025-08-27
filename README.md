# Caitlin Clark WNBA Data Scraper

Modular scraper for FanbaseHQ to collect Caitlin Clark milestones, shoes, and tunnel fits from social media.

## Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Set up API keys:**
   - Copy `config/.env.example` to `config/.env`
   - Add your OpenAI API key to `config/.env`

3. **Configure Twitter accounts (twscrape):**
```bash
twscrape add_account username password email password
twscrape login_accounts
```

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
- **Accounts**: `config/accounts.json` - X.com accounts to scrape 
- **Keywords**: `config/keywords.json` - Keywords for pre-filtering
- **Settings**: `config/settings.py` - API keys and general settings

## Output

Generates CSV files matching FanbaseHQ schema in the `output/` directory:
- `milestones.csv` - Player milestone submissions
- `shoes.csv` - Shoe submissions (coming soon)
- `tunnel_fits.csv` - Tunnel fit submissions (coming soon)

## Architecture

- **Modular design** - Easy to add new submission types or players
- **AI-powered parsing** - Uses GPT to extract structured data from tweets
- **Keyword pre-filtering** - Reduces API costs by filtering irrelevant posts
- **CSV output** - Matches exact FanbaseHQ Supabase schema

## Development

- Add new players to `config/players.json`
- Add new X.com accounts to `config/accounts.json` 
- Customize keywords in `config/keywords.json`
- Extend with new scrapers in `scrapers/` directory