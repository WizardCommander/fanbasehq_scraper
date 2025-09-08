"""
Tunnel Fit scraper for Caitlin Clark WNBA data - Following Existing Architecture
"""

import json
import logging
import asyncio
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import CONFIG_DIR, PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
from services.scraper_config import ScraperConfig
from services.twitter_search_service import TwitterSearchService
from services.tunnel_fit_processing_service import TunnelFitProcessingService
from parsers.ai_parser import AIParser
from parsers.tunnel_fit_csv_formatter import TunnelFitCSVFormatter


logger = logging.getLogger(__name__)


class TunnelFitScraper:
    """Main scraper orchestrator for tunnel fits - coordinates services to perform tunnel fit scraping"""

    def __init__(
        self,
        config: ScraperConfig,
        twitter_service: Optional[TwitterSearchService] = None,
        processing_service: Optional[TunnelFitProcessingService] = None,
        csv_formatter: Optional[TunnelFitCSVFormatter] = None,
    ):
        # Validate and store configuration
        config.validate()
        self.config = config

        # Initialize services with dependency injection
        self.twitter_service = twitter_service or TwitterSearchService()
        self.processing_service = processing_service or TunnelFitProcessingService()
        self.csv_formatter = csv_formatter or TunnelFitCSVFormatter(config.output_file)

    @classmethod
    def create_from_legacy_params(
        cls,
        player: str,
        start_date: date,
        end_date: date,
        output_file: str,
        limit: int = 100,
    ) -> "TunnelFitScraper":
        """Factory method for backward compatibility with legacy constructor"""

        # Load configurations the same way as milestone scraper
        player_config = cls._load_player_config(player.lower())
        accounts_config = cls._load_accounts_config()

        # Create config object - use tunnel_fit_accounts for target_accounts
        config = ScraperConfig(
            player=player.lower(),
            player_display_name=player.title(),
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            player_variations=player_config.get("variations", []),
            target_accounts=accounts_config.get("twitter_accounts", {}).get(
                "tunnel_fit_accounts", []
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

    async def scrape_tunnel_fits(self) -> Dict:
        """
        Orchestrate tunnel fit scraping using service layer architecture

        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting tunnel fit scrape for {self.config.player_display_name}")
        logger.info(f"Date range: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Output: {self.config.output_file}")

        # Search Twitter for tweets using tunnel fit accounts
        logger.info(
            f"Searching across {len(self.config.target_accounts)} tunnel fit accounts with {len(self.config.player_variations)} variations"
        )
        search_results = await self.twitter_service.search_tweets_for_player(
            accounts=self.config.target_accounts,
            variations=self.config.player_variations,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            limit=self.config.limit,
        )

        if not search_results:
            logger.warning("No tweets found across all searches")
            await self._write_empty_results()
            return self._create_results_summary(0, 0, [])

        # Process tweets into tunnel fits
        tunnel_fit_batches = []
        total_tweets_processed = 0

        for search_result in search_results:
            logger.info(
                f"Processing {len(search_result.tweets)} tweets from {search_result.account} × {search_result.variation}"
            )

            processing_result = (
                await self.processing_service.process_tweets_to_tunnel_fits(
                    tweets=search_result.tweets,
                    target_player=self.config.player_display_name,
                    start_date=self.config.start_date,
                    end_date=self.config.end_date,
                )
            )

            if processing_result.tunnel_fits:
                tunnel_fit_batches.append(
                    (processing_result.tunnel_fits, search_result.tweets)
                )
                logger.info(f"Found {processing_result.tunnel_fits_found} tunnel fits")

            total_tweets_processed += processing_result.tweets_processed

        # Combine all tunnel fits from different searches and match with source tweets
        if tunnel_fit_batches:
            all_tunnel_fits = []
            all_source_tweets = []
            
            # Create a lookup of all tweets by ID
            tweet_lookup = {}
            for tunnel_fits, tweets in tunnel_fit_batches:
                for tweet in tweets:
                    tweet_lookup[tweet.id] = tweet
            
            # Collect tunnel fits and their corresponding source tweets
            for tunnel_fits, tweets in tunnel_fit_batches:
                for tunnel_fit in tunnel_fits:
                    source_tweet = tweet_lookup.get(tunnel_fit.source_tweet_id.value)
                    if source_tweet:
                        all_tunnel_fits.append(tunnel_fit)
                        all_source_tweets.append(source_tweet)
                    else:
                        logger.warning(f"Could not find source tweet for tunnel fit: {tunnel_fit.event}")

            # Write results to CSV
            await self.csv_formatter.write_tunnel_fits_to_csv(
                tunnel_fits=all_tunnel_fits,
                tweets=all_source_tweets,
                player_name=self.config.player_display_name,
            )

            logger.info(
                f"Scraping complete: {len(all_tunnel_fits)} tunnel fits found"
            )

            return self._create_results_summary(
                len(all_tunnel_fits),
                total_tweets_processed,
                all_tunnel_fits,
            )
        else:
            logger.warning("No tunnel fits found after processing")
            await self._write_empty_results()
            return self._create_results_summary(0, total_tweets_processed, [])

    async def _write_empty_results(self) -> None:
        """Write empty CSV when no results found"""
        try:
            await self.csv_formatter.write_tunnel_fits_to_csv(
                tunnel_fits=[], tweets=[], player_name=self.config.player_display_name
            )
            logger.info("Empty results written to CSV")
        except Exception as e:
            logger.error(f"Error writing empty results: {e}")

    def _create_results_summary(
        self, tunnel_fits_count: int, tweets_processed: int, tunnel_fits: List
    ) -> Dict:
        """Create results summary dictionary"""
        return {
            "player": self.config.player_display_name,
            "date_range": f"{self.config.start_date} to {self.config.end_date}",
            "tunnel_fits_found": tunnel_fits_count,
            "tweets_processed": tweets_processed,
            "output_file": self.config.output_file,
            "tunnel_fits": tunnel_fits,
        }

    def run(self) -> Dict:
        """
        Run the scraper synchronously

        Returns:
            Scraping results dictionary
        """
        return asyncio.run(self.scrape_tunnel_fits())


# Test functions removed for production - see development branch for testing utilities
