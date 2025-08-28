"""
Game schedule validation service for WNBA milestone verification
Uses ESPN API to validate submission timing against actual games
"""

import json
import asyncio
import logging
import aiohttp
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from config.settings import CONFIG_DIR

logger = logging.getLogger(__name__)

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
SCHEDULE_CACHE_FILE = CONFIG_DIR / 'game_schedule_cache.json'
CACHE_EXPIRY_HOURS = 24


@dataclass
class GameInfo:
    """Information about a single game"""
    game_id: str
    date: date
    home_team: str
    away_team: str
    home_team_id: str
    away_team_id: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "unknown"
    venue: str = ""


class GameScheduleService:
    """Game schedule validation service with caching"""
    
    def __init__(self):
        self.cache_file = SCHEDULE_CACHE_FILE
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
        """Load cached game schedule data"""
        if not self.cache_file.exists():
            return {}
            
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            logger.info(f"Loaded game schedule cache with {len([k for k in cache.keys() if k != '_last_updated'])} team schedules")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load schedule cache: {e}")
            return {}
            
    def _save_cache(self, cache: Dict) -> None:
        """Save game schedule data to cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2, default=str)  # default=str handles date serialization
            logger.info(f"Saved game schedule cache")
        except Exception as e:
            logger.error(f"Failed to save schedule cache: {e}")
            
    def _is_cache_stale(self, cache: Dict) -> bool:
        """Check if cache is older than expiry period"""
        if not cache:
            return True
            
        cache_time_str = cache.get('_last_updated')
        if not cache_time_str:
            return True
            
        try:
            cache_time = datetime.fromisoformat(cache_time_str)
            expiry_time = cache_time + timedelta(hours=CACHE_EXPIRY_HOURS)
            is_stale = datetime.now() > expiry_time
            
            if is_stale:
                logger.info(f"Schedule cache is stale (updated {cache_time_str})")
            else:
                logger.info(f"Schedule cache is fresh (updated {cache_time_str})")
                
            return is_stale
        except Exception as e:
            logger.warning(f"Failed to parse cache timestamp: {e}")
            return True
            
    async def get_team_games(
        self, 
        team_name: str, 
        team_id: str, 
        start_date: date, 
        end_date: date
    ) -> List[GameInfo]:
        """
        Get all games for a team in date range
        
        Args:
            team_name: Team name for logging
            team_id: ESPN team ID
            start_date: Start date for games
            end_date: End date for games
            
        Returns:
            List of GameInfo objects for team's games
        """
        cache_key = f"{team_id}_{start_date}_{end_date}"
        
        # Load cache
        cache = self._load_cache()
        
        # Check if we have fresh cached data
        if not self._is_cache_stale(cache) and cache_key in cache:
            games_data = cache[cache_key]
            games = [self._dict_to_game(game_dict) for game_dict in games_data]
            logger.info(f"Found {len(games)} cached games for {team_name} ({start_date} to {end_date})")
            return games
            
        # Need to fetch fresh data
        logger.info(f"Fetching fresh game schedule for {team_name}...")
        games = await self._fetch_team_games(team_name, team_id, start_date, end_date)
        
        # Update cache
        cache = self._load_cache()  # Reload in case other processes updated it
        cache['_last_updated'] = datetime.now().isoformat()
        cache[cache_key] = [self._game_to_dict(game) for game in games]
        self._save_cache(cache)
        
        return games
        
    async def _fetch_team_games(
        self, 
        team_name: str, 
        team_id: str, 
        start_date: date, 
        end_date: date
    ) -> List[GameInfo]:
        """
        Fetch games for a team from ESPN API
        
        Strategy: Fetch scoreboard data for date range and filter for team
        """
        if not self.session:
            raise RuntimeError("Session not initialized - use async context manager")
            
        games = []
        current_date = start_date
        
        # ESPN scoreboard API requires date-by-date requests
        while current_date <= end_date:
            try:
                date_str = current_date.strftime('%Y%m%d')
                url = f"{ESPN_SCOREBOARD_URL}?dates={date_str}"
                
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch scoreboard for {date_str}: HTTP {response.status}")
                        current_date += timedelta(days=1)
                        continue
                        
                    data = await response.json()
                    
                    # Process games for this date
                    events = data.get('events', [])
                    for event in events:
                        competitions = event.get('competitions', [])
                        for comp in competitions:
                            competitors = comp.get('competitors', [])
                            
                            if len(competitors) != 2:
                                continue
                                
                            home_team = competitors[0] if competitors[0].get('homeAway') == 'home' else competitors[1]
                            away_team = competitors[1] if competitors[0].get('homeAway') == 'home' else competitors[0]
                            
                            home_team_id = home_team.get('team', {}).get('id', '')
                            away_team_id = away_team.get('team', {}).get('id', '')
                            
                            # Check if this team is involved in the game
                            if team_id in [home_team_id, away_team_id]:
                                game = self._parse_game_data(event, comp, home_team, away_team, current_date)
                                if game:
                                    games.append(game)
                                    
                # Rate limiting
                await asyncio.sleep(0.5)  # Be nice to ESPN API
                
            except Exception as e:
                logger.error(f"Error fetching games for {date_str}: {e}")
                
            current_date += timedelta(days=1)
            
        logger.info(f"Fetched {len(games)} games for {team_name} from {start_date} to {end_date}")
        return games
        
    def _parse_game_data(self, event: Dict, comp: Dict, home_team: Dict, away_team: Dict, game_date: date) -> Optional[GameInfo]:
        """Parse game data from ESPN API response"""
        try:
            game_id = event.get('id', '')
            
            home_team_data = home_team.get('team', {})
            away_team_data = away_team.get('team', {})
            
            home_name = home_team_data.get('displayName', '')
            away_name = away_team_data.get('displayName', '')
            home_id = home_team_data.get('id', '')
            away_id = away_team_data.get('id', '')
            
            # Get scores if available
            home_score = None
            away_score = None
            if home_team.get('score'):
                home_score = int(home_team['score'])
            if away_team.get('score'):
                away_score = int(away_team['score'])
                
            # Get game status
            status = event.get('status', {}).get('type', {}).get('name', 'unknown')
            
            # Get venue
            venue = comp.get('venue', {}).get('fullName', '')
            
            return GameInfo(
                game_id=game_id,
                date=game_date,
                home_team=home_name,
                away_team=away_name,
                home_team_id=home_id,
                away_team_id=away_id,
                home_score=home_score,
                away_score=away_score,
                status=status,
                venue=venue
            )
            
        except Exception as e:
            logger.error(f"Error parsing game data: {e}")
            return None
            
    def _game_to_dict(self, game: GameInfo) -> Dict:
        """Convert GameInfo to dictionary for JSON serialization"""
        return {
            'game_id': game.game_id,
            'date': game.date.isoformat(),
            'home_team': game.home_team,
            'away_team': game.away_team,
            'home_team_id': game.home_team_id,
            'away_team_id': game.away_team_id,
            'home_score': game.home_score,
            'away_score': game.away_score,
            'status': game.status,
            'venue': game.venue
        }
        
    def _dict_to_game(self, game_dict: Dict) -> GameInfo:
        """Convert dictionary to GameInfo object"""
        return GameInfo(
            game_id=game_dict['game_id'],
            date=date.fromisoformat(game_dict['date']),
            home_team=game_dict['home_team'],
            away_team=game_dict['away_team'],
            home_team_id=game_dict['home_team_id'],
            away_team_id=game_dict['away_team_id'],
            home_score=game_dict.get('home_score'),
            away_score=game_dict.get('away_score'),
            status=game_dict.get('status', 'unknown'),
            venue=game_dict.get('venue', '')
        )
        
    def validate_milestone_date(
        self, 
        milestone_date: date, 
        team_games: List[GameInfo], 
        tolerance_days: int = 2
    ) -> Tuple[bool, Optional[GameInfo], str]:
        """
        Validate if milestone date aligns with team's game schedule
        
        Args:
            milestone_date: Date of the milestone
            team_games: List of team's games
            tolerance_days: Days before/after games to consider valid
            
        Returns:
            Tuple of (is_valid, closest_game, reason)
        """
        if not team_games:
            return False, None, "No games found for team"
            
        # Find games within tolerance
        valid_games = []
        for game in team_games:
            days_diff = abs((milestone_date - game.date).days)
            if days_diff <= tolerance_days:
                valid_games.append((game, days_diff))
                
        if not valid_games:
            # Find closest game for context
            closest_game = min(team_games, key=lambda g: abs((milestone_date - g.date).days))
            days_diff = abs((milestone_date - closest_game.date).days)
            return False, closest_game, f"No games within {tolerance_days} days (closest: {days_diff} days)"
            
        # Return the closest valid game
        closest_valid = min(valid_games, key=lambda x: x[1])
        game, days_diff = closest_valid
        
        if days_diff == 0:
            return True, game, "Game day milestone"
        else:
            return True, game, f"Within {days_diff} days of game"


async def validate_player_milestones(
    player_name: str,
    team_name: str, 
    team_id: str,
    milestone_dates: List[date],
    start_date: date,
    end_date: date
) -> Dict:
    """
    Convenience function to validate multiple milestone dates
    
    Returns:
        Dictionary with validation results
    """
    async with GameScheduleService() as service:
        # Get team's games
        games = await service.get_team_games(team_name, team_id, start_date, end_date)
        
        # Validate each milestone date
        results = {
            'player': player_name,
            'team': team_name,
            'total_games': len(games),
            'milestones': []
        }
        
        for milestone_date in milestone_dates:
            is_valid, closest_game, reason = service.validate_milestone_date(milestone_date, games)
            results['milestones'].append({
                'date': milestone_date.isoformat(),
                'valid': is_valid,
                'reason': reason,
                'closest_game': closest_game.game_id if closest_game else None,
                'opponent': (closest_game.away_team if closest_game.home_team == team_name else closest_game.home_team) if closest_game else None
            })
            
        return results


async def test_game_schedule_service():
    """Test the game schedule service"""
    # Test with Indiana Fever (Caitlin Clark's team)
    team_name = "Indiana Fever"
    team_id = "11"
    start_date = date(2024, 8, 1)
    end_date = date(2024, 8, 27)
    
    async with GameScheduleService() as service:
        games = await service.get_team_games(team_name, team_id, start_date, end_date)
        
        print(f"Found {len(games)} games for {team_name}:")
        for game in games[:5]:  # Show first 5 games
            opponent = game.away_team if game.home_team == team_name else game.home_team
            print(f"  {game.date}: vs {opponent} ({game.status})")
            
        # Test validation
        if games:
            test_date = games[0].date
            is_valid, closest_game, reason = service.validate_milestone_date(test_date, games)
            print(f"\nValidation test for {test_date}: {is_valid} - {reason}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run test
    asyncio.run(test_game_schedule_service())