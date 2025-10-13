"""
AI-powered parser using OpenAI GPT for milestone extraction
"""

import json
import logging
import re
from datetime import datetime, date
from typing import Dict, Optional, List
from dataclasses import dataclass

from openai import OpenAI
import openai

from config.settings import OPENAI_API_KEY, GPT_MODEL, GPT_MAX_TOKENS, GPT_TEMPERATURE
from utils.branded_types import TweetId, tweet_id as create_tweet_id


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
    source_tweet_id: TweetId  # ID of the tweet this milestone came from
    content_hash: str = ""  # Semantic hash for deduplication
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


@dataclass
class TunnelFitData:
    """Structured tunnel fit data extracted by AI"""

    is_tunnel_fit: bool
    event: str  # "Fever vs Sky | Indianapolis, IN"
    date: Optional[date]  # Extracted from post text or tweet date
    type: str  # "gameday" or "events"
    outfit_details: List[
        Dict
    ]  # [{"item": "...", "brand": "...", "price": "...", "affiliate": bool}]
    location: str  # "Indianapolis, IN"
    player_name: str
    source_tweet_id: TweetId  # ID of the tweet this tunnel fit came from
    social_stats: Dict  # {"views": 3702, "likes": 122, etc.}
    # Internal fields for debugging/processing
    date_confidence: float = 0.0  # 0-1 confidence in extracted date
    fit_confidence: float = 0.0  # 0-1 confidence this is a genuine tunnel fit
    date_source: str = "tweet_text"  # "tweet_text" or "tweet_published"


