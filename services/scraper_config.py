"""
Scraper Configuration
Centralized configuration for milestone scraping
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict, Any


@dataclass
class ScraperConfig:
    """Configuration for milestone scraping operations"""

    # Required parameters
    player: str
    player_display_name: str
    start_date: date
    end_date: date
    output_file: str

    # Optional parameters with defaults
    limit: int = 100
    force_refresh: bool = False

    # Player and account configuration
    player_variations: List[str] = field(default_factory=list)
    target_accounts: List[str] = field(default_factory=list)

    # Team information (populated dynamically)
    team_name: str = ""
    team_id: str = ""

    # Advanced settings
    enable_game_validation: bool = True
    enable_preseason_validation: bool = True
    enhance_colorways: bool = True
    max_retries: int = 3

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ScraperConfig":
        """Create ScraperConfig from dictionary"""
        return cls(**config_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ScraperConfig to dictionary"""
        return {
            "player": self.player,
            "player_display_name": self.player_display_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "output_file": self.output_file,
            "limit": self.limit,
            "force_refresh": self.force_refresh,
            "player_variations": self.player_variations,
            "target_accounts": self.target_accounts,
            "team_name": self.team_name,
            "team_id": self.team_id,
            "enable_game_validation": self.enable_game_validation,
            "enable_preseason_validation": self.enable_preseason_validation,
            "enhance_colorways": self.enhance_colorways,
            "max_retries": self.max_retries,
        }

    def validate(self) -> None:
        """Validate configuration parameters"""
        if not self.player:
            raise ValueError("Player name is required")

        if not self.player_display_name:
            raise ValueError("Player display name is required")

        if not self.output_file:
            raise ValueError("Output file is required")

        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")

        if self.limit <= 0:
            raise ValueError("Limit must be positive")

        if not self.player_variations:
            raise ValueError("At least one player variation is required")
