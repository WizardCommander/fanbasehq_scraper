"""
Milestone scraper for Caitlin Clark WNBA data
"""

import json
import logging
import asyncio
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from config.settings import (
    CONFIG_DIR, PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
)
from utils.twitterapi_client import search_milestone_tweets, ScrapedTweet
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
        self.start_date = start_date
        self.end_date = end_date
        self.output_file = output_file
        self.limit = limit
        
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
    
    async def scrape_milestones(self) -> Dict:
        """
        Main scraping method
        
        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting milestone scrape for {self.player}")
        logger.info(f"Date range: {self.start_date} to {self.end_date}")
        logger.info(f"Output: {self.output_file}")
        
        # Get player variations and milestone accounts
        player_variations = self.player_config.get('variations', [])
        milestone_accounts = self.accounts_config.get('twitter_accounts', {}).get('milestone_accounts', [])
        
        logger.info(f"Player variations: {player_variations}")
        logger.info(f"Milestone accounts: {milestone_accounts}")
        
        # Step 1: Scrape tweets from milestone accounts
        tweets = await search_milestone_tweets(
            player=self.player,
            player_variations=player_variations,
            milestone_accounts=milestone_accounts,
            start_date=self.start_date,
            end_date=self.end_date,
            limit=self.limit
        )
        
        if not tweets:
            logger.warning("No tweets found")
            return {"count": 0, "milestones": [], "tweets": []}
        
        # Step 2: Convert tweets to format for AI parsing (skip keyword filtering)
        tweet_dicts = []
        for tweet in tweets:
            tweet_dicts.append({
                "text": tweet.text,
                "url": tweet.url,
                "id": tweet.id
            })
        
        logger.info(f"Sending {len(tweet_dicts)} tweets directly to AI parser (no keyword filtering)")
        
        # Step 3: Parse all tweets with AI (GPT will filter for milestones)
        milestones = self.ai_parser.batch_parse_tweets(tweet_dicts)
        
        if not milestones:
            logger.warning("No milestones found by AI parser")
            return {"count": 0, "milestones": [], "tweets": []}
        
        # Step 4: Match milestones to their source tweets using tweet IDs
        milestone_tweets = []
        tweet_lookup = {tweet.id: tweet for tweet in tweets}
        
        for milestone in milestones:
            source_tweet = tweet_lookup.get(milestone.source_tweet_id)
            if source_tweet:
                milestone_tweets.append(source_tweet)
            else:
                logger.warning(f"Could not find source tweet {milestone.source_tweet_id} for milestone: {milestone.title}")
                # Use first available tweet as fallback
                if tweets:
                    milestone_tweets.append(tweets[0])
        
        # Step 5: Write to CSV
        self.csv_formatter.write_milestones_to_csv(milestones, milestone_tweets)
        
        results = {
            "count": len(milestones),
            "milestones": [milestone.title for milestone in milestones],
            "tweets_scraped": len(tweets),
            "tweets_sent_to_ai": len(tweet_dicts), 
            "output_file": str(self.output_file)
        }
        
        logger.info(f"Scraping complete: {results}")
        return results
        
    def run(self) -> Dict:
        """
        Run the scraper synchronously
        
        Returns:
            Scraping results dictionary
        """
        return asyncio.run(self.scrape_milestones())


async def test_milestone_scraper():
    """Test function for the milestone scraper"""
    
    # Test with small date range
    scraper = MilestoneScraper(
        player="caitlin clark",
        start_date=date(2024, 8, 1),
        end_date=date(2024, 8, 27),
        output_file="output/test_milestones.csv",
        limit=10
    )
    
    results = await scraper.scrape_milestones()
    print(f"Test results: {results}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run test
    asyncio.run(test_milestone_scraper())