@dataclass
class ShoeData:
    """Structured shoe data extracted by AI"""

    is_shoe_post: bool
    shoe_name: str  # "Nike Kobe 6 Protro 'Light Armory Blue'"
    brand: str  # "Nike"
    model: str  # "Kobe 6 Protro"
    color_description: str  # "Light Armory Blue"
    date: Optional[date]  # Tweet/post date - for game stats matching
    release_date: Optional[
        date
    ]  # Shoe's actual release date - from AI extraction or fallback
    price: str  # "$190" (with currency symbol)
    signature_shoe: bool
    limited_edition: bool
    performance_features: List[str]  # ["Zoom Air", "Herringbone Traction"]
    description: str
    player_name: str
    source_tweet_id: TweetId
    social_stats: Dict  # {"views": 3702, "likes": 122, etc.}
    # Game stats integration - added by processing service
    game_stats: Optional[Dict] = None  # Complex JSON structure from CSV schema
    # Internal fields for debugging/processing
    date_confidence: float = 0.0  # 0-1 confidence in extracted date
    shoe_confidence: float = 0.0  # 0-1 confidence this is a genuine shoe post
    date_source: str = "tweet_text"  # "tweet_text" or "tweet_published"
    # Fields that may need fallback services
    has_missing_data: bool = False
    missing_fields: List[str] = None  # List of fields that need fallback

    def __post_init__(self):
        if self.missing_fields is None:
            self.missing_fields = []


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

            # Generate content hash for deduplication
            from utils.deduplication import MilestoneDeduplicator

            deduplicator = MilestoneDeduplicator()
            content_hash = deduplicator.generate_content_hash(
                title=result.get("title", ""),
                categories=result.get("categories", []),
                value=result.get("value", ""),
            )

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
                source_tweet_id=create_tweet_id(tweet_id),
                content_hash=content_hash,
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
   
   CRITICAL: DO NOT assign today's date to historical/career achievements:
   - "first in WNBA history" = LEAVE DATE BLANK (career milestone, not tied to specific game)
   - "most in a season" = LEAVE DATE BLANK (season achievement, not single game)
   - "career record" = LEAVE DATE BLANK (cumulative achievement)
   - Only assign dates when milestone clearly occurred on a specific game date

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

    def parse_tunnel_fit_tweet(
        self,
        tweet_text: str,
        target_player: str,
        tweet_url: str = "",
        tweet_id: str = "",
        tweet_created_at: Optional[datetime] = None,
    ) -> Optional[TunnelFitData]:
        """
        Parse a tweet to extract tunnel fit information using GPT and date extraction

        Args:
            tweet_text: The tweet content to analyze
            target_player: The specific player we're scraping for
            tweet_url: Optional URL for reference
            tweet_id: Optional tweet ID for reference
            tweet_created_at: Tweet creation date for fallback

        Returns:
            TunnelFitData object if tunnel fit found, None otherwise
        """
        prompt = self._create_tunnel_fit_prompt(tweet_text, target_player, tweet_url)

        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a fashion and style expert specializing in sports outfit analysis. Parse tweets for player outfit/tunnel fit information from style accounts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=GPT_MAX_TOKENS,
                temperature=GPT_TEMPERATURE,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("is_tunnel_fit", False):
                return None

            # Resolve final date using AI result with fallback
            final_date, date_source, date_confidence = self._resolve_tunnel_fit_date(
                result, tweet_text, tweet_created_at
            )

            return TunnelFitData(
                is_tunnel_fit=result.get("is_tunnel_fit", False),
                event=result.get("event", ""),
                date=final_date,
                type=result.get("type", ""),
                outfit_details=result.get("outfit_details", []),
                location=result.get("location", ""),
                player_name=result.get("player_name", ""),
                source_tweet_id=create_tweet_id(tweet_id),
                social_stats=result.get("social_stats", {}),
                date_confidence=date_confidence,
                fit_confidence=result.get("fit_confidence", 0.0),
                date_source=date_source,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from GPT for tunnel fit: {e}")
            return None
        except openai.APIError as e:
            logger.error(f"OpenAI API error for tunnel fit: {e}")
            return None
        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded for tunnel fit: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing tunnel fit tweet with GPT: {e}")
            return None

    def _resolve_tunnel_fit_date(
        self,
        ai_result: dict,
        tweet_text: str,
        tweet_created_at: Optional[datetime] = None,
    ) -> tuple[Optional[date], str, float]:
        """
        Resolve final date from AI result with fallback to text extraction

        Args:
            ai_result: AI parsing result dictionary
            tweet_text: Tweet content for fallback extraction
            tweet_created_at: Tweet creation datetime for final fallback

        Returns:
            Tuple of (date, source, confidence)
        """
        # Try AI-extracted date first
        if ai_result.get("date"):
            try:
                ai_date_str = ai_result.get("date")
                final_date = datetime.strptime(ai_date_str, "%Y-%m-%d").date()
                logger.info(f"Using AI-extracted date: {final_date}")
                return final_date, "ai_extraction", 0.9
            except (ValueError, TypeError):
                logger.warning(f"Could not parse AI-extracted date: {ai_date_str}")

        # Fall back to regex extraction if AI didn't find a date
        logger.debug("AI did not provide date, falling back to regex extraction")
        return self._extract_date_from_text(tweet_text, tweet_created_at)

    def _extract_date_from_text(
        self, tweet_text: str, tweet_created_at: Optional[datetime] = None
    ) -> tuple[Optional[date], str, float]:
        """
        Extract date from tweet text with fallback to tweet creation date

        Args:
            tweet_text: Tweet content to search for dates
            tweet_created_at: Tweet creation datetime for fallback

        Returns:
            Tuple of (date, source, confidence)
        """
        # Look for explicit dates in text like "September 5, 2025:" or "March 25, 2025:"
        date_patterns = [
            r"(\w+\s+\d{1,2},\s+\d{4}):",  # "September 5, 2025:"
            r"(\d{1,2}/\d{1,2}/\d{4}):",  # "9/5/2024:"
            r"(\d{4}-\d{2}-\d{2}):",  # "2024-09-05:"
        ]

        for pattern in date_patterns:
            match = re.search(pattern, tweet_text)
            if match:
                date_str = match.group(1)
                try:
                    # Try to parse the found date
                    if "/" in date_str:
                        parsed_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                    elif "-" in date_str:
                        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    else:
                        parsed_date = datetime.strptime(date_str, "%B %d, %Y").date()

                    logger.info(
                        f"Extracted date from text: {date_str} -> {parsed_date}"
                    )
                    return parsed_date, "tweet_text", 0.9
                except ValueError:
                    logger.warning(f"Could not parse extracted date: {date_str}")
                    continue

        # Fallback to tweet creation date
        if tweet_created_at:
            logger.info(
                f"Using tweet creation date as fallback: {tweet_created_at.date()}"
            )
            return tweet_created_at.date(), "tweet_published", 0.5

        return None, "no_date_found", 0.0

    def _create_tunnel_fit_prompt(
        self, tweet_text: str, target_player: str, tweet_url: str = ""
    ) -> str:
        """Create the prompt for GPT tunnel fit parsing"""

        return f"""
Analyze this tweet for tunnel fit/outfit information about "{target_player}":

Tweet: "{tweet_text}"
URL: {tweet_url}

INSTRUCTIONS:

1. TUNNEL FIT IDENTIFICATION - Only classify as tunnel fit if:
   - Contains outfit/fashion/style information about {target_player}
   - Shows or describes what {target_player} is wearing
   - From a style or fashion-focused account
   - NOT just general game stats or performance info

2. OUTFIT DETAILS EXTRACTION - Parse structured outfit information:
   - Item names (e.g., "Sevyn Jacket", "Chocolate patent leather loafers")
   - Brand names (e.g., "@Prada", "@veronicabeard", "Veronica Beard")
   - Prices (e.g., "$748", "$1200")
   - Shopping links (shopmy.us, go.shopmy.us links)
   - Affiliate status (true if contains affiliate links)

3. EVENT CLASSIFICATION:
   - "gameday" if mentions vs/against another team, game context
   - "events" if mentions named events, appearances, non-game activities

4. LOCATION EXTRACTION - Pull city/venue from event context

Return JSON format:
{{
  "is_tunnel_fit": boolean,
  "event": "Event name and context",
  "type": "gameday" or "events",
  "outfit_details": [
    {{
      "item": "Item name",
      "brand": "Brand name",
      "price": "$XXX",
      "shopLink": "URL if available",
      "affiliate": true/false
    }}
  ],
  "location": "City, State",
  "player_name": "{target_player}",
  "fit_confidence": 0.9
}}

REJECT Examples (return is_tunnel_fit: false):
- Game stats or performance tweets
- General basketball discussion
- Tweets not about {target_player}'s outfits

ACCEPT Examples:
- Style account posts about {target_player}'s outfits
- Tunnel walk outfit descriptions
- Fashion/outfit breakdowns with brands and prices
"""

    def parse_shoe_tweet(
        self,
        tweet_text: str,
        target_player: str,
        tweet_url: str = "",
        tweet_id: str = "",
        tweet_created_at: Optional[datetime] = None,
    ) -> Optional[ShoeData]:
        """
        Parse a tweet to extract shoe information using GPT and date extraction

        Args:
            tweet_text: The tweet content to analyze
            target_player: The specific player we're scraping for
            tweet_url: Optional URL for reference
            tweet_id: Optional tweet ID for reference
            tweet_created_at: Tweet creation date for fallback

        Returns:
            ShoeData object if shoe post found, None otherwise
        """
        prompt = self._create_shoe_prompt(tweet_text, target_player, tweet_url)

        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sneaker and basketball shoe expert specializing in player footwear analysis. Parse tweets for basketball shoe information and product details.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=GPT_MAX_TOKENS,
                temperature=GPT_TEMPERATURE,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("is_shoe_post", False):
                return None

            # Resolve final date using AI result with fallback
            final_date, date_source, date_confidence = self._resolve_shoe_date(
                result, tweet_text, tweet_created_at
            )

            # Try to extract shoe release date from AI result with robust parsing
            shoe_release_date = self._parse_release_date(result.get("release_date"))

            # Check for missing fields that might need fallback services (after processing)
            missing_fields = []
            if not shoe_release_date:
                missing_fields.append("release_date")
            if not result.get("price") or result.get("price") == "":
                missing_fields.append("price")
            if not result.get("performance_features"):
                missing_fields.append("performance_features")

            # Validate date relationships
            date_validation_issues = self._validate_shoe_dates(
                final_date, shoe_release_date
            )
            if date_validation_issues:
                logger.warning(
                    f"Date validation issues for shoe: {date_validation_issues}"
                )

            return ShoeData(
                is_shoe_post=result.get("is_shoe_post", False),
                shoe_name=result.get("shoe_name", ""),
                brand=result.get("brand", ""),
                model=result.get("model", ""),
                color_description=result.get("color_description", ""),
                date=final_date,  # Tweet/post date for game stats matching
                release_date=shoe_release_date,  # Shoe's actual release date
                price=result.get("price", ""),
                signature_shoe=result.get("signature_shoe", False),
                limited_edition=result.get("limited_edition", False),
                performance_features=result.get("performance_features", []),
                description=result.get("description", ""),
                player_name=result.get("player_name", target_player),
                source_tweet_id=create_tweet_id(tweet_id),
                social_stats=result.get("social_stats", {}),
                date_confidence=date_confidence,
                shoe_confidence=result.get("shoe_confidence", 0.0),
                date_source=date_source,
                has_missing_data=len(missing_fields) > 0,
                missing_fields=missing_fields,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from GPT for shoe: {e}")
            return None
        except openai.APIError as e:
            logger.error(f"OpenAI API error for shoe: {e}")
            return None
        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded for shoe: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing shoe tweet with GPT: {e}")
            return None

    def _resolve_shoe_date(
        self,
        ai_result: Dict,
        tweet_text: str,
        tweet_created_at: Optional[datetime] = None,
    ) -> tuple[Optional[date], str, float]:
        """Resolve the shoe date from AI extraction or fallback to tweet date"""

        # Try AI-extracted date first
        if ai_result.get("extracted_date"):
            try:
                extracted_date = datetime.fromisoformat(
                    ai_result["extracted_date"]
                ).date()
                return (
                    extracted_date,
                    "tweet_text",
                    ai_result.get("date_confidence", 0.8),
                )
            except (ValueError, TypeError):
                logger.debug("Invalid date format from AI extraction")

        # Fallback to tweet published date
        if tweet_created_at:
            return tweet_created_at.date(), "tweet_published", 0.5

        # No date available
        return None, "none", 0.0

    def _create_shoe_prompt(
        self, tweet_text: str, target_player: str, tweet_url: str = ""
    ) -> str:
        """Create prompt for shoe information extraction"""
        return f"""
Analyze this tweet for basketball shoe information related to {target_player}.

TWEET TEXT: "{tweet_text}"
URL: {tweet_url}

CLASSIFICATION CRITERIA:
1. SHOE POST IDENTIFICATION - Must contain:
   - Specific basketball shoe model/brand information
   - Related to {target_player} wearing or endorsing shoes
   - From sneaker accounts, sports accounts, or shoe retailers
   - NOT just general game highlights or performance stats

2. SHOE DETAILS EXTRACTION:
   - Full shoe name with colorway (e.g., "Nike Kobe 6 Protro 'Light Armory Blue'")
   - Brand (Nike, Adidas, Jordan, etc.)
   - Model line (Kobe 6 Protro, Air Jordan 1, etc.)
   - Colorway/description (Light Armory Blue, Bred, etc.)
   - Price information if mentioned
   - Release date if mentioned
   - Limited edition status
   - Signature shoe status (player's signature model)
   - Performance features (Zoom Air, React foam, etc.)

3. DATE EXTRACTION:
   - Look for dates in tweet text (game dates, release dates)
   - Format as YYYY-MM-DD if found

Return JSON format:
{{
  "is_shoe_post": boolean,
  "shoe_name": "Full shoe name with colorway",
  "brand": "Brand name",
  "model": "Model line",
  "color_description": "Colorway description",
  "release_date": "YYYY-MM-DD or null",
  "price": "$XXX or empty string",
  "signature_shoe": boolean,
  "limited_edition": boolean,
  "performance_features": ["feature1", "feature2"],
  "description": "Detailed description of the shoe post",
  "player_name": "{target_player}",
  "extracted_date": "YYYY-MM-DD if found in text",
  "date_confidence": 0.0-1.0,
  "shoe_confidence": 0.0-1.0
}}

REJECT Examples (return is_shoe_post: false):
- General game stats or performance tweets
- Tweets not mentioning specific shoe models
- Generic basketball discussion
- Tweets not about {target_player}'s footwear

ACCEPT Examples:
- Sneaker account posts about {target_player}'s game shoes
- Shoe release announcements related to {target_player}
- Product details about shoes worn by {target_player}
"""

    def _parse_release_date(self, release_date_str: Optional[str]) -> Optional[date]:
        """
        Robust parsing of shoe release dates from various formats

        Args:
            release_date_str: Date string from AI extraction

        Returns:
            Parsed date object or None if parsing fails
        """
        if not release_date_str or not isinstance(release_date_str, str):
            return None

        # Clean the input string
        cleaned_date = release_date_str.strip()
        if not cleaned_date or cleaned_date.lower() in ["null", "none", "unknown", ""]:
            return None

        # Common date formats to try
        date_formats = [
            "%Y-%m-%d",  # 2025-10-01 (ISO format)
            "%m/%d/%Y",  # 10/01/2025 (US format)
            "%m-%d-%Y",  # 10-01-2025
            "%B %d, %Y",  # October 1, 2025
            "%b %d, %Y",  # Oct 1, 2025
            "%Y/%m/%d",  # 2025/10/01
            "%d/%m/%Y",  # 01/10/2025 (European format)
            "%Y.%m.%d",  # 2025.10.01
            "%Y%m%d",  # 20251001 (compact format)
        ]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(cleaned_date, fmt).date()
                logger.debug(
                    f"Successfully parsed release date '{release_date_str}' using format '{fmt}'"
                )
                return parsed_date
            except ValueError:
                continue

        # Try ISO format parsing as fallback
        try:
            parsed_date = datetime.fromisoformat(cleaned_date).date()
            logger.debug(
                f"Successfully parsed release date '{release_date_str}' using ISO format"
            )
            return parsed_date
        except ValueError:
            pass

        logger.warning(
            f"Could not parse release date: '{release_date_str}' - no matching format found"
        )
        return None

    def _validate_shoe_dates(
        self, tweet_date: Optional[date], release_date: Optional[date]
    ) -> List[str]:
        """
        Validate business logic relationships between shoe dates

        Args:
            tweet_date: When the tweet was posted
            release_date: When the shoe was released

        Returns:
            List of validation issues (empty if no issues)
        """
        issues = []

        if not tweet_date and not release_date:
            return issues  # No dates to validate

        if tweet_date and release_date:
            # Basic business logic: can't tweet about a shoe before it's released
            # Allow some tolerance for leaks/early announcements (30 days)
            if release_date > tweet_date:
                days_early = (release_date - tweet_date).days
                if days_early > 30:  # More than 30 days before release
                    issues.append(
                        f"Tweet posted {days_early} days before shoe release - possible date error"
                    )

            # Sanity check: very old release dates are probably parsing errors
            if release_date.year < 1980:
                issues.append(
                    f"Release date {release_date} seems too old - possible parsing error"
                )

            # Future release dates beyond reasonable horizon
            if release_date.year > datetime.now().year + 5:
                issues.append(
                    f"Release date {release_date} is too far in future - possible parsing error"
                )

        return issues


# Unused functions removed for production - see development branch for utilities
