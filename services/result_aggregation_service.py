"""
Result Aggregation Service
Handles deduplication and aggregation of milestone results
"""

import logging
from typing import List, Set, Tuple
from dataclasses import dataclass

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import MilestoneData

logger = logging.getLogger(__name__)


@dataclass
class AggregationResult:
    """Result of milestone aggregation"""

    milestones: List[MilestoneData]
    source_tweets: List[ScrapedTweet]
    duplicates_removed: int
    total_processed: int


class ResultAggregationService:
    """Service for aggregating and deduplicating milestone results"""

    def __init__(self):
        self.processed_tweet_ids: Set[str] = set()

    def aggregate_milestone_results(
        self, milestone_batches: List[Tuple[List[MilestoneData], List[ScrapedTweet]]]
    ) -> AggregationResult:
        """
        Aggregate multiple batches of milestones, removing duplicates

        Args:
            milestone_batches: List of (milestones, tweets) tuples from different searches

        Returns:
            AggregationResult with deduplicated milestones
        """
        final_milestones = []
        final_tweets = []
        duplicates_removed = 0
        total_processed = 0

        for milestones, tweets in milestone_batches:
            dedupe_result = self._deduplicate_batch(milestones, tweets)

            final_milestones.extend(dedupe_result.milestones)
            final_tweets.extend(dedupe_result.source_tweets)
            duplicates_removed += dedupe_result.duplicates_removed
            total_processed += dedupe_result.total_processed

        logger.info(
            f"Aggregation complete: {len(final_milestones)} unique milestones, "
            f"{duplicates_removed} duplicates removed"
        )

        return AggregationResult(
            milestones=final_milestones,
            source_tweets=final_tweets,
            duplicates_removed=duplicates_removed,
            total_processed=total_processed,
        )

    def _deduplicate_batch(
        self, milestones: List[MilestoneData], tweets: List[ScrapedTweet]
    ) -> AggregationResult:
        """
        Remove duplicates from a single batch based on tweet IDs

        Args:
            milestones: Milestones to deduplicate
            tweets: Source tweets for milestones

        Returns:
            AggregationResult with deduplicated batch
        """
        deduplicated_milestones = []
        deduplicated_tweets = []
        duplicates_removed = 0
        tweet_lookup = {tweet.id: tweet for tweet in tweets}

        for milestone in milestones:
            if milestone.source_tweet_id not in self.processed_tweet_ids:
                # Not a duplicate, add to results
                self.processed_tweet_ids.add(milestone.source_tweet_id)
                deduplicated_milestones.append(milestone)

                # Find corresponding tweet
                source_tweet = tweet_lookup.get(milestone.source_tweet_id)
                if source_tweet:
                    deduplicated_tweets.append(source_tweet)
                else:
                    logger.warning(
                        f"Could not find source tweet for milestone: {milestone.title}"
                    )
                    # Use first available tweet as fallback
                    if tweets:
                        deduplicated_tweets.append(tweets[0])
            else:
                # Duplicate found
                duplicates_removed += 1
                logger.debug(
                    f"Skipping duplicate milestone from tweet {milestone.source_tweet_id}: {milestone.title}"
                )

        return AggregationResult(
            milestones=deduplicated_milestones,
            source_tweets=deduplicated_tweets,
            duplicates_removed=duplicates_removed,
            total_processed=len(milestones),
        )

    def reset_duplicate_tracking(self):
        """Reset the duplicate tracking for a new scraping session"""
        self.processed_tweet_ids.clear()
        logger.debug("Duplicate tracking reset")
