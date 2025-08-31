"""
Date resolution service for milestone dating accuracy using local roster cache + ESPN API
Combines AI-extracted dates with game schedule validation for precise milestone timing
"""

import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Tuple
from dateutil import parser as date_parser


from parsers.ai_parser import MilestoneData
from utils.roster_cache import lookup_player_team
from utils.player_game_logs import get_player_recent_game
from config.settings import (
    HIGH_CONFIDENCE_THRESHOLD, 
    GAME_SCHEDULE_CONFIDENCE, 
    TEXT_PARSING_CONFIDENCE,
    FALLBACK_CONFIDENCE
)

logger = logging.getLogger(__name__)


# ESPNScheduleLookup class removed - now using sportsdataverse for individual player game logs


class MilestoneDateResolver:
    """Resolves milestone dates using local roster cache + ESPN API"""
    
    # Date patterns to look for in tweets
    DATE_PATTERNS = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # MM/DD/YYYY or MM-DD-YYYY
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',  # YYYY/MM/DD or YYYY-MM-DD
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}',
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}',
    ]
    
    # Context patterns that indicate milestone timing
    CONTEXT_PATTERNS = [
        r'on this day in (\d{4})',
        r'in (\d{4})',
        r'last season',
        r'her rookie season',
        r'rookie year',
        r'yesterday',
        r'today',
        r'against the (\w+)',
        r'vs\.?\s+(\w+)',
    ]
    
    def __init__(self):
        pass
        
    async def resolve_milestone_date(
        self,
        milestone: MilestoneData,
        tweet_created_at: datetime,
        player_name: str
    ) -> Tuple[date, str, float]:
        """
        Resolve the actual date a milestone occurred
        
        Args:
            milestone: MilestoneData with extracted date info
            tweet_created_at: When the tweet was published
            player_name: Player name for team lookup
            
        Returns:
            Tuple of (resolved_date, source, confidence)
        """
        # Strategy 1: Use AI-extracted date if high confidence AND validate against game logs
        if milestone.extracted_date and milestone.date_confidence > HIGH_CONFIDENCE_THRESHOLD:
            try:
                extracted_date = self._parse_date_string(milestone.extracted_date)
                if extracted_date:
                    # Validate that player actually played on this date
                    if await self._validate_against_game_logs(extracted_date, player_name):
                        logger.info(f"Using validated AI-extracted date: {extracted_date} (confidence: {milestone.date_confidence:.2f})")
                        return extracted_date, "tweet_text_validated", milestone.date_confidence
                    else:
                        logger.warning(f"AI date {extracted_date} not valid - player didn't play that day")
            except Exception as e:
                logger.warning(f"Failed to parse AI-extracted date '{milestone.extracted_date}': {e}")
        
        # Strategy 2: Parse dates from tweet text directly and validate
        parsed_date, context = self._extract_date_from_text(milestone.description, tweet_created_at)
        if parsed_date:
            if await self._validate_against_game_logs(parsed_date, player_name):
                confidence = TEXT_PARSING_CONFIDENCE if context else 0.6
                logger.info(f"Using validated text-parsed date: {parsed_date} (context: {context})")
                return parsed_date, "tweet_text_validated", confidence
            else:
                logger.warning(f"Text-parsed date {parsed_date} not valid - player didn't play that day")
        
        # Strategy 3: Use most recent game date (fallback when no specific date found)
        game_date = await self._find_recent_game_date(player_name, tweet_created_at.date())
        if game_date:
            logger.info(f"Using most recent game date: {game_date}")
            return game_date, "game_schedule", GAME_SCHEDULE_CONFIDENCE
        
        # Strategy 4: Fallback to tweet publication date
        tweet_date = tweet_created_at.date()
        logger.warning(f"Falling back to tweet publication date: {tweet_date}")
        return tweet_date, "tweet_published", FALLBACK_CONFIDENCE
        
    async def _find_recent_game_date(self, player_name: str, tweet_date: date) -> Optional[date]:
        """Find most recent game where player actually played using individual game logs"""
        try:
            # Use player-specific game logs instead of team schedules
            recent_game_date = await get_player_recent_game(player_name, tweet_date)
            if recent_game_date:
                logger.debug(f"Found recent game for {player_name}: {recent_game_date}")
                return recent_game_date
                    
            logger.debug(f"No recent games found for {player_name}")
            return None
                    
        except Exception as e:
            logger.error(f"Error finding recent game for {player_name}: {e}")
            
        return None
        
    async def _validate_against_game_logs(self, target_date: date, player_name: str) -> bool:
        """
        Validate that the player actually played on the target date
        
        Args:
            target_date: Date to validate
            player_name: Player name to check
            
        Returns:
            True if player played on that date, False otherwise
        """
        try:
            from utils.player_game_logs import PlayerGameLogService
            
            # Check if player played on this specific date
            service = PlayerGameLogService(force_refresh=False)  # Use cache for validation
            
            # Get player's game dates for the season
            season = target_date.year
            player_game_dates = await service.get_player_game_dates(player_name, season)
            
            return target_date in player_game_dates
                
        except Exception as e:
            logger.error(f"Error validating game date: {e}")
            return False  # If we can't validate, reject the date
        
    def _extract_date_from_text(self, text: str, tweet_date: datetime) -> Tuple[Optional[date], str]:
        """Extract date from tweet text using patterns"""
        text_lower = text.lower()
        
        # Check for context patterns first
        for pattern in self.CONTEXT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if 'on this day in' in match.group().lower():
                    try:
                        year = int(match.group(1))
                        milestone_date = tweet_date.replace(year=year).date()
                        return milestone_date, f"on this day in {year}"
                    except:
                        pass
                        
                elif 'last season' in match.group().lower() or 'rookie' in match.group().lower():
                    try:
                        milestone_date = tweet_date.replace(year=2024).date()
                        return milestone_date, "rookie season context"
                    except:
                        pass
                        
                elif 'yesterday' in match.group().lower():
                    yesterday = tweet_date.date() - timedelta(days=1)
                    return yesterday, "yesterday"
                    
                elif 'today' in match.group().lower():
                    return tweet_date.date(), "today"
        
        # Look for explicit date patterns
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match if isinstance(match, str) else match[0]
                parsed_date = self._parse_date_string(date_str)
                if parsed_date:
                    return parsed_date, f"explicit date: {date_str}"
        
        return None, ""
        
    def _parse_date_string(self, date_str: str) -> Optional[date]:
        """Parse date string into date object"""
        from utils.date_utils import parse_date
        try:
            return parse_date(date_str, strict=False)
        except ValueError as e:
            logger.debug(f"Failed to parse date string '{date_str}': {e}")
            return None


def create_date_resolver() -> MilestoneDateResolver:
    """Factory function to create a date resolver"""
    return MilestoneDateResolver()


# Test functions removed for production - see development branch for testing utilities