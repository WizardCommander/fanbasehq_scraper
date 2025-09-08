"""
Result Aggregation Service
Handles deduplication and aggregation of milestone results
"""

import logging
from typing import List, Set, Tuple, Dict
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

        # Apply semantic deduplication across all milestones
        semantic_result = self._semantic_deduplication(final_milestones, final_tweets)
        final_milestones = semantic_result.milestones
        final_tweets = semantic_result.source_tweets
        duplicates_removed += semantic_result.duplicates_removed

        logger.info(
            f"Aggregation complete: {len(final_milestones)} unique milestones, "
            f"{duplicates_removed} total duplicates removed ({semantic_result.duplicates_removed} semantic)"
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
            if milestone.source_tweet_id.value not in self.processed_tweet_ids:
                # Not a duplicate, add to results
                self.processed_tweet_ids.add(milestone.source_tweet_id.value)
                deduplicated_milestones.append(milestone)

                # Find corresponding tweet
                source_tweet = tweet_lookup.get(milestone.source_tweet_id.value)
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
                    f"Skipping duplicate milestone from tweet {milestone.source_tweet_id.value}: {milestone.title}"
                )

        return AggregationResult(
            milestones=deduplicated_milestones,
            source_tweets=deduplicated_tweets,
            duplicates_removed=duplicates_removed,
            total_processed=len(milestones),
        )

    def _semantic_deduplication(
        self, milestones: List[MilestoneData], tweets: List[ScrapedTweet]
    ) -> AggregationResult:
        """
        Apply semantic deduplication to remove milestones with similar meaning

        Args:
            milestones: List of milestones to deduplicate
            tweets: Corresponding tweets

        Returns:
            AggregationResult with semantic duplicates removed
        """
        from utils.deduplication import MilestoneDeduplicator

        if not milestones:
            return AggregationResult([], [], 0, 0)

        deduplicator = MilestoneDeduplicator(similarity_threshold=85.0)
        tweet_lookup = {tweet.id: tweet for tweet in tweets}

        # Group milestones by categories for more efficient comparison
        category_groups = self._group_by_categories(milestones)

        final_milestones = []
        final_tweets = []
        semantic_duplicates_removed = 0

        # Process each category group separately
        for category, group_milestones in category_groups.items():
            if len(group_milestones) <= 1:
                # No duplicates possible in single milestone
                final_milestones.extend(group_milestones)
                continue

            # Find duplicate groups within this category
            duplicate_groups = []
            processed_indices = set()

            for i, milestone1 in enumerate(group_milestones):
                if i in processed_indices:
                    continue

                current_group = [milestone1]
                processed_indices.add(i)

                # Compare with remaining milestones in category
                for j, milestone2 in enumerate(group_milestones[i + 1 :], i + 1):
                    if j in processed_indices:
                        continue

                    # Convert to dict format for deduplicator
                    m1_dict = self._milestone_to_dict(milestone1)
                    m2_dict = self._milestone_to_dict(milestone2)

                    duplication_result = deduplicator.check_duplication(
                        m1_dict, m2_dict
                    )

                    if duplication_result.is_duplicate:
                        current_group.append(milestone2)
                        processed_indices.add(j)
                        logger.debug(
                            f"Found semantic duplicate: '{milestone1.title[:50]}...' vs '{milestone2.title[:50]}...' "
                            f"(similarity: {duplication_result.similarity_score:.1f}%, type: {duplication_result.match_type})"
                        )

                duplicate_groups.append(current_group)

            # Select best milestone from each duplicate group
            for group in duplicate_groups:
                if len(group) > 1:
                    semantic_duplicates_removed += len(group) - 1
                    group_dicts = [self._milestone_to_dict(m) for m in group]
                    best_dict = deduplicator.find_best_milestone(group_dicts)
                    best_milestone = self._dict_to_milestone(best_dict, group)
                else:
                    best_milestone = group[0]

                final_milestones.append(best_milestone)

        # Reconstruct tweet list for final milestones
        for milestone in final_milestones:
            source_tweet = tweet_lookup.get(milestone.source_tweet_id.value)
            if source_tweet:
                final_tweets.append(source_tweet)

        logger.info(
            f"Semantic deduplication removed {semantic_duplicates_removed} duplicates"
        )

        return AggregationResult(
            milestones=final_milestones,
            source_tweets=final_tweets,
            duplicates_removed=semantic_duplicates_removed,
            total_processed=len(milestones),
        )

    def _group_by_categories(
        self, milestones: List[MilestoneData]
    ) -> Dict[str, List[MilestoneData]]:
        """Group milestones by their primary categories for efficient comparison"""
        groups = {}

        for milestone in milestones:
            # Use first category as primary grouping key
            primary_category = (
                milestone.categories[0] if milestone.categories else "uncategorized"
            )

            if primary_category not in groups:
                groups[primary_category] = []
            groups[primary_category].append(milestone)

        return groups

    def _milestone_to_dict(self, milestone: MilestoneData) -> Dict[str, any]:
        """Convert MilestoneData to dict format for deduplicator"""
        return {
            "title": milestone.title,
            "categories": milestone.categories,
            "value": milestone.value,
            "description": milestone.description,
            "content_hash": milestone.content_hash,
            "source_reliability": milestone.source_reliability,
            "source_tweet_url": f"https://twitter.com/unknown/status/{milestone.source_tweet_id.value}",
            "source_tweet_id": milestone.source_tweet_id.value,
        }

    def _dict_to_milestone(
        self, milestone_dict: Dict[str, any], original_group: List[MilestoneData]
    ) -> MilestoneData:
        """Find the original MilestoneData object that matches the selected dict"""
        target_tweet_id = milestone_dict.get("source_tweet_id")

        for milestone in original_group:
            if milestone.source_tweet_id.value == target_tweet_id:
                return milestone

        # Fallback to first milestone if match not found
        return original_group[0]

    def reset_duplicate_tracking(self):
        """Reset the duplicate tracking for a new scraping session"""
        self.processed_tweet_ids.clear()
        logger.debug("Duplicate tracking reset")
