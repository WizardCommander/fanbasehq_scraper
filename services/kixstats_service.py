"""
KixStats Service
Web scraping service for extracting game-by-game shoe data from KixStats.com
"""

import logging
import asyncio
import json
from datetime import date, datetime
from typing import List, Optional
from dataclasses import dataclass
import aiohttp
from bs4 import BeautifulSoup

from utils.player_game_logs import PlayerGameLogService

logger = logging.getLogger(__name__)


@dataclass
class GameShoeData:
    """Game shoe data extracted from KixStats"""

    game_date: date
    shoe_name: str
    shoe_url: str
    minutes: int
    points: int
    rebounds: int
    assists: int
    steals: int
    blocks: int
    player_name: str = ""
    image_url: str = ""
    opponent: str = "Unknown"  # Team opponent for this game


async def resolve_shoe_opponent(game_date: date, player_name: str) -> str:
    """
    Resolve opponent using proven cross-reference logic from milestone date resolver:
    1. Exact date match in regular season games (SportDataverse)
    2. Exact date match in preseason games (ESPN API)
    3. Find most recent actual game before the target date (uses existing milestone logic)

    Args:
        game_date: Date of the game to look up
        player_name: Player name (e.g., "Caitlin Clark")

    Returns:
        Opponent team name from actual game data
    """
    try:
        # Strategy 1: Check for exact date match first
        game_log_service = PlayerGameLogService()
        # Use the game date's year to query the correct season
        season = game_date.year
        game_stats_list = await game_log_service.get_player_game_stats(
            player_name, season
        )

        # Find exact match in regular season
        for game_stat in game_stats_list:
            if game_stat.date == game_date:
                logger.info(
                    f"Found exact opponent for {game_date}: {game_stat.opponent}"
                )
                return game_stat.opponent

        # Strategy 2: Check preseason games for exact date match
        from parsers.date_resolver import lookup_player_team
        from services.preseason_schedule_service import PreseasonScheduleService

        team_name = lookup_player_team(player_name)
        if team_name:
            async with PreseasonScheduleService() as preseason_service:
                team_dates = await preseason_service.get_team_preseason_dates(
                    team_name, season
                )

                if game_date in team_dates:
                    opponent = await _get_preseason_opponent(
                        preseason_service, team_name, game_date, season
                    )
                    if opponent:
                        logger.info(
                            f"Found exact preseason opponent for {game_date}: {opponent}"
                        )
                        return opponent

        # Strategy 3: Use existing milestone logic - find most recent actual game
        from utils.player_game_logs import get_player_recent_game

        # Find the most recent game before the target date (within 60 days)
        recent_game_date = await get_player_recent_game(player_name, game_date)

        if recent_game_date:
            # Get the opponent for that actual game
            for game_stat in game_stats_list:
                if game_stat.date == recent_game_date:
                    logger.info(
                        f"Found recent game opponent for {game_date}: {game_stat.opponent} (from {recent_game_date})"
                    )
                    return game_stat.opponent

        # If we get here, no games found (shouldn't happen with valid player data)
        logger.warning(f"No opponent resolution possible for {game_date}")
        return "Unknown"

    except Exception as e:
        logger.error(f"Error resolving opponent for {game_date}: {e}")
        return "Unknown"


async def _get_preseason_opponent(
    preseason_service, team_name: str, game_date: date, season: int
) -> str:
    """
    Extract opponent information from preseason schedule data
    """
    try:
        # Access the cached schedule data to find opponent info
        season_key = f"preseason_{season}"
        schedules = preseason_service.cache.get("schedules", {})
        team_schedule = schedules.get(season_key, {}).get(team_name, [])

        # Look for the specific game date in the team's schedule
        for game_date_str in team_schedule:
            if game_date_str == game_date.isoformat():
                # For now, we know there was a game but don't have opponent data
                # The preseason service currently only stores dates, not opponents
                # This could be enhanced in the future to include opponent information
                return None

        return None
    except Exception as e:
        logger.debug(f"Error getting preseason opponent: {e}")
        return None


async def _find_nearest_game_opponent(game_stats_list, target_date: date) -> str:
    """
    Find the opponent from the nearest actual game (within 7 days)
    """
    try:
        nearest_game = None
        min_diff = float("inf")

        for game_stat in game_stats_list:
            diff = abs((game_stat.date - target_date).days)
            if diff <= 7 and diff < min_diff:  # Within 7 days
                min_diff = diff
                nearest_game = game_stat

        if nearest_game:
            return f"{nearest_game.opponent} (±{min_diff}d)"

        return None
    except Exception as e:
        logger.debug(f"Error finding nearest game opponent: {e}")
        return None


