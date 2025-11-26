"""
Photo Aggregation Service
Combines Instagram and Twitter photo sources into a unified tunnel fit photo stream
"""

import logging
import asyncio
from datetime import date, datetime
from typing import List, Optional, Dict, Set
from dataclasses import dataclass
import hashlib
from collections import defaultdict

from services.instagram_photo_service import InstagramPhotoService, InstagramPost
from utils.twitterapi_client import TwitterAPIClient, ScrapedTweet

logger = logging.getLogger(__name__)


@dataclass
class UnifiedPhoto:
    """Unified photo from any source (Instagram or Twitter)"""

    photo_id: str  # Unique ID (hash of image URL)
    image_url: str
    source: str  # "instagram" or "twitter"
    source_handle: str  # "@username" or "username"
    post_url: str  # Link to original post
    caption: str
    posted_at: datetime
    engagement: Dict[str, int]  # {"likes": X, "comments": Y, "retweets": Z}
    is_tunnel_fit_candidate: bool = False
    confidence_score: float = 0.0
    quality_score: float = 0.0  # Image quality/resolution estimate


class PhotoAggregationService:
    """Service for aggregating tunnel fit photos from multiple sources"""

    def __init__(
        self,
        instagram_service: Optional[InstagramPhotoService] = None,
        twitter_client: Optional[TwitterAPIClient] = None,
    ):
        """
        Initialize photo aggregation service

        Args:
            instagram_service: InstagramPhotoService instance (optional)
            twitter_client: TwitterAPIClient instance (optional)
        """
        self.instagram_service = instagram_service
        self.twitter_client = twitter_client

    async def get_all_tunnel_photos(
        self,
        player_name: str,
        start_date: date,
        end_date: date,
        instagram_handle: Optional[str] = None,
        twitter_accounts: Optional[List[str]] = None,
        limit_per_source: int = 50,
    ) -> List[UnifiedPhoto]:
        """
        Get tunnel fit photos from all available sources

        Args:
            player_name: Player name (e.g., "Caitlin Clark")
            start_date: Start date for photo search
            end_date: End date for photo search
            instagram_handle: Instagram handle (e.g., "@caitlinclark22")
            twitter_accounts: List of Twitter accounts to search (e.g., ["@caitlinclarksty"])
            limit_per_source: Max photos per source

        Returns:
            Deduplicated list of UnifiedPhoto objects, sorted by quality
        """
        all_photos: List[UnifiedPhoto] = []

        # Fetch from Instagram
        if instagram_handle and self.instagram_service:
            instagram_photos = await self._fetch_instagram_photos(
                instagram_handle, start_date, end_date, limit_per_source
            )
            all_photos.extend(instagram_photos)
            logger.info(f"Fetched {len(instagram_photos)} photos from Instagram")

        # Fetch from Twitter
        if twitter_accounts and self.twitter_client:
            twitter_photos = await self._fetch_twitter_photos(
                player_name, twitter_accounts, start_date, end_date, limit_per_source
            )
            all_photos.extend(twitter_photos)
            logger.info(f"Fetched {len(twitter_photos)} photos from Twitter")

        # Deduplicate by image hash
        deduplicated_photos = self._deduplicate_photos(all_photos)

        # Score and sort photos by quality
        scored_photos = self._score_photo_quality(deduplicated_photos)

        keyword_tagged = len([p for p in scored_photos if p.is_tunnel_fit_candidate])
        logger.info(
            f"Aggregated {len(scored_photos)} photos "
            f"({keyword_tagged} tagged by keywords) from {len(all_photos)} total photos"
        )

        return scored_photos

    async def _fetch_instagram_photos(
        self,
        instagram_handle: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> List[UnifiedPhoto]:
        """Fetch photos from Instagram"""
        try:
            # Calculate days since start_date (clamped to 365 per Bright Data guidance)
            days_ago = max((date.today() - start_date).days, 1)
            lookback_days = min(days_ago, 365)

            # Fetch Instagram posts
            posts = await self.instagram_service.get_recent_posts(
                instagram_handle=instagram_handle,
                limit=limit,
                since_days=lookback_days,
            )

            # Filter by date range (fallback to all posts when Bright Data timestamps differ)
            filtered_posts = [
                p for p in posts if start_date <= p.posted_at.date() <= end_date
            ]

            if not filtered_posts and posts:
                earliest = min(p.posted_at.date() for p in posts)
                latest = max(p.posted_at.date() for p in posts)
                logger.warning(
                    "Instagram returned %d posts between %s and %s but "
                    "none landed inside %s → %s. Using all posts.",
                    len(posts),
                    earliest,
                    latest,
                    start_date,
                    end_date,
                )
                filtered_posts = posts

            # Score tunnel fit likelihood but keep all posts for downstream AI filtering
            scored_posts = self.instagram_service.filter_tunnel_fit_candidates(
                filtered_posts
            )

            # Convert to UnifiedPhoto objects
            unified_photos = []
            for post in scored_posts:
                unified = self._convert_instagram_to_unified(post)
                unified_photos.append(unified)

            return unified_photos

        except Exception as e:
            logger.error(f"Error fetching Instagram photos: {e}")
            return []

    async def _fetch_twitter_photos(
        self,
        player_name: str,
        twitter_accounts: List[str],
        start_date: date,
        end_date: date,
        limit: int,
    ) -> List[UnifiedPhoto]:
        """Fetch photos from Twitter accounts"""
        try:
            all_twitter_photos = []

            for account in twitter_accounts:
                # Search tweets from this account
                tweets = await self.twitter_client.search_tweets(
                    query=f"from:{account.lstrip('@')} {player_name}",
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                )

                # Filter tweets with images
                tweets_with_images = [t for t in tweets if t.images]

                # Convert to UnifiedPhoto objects
                for tweet in tweets_with_images:
                    for image_url in tweet.images:
                        unified = self._convert_twitter_to_unified(
                            tweet, image_url, account
                        )
                        all_twitter_photos.append(unified)

            return all_twitter_photos

        except Exception as e:
            logger.error(f"Error fetching Twitter photos: {e}")
            return []

    def _convert_instagram_to_unified(self, post: InstagramPost) -> UnifiedPhoto:
        """Convert InstagramPost to UnifiedPhoto"""
        photo_id = self._generate_photo_id(post.image_url)

        return UnifiedPhoto(
            photo_id=photo_id,
            image_url=post.image_url,
            source="instagram",
            source_handle=post.instagram_handle,
            post_url=post.post_url or f"https://www.instagram.com/p/{post.post_id}/",
            caption=post.caption,
            posted_at=post.posted_at,
            engagement={
                "likes": post.likes,
                "comments": post.comments,
                "retweets": 0,
            },
            is_tunnel_fit_candidate=post.is_tunnel_fit_candidate,
            confidence_score=post.confidence_score,
        )

    def _convert_twitter_to_unified(
        self, tweet: ScrapedTweet, image_url: str, account: str
    ) -> UnifiedPhoto:
        """Convert Twitter tweet to UnifiedPhoto"""
        photo_id = self._generate_photo_id(image_url)

        return UnifiedPhoto(
            photo_id=photo_id,
            image_url=image_url,
            source="twitter",
            source_handle=account,
            post_url=f"https://twitter.com/{account.lstrip('@')}/status/{tweet.id}",
            caption=tweet.text,
            posted_at=tweet.created_at,
            engagement={
                "likes": tweet.like_count,
                "comments": tweet.reply_count,
                "retweets": tweet.retweet_count,
            },
            is_tunnel_fit_candidate=True,  # Twitter accounts are curated
            confidence_score=0.9,  # High confidence for curated accounts
        )

    def _generate_photo_id(self, image_url: str) -> str:
        """Generate unique photo ID from image URL"""
        return hashlib.md5(image_url.encode()).hexdigest()

    def _deduplicate_photos(self, photos: List[UnifiedPhoto]) -> List[UnifiedPhoto]:
        """
        Deduplicate photos by image hash

        If same image appears from multiple sources, keep the highest quality one

        Args:
            photos: List of UnifiedPhoto objects

        Returns:
            Deduplicated list
        """
        # Group by photo_id
        photo_groups: Dict[str, List[UnifiedPhoto]] = defaultdict(list)
        for photo in photos:
            photo_groups[photo.photo_id].append(photo)

        # Select best photo from each group
        deduplicated = []
        for photo_id, group in photo_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Multiple sources for same image - select best one
                best_photo = self._select_best_photo(group)
                deduplicated.append(best_photo)
                logger.info(
                    f"Deduplicated {len(group)} copies of photo {photo_id[:8]}... "
                    f"(kept {best_photo.source})"
                )

        return deduplicated

    def _select_best_photo(self, photos: List[UnifiedPhoto]) -> UnifiedPhoto:
        """
        Select the best photo from duplicates

        Priority:
        1. Curated Twitter accounts (highest confidence)
        2. Instagram official accounts
        3. Highest engagement
        4. Most recent
        """

        # Sort by priority
        def photo_priority(photo: UnifiedPhoto) -> tuple:
            # Priority: source type, confidence, engagement, recency
            source_priority = 0 if photo.source == "twitter" else 1
            total_engagement = sum(photo.engagement.values())
            recency = photo.posted_at.timestamp()

            return (
                source_priority,
                -photo.confidence_score,
                -total_engagement,
                -recency,
            )

        photos_sorted = sorted(photos, key=photo_priority)
        return photos_sorted[0]

    def _score_photo_quality(self, photos: List[UnifiedPhoto]) -> List[UnifiedPhoto]:
        """
        Assign quality scores to photos based on multiple factors

        Factors:
        - Engagement (likes, comments)
        - Source reliability
        - Confidence score
        - Caption quality (length, keywords)

        Args:
            photos: List of UnifiedPhoto objects

        Returns:
            Same list with quality_score populated and sorted by quality
        """
        for photo in photos:
            quality_score = 0.0

            # Engagement score (normalized, max 0.3)
            total_engagement = sum(photo.engagement.values())
            engagement_score = min(total_engagement / 1000, 0.3)

            # Source reliability (0.2 for curated Twitter, 0.1 for Instagram)
            source_score = 0.2 if photo.source == "twitter" else 0.1

            # Confidence score (max 0.3)
            confidence_contribution = photo.confidence_score * 0.3

            # Caption quality (max 0.2)
            caption_score = self._score_caption(photo.caption)

            quality_score = (
                engagement_score
                + source_score
                + confidence_contribution
                + caption_score
            )

            photo.quality_score = quality_score

        # Sort by quality score (descending)
        photos.sort(key=lambda p: p.quality_score, reverse=True)

        return photos

    def _score_caption(self, caption: str) -> float:
        """
        Score caption quality for tunnel fit relevance

        Args:
            caption: Post caption text

        Returns:
            Score between 0.0 and 0.2
        """
        if not caption:
            return 0.0

        caption_lower = caption.lower()

        # Tunnel fit keywords (higher value keywords)
        high_value_keywords = ["tunnel", "pregame", "gameday", "arrival"]
        medium_value_keywords = [
            "fit",
            "outfit",
            "ootd",
            "wearing",
            "styled",
            "fashion",
        ]

        # Count matches
        high_matches = sum(1 for kw in high_value_keywords if kw in caption_lower)
        medium_matches = sum(1 for kw in medium_value_keywords if kw in caption_lower)

        # Calculate score (max 0.2)
        score = min((high_matches * 0.1) + (medium_matches * 0.05), 0.2)

        return score

    def get_photo_sources_summary(self, photos: List[UnifiedPhoto]) -> Dict:
        """
        Get summary statistics about photo sources

        Args:
            photos: List of UnifiedPhoto objects

        Returns:
            Dictionary with source breakdown
        """
        summary = {
            "total_photos": len(photos),
            "instagram_photos": len([p for p in photos if p.source == "instagram"]),
            "twitter_photos": len([p for p in photos if p.source == "twitter"]),
            "tunnel_fit_candidates": len(
                [p for p in photos if p.is_tunnel_fit_candidate]
            ),
            "average_quality_score": (
                sum(p.quality_score for p in photos) / len(photos) if photos else 0.0
            ),
            "sources_by_handle": defaultdict(int),
        }

        for photo in photos:
            summary["sources_by_handle"][photo.source_handle] += 1

        summary["sources_by_handle"] = dict(summary["sources_by_handle"])

        return summary
