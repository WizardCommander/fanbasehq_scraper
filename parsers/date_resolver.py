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
from services.preseason_schedule_service import validate_preseason_game
from utils.roster_cache import lookup_player_team
from config.settings import (
    HIGH_CONFIDENCE_THRESHOLD,
    BOXSCORE_ANALYSIS_CONFIDENCE,
    GAME_SCHEDULE_CONFIDENCE,
    TEXT_PARSING_CONFIDENCE,
    FALLBACK_CONFIDENCE,
    MINIMUM_DATE_CONFIDENCE,
)

logger = logging.getLogger(__name__)


# ESPNScheduleLookup class removed - now using sportsdataverse for individual player game logs


class MilestoneDateResolver:
    """Resolves milestone dates using local roster cache + ESPN API"""

    # Date patterns to look for in tweets
    DATE_PATTERNS = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",  # MM/DD/YYYY or MM-DD-YYYY
        r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})",  # YYYY/MM/DD or YYYY-MM-DD
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}",
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}",
    ]

    # Context patterns that indicate milestone timing
    CONTEXT_PATTERNS = [
        r"on this day in (\d{4})",
        r"in (\d{4})",
        r"on this day last year",
        r"one year ago today",
        r"a year ago today",
        r"this day (\d+) years? ago",
        r"(\d+) years? ago today",
        r"last season",
        r"her rookie season",
        r"rookie year",
        r"yesterday",
        r"today",
        r"against the (\w+)",
        r"vs\.?\s+(\w+)",
    ]

    def __init__(self):
        pass

    async def resolve_milestone_date(
        self, milestone: MilestoneData, tweet_created_at: datetime, player_name: str
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
        # Strategy 1: Use AI-extracted date with boxscore analysis (highest priority)
        if (
            milestone.extracted_date
            and milestone.date_source == "boxscore_analysis"
            and milestone.date_confidence > HIGH_CONFIDENCE_THRESHOLD
        ):
            try:
                extracted_date = self._parse_date_string(milestone.extracted_date)
                if extracted_date:
                    # Boxscore analysis already includes game validation, so trust high confidence results
                    logger.info(
                        f"Using boxscore-analyzed date: {extracted_date} (confidence: {milestone.date_confidence:.2f})"
                    )
                    return (
                        extracted_date,
                        "boxscore_analysis",
                        BOXSCORE_ANALYSIS_CONFIDENCE,
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to parse boxscore-analyzed date '{milestone.extracted_date}': {e}"
                )

        # Strategy 2: Use AI-extracted date from text if high confidence AND validate against game logs
        if (
            milestone.extracted_date
            and milestone.date_source == "tweet_text"
            and milestone.date_confidence > HIGH_CONFIDENCE_THRESHOLD
        ):
            try:
                extracted_date = self._parse_date_string(milestone.extracted_date)
                if extracted_date:
                    # Validate that player actually played on this date
                    if await self._validate_against_game_logs(
                        extracted_date, player_name
                    ):
                        logger.info(
                            f"Using validated AI-extracted date: {extracted_date} (confidence: {milestone.date_confidence:.2f})"
                        )
                        return (
                            extracted_date,
                            "tweet_text_validated",
                            milestone.date_confidence,
                        )
                    else:
                        logger.warning(
                            f"AI date {extracted_date} not valid - player didn't play that day"
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to parse AI-extracted date '{milestone.extracted_date}': {e}"
                )

        # Strategy 3: Parse dates from tweet text directly and validate
        parsed_date, context = self._extract_date_from_text(
            milestone.description, tweet_created_at
        )
        if parsed_date:
            if await self._validate_against_game_logs(parsed_date, player_name):
                confidence = TEXT_PARSING_CONFIDENCE if context else 0.6
                # Check if confidence meets minimum threshold
                if confidence >= MINIMUM_DATE_CONFIDENCE:
                    logger.info(
                        f"Using validated text-parsed date: {parsed_date} (context: {context})"
                    )
                    return parsed_date, "tweet_text_validated", confidence
                else:
                    logger.info(
                        f"Text-parsed date confidence too low ({confidence:.2f} < {MINIMUM_DATE_CONFIDENCE}), rejecting date"
                    )
            else:
                logger.warning(
                    f"Text-parsed date {parsed_date} not valid - player didn't play that day"
                )

        # Strategy 4: Use most recent game date (regular season or preseason)
        game_date = await self._find_recent_game_date(
            player_name, tweet_created_at.date()
        )
        if game_date and GAME_SCHEDULE_CONFIDENCE >= MINIMUM_DATE_CONFIDENCE:
            # Determine if this was a preseason or regular season game
            source_type = "game_schedule"  # Default
            try:
                team_name = lookup_player_team(player_name)
                if team_name:
                    preseason_valid = await validate_preseason_game(
                        team_name, game_date, game_date.year
                    )
                    if preseason_valid:
                        source_type = "preseason_schedule"
            except Exception as e:
                logger.debug(f"Error determining game type: {e}")

            logger.info(
                f"Using most recent game date: {game_date} (source: {source_type})"
            )
            return game_date, source_type, GAME_SCHEDULE_CONFIDENCE

        # Strategy 5: Conservative fallback - return None for blank date
        logger.warning(
            f"No confident date found for milestone. Confidence thresholds not met - leaving date blank for manual review"
        )
        return None, "uncertain", 0.0

    async def _find_recent_game_date(
        self, player_name: str, tweet_date: date
    ) -> Optional[date]:
        """Find most recent game where player actually played using individual game logs and preseason schedules"""
        try:
            # First try regular season games
            recent_game_date = await get_player_recent_game(player_name, tweet_date)
            if recent_game_date:
                logger.debug(
                    f"Found recent regular season game for {player_name}: {recent_game_date}"
                )
                return recent_game_date

            # If no regular season game found, check preseason games
            team_name = lookup_player_team(player_name)
            if team_name:
                from services.preseason_schedule_service import PreseasonScheduleService

                async with PreseasonScheduleService() as preseason_service:
                    season = tweet_date.year
                    preseason_dates = await preseason_service.get_team_preseason_dates(
                        team_name, season
                    )

                    # Find most recent preseason game before tweet date
                    valid_preseason_dates = [
                        d for d in preseason_dates if d < tweet_date
                    ]
                    if valid_preseason_dates:
                        most_recent_preseason = max(valid_preseason_dates)
                        logger.debug(
                            f"Found recent preseason game for {player_name}'s team ({team_name}): {most_recent_preseason}"
                        )
                        return most_recent_preseason

            logger.debug(f"No recent games found for {player_name}")
            return None

        except Exception as e:
            logger.error(f"Error finding recent game for {player_name}: {e}")

        return None

    async def _validate_against_game_logs(
        self, target_date: date, player_name: str
    ) -> bool:
        """
        Validate that the player actually played on the target date
        Checks both regular season (SportDataverse) and preseason games (ESPN API)

        Args:
            target_date: Date to validate
            player_name: Player name to check

        Returns:
            True if player played on that date, False otherwise
        """
        try:
            # First check regular season games using existing logic
            from utils.player_game_logs import PlayerGameLogService

            service = PlayerGameLogService(
                force_refresh=False
            )  # Use cache for validation

            # Get player's regular season game dates
            season = target_date.year
            player_game_dates = await service.get_player_game_dates(player_name, season)

            # Check regular season first
            if target_date in player_game_dates:
                logger.debug(
                    f"Found regular season game for {player_name} on {target_date}"
                )
                return True

            # If not found in regular season, check preseason games
            team_name = lookup_player_team(player_name)
            if team_name:
                preseason_valid = await validate_preseason_game(
                    team_name, target_date, season
                )
                if preseason_valid:
                    logger.debug(
                        f"Found preseason game for {player_name}'s team ({team_name}) on {target_date}"
                    )
                    return True
                else:
                    logger.debug(
                        f"No preseason game found for {team_name} on {target_date}"
                    )
            else:
                logger.warning(
                    f"Could not find team for {player_name} to check preseason games"
                )

            return False

        except Exception as e:
            logger.error(f"Error validating game date: {e}")
            return False  # If we can't validate, reject the date

    def _extract_date_from_text(
        self, text: str, tweet_date: datetime
    ) -> Tuple[Optional[date], str]:
        """Extract date from tweet text using patterns"""
        text_lower = text.lower()

        # Check for context patterns first
        for pattern in self.CONTEXT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if "on this day in" in match.group().lower():
                    try:
                        year = int(match.group(1))
                        milestone_date = tweet_date.replace(year=year).date()
                        return milestone_date, f"on this day in {year}"
                    except:
                        pass

                elif (
                    "last year" in match.group().lower()
                    or "year ago" in match.group().lower()
                ):
                    try:
                        # Calculate date one year ago from tweet date
                        milestone_date = tweet_date.replace(
                            year=tweet_date.year - 1
                        ).date()
                        return milestone_date, "one year ago"
                    except ValueError:
                        # Handle leap year edge case (Feb 29)
                        try:
                            milestone_date = tweet_date.replace(
                                year=tweet_date.year - 1, day=28
                            ).date()
                            return milestone_date, "one year ago (leap year adjusted)"
                        except:
                            pass

                elif "years ago" in match.group().lower():
                    try:
                        # Extract number of years and calculate date
                        years_back = (
                            int(match.group(1))
                            if hasattr(match, "group") and len(match.groups()) > 0
                            else 1
                        )
                        milestone_date = tweet_date.replace(
                            year=tweet_date.year - years_back
                        ).date()
                        return milestone_date, f"{years_back} years ago"
                    except (ValueError, IndexError):
                        pass

                elif (
                    "last season" in match.group().lower()
                    or "rookie" in match.group().lower()
                ):
                    try:
                        milestone_date = tweet_date.replace(year=2024).date()
                        return milestone_date, "rookie season context"
                    except:
                        pass

                elif "yesterday" in match.group().lower():
                    yesterday = tweet_date.date() - timedelta(days=1)
                    return yesterday, "yesterday"

                elif "today" in match.group().lower():
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
