"""
Milestone scraper for Caitlin Clark WNBA data
"""

import json
import logging
import asyncio
from datetime import date
from pathlib import Path
from typing import Dict, List

from config.settings import (
    CONFIG_DIR, PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
)
from utils.twitterapi_client import ScrapedTweet
from utils.roster_cache import lookup_player_team_with_id
from parsers.ai_parser import AIParser
from parsers.csv_formatter import MilestoneCSVFormatter


logger = logging.getLogger(__name__)


class MilestoneScraper:
    """Main scraper class for milestone data"""
    
    def __init__(
        self,
        player: str,
        start_date: date,
        end_date: date,
        output_file: str,
        limit: int = 100
    ):
        self.player = player.lower()
        self.player_display_name = player.title()  # Store original case for display
        self.start_date = start_date
        self.end_date = end_date
        self.output_file = output_file
        self.limit = limit
        
        # Team information (will be populated dynamically)
        self.team_name = None
        self.team_id = None
        
        # Load configurations
        self.player_config = self._load_player_config()
        self.accounts_config = self._load_accounts_config()
        
        # Initialize components
        self.ai_parser = AIParser()
        self.csv_formatter = MilestoneCSVFormatter(output_file)
        
    def _load_player_config(self) -> Dict:
        """Load player configuration"""
        with open(PLAYERS_FILE, 'r') as f:
            players = json.load(f)
            
        if self.player not in players:
            raise ValueError(f"Player '{self.player}' not found in {PLAYERS_FILE}")
            
        return players[self.player]
        
    def _load_accounts_config(self) -> Dict:
        """Load accounts configuration"""
        with open(TWITTER_ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
            
    async def _lookup_player_team(self) -> bool:
        """
        Lookup player's current team dynamically with config fallback
        
        Returns:
            True if team found, False otherwise
        """
        if self.team_name and self.team_id:
            return True  # Already looked up
            
        # First try config fallback (faster)
        config_team = self.player_config.get('team')
        config_team_id = self.player_config.get('team_id')
        if config_team and config_team_id:
            self.team_name = config_team
            self.team_id = config_team_id
            logger.info(f"Using config team info: {self.player_display_name} plays for {self.team_name} (ID: {self.team_id})")
            return True
            
        # If no config, try dynamic lookup
        logger.info(f"Looking up team dynamically for {self.player_display_name}...")
        
        try:
            team_info = lookup_player_team_with_id(self.player_display_name)
            if team_info:
                self.team_name, self.team_id = team_info
                logger.info(f"{self.player_display_name} plays for {self.team_name} (ID: {self.team_id})")
                return True
            else:
                logger.warning(f"Could not find team for {self.player_display_name}")
                return False
        except Exception as e:
            logger.error(f"Error looking up team for {self.player_display_name}: {e}")
            return False
    
    async def scrape_milestones(self) -> Dict:
        """
        Streaming scraping method with memory management and game validation
        
        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting milestone scrape for {self.player_display_name}")
        logger.info(f"Date range: {self.start_date} to {self.end_date}")
        logger.info(f"Output: {self.output_file}")
        
        # Step 1: Lookup player's team dynamically
        team_found = await self._lookup_player_team()
        if not team_found:
            logger.warning(f"Proceeding without team validation for {self.player_display_name}")
            
        # Get player variations and milestone accounts
        player_variations = self.player_config.get('variations', [])
        milestone_accounts = self.accounts_config.get('twitter_accounts', {}).get('milestone_accounts', [])
        
        logger.info(f"Player variations: {player_variations}")
        logger.info(f"Milestone accounts: {milestone_accounts}")
        
        # Initialize counters and CSV writer
        total_tweets_processed = 0
        total_milestones_found = 0
        csv_initialized = False
        all_milestones = []  # Store all milestones for final validation
        processed_tweet_ids = set()  # Track processed tweet IDs to prevent duplicates
        
        # Process each account/variation combination separately for memory efficiency
        for account in milestone_accounts:
            account_clean = account.lstrip('@')
            
            for variation in player_variations:
                try:
                    logger.info(f"Processing {account} × {variation}")
                    
                    # Step 1: Get tweets for this specific combination (small batch)
                    tweets = await self._get_tweets_for_account_variation(
                        account_clean, variation, self.start_date, self.end_date, self.limit
                    )
                    
                    if not tweets:
                        logger.info(f"No tweets found for {account} × {variation}")
                        continue
                    
                    total_tweets_processed += len(tweets)
                    logger.info(f"Found {len(tweets)} tweets for {account} × {variation}")
                    
                    # Step 2: Process tweets in streaming fashion
                    milestones_batch = await self._process_tweets_streaming(tweets)
                    
                    if milestones_batch:
                        # Step 3: Deduplicate milestones by tweet ID
                        deduplicated_milestones = []
                        deduplicated_tweets = []
                        tweet_lookup = {tweet.id: tweet for tweet in tweets}
                        
                        for milestone in milestones_batch:
                            if milestone.source_tweet_id not in processed_tweet_ids:
                                processed_tweet_ids.add(milestone.source_tweet_id)
                                deduplicated_milestones.append(milestone)
                                
                                source_tweet = tweet_lookup.get(milestone.source_tweet_id)
                                if source_tweet:
                                    deduplicated_tweets.append(source_tweet)
                                else:
                                    logger.warning(f"Could not find source tweet for milestone: {milestone.title}")
                                    if tweets:  # Fallback to first tweet
                                        deduplicated_tweets.append(tweets[0])
                            else:
                                logger.debug(f"Skipping duplicate milestone from tweet {milestone.source_tweet_id}: {milestone.title}")
                        
                        milestones_batch = deduplicated_milestones
                        milestone_tweets = deduplicated_tweets
                        
                        # Step 4: Stream write to CSV (append mode)
                        if not csv_initialized:
                            await self.csv_formatter.write_milestones_to_csv(milestones_batch, milestone_tweets, self.player_display_name)
                            csv_initialized = True
                        else:
                            await self.csv_formatter.append_milestones_to_csv(milestones_batch, milestone_tweets, self.player_display_name)
                        
                        total_milestones_found += len(milestones_batch)
                        logger.info(f"Added {len(milestones_batch)} milestones from {account} × {variation}")
                        
                        # Store milestones for game validation
                        all_milestones.extend(milestones_batch)
                    
                    # Step 4: Clear memory - let Python GC handle cleanup
                    del tweets
                    del milestones_batch
                    
                except ValueError as e:
                    logger.error(f"Configuration error processing {account} × {variation}: {e}")
                    continue
                except ConnectionError as e:
                    logger.error(f"Network error processing {account} × {variation}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing {account} × {variation}: {e}")
                    # Re-raise for critical errors that shouldn't be silently ignored
                    if "authentication" in str(e).lower() or "api key" in str(e).lower():
                        raise
                    continue
        
        if total_milestones_found == 0:
            logger.warning("No milestones found across all accounts/variations")
            # Create empty CSV file
            await self.csv_formatter.write_milestones_to_csv([], [], self.player_display_name)
            
        # Log team and validation info for future enhancement
        validation_results = {
            "team_name": self.team_name,
            "team_id": self.team_id,
            "milestones_found": len(all_milestones),
            "note": "Game schedule validation available but simplified for v1"
        }
        
        results = {
            "count": total_milestones_found,
            "tweets_processed": total_tweets_processed,
            "output_file": str(self.output_file),
            "team_info": {
                "team_name": self.team_name,
                "team_id": self.team_id
            },
            "validation": validation_results
        }
        
        logger.info(f"Streaming scrape complete: {results}")
        return results
    
    async def _get_tweets_for_account_variation(
        self, account: str, variation: str, start_date, end_date, limit: int
    ) -> List[ScrapedTweet]:
        """Get tweets for a specific account/variation combination"""
        from utils.twitterapi_client import TwitterAPIClient
        
        client = TwitterAPIClient()
        query = f'from:{account} "{variation}"'
        
        tweets = await client.search_tweets(
            query=query,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        # Fix tweet URLs with known account info since TwitterAPI may not provide username
        for tweet in tweets:
            if not tweet.author_handle or tweet.author_handle == "@":
                tweet.author_handle = f"@{account}"
                tweet.url = f"https://twitter.com/{account}/status/{tweet.id}"
        
        return tweets
    
    async def _process_tweets_streaming(self, tweets: List[ScrapedTweet]) -> List:
        """Process tweets for milestones in streaming fashion"""
        milestones = []
        
        for tweet in tweets:
            # Process each tweet individually to minimize memory
            tweet_dict = {
                "text": tweet.text,
                "url": tweet.url,
                "id": tweet.id
            }
            
            # Parse single tweet with AI
            milestone = self.ai_parser.parse_milestone_tweet(
                tweet_text=tweet_dict["text"],
                target_player=self.player_display_name,
                tweet_url=tweet_dict["url"],
                tweet_id=tweet_dict["id"]
            )
            
            if milestone:
                milestones.append(milestone)
                logger.info(f"Found milestone: {milestone.title}")
        
        return milestones
        
            
        
    def run(self) -> Dict:
        """
        Run the scraper synchronously
        
        Returns:
            Scraping results dictionary
        """
        return asyncio.run(self.scrape_milestones())


# Test functions removed for production - see development branch for testing utilities