async def _get_most_common_season_opponent(game_stats_list, season_year: int) -> str:
    """
    Get the most frequently played opponent from that season or fallback to most recent available data
    """
    try:
        from collections import Counter

        # First try to get games from the requested season
        season_games = [
            game for game in game_stats_list if game.date.year == season_year
        ]

        if season_games:
            # Found games for the requested season - use them
            opponent_counts = Counter(game.opponent for game in season_games)
            most_common_opponent, count = opponent_counts.most_common(1)[0]
            return most_common_opponent  # Return just the team name, not the count

        # No games for requested season - use most recent available data
        if game_stats_list:
            # Use all available games (likely 2024)
            opponent_counts = Counter(game.opponent for game in game_stats_list)
            most_common_opponent, count = opponent_counts.most_common(1)[0]

            # Filter out non-team opponents like "Team USA"
            valid_opponents = [
                opponent
                for opponent, _ in opponent_counts.most_common()
                if opponent not in ["Team USA", "Olympic Team", "USA Basketball"]
            ]

            if valid_opponents:
                # Get the most common valid team opponent
                most_common_valid = opponent_counts[valid_opponents[0]]
                return valid_opponents[0]  # Return just the team name
            else:
                return most_common_opponent  # Fallback to any opponent

        return None

    except Exception as e:
        logger.debug(f"Error getting most common season opponent: {e}")
        return None


def _get_fallback_opponent(season_year: int) -> str:
    """
    Get a generic fallback opponent based on season and league knowledge
    """
    # WNBA teams that commonly play against Indiana Fever
    common_opponents = [
        "Sun",
        "Liberty",
        "Aces",
        "Storm",
        "Lynx",
        "Wings",
        "Dream",
        "Sky",
        "Sparks",
        "Mercury",
        "Mystics",
    ]

    if season_year >= 2025:
        return "Season Opponent"
    elif season_year == 2024:
        return "WNBA Opponent"
    else:
        return "League Opponent"


