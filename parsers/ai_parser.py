"""
AI-powered parser using OpenAI GPT for milestone extraction
"""

import json
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass

from openai import OpenAI
import openai

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
    source_tweet_id: str  # ID of the tweet this milestone came from
    # Internal fields for debugging/processing (not exported to CSV)
    extracted_date: str = ""  # Date found in tweet text
    date_confidence: float = 0.0  # 0-1 confidence in extracted date
    milestone_confidence: float = 0.0  # 0-1 confidence this is a genuine milestone
    attribution_confidence: float = (
        0.0  # 0-1 confidence milestone belongs to target player
    )
    date_source: str = (
        "tweet_published"  # tweet_text, game_schedule_inferred, tweet_published
    )


class AIParser:
    """AI parser using OpenAI GPT for content analysis"""

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found")

        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def parse_milestone_tweet(
        self,
        tweet_text: str,
        target_player: str,
        tweet_url: str = "",
        tweet_id: str = "",
        boxscore_context: Optional[str] = None,
    ) -> Optional[MilestoneData]:
        """
        Parse a tweet to extract milestone information using GPT with optional boxscore context

        Args:
            tweet_text: The tweet content to analyze
            target_player: The specific player we're scraping for
            tweet_url: Optional URL for reference
            tweet_id: Optional tweet ID for reference
            boxscore_context: Optional formatted boxscore data for milestone date inference

        Returns:
            MilestoneData object if milestone found, None otherwise
        """

        prompt = self._create_milestone_prompt(
            tweet_text, target_player, tweet_url, boxscore_context
        )

        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a WNBA statistics expert. Parse tweets for genuine player milestones, records, and achievements. Only identify significant accomplishments, not routine game stats.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=GPT_MAX_TOKENS,
                temperature=GPT_TEMPERATURE,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("is_milestone", False):
                return None

            # Additional validation to prevent wrong player attribution
            if not self._validate_player_attribution(tweet_text, target_player, result):
                logger.info(
                    f"Rejected milestone - wrong player attribution: {result.get('title', 'Unknown')}"
                )
                return None

            return MilestoneData(
                is_milestone=result.get("is_milestone", False),
                title=result.get("title", ""),
                value=result.get("value", ""),
                categories=result.get("categories", []),
                description=result.get("description", ""),
                previous_record=result.get("previous_record", ""),
                player_name=result.get("player_name", ""),
                date_context=result.get("date_context", ""),
                source_reliability=result.get("source_reliability", 0.5),
                source_tweet_id=tweet_id,
                # Internal debugging fields
                extracted_date=result.get("extracted_date", ""),
                date_confidence=result.get("date_confidence", 0.0),
                milestone_confidence=result.get("milestone_confidence", 0.0),
                attribution_confidence=result.get("attribution_confidence", 0.0),
                date_source=result.get("date_source", "tweet_published"),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from GPT: {e}")
            return None
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return None
        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing tweet with GPT: {e}")
            return None

    def _validate_player_attribution(
        self, tweet_text: str, target_player: str, ai_result: Dict
    ) -> bool:
        """
        Additional validation to catch wrong player attribution patterns
        that the AI might miss
        """
        text_lower = tweet_text.lower()
        target_lower = target_player.lower()

        # Reduced logging for production

        # Pattern: "X joins [target_player]" - X is the achiever, not target
        if "joins" in text_lower and target_lower in text_lower:
            # Check if another player name appears before "joins"
            words = text_lower.split()
            joins_index = words.index("joins") if "joins" in words else -1
            if joins_index > 0:
                logger.info(f"REJECTED: Detected 'joins' pattern - wrong attribution")
                return False

        # Pattern: "[Other player] tonight/today/yesterday: [stats]. The only other..."
        if (
            ": " in tweet_text
            and ("only other" in text_lower or "other players" in text_lower)
            and target_lower in text_lower
        ):
            logger.info(
                f"REJECTED: Detected 'only other' pattern - comparison, not {target_player}'s achievement"
            )
            logger.info(f"Tweet text: {tweet_text}")
            return False

        # Pattern: "Like [target_player], [other player]..."
        if text_lower.startswith("like " + target_lower):
            logger.info(
                f"REJECTED: Detected 'Like {target_player}' pattern - comparison"
            )
            return False

        # Let the AI handle player attribution in its prompt - if it returns is_milestone=true,
        # it should mean it's confident this milestone belongs to the target player

        return True

    def _create_milestone_prompt(
        self,
        tweet_text: str,
        target_player: str,
        tweet_url: str = "",
        boxscore_context: Optional[str] = None,
    ) -> str:
        """Create the prompt for GPT milestone parsing"""

        # Build base prompt
        base_prompt = f"""
Analyze this tweet for milestone information about "{target_player}":

Tweet: "{tweet_text}"
URL: {tweet_url}
"""

        # Add boxscore context if available
        if boxscore_context:
            base_prompt += f"""

Boxscore Context:
{boxscore_context}

USE THIS BOXSCORE DATA to help determine the exact date when milestones were achieved. If the milestone involves cumulative stats (like "500 assists" or "1000 points"), use the running totals to identify which game crossed the threshold.
"""

        return (
            base_prompt
            + """

CRITICAL INSTRUCTIONS - READ CAREFULLY:

1. PLAYER ATTRIBUTION - ONLY assign milestones to "{target_player}" if:
   - "{target_player}" is the SOLE achiever of the milestone being described
   - The sentence structure makes it clear "{target_player}" did the action
   - NOT if someone else achieved something and "{target_player}" is mentioned for comparison
   - NOT if the tweet says "X joins {target_player}" (X is the achiever, not {target_player})
   - NOT if the tweet says "Only X and {target_player}" (both achieved it previously, but X is the current achiever)
   - EXAMPLES TO REJECT:
     * "Kelsey Plum joins Caitlin Clark as the only players..." (Plum's achievement)
     * "Jackie Young did X. The only other players to do this? Clark & Taurasi" (Young's achievement)
     * "Like Caitlin Clark, Player X achieved..." (Player X's achievement)

2. MILESTONE REQUIREMENTS - Only classify as milestone if ALL are true:
   - Involves a record, "first", "most", "youngest", "fastest", "broke", "historic"
   - NOT routine game stats (15 pts, 8 assists) unless explicitly a record
   - NOT general praise or comparisons
   - NOT team achievements unless individual record within team context

3. DATE EXTRACTION - Look for dates in tweet text that indicate WHEN the milestone occurred:
   - "on this day in 2024", "last season", "in her rookie year" 
   - Specific dates like "August 18, 2024"
   - Game contexts like "against the Wings", "in yesterday's game"

4. CONFIDENCE SCORING:
   - milestone_confidence: How certain this is a genuine milestone (0-1)
   - attribution_confidence: How certain this milestone belongs to {target_player} (0-1)
   - date_confidence: How certain you are about extracted date (0-1)

Return JSON format:
{{
  "is_milestone": boolean,
  "title": "Brief milestone title",
  "value": "Key stat or achievement", 
  "categories": ["scoring", "assists", "rookie", "league", "team", "award"],
  "description": "Full context from tweet",
  "previous_record": "Previous record holder if mentioned",
  "player_name": "{target_player}" (ONLY if milestone belongs to them),
  "date_context": "Date or game context mentioned",
  "source_reliability": 0.8,
  "extracted_date": "Date found in tweet text or inferred from boxscore (YYYY-MM-DD format if possible)",
  "date_confidence": 0.9,
  "milestone_confidence": 0.9, 
  "attribution_confidence": 0.9,
  "date_source": "tweet_text" (if date found in text) or "boxscore_analysis" (if inferred from stats) or "tweet_published" (fallback)
}}

REJECT Examples (return is_milestone: false):
- "{target_player} scored 20 points" (routine stats)
- "Great performance by {target_player}" (general praise)
- "Arike Ogunbowale broke record, joining {target_player}" (other player's achievement)
- "Team won 85-72" (team result)

ACCEPT Examples:
- "{target_player} breaks WNBA rookie assist record"
- "First player since {target_player} to achieve..." (if {target_player} is the record setter)
- "{target_player} youngest to reach 1000 points"
"""
        )

    def batch_parse_tweets(
        self, tweets: List[Dict], target_player: str
    ) -> List[MilestoneData]:
        """
        Parse multiple tweets for milestones

        Args:
            tweets: List of tweet dictionaries with 'text' and 'url' keys
            target_player: The specific player we're scraping for

        Returns:
            List of MilestoneData objects for tweets containing milestones
        """
        milestones = []

        for i, tweet in enumerate(tweets):
            logger.info(f"Parsing tweet {i+1}/{len(tweets)} for {target_player}")

            milestone = self.parse_milestone_tweet(
                tweet_text=tweet.get("text", ""),
                target_player=target_player,
                tweet_url=tweet.get("url", ""),
                tweet_id=tweet.get("id", ""),
            )

            if milestone:
                milestones.append(milestone)
                logger.info(f"Found milestone: {milestone.title}")
                logger.debug(
                    f"Confidence scores - Milestone: {milestone.milestone_confidence:.2f}, Attribution: {milestone.attribution_confidence:.2f}, Date: {milestone.date_confidence:.2f}"
                )
                if milestone.extracted_date:
                    logger.debug(
                        f"Extracted date: {milestone.extracted_date} (source: {milestone.date_source})"
                    )
            else:
                logger.debug(
                    f"No milestone found in tweet: {tweet.get('text', '')[:100]}..."
                )

        logger.info(f"Found {len(milestones)} milestones out of {len(tweets)} tweets")
        return milestones


# Unused functions removed for production - see development branch for utilities
