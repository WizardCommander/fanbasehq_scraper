"""
Twitter/X.com client wrapper using twscrape
"""

import asyncio
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, AsyncGenerator
from dataclasses import dataclass

from twscrape import API, Tweet
from config.settings import DEFAULT_RATE_LIMIT_DELAY, MAX_RETRIES, X_COOKIES


logger = logging.getLogger(__name__)


@dataclass
class ScrapedTweet:
    """Structured tweet data"""
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


class TwitterClient:
    """Twitter scraping client using twscrape"""
    
    def __init__(self):
        self.api = API()
        
    async def setup(self):
        """Initialize the API (add accounts if needed)"""
        try:
            # Check if we have any accounts configured
            accounts = await self.api.pool.stats()
            total_accounts = accounts.get('total', 0) if accounts else 0
            logger.info(f"Twitter accounts available: {total_accounts}")
            
            if total_accounts == 0:
                logger.info("No Twitter accounts found. Adding account with cookies...")
                
                # Add account using cookies from .env file
                await self.api.pool.add_account(
                    username="cookie_user",          # Dummy username
                    password="dummy_pass",           # Dummy password  
                    email="dummy@example.com",       # Dummy email
                    email_password="dummy_email_pass", # Dummy email password
                    cookies=X_COOKIES                # Actual cookies from .env
                )
                
                logger.info("Account added successfully with cookies!")
                
                # Verify the account was added
                new_stats = await self.api.pool.stats()
                new_total = new_stats.get('total', 0) if new_stats else 0
                logger.info(f"Twitter accounts available after setup: {new_total}")
                
        except Exception as e:
            logger.error(f"Error setting up Twitter client: {e}")
            raise
            
    async def search_tweets(
        self, 
        query: str, 
        start_date: date, 
        end_date: date,
        limit: int = 100
    ) -> List[ScrapedTweet]:
        """
        Search for tweets matching query within date range
        
        Args:
            query: Search query string
            start_date: Start date for search
            end_date: End date for search  
            limit: Maximum number of tweets to return
            
        Returns:
            List of ScrapedTweet objects
        """
        tweets = []
        
        try:
            # Build search query with date filters
            date_query = f"{query} since:{start_date.isoformat()} until:{end_date.isoformat()}"
            logger.info(f"Searching tweets: {date_query}")
            
            # Search tweets
            async for tweet in self.api.search(date_query, limit=limit):
                scraped_tweet = self._convert_tweet(tweet)
                tweets.append(scraped_tweet)
                
                # Rate limiting
                await asyncio.sleep(DEFAULT_RATE_LIMIT_DELAY)
                
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            raise
            
        logger.info(f"Found {len(tweets)} tweets")
        return tweets
        
    async def get_tweets_from_accounts(
        self,
        accounts: List[str],
        player_variations: List[str],
        start_date: date,
        end_date: date,
        limit: int = 100
    ) -> List[ScrapedTweet]:
        """
        Get tweets from specific accounts mentioning player variations
        
        Args:
            accounts: List of Twitter handles to search
            player_variations: List of player name variations to search for
            start_date: Start date for search
            end_date: End date for search
            limit: Maximum tweets per account
            
        Returns:
            List of ScrapedTweet objects
        """
        all_tweets = []
        
        for account in accounts:
            # Remove @ symbol if present
            account_clean = account.lstrip('@')
            
            for variation in player_variations:
                try:
                    # Search for player mentions from this account
                    query = f'from:{account_clean} "{variation}"'
                    date_query = f"{query} since:{start_date.isoformat()} until:{end_date.isoformat()}"
                    
                    logger.info(f"Searching: {date_query}")
                    
                    tweet_count = 0
                    async for tweet in self.api.search(date_query, limit=limit):
                        scraped_tweet = self._convert_tweet(tweet)
                        
                        # Avoid duplicates
                        if not any(t.id == scraped_tweet.id for t in all_tweets):
                            all_tweets.append(scraped_tweet)
                            tweet_count += 1
                            
                        # Rate limiting
                        await asyncio.sleep(DEFAULT_RATE_LIMIT_DELAY)
                        
                    logger.info(f"Found {tweet_count} tweets from {account} mentioning '{variation}'")
                    
                except Exception as e:
                    logger.warning(f"Error searching {account} for '{variation}': {e}")
                    continue
                    
        logger.info(f"Total tweets found: {len(all_tweets)}")
        return all_tweets
        
    def _convert_tweet(self, tweet: Tweet) -> ScrapedTweet:
        """Convert twscrape Tweet object to ScrapedTweet"""
        
        # Extract images - handle different media formats safely
        images = []
        try:
            if hasattr(tweet, 'media') and tweet.media:
                # Handle case where media might be a single object or list
                media_list = tweet.media if isinstance(tweet.media, list) else [tweet.media]
                for media in media_list:
                    if hasattr(media, 'type') and media.type == 'photo':
                        if hasattr(media, 'media_url_https'):
                            images.append(media.media_url_https)
                    elif isinstance(media, dict) and media.get('type') == 'photo':
                        images.append(media.get('media_url_https', ''))
        except Exception as e:
            logger.warning(f"Error extracting media from tweet {tweet.id}: {e}")
        
        return ScrapedTweet(
            id=str(tweet.id),
            text=getattr(tweet, 'rawContent', None) or getattr(tweet, 'content', '') or '',
            author=getattr(tweet.user, 'displayname', '') or getattr(tweet.user, 'username', ''),
            author_handle=f"@{getattr(tweet.user, 'username', 'unknown')}",
            created_at=getattr(tweet, 'date', datetime.now()),
            retweet_count=getattr(tweet, 'retweetCount', 0) or 0,
            like_count=getattr(tweet, 'likeCount', 0) or 0,
            reply_count=getattr(tweet, 'replyCount', 0) or 0,
            quote_count=getattr(tweet, 'quoteCount', 0) or 0,
            view_count=getattr(tweet, 'viewCount', None),
            url=f"https://twitter.com/{getattr(tweet.user, 'username', 'unknown')}/status/{tweet.id}",
            images=images,
            is_retweet=hasattr(tweet, 'retweetedTweet') and getattr(tweet, 'retweetedTweet', None) is not None,
            is_quote=hasattr(tweet, 'quotedTweet') and getattr(tweet, 'quotedTweet', None) is not None
        )


async def search_milestone_tweets(
    player: str,
    player_variations: List[str], 
    milestone_accounts: List[str],
    start_date: date,
    end_date: date,
    limit: int = 100
) -> List[ScrapedTweet]:
    """
    Convenience function to search for milestone tweets
    
    Args:
        player: Player name for logging
        player_variations: List of name variations to search
        milestone_accounts: List of Twitter accounts to search
        start_date: Start date
        end_date: End date
        limit: Max tweets per account
        
    Returns:
        List of milestone-related tweets
    """
    client = TwitterClient()
    await client.setup()
    
    tweets = await client.get_tweets_from_accounts(
        accounts=milestone_accounts,
        player_variations=player_variations,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )
    
    return tweets