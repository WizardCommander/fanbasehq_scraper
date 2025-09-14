"""
CSV formatter for shoe data to match FanbaseHQ schema exactly
"""

import csv
import json
import logging
import uuid
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from parsers.ai_parser import ShoeData
from services.kixstats_service import GameShoeData
from config.settings import CSV_ENCODING

logger = logging.getLogger(__name__)


class ShoeCSVFormatter:
    """Format shoe data to match FanbaseHQ CSV schema exactly"""

    # CSV columns based on the actual database CSV schema
    CSV_COLUMNS = [
        "id",
        "player_name",
        "shoe_name",
        "brand",
        "model",
        "color_description",
        "release_date",
        "image_url",
        "image_data",
        "price",
        "shop_links",
        "signature_shoe",
        "limited_edition",
        "performance_features",
        "description",
        "social_stats",
        "source",
        "source_link",
        "photographer",
        "photographer_link",
        "additional_notes",
        "status",
        "submitter_name",
        "submitter_email",
        "user_id",
        "original_submission_id",
        "created_at",
        "updated_at",
        "game_stats",
        "player_edition",
    ]

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    def format_shoes_to_csv(
        self, shoes: List[ShoeData], tweet_sources: Dict[str, str] = None
    ) -> int:
        """
        Format shoe data to CSV matching exact FanbaseHQ schema

        Args:
            shoes: List of ShoeData objects to format
            tweet_sources: Dict mapping tweet_id -> source_account for accurate source attribution

        Returns:
            Number of shoes written to CSV
        """
        if not shoes:
            logger.warning("No shoes to format to CSV")
            return 0

        logger.info(f"Formatting {len(shoes)} shoes to CSV: {self.output_file}")

        try:
            with open(self.output_file, "w", newline="", encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
                writer.writeheader()

                for shoe in shoes:
                    row = self._format_shoe_to_row(shoe, tweet_sources)
                    writer.writerow(row)

            logger.info(f"Successfully wrote {len(shoes)} shoes to {self.output_file}")
            return len(shoes)

        except Exception as e:
            logger.error(f"Error writing shoes to CSV: {e}")
            return 0

    def _format_shoe_to_row(
        self, shoe: ShoeData, tweet_sources: Dict[str, str] = None
    ) -> Dict:
        """Format a single ShoeData object to CSV row dictionary"""

        now = datetime.now().isoformat()
        submission_id = str(uuid.uuid4())

        # Extract source information using the tweet_sources mapping
        source = self._extract_source_from_tweet_id(
            shoe.source_tweet_id.value, tweet_sources
        )
        source_link = (
            f"https://x.com/{source}/status/{shoe.source_tweet_id.value}"
            if source
            else ""
        )

        # Format performance features as JSON array
        performance_features_json = (
            json.dumps(shoe.performance_features) if shoe.performance_features else "[]"
        )

        # Format social stats as JSON string
        social_stats_json = (
            json.dumps(shoe.social_stats) if shoe.social_stats else json.dumps({})
        )

        # Format game stats as JSON string (complex structure)
        game_stats_json = (
            json.dumps(shoe.game_stats) if shoe.game_stats else json.dumps({})
        )

        # Handle missing data with fallback services
        price = self._format_price_with_fallback(
            shoe.price, shoe.has_missing_data, "price" in (shoe.missing_fields or [])
        )
        release_date = self._format_release_date_with_fallback(
            shoe.release_date,
            shoe.has_missing_data,
            "release_date" in (shoe.missing_fields or []),
        )

        row = {
            "id": len(str(submission_id)),  # Simple numeric ID for now
            "player_name": shoe.player_name,
            "shoe_name": shoe.shoe_name,
            "brand": shoe.brand,
            "model": shoe.model,
            "color_description": shoe.color_description,
            "release_date": release_date,
            "image_url": "",  # Would need image extraction from tweet
            "image_data": "",  # Would need base64 encoding - fallback service needed
            "price": price,
            "shop_links": "[]",  # Would extract from tweet links - fallback service needed
            "signature_shoe": shoe.signature_shoe,
            "limited_edition": shoe.limited_edition,
            "performance_features": performance_features_json,
            "description": shoe.description,
            "social_stats": social_stats_json,
            "source": source,
            "source_link": source_link,
            "photographer": "",  # Would need extraction - fallback service
            "photographer_link": "",  # Would need extraction - fallback service
            "additional_notes": self._build_additional_notes(shoe),
            "status": "approved",  # Default status
            "submitter_name": "shoe_scraper",  # Bot submission
            "submitter_email": "",
            "user_id": submission_id,
            "original_submission_id": submission_id,
            "created_at": now,
            "updated_at": now,
            "game_stats": game_stats_json,
            "player_edition": self._detect_player_edition(shoe),
        }

        return row

    def format_game_shoes_to_csv(self, game_shoes: List[GameShoeData]) -> int:
        """
        Format KixStats game shoe data to CSV matching exact FanbaseHQ schema

        Args:
            game_shoes: List of GameShoeData objects from KixStats

        Returns:
            Number of shoes written to CSV
        """
        if not game_shoes:
            logger.warning("No game shoes to format to CSV")
            return 0

        logger.info(
            f"Formatting {len(game_shoes)} game shoes to CSV: {self.output_file}"
        )

        try:
            with open(self.output_file, "w", newline="", encoding=CSV_ENCODING) as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
                writer.writeheader()

                for game_shoe in game_shoes:
                    row = self._format_game_shoe_to_row(game_shoe)
                    writer.writerow(row)

            logger.info(
                f"Successfully wrote {len(game_shoes)} game shoes to {self.output_file}"
            )
            return len(game_shoes)

        except Exception as e:
            logger.error(f"Error writing game shoes to CSV: {e}")
            return 0

    def _format_game_shoe_to_row(self, game_shoe: GameShoeData) -> Dict:
        """Format a single GameShoeData object to CSV row dictionary"""

        now = datetime.now().isoformat()
        submission_id = str(uuid.uuid4())

        # Extract brand and model from shoe_name (e.g., "Nike Kobe 6 Sail All-Star")
        brand, model, color_description = self._parse_shoe_name(game_shoe.shoe_name)

        # Build game stats JSON with actual performance data
        game_stats = {
            "games": [
                {
                    "date": game_shoe.game_date.isoformat(),
                    "points": game_shoe.points,
                    "rebounds": game_shoe.rebounds,
                    "assists": game_shoe.assists,
                    "steals": game_shoe.steals,
                    "blocks": game_shoe.blocks,
                    "minutes": game_shoe.minutes,
                    "opponent": "Unknown",  # KixStats doesn't provide opponent info
                }
            ],
            "summary": {
                "gamesPlayed": 1,
                "totalMinutes": game_shoe.minutes,
                "pointsPerGame": game_shoe.points,
                "assistsPerGame": game_shoe.assists,
                "reboundsPerGame": game_shoe.rebounds,
                "stealsPerGame": game_shoe.steals,
                "blocksPerGame": game_shoe.blocks,
                "bestGame": {
                    "date": game_shoe.game_date.isoformat(),
                    "points": game_shoe.points,
                    "rebounds": game_shoe.rebounds,
                    "assists": game_shoe.assists,
                    "minutes": game_shoe.minutes,
                    "opponent": "Unknown",
                },
            },
        }

        # Detect if this is a signature/player edition shoe
        is_signature = self._detect_signature_shoe(game_shoe.shoe_name)
        is_player_edition = self._detect_player_edition_from_name(game_shoe.shoe_name)

        row = {
            "id": len(str(submission_id)),  # Simple numeric ID for now
            "player_name": game_shoe.player_name,
            "shoe_name": game_shoe.shoe_name,
            "brand": brand,
            "model": model,
            "color_description": color_description,
            "release_date": "",  # KixStats doesn't provide release dates
            "image_url": game_shoe.image_url,  # Now extracted from KixStats
            "image_data": "",
            "price": "",  # KixStats doesn't provide pricing
            "shop_links": json.dumps(
                [self._build_goat_search_url(game_shoe.shoe_name)]
            ),
            "signature_shoe": is_signature,
            "limited_edition": False,  # Could enhance detection
            "performance_features": "[]",  # Could enhance with shoe database
            "description": f"Worn in game on {game_shoe.game_date.isoformat()}",
            "social_stats": "{}",  # No social data from KixStats
            "source": "KixStats",
            "source_link": game_shoe.shoe_url,
            "photographer": "",
            "photographer_link": "",
            "additional_notes": self._build_game_additional_notes(game_shoe),
            "status": "approved",  # Default status
            "submitter_name": "kixstats_scraper",
            "submitter_email": "",
            "user_id": submission_id,
            "original_submission_id": submission_id,
            "created_at": now,
            "updated_at": now,
            "game_stats": json.dumps(game_stats),
            "player_edition": is_player_edition,
        }

        return row

    def _parse_shoe_name(self, shoe_name: str) -> tuple:
        """Parse shoe name into brand, model, and color components"""
        # Examples:
        # "Nike Kobe 6 Sail All-Star" -> ("Nike", "Kobe 6", "Sail All-Star")
        # "Nike Kobe 5 Protro Indiana Fever" -> ("Nike", "Kobe 5 Protro", "Indiana Fever")
        # "Nike Kobe V" -> ("Nike", "Kobe V", "")

        parts = shoe_name.split()
        if len(parts) < 2:
            return shoe_name, "", ""

        # First part is usually brand
        brand = parts[0]

        # Look for common model patterns, especially Kobe shoes
        if len(parts) >= 3 and parts[1] == "Kobe":
            # Handle numeric versions (5, 6, 8, etc.) and Roman numerals (V, VI, VIII, etc.)
            if parts[2] in ["V", "VI", "VIII", "5", "6", "8", "9", "10", "11"]:
                model = f"{parts[1]} {parts[2]}"
                remaining_parts = parts[3:]

                # Check for "Protro" after the number/numeral
                if remaining_parts and remaining_parts[0] == "Protro":
                    model = f"{model} Protro"
                    color_description = (
                        " ".join(remaining_parts[1:])
                        if len(remaining_parts) > 1
                        else ""
                    )
                else:
                    color_description = " ".join(remaining_parts)
            else:
                # Non-standard Kobe model naming
                model = parts[1]
                color_description = " ".join(parts[2:])
        else:
            # Non-Kobe shoes or different brand patterns
            model = parts[1] if len(parts) > 1 else ""
            color_description = " ".join(parts[2:]) if len(parts) > 2 else ""

        return brand, model, color_description

    def _detect_signature_shoe(self, shoe_name: str) -> bool:
        """Detect if this is a signature shoe"""
        signature_indicators = ["kobe", "signature", "player exclusive", "pe"]
        shoe_name_lower = shoe_name.lower()

        return any(indicator in shoe_name_lower for indicator in signature_indicators)

    def _detect_player_edition_from_name(self, shoe_name: str) -> bool:
        """Detect if this is a player edition shoe from name"""
        pe_indicators = ["caitlin clark", "clark", "pe", "player exclusive", "fever"]
        shoe_name_lower = shoe_name.lower()

        return any(indicator in shoe_name_lower for indicator in pe_indicators)

    def _build_game_additional_notes(self, game_shoe: GameShoeData) -> str:
        """Build additional notes field for game shoe data"""
        notes = []

        # Add game performance summary
        notes.append(f"Game: {game_shoe.game_date.isoformat()}")
        notes.append(
            f"Stats: {game_shoe.points}pts, {game_shoe.rebounds}reb, {game_shoe.assists}ast"
        )
        notes.append(f"Minutes: {game_shoe.minutes}")

        # Add data source
        notes.append("Source: KixStats game-by-game tracking")

        return " | ".join(notes)

    def _extract_source_from_tweet_id(
        self, tweet_id: str, tweet_sources: Dict[str, str] = None
    ) -> str:
        """Extract source account from tweet ID using the tweet_sources mapping"""
        if tweet_sources and tweet_id in tweet_sources:
            source_account = tweet_sources[tweet_id]
            # Remove @ symbol if present
            return source_account.lstrip("@")

        # Fallback to empty string if no source mapping available
        return ""

    def _format_price_with_fallback(
        self, price: str, has_missing_data: bool, is_missing: bool
    ) -> str:
        """Format price with fallback service for missing data"""
        if price and price.strip():
            # Ensure price has currency symbol
            if not price.startswith("$"):
                return f"${price}"
            return price

        # Fallback for missing price data
        if is_missing:
            return ""  # Could be enhanced with external price lookup service

        return ""

    def _format_release_date_with_fallback(
        self, release_date: Optional[any], has_missing_data: bool, is_missing: bool
    ) -> str:
        """Format release date with fallback service for missing data"""
        if release_date:
            if hasattr(release_date, "isoformat"):
                return release_date.isoformat()
            return str(release_date)

        # Fallback for missing release date
        if is_missing:
            return ""  # Could be enhanced with external release date lookup service

        return ""

    def _detect_player_edition(self, shoe: ShoeData) -> bool:
        """Detect if this is a player edition shoe"""
        # Simple heuristic - could be enhanced
        player_indicators = ["caitlin clark", "clark", "signature"]
        shoe_name_lower = shoe.shoe_name.lower()

        for indicator in player_indicators:
            if indicator in shoe_name_lower:
                return True

        return shoe.signature_shoe  # Fall back to AI detection

    def _build_additional_notes(self, shoe: ShoeData) -> str:
        """Build additional notes field with confidence scores and missing data info"""
        notes = []

        # Add confidence information
        notes.append(f"Shoe confidence: {shoe.shoe_confidence:.2f}")
        notes.append(f"Date confidence: {shoe.date_confidence:.2f}")
        notes.append(f"Date source: {shoe.date_source}")

        # Add missing data information for transparency
        if shoe.has_missing_data and shoe.missing_fields:
            notes.append(f"Missing data: {', '.join(shoe.missing_fields)}")

        # Add game stats summary if available
        if shoe.game_stats and isinstance(shoe.game_stats, dict):
            summary = shoe.game_stats.get("summary", {})
            games_played = summary.get("gamesPlayed", 0)
            if games_played > 0:
                notes.append(f"Games integrated: {games_played}")

        return " | ".join(notes)

    def _build_goat_search_url(self, shoe_name: str) -> str:
        """Build GOAT search URL from shoe name"""
        query = urllib.parse.quote(shoe_name)
        return f"https://www.goat.com/search?query={query}"
