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
    CONFIG_DIR, PLAYERS_FILE, ACCOUNTS_FILE, TWITTER_KEYWORDS_FILE
)
from utils.twitter_client import search_milestone_tweets, ScrapedTweet
from parsers.ai_parser import AIParser, filter_tweets_by_keywords
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
        self.keywords_config = self._load_keywords_config()
        
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
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
            
    def _load_keywords_config(self) -> Dict:
        """Load keywords configuration"""
        with open(TWITTER_KEYWORDS_FILE, 'r') as f:
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
        
        # Step 2: Convert tweets to format for filtering
        tweet_dicts = []
        for tweet in tweets:
            tweet_dicts.append({
                "text": tweet.text,
                "url": tweet.url,
                "id": tweet.id
            })
        
        # Step 3: Pre-filter tweets using keywords
        milestone_keywords = []
        keywords_config = self.keywords_config.get('milestones', {})
        milestone_keywords.extend(keywords_config.get('achievement_words', []))
        milestone_keywords.extend(keywords_config.get('stat_words', []))
        
        filtered_tweets = filter_tweets_by_keywords(tweet_dicts, milestone_keywords)
        
        if not filtered_tweets:
            logger.warning("No tweets passed keyword filtering")
            return {"count": 0, "milestones": [], "tweets": []}
        
        # Step 4: Parse filtered tweets with AI
        milestones = self.ai_parser.batch_parse_tweets(filtered_tweets)
        
        if not milestones:
            logger.warning("No milestones found by AI parser")
            return {"count": 0, "milestones": [], "tweets": []}
        
        # Step 5: Match milestones back to original tweet objects
        milestone_tweets = []
        for milestone in milestones:
            # Find corresponding tweet object
            for tweet in tweets:
                if any(filtered_tweet["id"] == tweet.id for filtered_tweet in filtered_tweets):
                    milestone_tweets.append(tweet)
                    break
        
        # Step 6: Write to CSV
        self.csv_formatter.write_milestones_to_csv(milestones, milestone_tweets)
        
        results = {
            "count": len(milestones),
            "milestones": [milestone.title for milestone in milestones],
            "tweets_scraped": len(tweets),
            "tweets_filtered": len(filtered_tweets), 
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