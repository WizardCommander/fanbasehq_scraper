"""
Shoe scraper for Caitlin Clark WNBA data - Following Existing Architecture
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import CONFIG_DIR, PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
from services.scraper_config import ScraperConfig
from services.twitter_search_service import TwitterSearchService
from services.shoe_processing_service import ShoeProcessingService
from parsers.ai_parser import AIParser
from parsers.shoe_csv_formatter import ShoeCSVFormatter

logger = logging.getLogger(__name__)


class ShoeScraper:
    """Main scraper orchestrator for shoes - coordinates services to perform shoe scraping"""

    def __init__(
        self,
        config: ScraperConfig,
        twitter_service: Optional[TwitterSearchService] = None,
        processing_service: Optional[ShoeProcessingService] = None,
        csv_formatter: Optional[ShoeCSVFormatter] = None,
    ):
        # Validate and store configuration
        config.validate()
        self.config = config

        # Initialize services with dependency injection
        self.twitter_service = twitter_service or TwitterSearchService()
        self.processing_service = processing_service or ShoeProcessingService()
        self.csv_formatter = csv_formatter or ShoeCSVFormatter(config.output_file)

    @classmethod
    def create_from_legacy_params(
        cls,
        player: str,
        start_date: date,
        end_date: date,
        output_file: str,
        limit: int = 100,
    ) -> "ShoeScraper":
        """Factory method for backward compatibility with legacy constructor"""

        # Load configurations the same way as other scrapers
        player_config = cls._load_player_config(player.lower())
        accounts_config = cls._load_accounts_config()

        # Create config object - use shoe_accounts for target_accounts
        config = ScraperConfig(
            player=player.lower(),
            player_display_name=player.title(),
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            player_variations=player_config.get("variations", []),
            target_accounts=accounts_config.get("twitter_accounts", {}).get(
                "shoe_accounts", []
            ),
        )

        return cls(config)

    @staticmethod
    def _load_player_config(player: str) -> Dict:
        """Load player configuration"""
        with open(PLAYERS_FILE, "r") as f:
            players = json.load(f)

        if player not in players:
            raise ValueError(f"Player '{player}' not found in {PLAYERS_FILE}")

        return players[player]

    @staticmethod
    def _load_accounts_config() -> Dict:
        """Load accounts configuration"""
        with open(TWITTER_ACCOUNTS_FILE, "r") as f:
            return json.load(f)

    async def run(self) -> Dict:
        """
        Run the complete shoe scraping pipeline

        Returns:
            Dict with scraping results and statistics
        """
        logger.info(f"Starting shoe scraping for {self.config.player_display_name}")
        logger.info(f"Date range: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Target accounts: {self.config.target_accounts}")
        logger.info(f"Player variations: {self.config.player_variations}")
        logger.info(f"Limit: {self.config.limit} tweets per account")

        try:
            # Step 1: Search and scrape tweets from shoe accounts
            scraped_tweets, tweet_sources = await self._scrape_tweets_with_sources()
            logger.info(f"Scraped {len(scraped_tweets)} tweets from shoe accounts")

            if not scraped_tweets:
                logger.warning("No tweets found - checking account configuration")
                return {
                    "shoes_found": 0,
                    "tweets_processed": 0,
                    "accounts_searched": len(self.config.target_accounts),
                    "status": "no_tweets_found"
                }

            # Step 2: Process tweets to extract shoes with game stats integration
            processing_result = await self.processing_service.process_tweets_to_shoes(
                scraped_tweets,
                self.config.player_display_name,
                self.config.start_date,
                self.config.end_date,
            )

            logger.info(f"Found {processing_result.shoes_found} shoes from {processing_result.tweets_processed} tweets")

            if not processing_result.shoes:
                logger.warning("No shoes found in tweets")
                return {
                    "shoes_found": 0,
                    "tweets_processed": processing_result.tweets_processed,
                    "accounts_searched": len(self.config.target_accounts),
                    "status": "no_shoes_found"
                }

            # Step 3: Format and save to CSV with source attribution
            csv_count = self.csv_formatter.format_shoes_to_csv(
                processing_result.shoes, tweet_sources
            )

            logger.info(f"Successfully saved {csv_count} shoes to {self.config.output_file}")

            return {
                "shoes_found": processing_result.shoes_found,
                "tweets_processed": processing_result.tweets_processed,
                "accounts_searched": len(self.config.target_accounts),
                "csv_records_written": csv_count,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error during shoe scraping: {e}")
            return {
                "shoes_found": 0,
                "tweets_processed": 0,
                "accounts_searched": len(self.config.target_accounts),
                "error": str(e),
                "status": "error"
            }

    async def _scrape_tweets_with_sources(self):
        """
        Scrape tweets while tracking which account each tweet came from
        
        Returns:
            Tuple of (scraped_tweets, tweet_sources_dict)
        """
        all_tweets = []
        tweet_sources = {}  # tweet_id -> source_account mapping

        # Create search variations that include shoe-specific terms
        shoe_variations = []
        for variation in self.config.player_variations:
            # Add base player variation
            shoe_variations.append(variation)
            # Add shoe-specific combinations
            shoe_variations.extend([
                f"{variation} shoe",
                f"{variation} sneaker", 
                f"{variation} nike",
                f"{variation} kobe",
            ])

        try:
            # Use the existing TwitterSearchService API
            search_results = await self.twitter_service.search_tweets_for_player(
                accounts=self.config.target_accounts,
                variations=shoe_variations,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                limit=self.config.limit
            )

            # Extract tweets and build source mapping
            for result in search_results:
                for tweet in result.tweets:
                    all_tweets.append(tweet)
                    # Map tweet_id to the account it came from
                    tweet_sources[tweet.id] = result.account

            logger.info(f"Found {len(all_tweets)} total tweets from {len(search_results)} successful searches")

        except Exception as e:
            logger.error(f"Error during Twitter search: {e}")

        return all_tweets, tweet_sources