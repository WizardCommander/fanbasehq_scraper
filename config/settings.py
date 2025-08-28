"""
Configuration settings for the scraper
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in config folder
config_dir = Path(__file__).parent
load_dotenv(config_dir / '.env')

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / 'config'
OUTPUT_DIR = PROJECT_ROOT / 'output'

# API Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")

# X.com Cookie Authentication
X_COOKIES = os.getenv('X_COOKIES', '')
if not X_COOKIES:
    raise ValueError("X_COOKIES not found in .env file")

# Twitter/X.com Configuration
TWITTER_ACCOUNTS_FILE = CONFIG_DIR / 'accounts.json'
TWITTER_KEYWORDS_FILE = CONFIG_DIR / 'keywords.json'
PLAYERS_FILE = CONFIG_DIR / 'players.json'

# Scraping Configuration
DEFAULT_RATE_LIMIT_DELAY = 5  # seconds between requests (increased for rate limiting)
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30  # seconds

# CSV Configuration
CSV_ENCODING = 'utf-8'
CSV_DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f%z'

# AI Parser Configuration (GPT)
GPT_MODEL = 'gpt-3.5-turbo'  # Can upgrade to 'gpt-4' later if needed
GPT_MAX_TOKENS = 1000
GPT_TEMPERATURE = 0.1  # Low temperature for consistent parsing

# Logging Configuration
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'