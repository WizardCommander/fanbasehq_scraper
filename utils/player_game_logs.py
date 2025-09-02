"""
Individual Player Game Logs Service
Tracks when specific players actually played in games using sportsdataverse
"""

import json
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from pathlib import Path

try:
    from sportsdataverse.wnba import load_wnba_player_boxscore
except ImportError:
    raise ImportError(
        "sportsdataverse is required. Install with: pip install sportsdataverse"
    )

from config.settings import CONFIG_DIR

logger = logging.getLogger(__name__)


class GameStats(NamedTuple):
    """Individual game statistics"""

    date: date
    points: int
    assists: int
    rebounds: int
    field_goals_made: int
    field_goals_attempted: int
    three_point_made: int
    three_point_attempted: int
    free_throws_made: int
    free_throws_attempted: int
    minutes: Optional[int]
    opponent: str
    # Running totals
    season_points_total: int
    season_assists_total: int
    season_rebounds_total: int


class PlayerGameLogService:
    """Service to track individual player game participation"""

    def __init__(self, force_refresh: bool = False):
        self.cache_file = CONFIG_DIR / "player_game_logs.json"
        self.cache = {}

        if force_refresh:
            self.cache = {"last_updated": 0, "players": {}}
            logger.info("Player game log cache cleared for fresh scrape")
        else:
            self.load_cache()

    def load_cache(self):
        """Load cached player game logs"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(
                    f"Loaded player game log cache with {len(self.cache)} entries"
                )
            else:
                self.cache = {"last_updated": 0, "players": {}}
                logger.info("No player game log cache found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load player game log cache: {e}")
            self.cache = {"last_updated": 0, "players": {}}

    def save_cache(self):
        """Save player game logs cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, default=str)
            logger.info(f"Saved player game log cache to {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to save player game log cache: {e}")

    def _is_cache_stale(self, hours: int = 6) -> bool:
        """Check if cache needs updating"""
        if "last_updated" not in self.cache:
            return True

        last_updated = self.cache["last_updated"]
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated).timestamp()

        return (datetime.now().timestamp() - last_updated) > (hours * 3600)

    async def get_player_game_stats(
        self, player_name: str, season: int = 2024
    ) -> List[GameStats]:
        """
        Get full game statistics with running totals for a player

        Args:
            player_name: Player name to look up
            season: WNBA season year

        Returns:
            List of GameStats with running totals
        """
        cache_key = f"{player_name.lower()}_{season}"

        # Check cache first
        if not self._is_cache_stale() and cache_key in self.cache.get("players", {}):
            cached_games = self.cache["players"][cache_key].get("games", [])
            if cached_games:
                logger.info(
                    f"Found {len(cached_games)} cached games with stats for {player_name}"
                )
                return self._parse_cached_game_stats(cached_games)

        # Fetch and cache new data
        game_stats = await self._fetch_and_cache_game_stats(player_name, season)
        return game_stats

    async def get_player_game_dates(
        self, player_name: str, season: int = 2024
    ) -> List[date]:
        """
        Get list of dates when a specific player actually played (backward compatibility)

        Args:
            player_name: Player name to look up
            season: WNBA season year

        Returns:
            List of dates when the player participated in games
        """
        # Use new method and extract dates
        game_stats = await self.get_player_game_stats(player_name, season)
        return [game.date for game in game_stats]

    async def _fetch_and_cache_game_stats(
        self, player_name: str, season: int
    ) -> List[GameStats]:
        """
        Fetch game stats from SportDataverse and cache with running totals
        """
        cache_key = f"{player_name.lower()}_{season}"

        try:
            # Load player boxscore data for the season
            logger.info(
                f"Fetching game log data for {player_name} in {season} season..."
            )

            # Get player boxscore data
            df = load_wnba_player_boxscore(seasons=[season])

            if df is None or len(df) == 0:
                logger.warning(f"No boxscore data found for {season} season")
                return []

            logger.info(
                f"DEBUG: Loaded {len(df)} total boxscore records for {season} season"
            )
            logger.info(f"DEBUG: Available columns: {list(df.columns)}")

            # Filter for specific player (sportsdataverse returns Polars DataFrames)
            player_games = df.filter(
                df["athlete_display_name"].str.contains(f"(?i){player_name}")
            )

            if len(player_games) == 0:
                logger.warning(f"No games found for player: {player_name}")
                return []

            logger.info(f"DEBUG: Found {len(player_games)} games for {player_name}")

            # Show sample data for debugging
            if len(player_games) > 0:
                sample_games = (
                    player_games.head(3).to_dicts()
                    if hasattr(player_games, "head")
                    else list(player_games.to_dicts())[:3]
                )
                for i, game in enumerate(sample_games):
                    logger.info(
                        f"DEBUG: Game {i+1} - Date: {game.get('game_date', 'N/A')}, Minutes: {game.get('minutes', 'N/A')}, Points: {game.get('points', 'N/A')}"
                    )
                    logger.info(f"DEBUG: Game {i+1} - All keys: {list(game.keys())}")
                    if i >= 2:  # Only show first 3 games
                        break

            # Process games and calculate running totals
            games_list = []
            for game in player_games.to_dicts():
                try:
                    # Check if player actually played
                    minutes = (
                        game.get("minutes", 0)
                        or game.get("mins", 0)
                        or game.get("min", 0)
                    )
                    points = game.get("points", 0) or game.get("pts", 0)

                    # Skip if player didn't play
                    if (minutes == 0 or minutes is None) and (
                        points == 0 or points is None
                    ):
                        logger.debug(
                            f"Skipping game on {game.get('game_date', 'unknown')} - player did not play (0 min, 0 pts)"
                        )
                        continue

                    # Parse game date
                    game_date_str = game.get("game_date", "")
                    if game_date_str:
                        if "T" in str(game_date_str):
                            game_date = datetime.fromisoformat(
                                str(game_date_str).replace("Z", "+00:00")
                            ).date()
                        else:
                            game_date = datetime.strptime(
                                str(game_date_str), "%Y-%m-%d"
                            ).date()

                        # Extract all stats
                        game_data = {
                            "date": game_date,
                            "points": int(points or 0),
                            "assists": int(game.get("assists", 0) or 0),
                            "rebounds": int(game.get("rebounds", 0) or 0),
                            "field_goals_made": int(
                                game.get("field_goals_made", 0) or 0
                            ),
                            "field_goals_attempted": int(
                                game.get("field_goals_attempted", 0) or 0
                            ),
                            "three_point_made": int(
                                game.get("three_point_field_goals_made", 0) or 0
                            ),
                            "three_point_attempted": int(
                                game.get("three_point_field_goals_attempted", 0) or 0
                            ),
                            "free_throws_made": int(
                                game.get("free_throws_made", 0) or 0
                            ),
                            "free_throws_attempted": int(
                                game.get("free_throws_attempted", 0) or 0
                            ),
                            "minutes": int(minutes) if minutes else None,
                            "opponent": game.get("opponent_team_name", "")
                            or game.get("opponent_team_abbreviation", ""),
                        }
                        games_list.append(game_data)

                except Exception as e:
                    logger.debug(f"Error parsing game {game_date_str}: {e}")
                    continue

            # Sort by date and calculate running totals
            games_list.sort(key=lambda x: x["date"])

            game_stats = []
            running_points = 0
            running_assists = 0
            running_rebounds = 0

            for game_data in games_list:
                running_points += game_data["points"]
                running_assists += game_data["assists"]
                running_rebounds += game_data["rebounds"]

                game_stat = GameStats(
                    date=game_data["date"],
                    points=game_data["points"],
                    assists=game_data["assists"],
                    rebounds=game_data["rebounds"],
                    field_goals_made=game_data["field_goals_made"],
                    field_goals_attempted=game_data["field_goals_attempted"],
                    three_point_made=game_data["three_point_made"],
                    three_point_attempted=game_data["three_point_attempted"],
                    free_throws_made=game_data["free_throws_made"],
                    free_throws_attempted=game_data["free_throws_attempted"],
                    minutes=game_data["minutes"],
                    opponent=game_data["opponent"],
                    season_points_total=running_points,
                    season_assists_total=running_assists,
                    season_rebounds_total=running_rebounds,
                )
                game_stats.append(game_stat)

            # Cache the enhanced results
            if "players" not in self.cache:
                self.cache["players"] = {}

            # Convert GameStats to cacheable format
            cached_games = []
            for stat in game_stats:
                cached_games.append(
                    {
                        "date": stat.date.isoformat(),
                        "points": stat.points,
                        "assists": stat.assists,
                        "rebounds": stat.rebounds,
                        "field_goals_made": stat.field_goals_made,
                        "field_goals_attempted": stat.field_goals_attempted,
                        "three_point_made": stat.three_point_made,
                        "three_point_attempted": stat.three_point_attempted,
                        "free_throws_made": stat.free_throws_made,
                        "free_throws_attempted": stat.free_throws_attempted,
                        "minutes": stat.minutes,
                        "opponent": stat.opponent,
                        "season_points_total": stat.season_points_total,
                        "season_assists_total": stat.season_assists_total,
                        "season_rebounds_total": stat.season_rebounds_total,
                    }
                )

            self.cache["players"][cache_key] = {
                "player_name": player_name,
                "season": season,
                "games": cached_games,
                "game_dates": [
                    stat.date.isoformat() for stat in game_stats
                ],  # Backward compatibility
                "total_games": len(game_stats),
                "fetched_at": datetime.now().isoformat(),
            }

            self.cache["last_updated"] = datetime.now().isoformat()
            self.save_cache()

            logger.info(
                f"Found {len(game_stats)} games with full stats for {player_name} in {season}"
            )
            return game_stats

        except Exception as e:
            logger.error(f"Error fetching player game stats for {player_name}: {e}")
            return []

    def _parse_cached_game_stats(self, cached_games: List[Dict]) -> List[GameStats]:
        """Parse cached game data back to GameStats objects"""
        game_stats = []
        for game_data in cached_games:
            try:
                game_stat = GameStats(
                    date=date.fromisoformat(game_data["date"]),
                    points=game_data.get("points", 0),
                    assists=game_data.get("assists", 0),
                    rebounds=game_data.get("rebounds", 0),
                    field_goals_made=game_data.get("field_goals_made", 0),
                    field_goals_attempted=game_data.get("field_goals_attempted", 0),
                    three_point_made=game_data.get("three_point_made", 0),
                    three_point_attempted=game_data.get("three_point_attempted", 0),
                    free_throws_made=game_data.get("free_throws_made", 0),
                    free_throws_attempted=game_data.get("free_throws_attempted", 0),
                    minutes=game_data.get("minutes"),
                    opponent=game_data.get("opponent", ""),
                    season_points_total=game_data.get("season_points_total", 0),
                    season_assists_total=game_data.get("season_assists_total", 0),
                    season_rebounds_total=game_data.get("season_rebounds_total", 0),
                )
                game_stats.append(game_stat)
            except Exception as e:
                logger.warning(f"Error parsing cached game data: {e}")
                continue
        return game_stats

    async def get_player_stats_in_date_range(
        self, player_name: str, start_date: date, end_date: date
    ) -> List[GameStats]:
        """
        Get player stats within a specific date range

        Args:
            player_name: Player name to look up
            start_date: Start date for range
            end_date: End date for range

        Returns:
            List of GameStats within the date range
        """
        # Determine season(s) to check
        seasons = set()
        current_date = start_date
        while current_date <= end_date:
            seasons.add(current_date.year)
            current_date = current_date.replace(year=current_date.year + 1)

        all_stats = []
        for season in seasons:
            season_stats = await self.get_player_game_stats(player_name, season)
            # Filter for date range
            filtered_stats = [
                stat for stat in season_stats if start_date <= stat.date <= end_date
            ]
            all_stats.extend(filtered_stats)

        # Sort by date
        all_stats.sort(key=lambda x: x.date)

        logger.info(
            f"Found {len(all_stats)} games for {player_name} between {start_date} and {end_date}"
        )
        return all_stats

    async def find_recent_player_game(
        self, player_name: str, before_date: date, days_back: int = 60
    ) -> Optional[date]:
        """
        Find the most recent game where a player actually played

        Args:
            player_name: Player name to look up
            before_date: Look for games before this date
            days_back: How many days back to search

        Returns:
            Date of most recent game the player participated in
        """
        # Use date range method for consistency
        earliest_date = before_date - timedelta(days=days_back)
        stats_in_range = await self.get_player_stats_in_date_range(
            player_name, earliest_date, before_date
        )

        if not stats_in_range:
            logger.debug(
                f"No games found for {player_name} between {earliest_date} and {before_date}"
            )
            return None

        # Return most recent game date
        most_recent = max(stat.date for stat in stats_in_range)
        logger.info(
            f"Most recent game for {player_name} before {before_date}: {most_recent}"
        )
        return most_recent

    def get_cached_player_names(self) -> List[str]:
        """Get list of players in cache"""
        if "players" not in self.cache:
            return []

        players = set()
        for key, data in self.cache["players"].items():
            players.add(data.get("player_name", ""))

        return sorted(list(players))


async def get_player_recent_game(
    player_name: str, before_date: date, force_refresh: bool = False
) -> Optional[date]:
    """
    Convenience function to get most recent game for a player

    Args:
        player_name: Player name to look up
        before_date: Look for games before this date
        force_refresh: Whether to force cache refresh

    Returns:
        Date of most recent game or None if not found
    """
    service = PlayerGameLogService(force_refresh=force_refresh)
    return await service.find_recent_player_game(player_name, before_date)


# Test functions removed for production - see development branch for testing utilities
