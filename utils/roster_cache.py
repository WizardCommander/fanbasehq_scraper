"""
WNBA Team Roster Cache Builder
Fetches and caches all team rosters from ESPN API
"""

import json
import asyncio
import logging
from pathlib import Path
import aiohttp
from typing import Dict, List, Optional, Tuple

# Configuration
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams"
ESPN_ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{team_id}/roster"
CACHE_FILE = Path(__file__).parent.parent / "config" / "team_rosters.json"
REQUEST_DELAY = 1.0  # Be respectful to ESPN API

logger = logging.getLogger(__name__)


class RosterCacheBuilder:
    """Builds and maintains local cache of WNBA team rosters"""

    def __init__(self):
        self.session = None
        self.last_request_time = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; WNBA-data-collector)",
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _rate_limited_get(self, url: str):
        """Make rate-limited request to ESPN API"""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - time_since_last)

        logger.debug(f"Fetching: {url}")
        self.last_request_time = asyncio.get_event_loop().time()
        return await self.session.get(url)

    async def get_all_teams(self) -> List[Dict]:
        """Get list of all WNBA teams from ESPN"""
        async with await self._rate_limited_get(ESPN_TEAMS_URL) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch teams: HTTP {response.status}")
                return []

            data = await response.json()
            # Navigate ESPN's nested structure
            sports = data.get("sports", [])
            if not sports:
                logger.error("No sports data found")
                return []

            leagues = sports[0].get("leagues", [])
            if not leagues:
                logger.error("No leagues data found")
                return []

            teams = leagues[0].get("teams", [])
            logger.info(f"Found {len(teams)} WNBA teams")
            return teams

    async def get_team_roster(self, team_id: str, team_name: str) -> List[Dict]:
        """Get roster for a specific team"""
        url = ESPN_ROSTER_URL.format(team_id=team_id)

        try:
            async with await self._rate_limited_get(url) as response:
                if response.status != 200:
                    logger.warning(
                        f"Failed to fetch roster for {team_name}: HTTP {response.status}"
                    )
                    return []

                data = await response.json()
                athletes = data.get("athletes", [])

                roster = []
                for athlete in athletes:
                    # Extract player info
                    player_info = {
                        "name": athlete.get("displayName", ""),
                        "full_name": athlete.get("fullName", ""),
                        "jersey": athlete.get("jersey", ""),
                        "position": athlete.get("position", {}).get("abbreviation", ""),
                        "position_name": athlete.get("position", {}).get("name", ""),
                        "age": athlete.get("age", 0),
                        "height": athlete.get("displayHeight", ""),
                        "weight": athlete.get("displayWeight", ""),
                        "experience": athlete.get("experience", {}).get("years", 0),
                    }
                    roster.append(player_info)

                logger.info(f"Found {len(roster)} players for {team_name}")
                return roster

        except Exception as e:
            logger.error(f"Error fetching roster for {team_name}: {e}")
            return []

    async def build_roster_cache(self) -> Dict:
        """Build complete roster cache for all WNBA teams"""
        logger.info("Building WNBA roster cache...")

        # Get all teams
        teams = await self.get_all_teams()
        if not teams:
            logger.error("Could not fetch team list")
            return {}

        roster_cache = {
            "last_updated": asyncio.get_event_loop().time(),
            "season": "2025",
            "teams": {},
            "players": {},  # player_name -> team_name mapping
        }

        # Fetch each team's roster
        for team in teams:
            team_name = team.get("team", {}).get("displayName", "")
            team_id = team.get("team", {}).get("id", "")
            team_abbr = team.get("team", {}).get("abbreviation", "")

            if not team_name or not team_id:
                logger.warning(f"Skipping team with incomplete data: {team}")
                continue

            logger.info(f"Fetching roster for {team_name} (ID: {team_id})")

            roster = await self.get_team_roster(team_id, team_name)

            # Store team info and roster
            roster_cache["teams"][team_name] = {
                "id": team_id,
                "abbreviation": team_abbr,
                "name": team_name,
                "roster": roster,
            }

            # Build player -> team mapping
            for player in roster:
                player_name = player["name"].lower().strip()
                full_name = player["full_name"].lower().strip()

                roster_cache["players"][player_name] = team_name
                if full_name != player_name:
                    roster_cache["players"][full_name] = team_name

        logger.info(f"Built roster cache for {len(roster_cache['teams'])} teams")
        logger.info(f"Cached {len(roster_cache['players'])} player entries")

        return roster_cache

    def save_cache(self, cache_data: Dict):
        """Save roster cache to JSON file"""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Roster cache saved to {CACHE_FILE}")

        except Exception as e:
            logger.error(f"Failed to save roster cache: {e}")

    def load_cache(self) -> Dict:
        """Load existing roster cache"""
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                logger.info(f"Loaded roster cache from {CACHE_FILE}")
                return cache
            else:
                logger.info("No existing roster cache found")
                return {}
        except Exception as e:
            logger.error(f"Failed to load roster cache: {e}")
            return {}


def lookup_player_team(player_name: str, cache_file: str = None) -> str:
    """
    Quick lookup function to find what team a player is on

    Args:
        player_name: Player name to look up
        cache_file: Optional path to cache file

    Returns:
        Team name or None if not found
    """
    if cache_file is None:
        cache_file = CACHE_FILE

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)

        normalized_name = player_name.lower().strip()
        return cache.get("players", {}).get(normalized_name)

    except Exception as e:
        logger.error(f"Failed to lookup player {player_name}: {e}")
        return None


def lookup_player_team_with_id(
    player_name: str, cache_file: str = None
) -> Optional[Tuple[str, str]]:
    """
    Lookup function to find team name and ID for a player

    Args:
        player_name: Player name to look up
        cache_file: Optional path to cache file

    Returns:
        Tuple of (team_name, team_id) or None if not found
    """
    if cache_file is None:
        cache_file = CACHE_FILE

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)

        normalized_name = player_name.lower().strip()
        team_name = cache.get("players", {}).get(normalized_name)

        if not team_name:
            return None

        # Look up team ID from teams data
        teams = cache.get("teams", {})
        if team_name in teams:
            team_id = teams[team_name]["id"]
            return (team_name, team_id)

        return None

    except Exception as e:
        logger.error(f"Failed to lookup player {player_name}: {e}")
        return None


async def build_and_save_roster_cache():
    """Main function to build and save roster cache"""
    async with RosterCacheBuilder() as builder:
        cache_data = await builder.build_roster_cache()

        if cache_data:
            builder.save_cache(cache_data)

            # Test the lookup function
            test_players = ["caitlin clark", "kelsey plum", "breanna stewart"]
            print("\n=== Testing player lookups ===")
            for player in test_players:
                team = lookup_player_team(player)
                print(f"{player.title()}: {team}")

            print(f"\nRoster cache built successfully!")
            print(f"Cached {len(cache_data.get('teams', {}))} teams")
            print(f"Cached {len(cache_data.get('players', {}))} player entries")
        else:
            logger.error("Failed to build roster cache")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Build the cache
    asyncio.run(build_and_save_roster_cache())
