"""
Shoe scraper for Caitlin Clark WNBA data - KixStats Integration
"""

import json
import logging
from datetime import date
from typing import Dict, List, Optional

from config.settings import CONFIG_DIR, PLAYERS_FILE
from services.scraper_config import ScraperConfig
from services.kixstats_service import KixStatsService
from parsers.shoe_csv_formatter import ShoeCSVFormatter

logger = logging.getLogger(__name__)


class ShoeScraper:
    """Main scraper orchestrator for shoes - uses KixStats for game-by-game shoe data"""

    def __init__(
        self,
        config: ScraperConfig,
        kixstats_service: Optional[KixStatsService] = None,
        csv_formatter: Optional[ShoeCSVFormatter] = None,
    ):
        # Validate and store configuration
        config.validate()
        self.config = config

        # Initialize services with dependency injection
        self.kixstats_service = kixstats_service or KixStatsService()
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

        # Load player configuration
        player_config = cls._load_player_config(player.lower())

        # Create config object - KixStats doesn't need Twitter accounts
        config = ScraperConfig(
            player=player.lower(),
            player_display_name=player.title(),
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            player_variations=player_config.get("variations", []),
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

    async def run(self) -> Dict:
        """
        Run the complete shoe scraping pipeline using KixStats

        Returns:
            Dict with scraping results and statistics
        """
        logger.info(
            f"Starting KixStats shoe scraping for {self.config.player_display_name}"
        )
        logger.info(f"Date range: {self.config.start_date} to {self.config.end_date}")

        try:
            # Step 1: Get player ID for KixStats
            player_id = KixStatsService.get_player_id_from_name(self.config.player)
            logger.info(f"Using KixStats player ID: {player_id}")

            # Step 2: Scrape game shoe data from KixStats
            game_shoes = await self.kixstats_service.scrape_player_games(
                player_id=player_id, player_name=self.config.player_display_name
            )

            logger.info(f"Scraped {len(game_shoes)} games from KixStats")

            if not game_shoes:
                logger.warning("No game data found from KixStats")
                return {
                    "shoes_found": 0,
                    "games_processed": 0,
                    "status": "no_games_found",
                }

            # Step 3: Filter by date range
            filtered_games = [
                game
                for game in game_shoes
                if self.config.start_date <= game.game_date <= self.config.end_date
            ]

            logger.info(f"Filtered to {len(filtered_games)} games in date range")

            # Step 4: Format and save to CSV (enhanced with KicksCrew and colorway data)
            # Enable colorway enhancement if configured
            self.csv_formatter._should_enhance_colorways = self.config.enhance_colorways

            csv_count = await self.csv_formatter.format_game_shoes_to_csv(
                filtered_games
            )

            logger.info(
                f"Successfully saved {csv_count} game shoes to {self.config.output_file}"
            )

            return {
                "shoes_found": csv_count,
                "games_processed": len(game_shoes),
                "games_in_range": len(filtered_games),
                "csv_records_written": csv_count,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Error during KixStats shoe scraping: {e}")
            return {
                "shoes_found": 0,
                "games_processed": 0,
                "error": str(e),
                "status": "error",
            }
