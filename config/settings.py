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

# TwitterAPI.io Configuration
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY', '')
if not TWITTER_API_KEY:
    raise ValueError("TWITTER_API_KEY not found in .env file. Get your API key from https://twitterapi.io/dashboard")

# TwitterAPI.io Settings
TWITTER_API_BASE_URL = "https://api.twitterapi.io"
TWITTER_API_TIMEOUT = 30  # seconds
TWEETS_PER_PAGE = 20  # TwitterAPI.io returns up to 20 tweets per page

# Configuration Files
TWITTER_ACCOUNTS_FILE = CONFIG_DIR / 'accounts.json'
PLAYERS_FILE = CONFIG_DIR / 'players.json'

# TwitterAPI.io free tier: 1 request per 5 seconds
DEFAULT_RATE_LIMIT_DELAY = 8  # seconds between requests (free tier limit + buffer)  
MAX_RETRIES = 3

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