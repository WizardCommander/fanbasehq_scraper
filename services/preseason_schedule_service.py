"""
WNBA Preseason Schedule Service
Manages team-based preseason schedules as source of truth for milestone date validation
"""

import json
import asyncio
import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import aiohttp

from config.settings import CONFIG_DIR
from utils.roster_cache import RosterCacheBuilder

logger = logging.getLogger(__name__)


class PreseasonScheduleService:
    """Service for managing WNBA team preseason schedules"""

    def __init__(self, force_refresh: bool = False):
        self.cache_file = CONFIG_DIR / "preseason_schedules.json"
        self.cache = {}
        self.session = None

        # ESPN API configuration
        self.espn_base_url = (
            "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
        )
        self.request_delay = 1.0  # Be respectful to ESPN API
        self.last_request_time = 0

        if force_refresh:
            self.cache = {"last_updated": 0, "schedules": {}}
            logger.info("Preseason schedule cache cleared for fresh scrape")
        else:
            self.load_cache()

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; WNBA-preseason-collector)",
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    def load_cache(self):
        """Load cached preseason schedules"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(
                    f"Loaded preseason schedule cache with {len(self.cache.get('schedules', {}))} seasons"
                )
            else:
                self.cache = {"last_updated": 0, "schedules": {}}
                logger.info("No preseason schedule cache found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load preseason schedule cache: {e}")
            self.cache = {"last_updated": 0, "schedules": {}}

    def save_cache(self):
        """Save preseason schedules cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, default=str)
            logger.info(f"Saved preseason schedule cache to {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to save preseason schedule cache: {e}")

    def _is_cache_stale(self, season: int, hours: int = 24) -> bool:
        """Check if cache needs updating for a specific season"""
        if "schedules" not in self.cache:
            return True

        season_key = f"preseason_{season}"
        if season_key not in self.cache["schedules"]:
            return True

        season_data = self.cache["schedules"][season_key]
        last_updated = season_data.get("last_updated", 0)

        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated).timestamp()

        return (datetime.now().timestamp() - last_updated) > (hours * 3600)

    async def _rate_limited_get(self, url: str):
        """Make rate-limited request to ESPN API"""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.request_delay:
            await asyncio.sleep(self.request_delay - time_since_last)

        logger.debug(f"Fetching: {url}")
        self.last_request_time = asyncio.get_event_loop().time()
        return await self.session.get(url)

    def _get_team_data(self) -> Dict[str, Dict]:
        """Get team data from roster cache"""
        try:
            cache_builder = RosterCacheBuilder()
            team_cache = cache_builder.load_cache()

            if "teams" in team_cache:
                return team_cache["teams"]
            else:
                logger.warning("No teams found in roster cache")
                return {}

        except Exception as e:
            logger.error(f"Error loading team data from roster cache: {e}")
            return {}

    def _process_team_schedule_data(
        self, data: Dict, team_name: str, season: int
    ) -> List[str]:
        """Process team-specific schedule data from ESPN API - returns dates only"""
        team_dates = []

        try:
            events = data.get("events", [])
            logger.debug(f"Processing {len(events)} events for {team_name}")

            for event in events:
                try:
                    game_date_str = event.get("date", "")
                    if not game_date_str:
                        continue

                    game_date = datetime.fromisoformat(
                        game_date_str.replace("Z", "+00:00")
                    ).date()

                    # Check if this is a preseason game (typically May for WNBA)
                    if self._is_preseason_date(game_date, season):
                        team_dates.append(game_date.isoformat())

                except Exception as e:
                    logger.debug(f"Error processing event for {team_name}: {e}")
                    continue

            # Remove duplicates and sort
            unique_dates = sorted(list(set(team_dates)))
            return unique_dates

        except Exception as e:
            logger.error(f"Error processing team schedule data for {team_name}: {e}")
            return []

    def _is_preseason_date(self, game_date: date, season: int) -> bool:
        """Check if a game date falls within preseason period"""
        # WNBA preseason typically occurs in May
        if season == 2025:
            # 2025 preseason: May 6-16
            return (
                game_date.month == 5
                and game_date.year == season
                and 6 <= game_date.day <= 16
            )
        elif season == 2024:
            # 2024 preseason: May 9-19
            return (
                game_date.month == 5
                and game_date.year == season
                and 9 <= game_date.day <= 19
            )
        else:
            # Default: any May game is likely preseason
            return game_date.month == 5 and game_date.year == season

    async def get_team_preseason_dates(
        self, team_name: str, season: int = 2025
    ) -> List[date]:
        """
        Get all preseason game dates for a team

        Args:
            team_name: Team name
            season: Season year

        Returns:
            List of dates when team played preseason games
        """
        season_key = f"preseason_{season}"

        # Check cache first
        if not self._is_cache_stale(season):
            cached_dates = self._get_cached_team_dates(team_name, season_key)
            if cached_dates:
                logger.info(
                    f"Found {len(cached_dates)} cached preseason dates for {team_name} in {season}"
                )
                return cached_dates

        # Fetch and cache new data
        await self._fetch_and_cache_preseason_schedules(season)

        # Return requested team's dates
        return self._get_cached_team_dates(team_name, season_key)

    async def _fetch_and_cache_preseason_schedules(self, season: int):
        """Fetch preseason schedules from ESPN API using team-specific endpoints"""
        season_key = f"preseason_{season}"

        try:
            logger.info(f"Fetching {season} preseason schedules from ESPN API...")

            # Get all WNBA teams from roster cache
            team_data = self._get_team_data()
            if not team_data:
                logger.error("Could not load team data from roster cache")
                return

            # Fetch all team schedules in parallel with rate limiting
            all_team_schedules = {}
            successful_teams = 0

            for team_name, team_info in team_data.items():
                team_id = team_info.get("id")
                if not team_id:
                    logger.debug(f"No team ID found for {team_name}, skipping")
                    continue

                try:
                    url = f"{self.espn_base_url}/teams/{team_id}/schedule?season={season}&seasontype=1"

                    async with await self._rate_limited_get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            team_dates = self._process_team_schedule_data(
                                data, team_name, season
                            )

                            if team_dates:
                                all_team_schedules[team_name] = team_dates
                                successful_teams += 1
                                logger.debug(
                                    f"Found {len(team_dates)} preseason dates for {team_name}"
                                )
                            else:
                                logger.debug(
                                    f"No preseason dates found for {team_name}"
                                )
                        else:
                            logger.debug(
                                f"Failed to fetch schedule for {team_name}: HTTP {response.status}"
                            )

                except Exception as e:
                    logger.debug(f"Error fetching schedule for {team_name}: {e}")
                    continue

            if successful_teams == 0:
                logger.warning(
                    f"Could not fetch preseason schedules for any teams in {season}"
                )
                return

            # Cache the results
            if "schedules" not in self.cache:
                self.cache["schedules"] = {}

            self.cache["schedules"][season_key] = {
                "teams": all_team_schedules,
                "total_dates": sum(len(dates) for dates in all_team_schedules.values()),
                "last_updated": datetime.now().isoformat(),
                "source": "espn_team_api",
                "successful_teams": successful_teams,
            }

            logger.info(
                f"Cached {season} preseason schedules for {successful_teams}/{len(team_data)} teams"
            )
            self.save_cache()

        except Exception as e:
            logger.error(f"Error fetching {season} preseason schedules: {e}")

    async def validate_team_game_date(
        self, team_name: str, target_date: date, season: int = None
    ) -> bool:
        """
        Validate if a team played a preseason game on a specific date

        Args:
            team_name: Team name to check
            target_date: Date to validate
            season: Season year (defaults to target_date year)

        Returns:
            True if team had a preseason game on that date
        """
        if season is None:
            season = target_date.year

        try:
            team_dates = await self.get_team_preseason_dates(team_name, season)

            if target_date in team_dates:
                logger.debug(f"Found preseason game for {team_name} on {target_date}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error validating preseason game date: {e}")
            return False

    def _get_cached_team_dates(self, team_name: str, season_key: str) -> List[date]:
        """Get cached team dates from cache"""
        try:
            cached_schedules = self.cache.get("schedules", {}).get(season_key, {})
            date_strings = cached_schedules.get("teams", {}).get(team_name, [])
            return [date.fromisoformat(date_str) for date_str in date_strings]
        except Exception as e:
            logger.debug(f"Error parsing cached dates for {team_name}: {e}")
            return []


async def validate_preseason_game(
    team_name: str, target_date: date, season: int = None
) -> bool:
    """
    Convenience function to validate preseason game dates

    Args:
        team_name: Team name to check
        target_date: Date to validate
        season: Season year (defaults to target_date year)

    Returns:
        True if team had a preseason game on that date
    """
    async with PreseasonScheduleService() as service:
        return await service.validate_team_game_date(team_name, target_date, season)
