"""
Milestone Processing Service
Handles milestone detection and validation from tweets
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import AIParser, MilestoneData

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of milestone processing"""
    milestones: List[MilestoneData]
    tweets_processed: int
    milestones_found: int


class MilestoneProcessingService:
    """Service for processing tweets into validated milestones"""
    
    def __init__(self, ai_parser: AIParser = None):
        self.ai_parser = ai_parser or AIParser()
    
    async def process_tweets_to_milestones(
        self,
        tweets: List[ScrapedTweet],
        target_player: str
    ) -> ProcessingResult:
        """
        Process a list of tweets to extract milestones
        
        Args:
            tweets: List of tweets to process
            target_player: The player we're looking for milestones about
            
        Returns:
            ProcessingResult with extracted milestones
        """
        milestones = []
        tweets_processed = 0
        
        for tweet in tweets:
            tweets_processed += 1
            
            # Process single tweet for milestone
            milestone = await self._process_single_tweet(tweet, target_player)
            
            if milestone:
                milestones.append(milestone)
                logger.info(f"Found milestone: {milestone.title}")
                logger.debug(f"Confidence - Milestone: {milestone.milestone_confidence:.2f}, "
                           f"Attribution: {milestone.attribution_confidence:.2f}")
        
        logger.info(f"Processed {tweets_processed} tweets, found {len(milestones)} milestones")
        
        return ProcessingResult(
            milestones=milestones,
            tweets_processed=tweets_processed,
            milestones_found=len(milestones)
        )
    
    async def _process_single_tweet(
        self,
        tweet: ScrapedTweet,
        target_player: str
    ) -> Optional[MilestoneData]:
        """Process a single tweet for milestone extraction"""
        try:
            # Convert tweet to format expected by AI parser
            milestone = self.ai_parser.parse_milestone_tweet(
                tweet_text=tweet.text,
                target_player=target_player,
                tweet_url=tweet.url,
                tweet_id=tweet.id
            )
            
            if milestone:
                logger.debug(f"Milestone extracted from tweet {tweet.id}: {milestone.title}")
            
            return milestone
            
        except Exception as e:
            logger.error(f"Error processing tweet {tweet.id}: {e}")
            return None