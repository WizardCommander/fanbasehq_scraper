"""
Fast team roster lookup service for WNBA players
Uses ESPN API with static team IDs for optimal performance
"""

import json
import asyncio
import logging
import aiohttp
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from config.settings import CONFIG_DIR

logger = logging.getLogger(__name__)

# Static WNBA team IDs for fast lookup (rarely change)
WNBA_TEAMS = [
    {"name": "Atlanta Dream", "id": "1"},
    {"name": "Chicago Sky", "id": "2"},
    {"name": "Connecticut Sun", "id": "3"},
    {"name": "Dallas Wings", "id": "4"},
    {"name": "Indiana Fever", "id": "11"},
    {"name": "Las Vegas Aces", "id": "21"},
    {"name": "Minnesota Lynx", "id": "16"},
    {"name": "New York Liberty", "id": "18"},
    {"name": "Phoenix Mercury", "id": "19"},
    {"name": "Seattle Storm", "id": "23"},
    {"name": "Washington Mystics", "id": "26"},
    {"name": "Los Angeles Sparks", "id": "14"}
]

ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
CACHE_FILE = CONFIG_DIR / 'player_teams.json'
CACHE_EXPIRY_DAYS = 30


class TeamRosterService:
    """Fast team roster lookup service with caching"""
    
    def __init__(self):
        self.cache_file = CACHE_FILE
        self.teams = WNBA_TEAMS
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
            
    def _load_cache(self) -> Dict:
        """Load cached player-team mappings"""
        if not self.cache_file.exists():
            return {}
            
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            logger.info(f"Loaded {len(cache)} cached player-team mappings")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return {}
            
    def _save_cache(self, cache: Dict) -> None:
        """Save player-team mappings to cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
            logger.info(f"Saved {len(cache)} player-team mappings to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            
    def _is_cache_stale(self, cache: Dict) -> bool:
        """Check if cache is older than expiry period"""
        if not cache:
            return True
            
        cache_date_str = cache.get('_last_updated')
        if not cache_date_str:
            return True
            
        try:
            cache_date = datetime.fromisoformat(cache_date_str)
            expiry_date = cache_date + timedelta(days=CACHE_EXPIRY_DAYS)
            is_stale = datetime.now() > expiry_date
            
            if is_stale:
                logger.info(f"Cache is stale (updated {cache_date_str}, expires after {CACHE_EXPIRY_DAYS} days)")
            else:
                logger.info(f"Cache is fresh (updated {cache_date_str})")
                
            return is_stale
        except Exception as e:
            logger.warning(f"Failed to parse cache date: {e}")
            return True
            
    async def get_player_team(self, player_name: str) -> Optional[Tuple[str, str]]:
        """
        Get team name and ID for a player
        
        Args:
            player_name: Player name (case insensitive)
            
        Returns:
            Tuple of (team_name, team_id) or None if not found
        """
        player_key = player_name.lower().strip()
        
        # Load cache
        cache = self._load_cache()
        
        # Check if we have fresh cached data
        if not self._is_cache_stale(cache) and player_key in cache:
            team_data = cache[player_key]
            logger.info(f"Found {player_name} in cache: {team_data['team_name']}")
            return team_data['team_name'], team_data['team_id']
            
        # Need to refresh cache
        logger.info(f"Cache miss or stale - fetching fresh roster data")
        await self._refresh_cache()
        
        # Try again with fresh cache
        cache = self._load_cache()
        if player_key in cache:
            team_data = cache[player_key]
            logger.info(f"Found {player_name} after cache refresh: {team_data['team_name']}")
            return team_data['team_name'], team_data['team_id']
            
        logger.warning(f"Player {player_name} not found in any WNBA roster")
        return None
        
    async def _refresh_cache(self) -> None:
        """Refresh the entire player-team cache by fetching all rosters"""
        logger.info("Refreshing player-team cache from ESPN API...")
        start_time = datetime.now()
        
        if not self.session:
            raise RuntimeError("Session not initialized - use async context manager")
            
        cache = {'_last_updated': datetime.now().isoformat()}
        
        # Fetch all team rosters in parallel for speed
        tasks = []
        for team in self.teams:
            task = self._fetch_team_roster(team['name'], team['id'])
            tasks.append(task)
            
        # Execute all requests in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        total_players = 0
        successful_teams = 0
        
        for i, result in enumerate(results):
            team = self.teams[i]
            
            if isinstance(result, Exception):
                logger.error(f"Failed to fetch roster for {team['name']}: {result}")
                continue
                
            if result:  # List of players
                for player_name in result:
                    player_key = player_name.lower().strip()
                    cache[player_key] = {
                        'team_name': team['name'],
                        'team_id': team['id'],
                        'display_name': player_name
                    }
                    total_players += 1
                    
                successful_teams += 1
                logger.info(f"Cached {len(result)} players from {team['name']}")
                
        # Save updated cache
        self._save_cache(cache)
        
        elapsed = datetime.now() - start_time
        logger.info(f"Cache refresh complete: {total_players} players from {successful_teams}/{len(self.teams)} teams in {elapsed.total_seconds():.1f}s")
        
    async def _fetch_team_roster(self, team_name: str, team_id: str) -> Optional[List[str]]:
        """
        Fetch roster for a single team
        
        Args:
            team_name: Team name for logging
            team_id: ESPN team ID
            
        Returns:
            List of player names or None if failed
        """
        try:
            url = f"{ESPN_BASE_URL}/teams/{team_id}/roster"
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {team_name} roster: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                
                # Extract player names from roster data
                players = []
                athletes = data.get('team', {}).get('roster', {}).get('entries', [])
                
                for entry in athletes:
                    athlete = entry.get('athlete', {})
                    display_name = athlete.get('displayName', '')
                    if display_name:
                        players.append(display_name)
                        
                logger.debug(f"Fetched {len(players)} players from {team_name}")
                return players
                
        except Exception as e:
            logger.error(f"Exception fetching {team_name} roster: {e}")
            return None
            
    def get_cached_player_team(self, player_name: str) -> Optional[Tuple[str, str]]:
        """
        Get team from cache only (synchronous)
        
        Args:
            player_name: Player name (case insensitive)
            
        Returns:
            Tuple of (team_name, team_id) or None if not found
        """
        player_key = player_name.lower().strip()
        cache = self._load_cache()
        
        if player_key in cache:
            team_data = cache[player_key]
            return team_data['team_name'], team_data['team_id']
            
        return None
        
    def list_cached_players(self) -> List[str]:
        """List all players in cache"""
        cache = self._load_cache()
        players = [data['display_name'] for key, data in cache.items() if key != '_last_updated']
        return sorted(players)


async def get_player_team_fast(player_name: str) -> Optional[Tuple[str, str]]:
    """
    Convenience function to get player team with optimal caching
    
    Args:
        player_name: Player name to lookup
        
    Returns:
        Tuple of (team_name, team_id) or None if not found
    """
    async with TeamRosterService() as service:
        return await service.get_player_team(player_name)


def get_player_team_cached(player_name: str) -> Optional[Tuple[str, str]]:
    """
    Get player team from cache only (no API calls)
    
    Args:
        player_name: Player name to lookup
        
    Returns:
        Tuple of (team_name, team_id) or None if not found
    """
    service = TeamRosterService()
    return service.get_cached_player_team(player_name)


async def test_team_roster_service():
    """Test the team roster service"""
    async with TeamRosterService() as service:
        # Test with Caitlin Clark
        result = await service.get_player_team("Caitlin Clark")
        if result:
            team_name, team_id = result
            print(f"Caitlin Clark plays for: {team_name} (ID: {team_id})")
        else:
            print("Caitlin Clark not found")
            
        # List some cached players
        players = service.list_cached_players()
        print(f"Found {len(players)} players in cache")
        if players:
            print(f"Sample players: {players[:5]}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run test
    asyncio.run(test_team_roster_service())