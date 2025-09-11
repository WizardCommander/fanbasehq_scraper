"""
Shoe Processing Service
Handles shoe detection and validation from tweets with game stats integration
"""

import logging
from datetime import date, timedelta
from typing import List, Optional, Dict
from dataclasses import dataclass

from utils.twitterapi_client import ScrapedTweet
from utils.player_game_logs import PlayerGameLogService, GameStats
from parsers.ai_parser import AIParser, ShoeData

logger = logging.getLogger(__name__)


@dataclass
class ShoeProcessingResult:
    """Result of shoe processing"""

    shoes: List[ShoeData]
    tweets_processed: int
    shoes_found: int


class ShoeProcessingService:
    """Service for processing tweets into validated shoes with game stats integration"""

    def __init__(self, ai_parser: AIParser = None, game_log_service: PlayerGameLogService = None):
        self.ai_parser = ai_parser or AIParser()
        self.game_log_service = game_log_service or PlayerGameLogService()

    async def process_tweets_to_shoes(
        self,
        tweets: List[ScrapedTweet],
        target_player: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ShoeProcessingResult:
        """
        Process a list of tweets to extract shoes with game stats integration

        Args:
            tweets: List of tweets to process
            target_player: The player we're looking for shoes about
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            ShoeProcessingResult with shoes found
        """
        logger.info(f"Processing {len(tweets)} tweets for {target_player} shoes")

        shoes = []
        tweets_processed = 0

        for tweet in tweets:
            tweets_processed += 1
            logger.debug(
                f"Processing tweet {tweets_processed}/{len(tweets)}: {tweet.text[:100]}..."
            )

            try:
                # Parse tweet for shoe information
                shoe = self.ai_parser.parse_shoe_tweet(
                    tweet_text=tweet.text,
                    target_player=target_player,
                    tweet_url=tweet.url,
                    tweet_id=tweet.id,
                    tweet_created_at=tweet.created_at,
                )

                if shoe and shoe.is_shoe_post:
                    # Override AI-extracted social stats with real Twitter metrics
                    shoe.social_stats = {
                        "views": tweet.view_count,
                        "likes": tweet.like_count,
                        "retweets": tweet.retweet_count,
                        "replies": tweet.reply_count,
                        "quotes": tweet.quote_count,
                    }

                    # Apply date filtering if specified
                    if self._should_include_by_date(shoe, start_date, end_date):
                        # Add game stats integration - this is the key differentiator
                        await self._integrate_game_stats(shoe, target_player)
                        shoes.append(shoe)
                        logger.info(f"Found shoe: {shoe.shoe_name}")
                    else:
                        logger.debug(f"Shoe excluded by date filter: {shoe.shoe_name}")

            except Exception as e:
                logger.error(f"Error processing tweet for shoes: {e}")
                continue

        logger.info(f"Found {len(shoes)} shoes from {tweets_processed} tweets")
        return ShoeProcessingResult(
            shoes=shoes,
            tweets_processed=tweets_processed,
            shoes_found=len(shoes)
        )

    async def _integrate_game_stats(self, shoe: ShoeData, target_player: str) -> None:
        """
        Integrate game statistics for a shoe based on when it was posted/worn
        
        This builds the complex game_stats JSON structure required by the CSV schema
        """
        if not shoe.date:
            logger.debug(f"No date available for shoe {shoe.shoe_name}, skipping game stats")
            return

        try:
            # Find games within ±7 days of the shoe post date
            # This represents the "wearing period" for this shoe
            search_start = shoe.date - timedelta(days=7)
            search_end = shoe.date + timedelta(days=7)

            games_in_range = await self.game_log_service.get_player_stats_in_date_range(
                target_player, search_start, search_end
            )

            if not games_in_range:
                logger.debug(f"No games found near {shoe.date} for {shoe.shoe_name}")
                return

            # Build the game_stats JSON structure matching the CSV schema
            games_array = []
            total_points = 0
            total_assists = 0
            total_rebounds = 0
            total_minutes = 0
            best_game = None
            best_game_points = -1

            for game in games_in_range:
                game_dict = {
                    "date": game.date.isoformat(),
                    "points": game.points,
                    "assists": game.assists,
                    "rebounds": game.rebounds,
                    "blocks": getattr(game, 'blocks', 0),  # May not exist in GameStats
                    "steals": getattr(game, 'steals', 0),  # May not exist in GameStats
                    "minutes": game.minutes or 0,
                    "opponent": game.opponent,
                }
                games_array.append(game_dict)

                # Track totals for averages
                total_points += game.points
                total_assists += game.assists
                total_rebounds += game.rebounds
                total_minutes += game.minutes or 0

                # Find best game (highest scoring)
                if game.points > best_game_points:
                    best_game_points = game.points
                    best_game = game_dict

            games_played = len(games_in_range)
            
            # Build the complete game_stats structure
            game_stats = {
                "games": games_array,
                "summary": {
                    "gamesPlayed": games_played,
                    "totalMinutes": total_minutes,
                    "pointsPerGame": round(total_points / games_played, 1) if games_played > 0 else 0,
                    "assistsPerGame": round(total_assists / games_played, 1) if games_played > 0 else 0,
                    "reboundsPerGame": round(total_rebounds / games_played, 1) if games_played > 0 else 0,
                    "blocksPerGame": 0,  # Would need to be calculated if available
                    "stealsPerGame": 0,  # Would need to be calculated if available
                    "bestGame": best_game,
                }
            }

            # Store the game stats in the shoe object (we'll use this in CSV formatting)
            shoe.game_stats = game_stats
            
            logger.info(f"Integrated {games_played} games for shoe {shoe.shoe_name}")

        except Exception as e:
            logger.error(f"Error integrating game stats for {shoe.shoe_name}: {e}")

    def _should_include_by_date(
        self, shoe: ShoeData, start_date: Optional[date], end_date: Optional[date]
    ) -> bool:
        """Check if shoe should be included based on date filtering"""
        if not shoe.date:
            return True  # Include if no date (can't filter)

        if start_date and shoe.date < start_date:
            return False

        if end_date and shoe.date > end_date:
            return False

        return True