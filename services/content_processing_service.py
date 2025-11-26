"""
Generic Content Processing Service
Consolidates milestone and tunnel fit processing into a single reusable service
"""

import logging
from datetime import date
from typing import List, Optional, Callable, Any, Union
from dataclasses import dataclass
from enum import Enum

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import AIParser, MilestoneData, TunnelFitData
from services.boxscore_stats_service import BoxscoreStatsService

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Supported content types for processing"""

    MILESTONE = "milestone"
    TUNNEL_FIT = "tunnel_fit"
    SHOE = "shoe"


@dataclass
class ProcessingResult:
    """Generic result of content processing"""

    content_items: List[Union[MilestoneData, TunnelFitData, Any]]
    posts_processed: int
    items_found: int
    content_type: ContentType


class ContentProcessingService:
    """
    Generic service for processing tweets into any content type
    Consolidates MilestoneProcessingService and TunnelFitProcessingService
    """

    def __init__(
        self,
        ai_parser: Optional[AIParser] = None,
        boxscore_service: Optional[BoxscoreStatsService] = None,
    ):
        self.ai_parser = ai_parser or AIParser()
        self.boxscore_service = boxscore_service or BoxscoreStatsService()

    async def process_tweets(
        self,
        tweets: List[ScrapedTweet],
        content_type: ContentType,
        target_player: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        quality_filter: Optional[Callable[[Any], bool]] = None,
        post_processor: Optional[Callable[[Any, ScrapedTweet], Any]] = None,
    ) -> ProcessingResult:
        """
        Process tweets into content items using AI parser

        Args:
            tweets: List of tweets to process
            content_type: Type of content to extract (milestone, tunnel_fit, etc.)
            target_player: Player name for content extraction
            start_date: Optional start date for filtering/context
            end_date: Optional end date for filtering/context
            quality_filter: Optional function to filter low-quality items
            post_processor: Optional function to post-process items (e.g., override social stats)

        Returns:
            ProcessingResult with extracted content items
        """
        logger.info(
            f"Processing {len(tweets)} tweets for {target_player} {content_type.value}s"
        )

        # Get additional context if needed (milestone-specific)
        additional_context = await self._get_additional_context(
            content_type, target_player, start_date, end_date
        )

        content_items = []
        posts_processed = 0

        for tweet in tweets:
            posts_processed += 1

            # Process single tweet
            item = await self._process_single_tweet(
                tweet=tweet,
                content_type=content_type,
                target_player=target_player,
                additional_context=additional_context,
            )

            if item:
                # Apply quality filter if provided
                if quality_filter and not quality_filter(item):
                    logger.debug(
                        f"Item filtered out by quality check: {self._get_item_description(item)}"
                    )
                    continue

                # Apply post-processor if provided (e.g., override social stats)
                if post_processor:
                    item = post_processor(item, tweet)

                # Apply date filtering if needed (tunnel fit-specific)
                if hasattr(item, "date") and item.date:
                    if start_date and item.date < start_date:
                        logger.debug(f"Item filtered out by start date: {item.date}")
                        continue
                    if end_date and item.date > end_date:
                        logger.debug(f"Item filtered out by end date: {item.date}")
                        continue

                content_items.append(item)
                logger.info(
                    f"Found {content_type.value}: {self._get_item_description(item)}"
                )
                self._log_confidence_scores(item)

        logger.info(
            f"Processed {posts_processed} posts, found {len(content_items)} {content_type.value}s"
        )

        return ProcessingResult(
            content_items=content_items,
            posts_processed=posts_processed,
            items_found=len(content_items),
            content_type=content_type,
        )

    async def _get_additional_context(
        self,
        content_type: ContentType,
        target_player: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> Optional[str]:
        """Get additional context for AI parsing (e.g., boxscore for milestones)"""

        if content_type == ContentType.MILESTONE and start_date and end_date:
            try:
                context = await self.boxscore_service.get_boxscore_context_for_ai(
                    player_name=target_player, start_date=start_date, end_date=end_date
                )
                formatted_context = self.boxscore_service.format_boxscore_for_ai_prompt(
                    context
                )
                logger.info(f"Using boxscore context with {context.total_games} games")
                return formatted_context
            except Exception as e:
                logger.warning(f"Failed to get boxscore context: {e}")
                return None

        return None

    async def _process_single_tweet(
        self,
        tweet: ScrapedTweet,
        content_type: ContentType,
        target_player: str,
        additional_context: Optional[str] = None,
    ) -> Optional[Union[MilestoneData, TunnelFitData, Any]]:
        """Process a single tweet using the appropriate AI parser method"""

        try:
            # Route to appropriate parser method based on content type
            if content_type == ContentType.MILESTONE:
                item = self.ai_parser.parse_milestone_tweet(
                    tweet_text=tweet.text,
                    target_player=target_player,
                    tweet_url=tweet.url,
                    tweet_id=tweet.id,
                    boxscore_context=additional_context,
                )
            elif content_type == ContentType.TUNNEL_FIT:
                item = self.ai_parser.parse_tunnel_fit_tweet(
                    tweet_text=tweet.text,
                    target_player=target_player,
                    tweet_url=tweet.url,
                    tweet_id=tweet.id,
                    tweet_created_at=tweet.created_at,
                )
                # Check if it's actually a tunnel fit
                if item and not item.is_tunnel_fit:
                    return None
            else:
                logger.warning(f"Unsupported content type: {content_type}")
                return None

            if item:
                logger.debug(
                    f"{content_type.value.capitalize()} extracted from tweet {tweet.id}: {self._get_item_description(item)}"
                )

            return item

        except Exception as e:
            logger.error(f"Error processing tweet {tweet.id}: {e}")
            return None

    def _get_item_description(
        self, item: Union[MilestoneData, TunnelFitData, Any]
    ) -> str:
        """Get a brief description of the item for logging"""
        if isinstance(item, MilestoneData):
            return item.title
        elif isinstance(item, TunnelFitData):
            return f"{item.event} on {item.date}"
        else:
            return str(item)

    def _log_confidence_scores(self, item: Union[MilestoneData, TunnelFitData, Any]):
        """Log confidence scores if available"""
        if isinstance(item, MilestoneData):
            logger.debug(
                f"Confidence - Milestone: {item.milestone_confidence:.2f}, "
                f"Attribution: {item.attribution_confidence:.2f}"
            )
        elif isinstance(item, TunnelFitData):
            logger.debug(
                f"Confidence - Fit: {item.fit_confidence:.2f}, "
                f"Date: {item.date_confidence:.2f}"
            )