class KixStatsService:
    """Service for scraping game shoe data from KixStats.com"""

    def __init__(self):
        self.base_url = "https://kixstats.com"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def scrape_player_games(
        self, player_id: str, player_name: str = ""
    ) -> List[GameShoeData]:
        """
        Scrape game-by-game shoe data for a player

        Args:
            player_id: KixStats player ID (e.g., "caitlin-clark-44")
            player_name: Display name for the player

        Returns:
            List of GameShoeData objects
        """
        url = f"{self.base_url}/playerstats/{player_id}"
        logger.info(f"Scraping KixStats data from: {url}")

        try:
            if not self.session:
                async with aiohttp.ClientSession() as session:
                    return await self._scrape_with_session(session, url, player_name)
            else:
                return await self._scrape_with_session(self.session, url, player_name)

        except Exception as e:
            logger.error(f"Error scraping KixStats data: {e}")
            return []

    async def _scrape_with_session(
        self, session: aiohttp.ClientSession, url: str, player_name: str
    ) -> List[GameShoeData]:
        """Internal method to scrape with provided session"""

        # Add respectful delay
        await asyncio.sleep(2)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch KixStats page: HTTP {response.status}")
                return []

            html = await response.text()
            return await self._parse_games_table(html, player_name)

    async def _parse_games_table(
        self, html: str, player_name: str
    ) -> List[GameShoeData]:
        """Parse the games table from HTML"""

        soup = BeautifulSoup(html, "html.parser")

        # Find the games table
        table = soup.find("table", class_="table ttable")
        if not table:
            logger.error("Could not find games table with class 'table ttable'")
            return []

        tbody = table.find("tbody")
        if not tbody:
            logger.error("Could not find tbody in games table")
            return []

        games = []
        rows = tbody.find_all("tr")

        logger.info(f"Found {len(rows)} game rows to parse")

        for row in rows:
            try:
                game_data = await self._parse_game_row_with_opponent(row, player_name)
                if game_data:
                    games.append(game_data)
            except Exception as e:
                logger.error(f"Error parsing game row: {e}")
                continue

        logger.info(f"Successfully parsed {len(games)} games")
        return games

    def _parse_game_row(self, row, player_name: str) -> Optional[GameShoeData]:
        """Parse a single game row"""

        cells = row.find_all("td")
        if len(cells) < 10:
            logger.debug(f"Row has insufficient cells: {len(cells)}")
            return None

        try:
            # Parse date (first column)
            date_text = cells[0].get_text(strip=True)
            game_date = datetime.strptime(date_text, "%Y-%m-%d").date()

            # Parse shoe name and URL (third column)
            shoe_link = cells[2].find("a")
            if not shoe_link:
                logger.debug("No shoe link found in row")
                return None

            shoe_name = shoe_link.get_text(strip=True)
            shoe_url = shoe_link.get("href", "")
            if shoe_url and not shoe_url.startswith("http"):
                shoe_url = f"{self.base_url}{shoe_url}"

            # Extract shoe images - both product image and game photo
            image_urls = []

            # 1. Get shoe product image from column 1 (kickstats links)
            images_cell = cells[1]
            kickstats_links = images_cell.find_all(
                "a", href=lambda href: href and "kickstats" in href
            )
            for link in kickstats_links:
                img_tag = link.find("img")
                if img_tag:
                    img_src = img_tag.get("src", "")
                    # Only get images from /img/kicks/ path, not jerseys
                    if img_src and "/img/kicks/" in img_src:
                        if img_src.startswith("/"):
                            image_urls.append(f"{self.base_url}{img_src}")
                        else:
                            image_urls.append(img_src)
                        break  # Use the first shoe product image

            # 2. Get game photo from column 3 (4th column) if available
            if len(cells) > 3:
                game_photo_cell = cells[3]  # Column 3 = 4th column (0-indexed)
                game_photo_links = game_photo_cell.find_all(
                    "a", href=lambda href: href and "/img/games/" in str(href)
                )
                for link in game_photo_links:
                    img_tag = link.find("img")
                    if img_tag:
                        img_src = img_tag.get("src", "")
                        if img_src and "/img/games/" in img_src:
                            if img_src.startswith("/"):
                                image_urls.append(f"{self.base_url}{img_src}")
                            else:
                                image_urls.append(img_src)
                            break  # Use the first game photo

            # Format as JSON array string or empty string if no images
            import json

            image_url = json.dumps(image_urls) if image_urls else ""

            # Parse stats (columns 5-10: Min, Pts, Reb, Ast, Stl, Blk)
            def parse_stat(cell) -> int:
                span = cell.find("span")
                if span:
                    text = span.get_text(strip=True)
                    try:
                        return int(text)
                    except ValueError:
                        return 0
                return 0

            minutes = parse_stat(cells[4])
            points = parse_stat(cells[5])
            rebounds = parse_stat(cells[6])
            assists = parse_stat(cells[7])
            steals = parse_stat(cells[8])
            blocks = parse_stat(cells[9])

            return GameShoeData(
                game_date=game_date,
                shoe_name=shoe_name,
                shoe_url=shoe_url,
                minutes=minutes,
                points=points,
                rebounds=rebounds,
                assists=assists,
                steals=steals,
                blocks=blocks,
                player_name=player_name,
                image_url=image_url,
            )

        except Exception as e:
            logger.error(f"Error parsing game row data: {e}")
            return None

    async def _parse_game_row_with_opponent(
        self, row, player_name: str
    ) -> Optional[GameShoeData]:
        """Parse game row and resolve opponent using existing game log infrastructure"""
        try:
            # First parse the basic game data
            game_data = self._parse_game_row(row, player_name)
            if not game_data:
                return None

            # Resolve opponent using existing game log infrastructure
            opponent = await resolve_shoe_opponent(game_data.game_date, player_name)

            # Create new GameShoeData with the resolved opponent
            return GameShoeData(
                game_date=game_data.game_date,
                shoe_name=game_data.shoe_name,
                shoe_url=game_data.shoe_url,
                minutes=game_data.minutes,
                points=game_data.points,
                rebounds=game_data.rebounds,
                assists=game_data.assists,
                steals=game_data.steals,
                blocks=game_data.blocks,
                player_name=game_data.player_name,
                image_url=game_data.image_url,
                opponent=opponent,  # Use resolved opponent instead of default "Unknown"
            )

        except Exception as e:
            logger.error(f"Error parsing game row with opponent: {e}")
            return None

    @staticmethod
    def get_player_id_from_name(player_name: str) -> str:
        """Convert player name to KixStats player ID format"""
        # Convert "caitlin clark" -> "caitlin-clark-44"
        # Note: The number at the end may vary per player
        normalized = player_name.lower().replace(" ", "-")

        # For now, hardcode Caitlin Clark's ID since we know it
        if "caitlin" in normalized and "clark" in normalized:
            return "caitlin-clark-44"

        # For other players, we'd need to research their IDs
        return f"{normalized}-unknown"
