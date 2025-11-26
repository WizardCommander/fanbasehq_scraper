"""
Configuration settings for the scraper
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in config folder
config_dir = Path(__file__).parent
load_dotenv(config_dir / ".env")

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")

# TwitterAPI.io Configuration
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
if not TWITTER_API_KEY:
    raise ValueError(
        "TWITTER_API_KEY not found in .env file. Get your API key from https://twitterapi.io/dashboard"
    )

# Scrape Creators Instagram API (optional for multi-source tunnel fits)
SCRAPE_CREATORS_API_KEY = os.getenv("SCRAPE_CREATORS_API_KEY", "")

# Oxylabs API (for Google Lens visual search - shopping link discovery)
OXYLABS_USERNAME = os.getenv("OXYLABS_USERNAME", "")
OXYLABS_PASSWORD = os.getenv("OXYLABS_PASSWORD", "")

# TwitterAPI.io Settings
TWITTER_API_BASE_URL = "https://api.twitterapi.io"
TWITTER_API_TIMEOUT = 30  # seconds
TWEETS_PER_PAGE = 20  # TwitterAPI.io returns up to 20 tweets per page

# Configuration Files
TWITTER_ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"
PLAYERS_FILE = CONFIG_DIR / "players.json"

# TwitterAPI.io free tier: 1 request per 5 seconds
DEFAULT_RATE_LIMIT_DELAY = 8  # seconds between requests (free tier limit + buffer)
MAX_RETRIES = 3

# Scraper Types Configuration
SCRAPER_TYPES = ["milestones", "shoes", "tunnel-fits"]

# CSV Configuration
CSV_ENCODING = "utf-8"
CSV_DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f%z"

# Date Resolution Confidence Thresholds
HIGH_CONFIDENCE_THRESHOLD = (
    0.8  # Minimum confidence to use AI-extracted dates (conservative)
)
BOXSCORE_ANALYSIS_CONFIDENCE = 0.9  # High confidence for boxscore-derived dates
GAME_SCHEDULE_CONFIDENCE = 0.7  # Confidence when using game schedule inference
TEXT_PARSING_CONFIDENCE = 0.8  # Confidence when parsing dates from text
FALLBACK_CONFIDENCE = 0.3  # Confidence when falling back to tweet date
MINIMUM_DATE_CONFIDENCE = (
    0.7  # Minimum confidence to assign any date (leave blank below this)
)

# Cache Configuration
DEFAULT_CACHE_HOURS = 6  # Default cache expiration time
CURRENT_SEASON_CACHE_HOURS = 1  # Cache time for current season data

# AI Parser Configuration (GPT)
GPT_MODEL = "gpt-4o-mini"
GPT_MAX_TOKENS = 1000
GPT_TEMPERATURE = 0.1  # Low temperature for consistent parsing

# Client Submission Configuration
CLIENT_SUBMITTER_NAME = "sage3313"
CLIENT_SUBMITTER_EMAIL = "sage3313@gmail.com"
CLIENT_USER_ID = "d5365abd-aa91-4de6-8041-5b9136ea2a66"
CLIENT_ORIGINAL_SUBMISSION_ID = ""  # Blank as requested

# Email Configuration
# SendGrid HTTP API (recommended - uses HTTPS port 443, no blocking issues)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv(
    "SENDGRID_FROM_EMAIL", ""
)  # FROM address (must be verified sender in SendGrid)
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")

# Legacy SMTP Configuration (deprecated - use SendGrid API instead)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "120"))

# Monitoring Configuration
ENABLE_EMAIL_DELIVERY = os.getenv("ENABLE_EMAIL_DELIVERY", "true").lower() == "true"
ENABLE_ERROR_ALERTS = os.getenv("ENABLE_ERROR_ALERTS", "true").lower() == "true"
HEALTH_CHECK_DAYS = int(os.getenv("HEALTH_CHECK_DAYS", "3"))

# Tunnel Fits Multi-Player Configuration

# Oxylabs for Google Lens reverse image search
OXYLABS_RATE_LIMIT_DELAY = 1.0  # Seconds between API calls
OXYLABS_MAX_RESULTS_PER_ITEM = 5  # Max shop links per outfit item

# Vision Analysis Confidence Thresholds
VISION_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence for outfit pieces
AUTO_PUBLISH_THRESHOLD = 0.85  # Auto-publish tunnel fits above this confidence
MANUAL_REVIEW_THRESHOLD = 0.60  # Manual review between 0.60-0.85, reject below 0.60

# Photo Source Priorities
PHOTO_SOURCE_PRIORITY = {
    "twitter": 1,  # Prioritize curated Twitter accounts
    "instagram": 2,  # Fallback to Instagram
}

# Vision API Settings
VISION_MODEL = "gpt-4o-mini"  # Cost-effective vision model
VISION_MAX_TOKENS = 1500  # Max tokens for outfit analysis
VISION_TEMPERATURE = 0.1  # Low temperature for consistent analysis


# Instagram Photo Settings
INSTAGRAM_CACHE_HOURS = 6  # Cache Instagram data for 6 hours
INSTAGRAM_PHOTOS_LIMIT = 50  # Max photos to fetch per player
INSTAGRAM_DAYS_LOOKBACK = 30  # Only fetch posts from last 30 days

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# Settings object for easier import
class Settings:
    """Settings object for convenient access to configuration values"""

    # API Keys
    openai_api_key = OPENAI_API_KEY
    twitter_api_key = TWITTER_API_KEY
    scrape_creators_api_key = SCRAPE_CREATORS_API_KEY
    oxylabs_username = OXYLABS_USERNAME
    oxylabs_password = OXYLABS_PASSWORD

    # Paths
    project_root = PROJECT_ROOT
    config_dir = CONFIG_DIR
    output_dir = OUTPUT_DIR


settings = Settings()
