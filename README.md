# Caitlin Clark Data Scraper

**Automatically collect Caitlin Clark's milestones, shoes, and tunnel fits from social media**

This tool runs daily to gather data and email you CSV files ready for import into your database.

## ⚡ Quick Start

**For non-technical users**: Follow the complete [Setup Guide](SETUP_GUIDE.md) for step-by-step instructions.

**For technical users**:

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

2. **Configure API keys:**
   - Copy `deployment/.env.production.example` to `config/.env`
   - Add your OpenAI API key (get from https://platform.openai.com)
   - Add your TwitterAPI.io API key (get from https://twitterapi.io)
   - Add your email settings for daily notifications

3. **Test the scraper:**
```bash
python main.py --player "caitlin clark" --type milestones --start-date 2024-10-01 --end-date 2024-10-01
```

## 📊 What You Get

**Daily email with 3 CSV files:**
- **milestones.csv** - Records, achievements, stats milestones
- **shoes.csv** - Game shoes with performance stats and pricing
- **tunnel_fits.csv** - Outfit details and shopping links

## 🔧 Manual Usage

### Run scrapers manually:
```bash
# Get yesterday's milestones
python main.py --player "caitlin clark" --type milestones

# Get shoes from specific date range
python main.py --player "caitlin clark" --type shoes --start-date 2024-04-01 --end-date 2024-08-27

# Get tunnel fits with custom output file
python main.py --player "caitlin clark" --type tunnel-fits --output custom_fits.csv

# See what would be scraped (test mode)
python main.py --player "caitlin clark" --type milestones --dry-run
```

> 💡 **Auto Virtual Environment**: The scraper automatically detects and activates the virtual environment if needed. No need to manually run `source venv/bin/activate` first!

## 📁 Key Files

- **config/.env** - Your API keys and email settings
- **config/players.json** - Player name variations for search
- **config/accounts.json** - Twitter accounts to monitor
- **output/** - CSV files generated daily
- **SETUP_GUIDE.md** - Complete setup instructions

## 🏗️ How It Works

1. **Searches Twitter** - Monitors specific accounts for mentions of Caitlin Clark
2. **AI Analysis** - OpenAI GPT-4o-mini extracts structured data from tweets
3. **Game Data Integration** - Adds real game stats from SportDataverse and KixStats
4. **Smart Deduplication** - Removes duplicate content across different sources
5. **CSV Export** - Formats everything to match your database schema
6. **Email Delivery** - Sends daily results automatically

## 🚀 Production Setup

For complete deployment on a server with automatic daily runs, see the [Setup Guide](SETUP_GUIDE.md).

## 👥 Adding More Players

Edit `config/players.json` to add new players and `config/accounts.json` to monitor additional Twitter accounts.