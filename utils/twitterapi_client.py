"""
TwitterAPI.io client for Caitlin Clark WNBA data scraper
Professional Twitter API service to replace web scraping
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, date
from typing import List, Dict, Optional
from dataclasses import dataclass

from config.settings import (
    TWITTER_API_KEY,
    TWITTER_API_BASE_URL,
    TWITTER_API_TIMEOUT,
    TWEETS_PER_PAGE,
    DEFAULT_RATE_LIMIT_DELAY,
)


logger = logging.getLogger(__name__)


@dataclass
class ScrapedTweet:
    """Structured tweet data - keeping same interface as twscrape version"""

    id: str
    text: str
    author: str
    author_handle: str
    created_at: datetime
    retweet_count: int
    like_count: int
    reply_count: int
    quote_count: int
    view_count: Optional[int]
    url: str
    images: List[str]
    is_retweet: bool
    is_quote: bool


class TwitterAPIClient:
    """TwitterAPI.io client for professional Twitter data access"""

    def __init__(self):
        self.base_url = TWITTER_API_BASE_URL
        self.headers = {
            "x-api-key": TWITTER_API_KEY,
            "Content-Type": "application/json",
        }

    async def search_tweets(
        self,
        query: str,
        start_date: date,
        end_date: date,
        query_type: str = "Latest",
        limit: int = 100,
    ) -> List[ScrapedTweet]:
        """
        Search for tweets using TwitterAPI.io advanced search

        Args:
            query: Search query string
            start_date: Start date for search
            end_date: End date for search
            query_type: "Latest" or "Top"
            limit: Maximum number of tweets to return

        Returns:
            List of ScrapedTweet objects
        """
        tweets = []
        cursor = ""
        pages_fetched = 0
        max_pages = (limit + TWEETS_PER_PAGE - 1) // TWEETS_PER_PAGE  # Round up

        # Build query with date filters
        formatted_query = f"{query} since:{start_date.strftime('%Y-%m-%d')} until:{end_date.strftime('%Y-%m-%d')}"

        logger.info(f"Searching tweets: {formatted_query}")
        logger.info(f"Will fetch up to {max_pages} pages ({limit} tweets)")

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=TWITTER_API_TIMEOUT)
        ) as session:
            while pages_fetched < max_pages and len(tweets) < limit:
                try:
                    # Prepare request parameters
                    params = {
                        "query": formatted_query,
                        "queryType": query_type,
                        "cursor": cursor,
                    }

                    url = f"{self.base_url}/twitter/tweet/advanced_search"

                    logger.info(f"Fetching page {pages_fetched + 1}/{max_pages}")

                    async with session.get(
                        url, headers=self.headers, params=params
                    ) as response:
                        if response.status != 200:
                            logger.error(
                                f"API request failed: {response.status} - {await response.text()}"
                            )
                            break

                        data = await response.json()

                        # Process tweets from this page
                        page_tweets = data.get("tweets", [])
                        if not page_tweets:
                            logger.info("No more tweets found")
                            break

                        for tweet_data in page_tweets:
                            if len(tweets) >= limit:
                                break

                            tweet = self._convert_tweet_data(tweet_data)
                            if tweet:
                                tweets.append(tweet)

                        logger.info(
                            f"Got {len(page_tweets)} tweets from page {pages_fetched + 1}"
                        )

                        # Check if there are more pages
                        if not data.get("has_next_page", False):
                            logger.info("No more pages available")
                            break

                        cursor = data.get("next_cursor", "")
                        if not cursor:
                            logger.info("No next cursor available")
                            break

                        pages_fetched += 1

                        # Rate limiting - be nice to the API
                        await asyncio.sleep(DEFAULT_RATE_LIMIT_DELAY)

                except Exception as e:
                    logger.error(f"Error fetching page {pages_fetched + 1}: {e}")
                    break

        logger.info(f"Found {len(tweets)} total tweets")
        return tweets

    async def get_tweets_from_accounts(
        self,
        accounts: List[str],
        player_variations: List[str],
        start_date: date,
        end_date: date,
        limit: int = 100,
    ) -> List[ScrapedTweet]:
        """
        Get tweets from specific accounts mentioning player variations

        Args:
            accounts: List of Twitter handles to search
            player_variations: List of player name variations to search for
            start_date: Start date for search
            end_date: End date for search
            limit: Maximum tweets per account/variation combo

        Returns:
            List of ScrapedTweet objects
        """
        all_tweets = []
        seen_tweet_ids: Set[str] = set()

        for account in accounts:
            # Clean account handle
            account_clean = account.lstrip("@")

            for variation in player_variations:
                try:
                    # Build query: from:account "player variation"
                    query = f'from:{account_clean} "{variation}"'

                    logger.info(f"Searching: {query}")

                    # Search for this specific combination
                    tweets = await self.search_tweets(
                        query=query,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                    )

                    # Add to results, avoiding duplicates with O(1) lookup
                    for tweet in tweets:
                        if tweet.id not in seen_tweet_ids:
                            all_tweets.append(tweet)
                            seen_tweet_ids.add(tweet.id)

                    logger.info(
                        f"Found {len(tweets)} tweets from {account} mentioning '{variation}'"
                    )

                except Exception as e:
                    logger.warning(f"Error searching {account} for '{variation}': {e}")
                    continue

        logger.info(f"Total unique tweets found: {len(all_tweets)}")
        return all_tweets

    def _convert_tweet_data(self, tweet_data: Dict) -> Optional[ScrapedTweet]:
        """Convert TwitterAPI.io tweet data to ScrapedTweet object"""

        try:
            # Extract basic tweet info
            tweet_id = str(tweet_data.get("id", ""))
            text = tweet_data.get("text", "")

            # Filter out reply tweets - too messy to process
            if self._is_reply_tweet(tweet_data):
                logger.debug("Filtering out reply tweet %s", tweet_id)
                return None

            # Extract author info - TwitterAPI.io uses camelCase 'userName'
            author_info = tweet_data.get("author", {})
            author_name = author_info.get("name", "")
            author_username = author_info.get("userName", "")

            # Extract dates - TwitterAPI.io uses camelCase 'createdAt'
            created_at_str = tweet_data.get("createdAt", "") or tweet_data.get(
                "created_at", ""
            )

            try:
                if created_at_str:
                    # TwitterAPI.io uses Twitter's standard format: 'Tue Aug 27 19:42:18 +0000 2024'
                    created_at = datetime.strptime(
                        created_at_str, "%a %b %d %H:%M:%S %z %Y"
                    )
                else:
                    logger.warning(f"Tweet {tweet_id} has no date - using fallback")
                    from datetime import timezone

                    created_at = datetime(2024, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Tweet {tweet_id} date parsing failed for '{created_at_str}': {e}"
                )
                from datetime import timezone

                created_at = datetime(2024, 8, 27, 12, 0, 0, tzinfo=timezone.utc)

            # Extract engagement metrics - TwitterAPI.io uses camelCase directly on tweet object
            retweet_count = tweet_data.get("retweetCount", 0)
            like_count = tweet_data.get("likeCount", 0)
            reply_count = tweet_data.get("replyCount", 0)
            quote_count = tweet_data.get("quoteCount", 0)
            view_count = tweet_data.get("viewCount")

            # Extract media/images
            images = []
            includes = tweet_data.get("includes", {})
            media_list = includes.get("media", [])

            for media in media_list:
                if media.get("type") == "photo":
                    image_url = media.get("url", "")
                    if image_url:  # Only add non-empty URLs
                        images.append(image_url)

            # Check if retweet or quote
            is_retweet = "retweeted" in text.lower() or tweet_data.get(
                "referenced_tweets", []
            )
            is_quote = any(
                ref.get("type") == "quoted"
                for ref in tweet_data.get("referenced_tweets", [])
            )

            return ScrapedTweet(
                id=tweet_id,
                text=text,
                author=author_name,
                author_handle=f"@{author_username}" if author_username else "",
                created_at=created_at,
                retweet_count=retweet_count,
                like_count=like_count,
                reply_count=reply_count,
                quote_count=quote_count,
                view_count=view_count,
                url=(
                    f"https://twitter.com/{author_username}/status/{tweet_id}"
                    if author_username
                    else f"https://twitter.com/unknown/status/{tweet_id}"
                ),
                images=images,
                is_retweet=is_retweet,
                is_quote=is_quote,
            )

        except Exception as e:
            logger.error("Error converting tweet data: %s", e)
            return None

    def _is_reply_tweet(self, tweet_data: Dict) -> bool:
        """Check if tweet is a reply using TwitterAPI.io response fields"""

        # TwitterAPI.io provides direct isReply boolean (primary method)
        return bool(tweet_data.get("isReply", False))
