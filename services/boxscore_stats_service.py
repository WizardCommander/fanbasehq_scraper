"""
Boxscore Statistics Service
Provides formatted game statistics for AI milestone date inference
"""

import logging
from datetime import date
from typing import List, Dict, Optional
from dataclasses import dataclass

from utils.player_game_logs import PlayerGameLogService, GameStats

logger = logging.getLogger(__name__)


@dataclass
class BoxscoreContext:
    """Formatted boxscore context for AI analysis"""

    player_name: str
    start_date: date
    end_date: date
    games: List[Dict[str, any]]
    total_games: int


class BoxscoreStatsService:
    """Service for providing formatted boxscore data for AI milestone analysis"""

    def __init__(self, game_log_service: PlayerGameLogService = None):
        self.game_log_service = game_log_service or PlayerGameLogService()

    async def get_boxscore_context_for_ai(
        self, player_name: str, start_date: date, end_date: date
    ) -> BoxscoreContext:
        """
        Get formatted boxscore context for AI milestone date inference

        Args:
            player_name: Player name to analyze
            start_date: Start of analysis period
            end_date: End of analysis period

        Returns:
            BoxscoreContext with formatted game data
        """
        logger.info(
            f"Fetching boxscore context for {player_name} from {start_date} to {end_date}"
        )

        # Get player stats in date range
        game_stats = await self.game_log_service.get_player_stats_in_date_range(
            player_name=player_name, start_date=start_date, end_date=end_date
        )

        if not game_stats:
            logger.warning(f"No games found for {player_name} in specified period")
            return BoxscoreContext(
                player_name=player_name,
                start_date=start_date,
                end_date=end_date,
                games=[],
                total_games=0,
            )

        # Format for AI consumption
        formatted_games = []
        for stat in game_stats:
            formatted_game = {
                "date": stat.date.strftime("%B %d, %Y"),  # e.g., "June 14, 2024"
                "opponent": f"vs {stat.opponent}" if stat.opponent else "vs Unknown",
                "points": stat.points,
                "assists": stat.assists,
                "rebounds": stat.rebounds,
                "minutes": stat.minutes,
                "field_goal_pct": (
                    f"{stat.field_goals_made}/{stat.field_goals_attempted}"
                    if stat.field_goals_attempted > 0
                    else "0/0"
                ),
                "three_point_pct": (
                    f"{stat.three_point_made}/{stat.three_point_attempted}"
                    if stat.three_point_attempted > 0
                    else "0/0"
                ),
                "free_throw_pct": (
                    f"{stat.free_throws_made}/{stat.free_throws_attempted}"
                    if stat.free_throws_attempted > 0
                    else "0/0"
                ),
                # Running totals (key for milestone analysis)
                "season_points_total": stat.season_points_total,
                "season_assists_total": stat.season_assists_total,
                "season_rebounds_total": stat.season_rebounds_total,
            }
            formatted_games.append(formatted_game)

        logger.info(f"Formatted {len(formatted_games)} games for AI analysis")

        return BoxscoreContext(
            player_name=player_name,
            start_date=start_date,
            end_date=end_date,
            games=formatted_games,
            total_games=len(formatted_games),
        )

    def format_boxscore_for_ai_prompt(self, context: BoxscoreContext) -> str:
        """
        Format boxscore context into AI-readable text for prompts

        Args:
            context: BoxscoreContext to format

        Returns:
            Formatted string for AI prompt inclusion
        """
        if not context.games:
            return f"No games found for {context.player_name} between {context.start_date} and {context.end_date}."

        lines = [
            f"Recent Games for {context.player_name} ({context.start_date} to {context.end_date}):"
        ]

        # Show games in reverse chronological order (most recent first)
        for game in reversed(context.games):
            game_line = (
                f"{game['date']}: {game['points']} pts, {game['assists']} ast, {game['rebounds']} reb "
                f"{game['opponent']} (season totals: {game['season_points_total']} pts, "
                f"{game['season_assists_total']} ast, {game['season_rebounds_total']} reb)"
            )
            lines.append(game_line)

        return "\n".join(lines)

    async def analyze_milestone_achievement_date(
        self,
        player_name: str,
        milestone_description: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, any]]:
        """
        Analyze when a milestone was likely achieved based on boxscore progression

        Args:
            player_name: Player name
            milestone_description: Description of the milestone
            start_date: Analysis start date
            end_date: Analysis end date

        Returns:
            Dict with analysis results or None if no clear achievement date
        """
        context = await self.get_boxscore_context_for_ai(
            player_name, start_date, end_date
        )

        if not context.games:
            return None

        # Look for threshold crossings in common milestone categories
        analysis = {
            "player_name": player_name,
            "milestone_description": milestone_description,
            "analysis_period": f"{start_date} to {end_date}",
            "total_games_analyzed": context.total_games,
            "potential_achievement_dates": [],
        }

        # Analyze for common milestone patterns
        milestone_lower = milestone_description.lower()

        # Points milestones (e.g., "500 points", "1000 points")
        if "point" in milestone_lower:
            analysis["potential_achievement_dates"].extend(
                self._find_threshold_crossings(
                    context.games, "season_points_total", milestone_lower
                )
            )

        # Assists milestones (e.g., "200 assists", "300 assists")
        if "assist" in milestone_lower:
            analysis["potential_achievement_dates"].extend(
                self._find_threshold_crossings(
                    context.games, "season_assists_total", milestone_lower
                )
            )

        # Rebounds milestones (e.g., "400 rebounds")
        if "rebound" in milestone_lower:
            analysis["potential_achievement_dates"].extend(
                self._find_threshold_crossings(
                    context.games, "season_rebounds_total", milestone_lower
                )
            )

        logger.info(
            f"Found {len(analysis['potential_achievement_dates'])} potential achievement dates"
        )

        return analysis if analysis["potential_achievement_dates"] else None

    def _find_threshold_crossings(
        self, games: List[Dict], stat_field: str, milestone_text: str
    ) -> List[Dict]:
        """Find games where statistical thresholds were crossed"""
        import re

        # Extract numbers from milestone text
        numbers = re.findall(r"\b(\d+)\b", milestone_text)
        if not numbers:
            return []

        crossings = []

        for threshold_str in numbers:
            threshold = int(threshold_str)

            # Find crossing point
            for i, game in enumerate(games):
                current_total = game.get(stat_field, 0)
                previous_total = games[i - 1].get(stat_field, 0) if i > 0 else 0

                # Check if threshold was crossed in this game
                if previous_total < threshold <= current_total:
                    crossings.append(
                        {
                            "date": game["date"],
                            "threshold": threshold,
                            "stat_type": stat_field,
                            "previous_total": previous_total,
                            "new_total": current_total,
                            "confidence": 0.9,  # High confidence for statistical crossings
                        }
                    )

        return crossings
