"""
Twitter Search Service
Handles all Twitter API interactions for milestone scraping
"""

import logging
from datetime import date
from typing import List, Dict
from dataclasses import dataclass

from utils.twitterapi_client import TwitterAPIClient, ScrapedTweet

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result of a Twitter search operation"""
    account: str
    variation: str
    tweets: List[ScrapedTweet]
    tweets_processed: int


class TwitterSearchService:
    """Service for searching Twitter for milestone-related tweets"""
    
    def __init__(self, client: TwitterAPIClient = None):
        self.client = client or TwitterAPIClient()
    
    async def search_tweets_for_player(
        self,
        accounts: List[str],
        variations: List[str], 
        start_date: date,
        end_date: date,
        limit: int
    ) -> List[SearchResult]:
        """
        Search Twitter for tweets across multiple accounts and player variations
        
        Args:
            accounts: List of Twitter accounts to search
            variations: List of player name variations
            start_date: Search start date
            end_date: Search end date
            limit: Max tweets per search
            
        Returns:
            List of SearchResult objects
        """
        results = []
        total_tweets = 0
        
        for account in accounts:
            account_clean = account.lstrip('@')
            
            for variation in variations:
                try:
                    logger.info(f"Searching {account} × {variation}")
                    
                    tweets = await self._search_account_variation(
                        account_clean, variation, start_date, end_date, limit
                    )
                    
                    if tweets:
                        # Fix tweet URLs with known account info
                        for tweet in tweets:
                            if not tweet.author_handle or tweet.author_handle == "@":
                                tweet.author_handle = f"@{account_clean}"
                                tweet.url = f"https://twitter.com/{account_clean}/status/{tweet.id}"
                        
                        results.append(SearchResult(
                            account=account,
                            variation=variation,
                            tweets=tweets,
                            tweets_processed=len(tweets)
                        ))
                        
                        total_tweets += len(tweets)
                        logger.info(f"Found {len(tweets)} tweets for {account} × {variation}")
                    else:
                        logger.info(f"No tweets found for {account} × {variation}")
                        
                except Exception as e:
                    logger.error(f"Error searching {account} × {variation}: {e}")
                    continue
        
        logger.info(f"Total search completed: {len(results)} successful searches, {total_tweets} tweets")
        return results
    
    async def _search_account_variation(
        self, 
        account: str, 
        variation: str, 
        start_date: date, 
        end_date: date, 
        limit: int
    ) -> List[ScrapedTweet]:
        """Search for tweets from a specific account with player variation"""
        query = f'from:{account} "{variation}"'
        
        return await self.client.search_tweets(
            query=query,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )