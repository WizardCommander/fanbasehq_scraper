"""
Milestone Processing Service
Handles milestone detection and validation from tweets
"""

import logging
from datetime import date
from typing import List, Optional
from dataclasses import dataclass

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import AIParser, MilestoneData
from services.boxscore_stats_service import BoxscoreStatsService

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of milestone processing"""

    milestones: List[MilestoneData]
    tweets_processed: int
    milestones_found: int


class MilestoneProcessingService:
    """Service for processing tweets into validated milestones"""

    def __init__(
        self, ai_parser: AIParser = None, boxscore_service: BoxscoreStatsService = None
    ):
        self.ai_parser = ai_parser or AIParser()
        self.boxscore_service = boxscore_service or BoxscoreStatsService()

    async def process_tweets_to_milestones(
        self,
        tweets: List[ScrapedTweet],
        target_player: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ProcessingResult:
        """
        Process a list of tweets to extract milestones with optional boxscore context

        Args:
            tweets: List of tweets to process
            target_player: The player we're looking for milestones about
            start_date: Optional start date for boxscore context
            end_date: Optional end date for boxscore context

        Returns:
            ProcessingResult with extracted milestones
        """
        # Get boxscore context if date range provided
        boxscore_context = None
        if start_date and end_date:
            try:
                context = await self.boxscore_service.get_boxscore_context_for_ai(
                    player_name=target_player, start_date=start_date, end_date=end_date
                )
                boxscore_context = self.boxscore_service.format_boxscore_for_ai_prompt(
                    context
                )
                logger.info(f"Using boxscore context with {context.total_games} games")
            except Exception as e:
                logger.warning(f"Failed to get boxscore context: {e}")
                boxscore_context = None
        milestones = []
        tweets_processed = 0

        for tweet in tweets:
            tweets_processed += 1

            # Process single tweet for milestone with optional boxscore context
            milestone = await self._process_single_tweet(
                tweet, target_player, boxscore_context
            )

            if milestone:
                milestones.append(milestone)
                logger.info(f"Found milestone: {milestone.title}")
                logger.debug(
                    f"Confidence - Milestone: {milestone.milestone_confidence:.2f}, "
                    f"Attribution: {milestone.attribution_confidence:.2f}"
                )

        logger.info(
            f"Processed {tweets_processed} tweets, found {len(milestones)} milestones"
        )

        return ProcessingResult(
            milestones=milestones,
            tweets_processed=tweets_processed,
            milestones_found=len(milestones),
        )

    async def _process_single_tweet(
        self,
        tweet: ScrapedTweet,
        target_player: str,
        boxscore_context: Optional[str] = None,
    ) -> Optional[MilestoneData]:
        """Process a single tweet for milestone extraction"""
        try:
            # Convert tweet to format expected by AI parser with optional boxscore context
            milestone = self.ai_parser.parse_milestone_tweet(
                tweet_text=tweet.text,
                target_player=target_player,
                tweet_url=tweet.url,
                tweet_id=tweet.id,
                boxscore_context=boxscore_context,
            )

            if milestone:
                logger.debug(
                    f"Milestone extracted from tweet {tweet.id}: {milestone.title}"
                )

            return milestone

        except Exception as e:
            logger.error(f"Error processing tweet {tweet.id}: {e}")
            return None
