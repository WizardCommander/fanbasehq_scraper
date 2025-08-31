"""
Individual Player Game Logs Service
Tracks when specific players actually played in games using sportsdataverse
"""

import json
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    from sportsdataverse.wnba import load_wnba_player_boxscore
except ImportError:
    raise ImportError("sportsdataverse is required. Install with: pip install sportsdataverse")

from config.settings import CONFIG_DIR

logger = logging.getLogger(__name__)


class PlayerGameLogService:
    """Service to track individual player game participation"""
    
    def __init__(self, force_refresh: bool = False):
        self.cache_file = CONFIG_DIR / "player_game_logs.json"
        self.cache = {}
        
        if force_refresh:
            self.cache = {'last_updated': 0, 'players': {}}
            logger.info("Player game log cache cleared for fresh scrape")
        else:
            self.load_cache()
        
    def load_cache(self):
        """Load cached player game logs"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded player game log cache with {len(self.cache)} entries")
            else:
                self.cache = {'last_updated': 0, 'players': {}}
                logger.info("No player game log cache found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load player game log cache: {e}")
            self.cache = {'last_updated': 0, 'players': {}}
            
    def save_cache(self):
        """Save player game logs cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, default=str)
            logger.info(f"Saved player game log cache to {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to save player game log cache: {e}")
            
    def _is_cache_stale(self, hours: int = 6) -> bool:
        """Check if cache needs updating"""
        if 'last_updated' not in self.cache:
            return True
            
        last_updated = self.cache['last_updated']
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated).timestamp()
            
        return (datetime.now().timestamp() - last_updated) > (hours * 3600)
        
    async def get_player_game_dates(self, player_name: str, season: int = 2024) -> List[date]:
        """
        Get list of dates when a specific player actually played
        
        Args:
            player_name: Player name to look up
            season: WNBA season year
            
        Returns:
            List of dates when the player participated in games
        """
        cache_key = f"{player_name.lower()}_{season}"
        
        # Check cache first
        if not self._is_cache_stale() and cache_key in self.cache.get('players', {}):
            cached_dates = self.cache['players'][cache_key]['game_dates']
            logger.info(f"Found {len(cached_dates)} cached game dates for {player_name}")
            return [date.fromisoformat(d) for d in cached_dates]
            
        try:
            # Load player boxscore data for the season
            logger.info(f"Fetching game log data for {player_name} in {season} season...")
            
            # Get player boxscore data
            df = load_wnba_player_boxscore(seasons=[season])
            
            if df is None or len(df) == 0:
                logger.warning(f"No boxscore data found for {season} season")
                return []
            
            logger.info(f"DEBUG: Loaded {len(df)} total boxscore records for {season} season")
            logger.info(f"DEBUG: Available columns: {list(df.columns)}")
            
            # Filter for specific player (sportsdataverse returns Polars DataFrames)
            player_games = df.filter(df['athlete_display_name'].str.contains(f"(?i){player_name}"))
            
            if len(player_games) == 0:
                logger.warning(f"No games found for player: {player_name}")
                return []
            
            logger.info(f"DEBUG: Found {len(player_games)} games for {player_name}")
            
            # Show sample data for debugging
            if len(player_games) > 0:
                sample_games = player_games.head(3).to_dicts() if hasattr(player_games, 'head') else list(player_games.to_dicts())[:3]
                for i, game in enumerate(sample_games):
                    logger.info(f"DEBUG: Game {i+1} - Date: {game.get('game_date', 'N/A')}, Minutes: {game.get('minutes', 'N/A')}, Points: {game.get('points', 'N/A')}")
                    logger.info(f"DEBUG: Game {i+1} - All keys: {list(game.keys())}")
                    if i >= 2:  # Only show first 3 games
                        break
                
            # Extract game dates (Polars DataFrame) - only games where player actually played
            game_dates = []
            for game in player_games.to_dicts():
                try:
                    # Check if player actually played (had minutes or any stats)
                    minutes = game.get('minutes', 0) or game.get('mins', 0) or game.get('min', 0)
                    points = game.get('points', 0) or game.get('pts', 0)
                    
                    # Skip if player didn't play (0 minutes and 0 points typically means DNP)
                    if (minutes == 0 or minutes is None) and (points == 0 or points is None):
                        logger.debug(f"Skipping game on {game.get('game_date', 'unknown')} - player did not play (0 min, 0 pts)")
                        continue
                    
                    # Parse game date (format might vary)
                    game_date_str = game.get('game_date', '')
                    if game_date_str:
                        # Handle different date formats
                        if 'T' in str(game_date_str):
                            game_date = datetime.fromisoformat(str(game_date_str).replace('Z', '+00:00')).date()
                        else:
                            game_date = datetime.strptime(str(game_date_str), '%Y-%m-%d').date()
                        game_dates.append(game_date)
                        logger.debug(f"Valid game on {game_date}: {minutes} min, {points} pts")
                except Exception as e:
                    logger.debug(f"Error parsing game date {game_date_str}: {e}")
                    continue
                    
            # Remove duplicates and sort
            game_dates = sorted(list(set(game_dates)))
            
            # Cache the results
            if 'players' not in self.cache:
                self.cache['players'] = {}
                
            self.cache['players'][cache_key] = {
                'player_name': player_name,
                'season': season,
                'game_dates': [d.isoformat() for d in game_dates],
                'total_games': len(game_dates),
                'fetched_at': datetime.now().isoformat()
            }
            
            self.cache['last_updated'] = datetime.now().isoformat()
            self.save_cache()
            
            logger.info(f"Found {len(game_dates)} games for {player_name} in {season}")
            return game_dates
            
        except Exception as e:
            logger.error(f"Error fetching player game dates for {player_name}: {e}")
            return []
            
    async def find_recent_player_game(self, player_name: str, before_date: date, days_back: int = 60) -> Optional[date]:
        """
        Find the most recent game where a player actually played
        
        Args:
            player_name: Player name to look up
            before_date: Look for games before this date
            days_back: How many days back to search
            
        Returns:
            Date of most recent game the player participated in
        """
        # Determine which season(s) to check
        seasons_to_check = [before_date.year]
        if before_date.year > 2024:
            seasons_to_check.append(2024)  # Also check previous season
            
        all_game_dates = []
        
        for season in seasons_to_check:
            game_dates = await self.get_player_game_dates(player_name, season)
            all_game_dates.extend(game_dates)
            
        if not all_game_dates:
            logger.warning(f"No game dates found for {player_name}")
            return None
            
        # Filter for games before the target date and within the search window
        earliest_date = before_date - timedelta(days=days_back)
        valid_games = [
            game_date for game_date in all_game_dates
            if earliest_date <= game_date <= before_date
        ]
        
        if not valid_games:
            logger.debug(f"No games found for {player_name} between {earliest_date} and {before_date}")
            return None
            
        # Return most recent game
        most_recent = max(valid_games)
        logger.info(f"Most recent game for {player_name} before {before_date}: {most_recent}")
        return most_recent
        
    def get_cached_player_names(self) -> List[str]:
        """Get list of players in cache"""
        if 'players' not in self.cache:
            return []
            
        players = set()
        for key, data in self.cache['players'].items():
            players.add(data.get('player_name', ''))
            
        return sorted(list(players))


async def get_player_recent_game(player_name: str, before_date: date, force_refresh: bool = False) -> Optional[date]:
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