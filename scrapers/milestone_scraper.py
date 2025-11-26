"""
Milestone scraper for Caitlin Clark WNBA data - Refactored Architecture
"""

import json
import logging
import asyncio
from datetime import date
from typing import Dict, List, Optional

from config.settings import PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
from services.scraper_config import ScraperConfig
from services.twitter_search_service import TwitterSearchService
from services.content_processing_service import ContentProcessingService, ContentType
from services.result_aggregation_service import ResultAggregationService
from parsers.csv_formatter import MilestoneCSVFormatter


logger = logging.getLogger(__name__)


class MilestoneScraper:
    """Main scraper orchestrator - coordinates services to perform milestone scraping"""

    def __init__(
        self,
        config: ScraperConfig,
        twitter_service: Optional[TwitterSearchService] = None,
        processing_service: Optional[ContentProcessingService] = None,
        aggregation_service: Optional[ResultAggregationService] = None,
        csv_formatter: Optional[MilestoneCSVFormatter] = None,
    ):
        # Validate and store configuration
        config.validate()
        self.config = config

        # Initialize services with dependency injection
        self.twitter_service = twitter_service or TwitterSearchService()
        self.processing_service = processing_service or ContentProcessingService()
        self.aggregation_service = aggregation_service or ResultAggregationService()
        self.csv_formatter = csv_formatter or MilestoneCSVFormatter(config.output_file)

    @classmethod
    def create_from_legacy_params(
        cls,
        player: str,
        start_date: date,
        end_date: date,
        output_file: str,
        limit: int = 100,
    ) -> "MilestoneScraper":
        """Factory method for backward compatibility with legacy constructor"""

        # Load configurations the old way for now
        player_config = cls._load_player_config(player.lower())
        accounts_config = cls._load_accounts_config()

        # Create config object
        config = ScraperConfig(
            player=player.lower(),
            player_display_name=player.title(),
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            player_variations=player_config.get("variations", []),
            target_accounts=accounts_config.get("twitter_accounts", {}).get(
                "milestone_accounts", []
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

    async def scrape_milestones(self) -> Dict:
        """
        Orchestrate milestone scraping using service layer architecture

        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting milestone scrape for {self.config.player_display_name}")
        logger.info(f"Date range: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Output: {self.config.output_file}")

        # Step 1: Setup team information
        await self._setup_team_information()

        # Step 2: Search Twitter for tweets
        logger.info(
            f"Searching across {len(self.config.target_accounts)} accounts with {len(self.config.player_variations)} variations"
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

        # Step 3: Process tweets into milestones
        milestone_batches = []
        total_posts_processed = 0

        for search_result in search_results:
            logger.info(
                f"Processing {len(search_result.tweets)} tweets from {search_result.account} × {search_result.variation}"
            )

            processing_result = await self.processing_service.process_tweets(
                tweets=search_result.tweets,
                content_type=ContentType.MILESTONE,
                target_player=self.config.player_display_name,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
            )

            if processing_result.content_items:
                milestone_batches.append(
                    (processing_result.content_items, search_result.tweets)
                )
                logger.info(f"Found {processing_result.items_found} milestones")

            total_posts_processed += processing_result.posts_processed

        # Step 4: Aggregate and deduplicate results
        if milestone_batches:
            aggregation_result = self.aggregation_service.aggregate_milestone_results(
                milestone_batches
            )

            # Step 5: Write results to CSV
            await self.csv_formatter.write_milestones_to_csv(
                milestones=aggregation_result.milestones,
                tweets=aggregation_result.source_tweets,
                player_name=self.config.player_display_name,
            )

            logger.info(
                f"Scraping complete: {len(aggregation_result.milestones)} unique milestones, "
                f"{aggregation_result.duplicates_removed} duplicates removed"
            )

            return self._create_results_summary(
                len(aggregation_result.milestones),
                total_posts_processed,
                aggregation_result.milestones,
            )
        else:
            logger.warning("No milestones found after processing")
            await self._write_empty_results()
            return self._create_results_summary(0, total_posts_processed, [])

    async def _setup_team_information(self) -> None:
        """Setup team information for the player"""
        try:
            from utils.roster_cache import lookup_player_team_with_id

            # First check if team info already available in config
            if self.config.team_name and self.config.team_id:
                logger.info(
                    f"Using config team info: {self.config.player_display_name} plays for {self.config.team_name} (ID: {self.config.team_id})"
                )
                return

            # Try to lookup team dynamically
            logger.info(
                f"Looking up team information for {self.config.player_display_name}"
            )
            team_info = lookup_player_team_with_id(self.config.player_display_name)

            if team_info:
                self.config.team_name, self.config.team_id = team_info
                logger.info(
                    f"{self.config.player_display_name} plays for {self.config.team_name} (ID: {self.config.team_id})"
                )
            else:
                logger.warning(
                    f"Could not find team for {self.config.player_display_name}"
                )

        except Exception as e:
            logger.error(f"Error setting up team information: {e}")

    async def _write_empty_results(self) -> None:
        """Write empty CSV when no results found"""
        try:
            await self.csv_formatter.write_milestones_to_csv(
                milestones=[], tweets=[], player_name=self.config.player_display_name
            )
            logger.info("Empty results written to CSV")
        except Exception as e:
            logger.error(f"Error writing empty results: {e}")

    def _create_results_summary(
        self, milestones_count: int, posts_processed: int, milestones: List
    ) -> Dict:
        """Create results summary dictionary"""
        return {
            "player": self.config.player_display_name,
            "date_range": f"{self.config.start_date} to {self.config.end_date}",
            "milestones_found": milestones_count,
            "posts_processed": posts_processed,
            "output_file": self.config.output_file,
            "milestones": milestones,
        }

    def run(self) -> Dict:
        """
        Run the scraper synchronously

        Returns:
            Scraping results dictionary
        """
        return asyncio.run(self.scrape_milestones())


# Test functions removed for production - see development branch for testing utilities
