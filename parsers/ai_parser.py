"""
AI-powered parser using OpenAI GPT for milestone extraction
"""

import json
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass

import openai
from openai import OpenAI

from config.settings import OPENAI_API_KEY, GPT_MODEL, GPT_MAX_TOKENS, GPT_TEMPERATURE


logger = logging.getLogger(__name__)


@dataclass
class MilestoneData:
    """Structured milestone data extracted by AI"""
    is_milestone: bool
    title: str
    value: str
    categories: List[str]
    description: str
    previous_record: str
    player_name: str
    date_context: str
    source_reliability: float  # 0-1 confidence score


class AIParser:
    """AI parser using OpenAI GPT for content analysis"""
    
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found")
            
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        
    def parse_milestone_tweet(self, tweet_text: str, tweet_url: str = "") -> Optional[MilestoneData]:
        """
        Parse a tweet to extract milestone information using GPT
        
        Args:
            tweet_text: The tweet content to analyze
            tweet_url: Optional URL for reference
            
        Returns:
            MilestoneData object if milestone found, None otherwise
        """
        
        prompt = self._create_milestone_prompt(tweet_text, tweet_url)
        
        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a WNBA statistics expert. Parse tweets for genuine player milestones, records, and achievements. Only identify significant accomplishments, not routine game stats."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=GPT_MAX_TOKENS,
                temperature=GPT_TEMPERATURE,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            if not result.get('is_milestone', False):
                return None
                
            return MilestoneData(
                is_milestone=result.get('is_milestone', False),
                title=result.get('title', ''),
                value=result.get('value', ''),
                categories=result.get('categories', []),
                description=result.get('description', ''),
                previous_record=result.get('previous_record', ''),
                player_name=result.get('player_name', ''),
                date_context=result.get('date_context', ''),
                source_reliability=result.get('source_reliability', 0.5)
            )
            
        except Exception as e:
            logger.error(f"Error parsing tweet with GPT: {e}")
            return None
            
    def _create_milestone_prompt(self, tweet_text: str, tweet_url: str = "") -> str:
        """Create the prompt for GPT milestone parsing"""
        
        return f"""
Analyze this tweet about Caitlin Clark for milestone information:

Tweet: "{tweet_text}"
URL: {tweet_url}

Instructions:
- Only identify GENUINE milestones, records, or significant achievements
- NOT routine game stats like "scored 25 points" unless it's a record
- Look for words like: record, first, youngest, most, broke, milestone, historic
- Categorize milestones as: scoring, assists, rebounds, steals, blocks, shooting, league, rookie, team, award

Return JSON format:
{{
  "is_milestone": boolean,
  "title": "Brief milestone title (e.g. 'Fastest to 300 career threes')",
  "value": "Key stat or achievement (e.g. '300 career threes in 114 games')",
  "categories": ["scoring", "league"], 
  "description": "Full context from the tweet",
  "previous_record": "Previous record holder if mentioned",
  "player_name": "Player name mentioned",
  "date_context": "Date or game context if mentioned", 
  "source_reliability": 0.8 (0-1 confidence this is a real milestone)
}}

Examples of REAL milestones:
- "Caitlin Clark breaks WNBA rookie assist record"
- "First rookie to reach 300 assists and 100 threes" 
- "Youngest player to score 40+ points"

Examples of NOT milestones:
- "Caitlin had 15 points and 8 assists" (routine stats)
- "Great game by CC tonight" (general praise)
- "Fever won 85-72" (team result only)
"""

    def batch_parse_tweets(self, tweets: List[Dict]) -> List[MilestoneData]:
        """
        Parse multiple tweets for milestones
        
        Args:
            tweets: List of tweet dictionaries with 'text' and 'url' keys
            
        Returns:
            List of MilestoneData objects for tweets containing milestones
        """
        milestones = []
        
        for i, tweet in enumerate(tweets):
            logger.info(f"Parsing tweet {i+1}/{len(tweets)}")
            
            milestone = self.parse_milestone_tweet(
                tweet_text=tweet.get('text', ''),
                tweet_url=tweet.get('url', '')
            )
            
            if milestone:
                milestones.append(milestone)
                logger.info(f"Found milestone: {milestone.title}")
                
        logger.info(f"Found {len(milestones)} milestones out of {len(tweets)} tweets")
        return milestones


def filter_tweets_by_keywords(tweets: List[Dict], milestone_keywords: List[str]) -> List[Dict]:
    """
    Pre-filter tweets using keyword matching before sending to GPT
    
    Args:
        tweets: List of tweet dictionaries 
        milestone_keywords: List of milestone-related keywords
        
    Returns:
        Filtered list of tweets that might contain milestones
    """
    filtered_tweets = []
    
    for tweet in tweets:
        text = tweet.get('text', '').lower()
        
        # Check if tweet contains any milestone keywords
        if any(keyword.lower() in text for keyword in milestone_keywords):
            filtered_tweets.append(tweet)
            
    logger.info(f"Filtered {len(filtered_tweets)} potential milestone tweets from {len(tweets)} total")
    return filtered_tweets