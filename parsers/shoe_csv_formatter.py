"""
CSV formatter for shoe data to match FanbaseHQ schema exactly
"""

import csv
import json
import logging
import re
import uuid
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from parsers.ai_parser import ShoeData
from services.kixstats_service import GameShoeData
from services.kickscrew_service import KicksCrewService
from utils.image_service import _select_best_shoe_image
from config.settings import (
    CSV_ENCODING,
    CLIENT_SUBMITTER_NAME,
    CLIENT_SUBMITTER_EMAIL,
    CLIENT_USER_ID,
    CLIENT_ORIGINAL_SUBMISSION_ID,
)

logger = logging.getLogger(__name__)

BOOK_PATTERN = re.compile(r"^Book\s+(?P<version>\d+)(?:\s+(?P<color>.+))?$", re.IGNORECASE)
GT_CUT_PATTERN = re.compile(
    r"^(?P<model>Air\s+Zoom\s+G\.T\.\s+Cut\s+\d+)(?:\s+(?P<color>.+))?$",
    re.IGNORECASE,
)
LEBRON_PATTERN = re.compile(
    r"^LeBron\s+(?P<version>[IVXLCDM]+|\d+)(?:\s+(?P<color>.+))?$",
    re.IGNORECASE,
)


@dataclass
class GroupedGameShoe:
    """Aggregated representation of games played in the same shoe/colorway"""

    brand: str
    model: str
    color_description: str
    shoe_name: str
    player_name: str
    primary_source_url: str
    games: List[GameShoeData] = field(default_factory=list)
    image_urls: List[str] = field(default_factory=list)


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

    async def format_shoes_to_csv(
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
                    row = await self._format_shoe_to_row(shoe, tweet_sources)
                    writer.writerow(row)

            logger.info(f"Successfully wrote {len(shoes)} shoes to {self.output_file}")
            return len(shoes)

        except Exception as e:
            logger.error(f"Error writing shoes to CSV: {e}")
            return 0

    async def _format_shoe_to_row(
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
            "id": submission_id,
            "player_name": shoe.player_name,
            "shoe_name": shoe.shoe_name,
            "brand": shoe.brand,
            "model": shoe.model,
            "color_description": shoe.color_description,
            "release_date": release_date,
            "image_url": "",  # Twitter-based shoes don't have direct image URLs in ShoeData
            "image_data": "",  # Image processing only available for KixStats game shoes
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
            "submitter_name": CLIENT_SUBMITTER_NAME,
            "submitter_email": CLIENT_SUBMITTER_EMAIL,
            "user_id": CLIENT_USER_ID,
            "original_submission_id": CLIENT_ORIGINAL_SUBMISSION_ID,
            "created_at": now,
            "updated_at": now,
            "game_stats": game_stats_json,
            "player_edition": self._detect_player_edition(shoe),
        }

        return row

    async def format_game_shoes_to_csv(self, game_shoes: List[GameShoeData]) -> int:
        """
        Format KixStats game shoe data to CSV matching exact FanbaseHQ schema
        Enhanced with KicksCrew data for release dates and pricing

        Args:
            game_shoes: List of GameShoeData objects from KixStats

        Returns:
            Number of shoes written to CSV
        """
        if not game_shoes:
            logger.warning("No game shoes to format to CSV")
            return 0

        grouped_shoes = await self._group_game_shoes(game_shoes)

        if not grouped_shoes:
            logger.warning("No grouped shoes available after parsing shoe metadata")
            return 0

        logger.info(
            f"Formatting {len(game_shoes)} game entries as {len(grouped_shoes)} grouped shoes to CSV: {self.output_file}"
        )

        try:
            # Use KicksCrew service to enhance pricing data
            async with KicksCrewService() as kickscrew_service:
                with open(
                    self.output_file, "w", newline="", encoding=CSV_ENCODING
                ) as f:
                    writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
                    writer.writeheader()

                    for grouped_shoe in grouped_shoes:
                        row = await self._format_grouped_game_shoe_to_row(
                            grouped_shoe, kickscrew_service
                        )
                        writer.writerow(row)

            logger.info(
                f"Successfully wrote {len(grouped_shoes)} grouped shoes to {self.output_file}"
            )
            return len(grouped_shoes)

        except Exception as e:
            logger.error(f"Error writing game shoes to CSV: {e}")
            return 0

    async def _format_grouped_game_shoe_to_row(
        self, grouped_shoe: GroupedGameShoe, kickscrew_service: KicksCrewService
    ) -> Dict:
        """Format an aggregated shoe entry (model + colorway) to CSV row"""

        now = datetime.now().isoformat()
        submission_id = str(uuid.uuid4())

        brand = grouped_shoe.brand
        model = grouped_shoe.model
        color_description = grouped_shoe.color_description

        # Get KicksCrew pricing data
        kickscrew_data = await self._get_kickscrew_enhanced_data(
            grouped_shoe.games[0], kickscrew_service
        )

        # Try to get KicksCrew URL even if page data failed
        kickscrew_url = None
        representative_game = grouped_shoe.games[0]
        if not kickscrew_data and representative_game.shoe_url:
            try:
                kickscrew_url = (
                    await kickscrew_service._extract_kickscrew_url_from_kixstats(
                        representative_game.shoe_url
                    )
                )
            except Exception as e:
                logger.debug(
                    f"Could not extract KicksCrew URL from {representative_game.shoe_url}: {e}"
                )

        # Build enhanced pricing and links
        release_date, price, shop_links = self._build_enhanced_pricing_data(
            kickscrew_data,
            grouped_shoe.shoe_name,
            kickscrew_url,
            brand,
            model,
            color_description,
            kickscrew_service,
        )

        # Build game stats JSON
        game_stats_json = self._build_grouped_game_stats_json(grouped_shoe.games)
        description = self._build_group_description(grouped_shoe.games)
        additional_notes = self._build_group_additional_notes(
            grouped_shoe.games, kickscrew_data
        )

        # Detect shoe characteristics
        is_signature = self._detect_signature_shoe(grouped_shoe.shoe_name)
        is_player_edition = self._detect_player_edition_from_name(
            grouped_shoe.shoe_name
        )

        image_url = self._format_group_image_urls(grouped_shoe.image_urls)
        row = {
            "id": submission_id,
            "player_name": grouped_shoe.player_name,
            "shoe_name": grouped_shoe.shoe_name,
            "brand": brand,
            "model": model,
            "color_description": color_description,
            "release_date": release_date,
            "image_url": image_url,
            "image_data": "",
            "price": price,
            "shop_links": shop_links,
            "signature_shoe": is_signature,
            "limited_edition": False,  # Could enhance detection
            "performance_features": "[]",  # Could enhance with shoe database
            "description": description,
            "social_stats": "{}",  # No social data from KixStats
            "source": "KixStats",
            "source_link": grouped_shoe.primary_source_url,
            "photographer": "",
            "photographer_link": "",
            "additional_notes": additional_notes,
            "status": "approved",  # Default status
            "submitter_name": CLIENT_SUBMITTER_NAME,
            "submitter_email": CLIENT_SUBMITTER_EMAIL,
            "user_id": CLIENT_USER_ID,
            "original_submission_id": CLIENT_ORIGINAL_SUBMISSION_ID,
            "created_at": now,
            "updated_at": now,
            "game_stats": game_stats_json,
            "player_edition": is_player_edition,
        }

        return row

    async def _group_game_shoes(
        self, game_shoes: List[GameShoeData]
    ) -> List[GroupedGameShoe]:
        """Group individual game shoes by brand + model + colorway"""
        grouped: Dict[str, GroupedGameShoe] = {}
        sorted_games = sorted(game_shoes, key=lambda g: g.game_date)

        for game_shoe in sorted_games:
            brand, model, color_description = await self._parse_shoe_name_enhanced(
                game_shoe
            )
            display_color = color_description.strip()
            color_key = display_color.lower() if display_color else "unknown"
            group_key = self._build_group_key(brand, model, color_key)

            group = grouped.get(group_key)
            if not group:
                shoe_name = self._compose_shoe_name(
                    brand, model, display_color, game_shoe.shoe_name
                )
                group = GroupedGameShoe(
                    brand=brand,
                    model=model,
                    color_description=display_color,
                    shoe_name=shoe_name,
                    player_name=game_shoe.player_name,
                    primary_source_url=game_shoe.shoe_url,
                )
                grouped[group_key] = group
            else:
                if not group.color_description and display_color:
                    group.color_description = display_color
                if not group.shoe_name:
                    group.shoe_name = self._compose_shoe_name(
                        brand, model, display_color, game_shoe.shoe_name
                    )
                if not group.primary_source_url and game_shoe.shoe_url:
                    group.primary_source_url = game_shoe.shoe_url

            group.games.append(game_shoe)

            image_urls = self._extract_image_urls(game_shoe.image_url)
            if image_urls:
                group.image_urls.extend(image_urls)

        ordered_groups = sorted(
            grouped.values(),
            key=lambda g: g.games[0].game_date if g.games else datetime.max.date(),
        )
        return ordered_groups

    def _build_group_key(self, brand: str, model: str, color_key: str) -> str:
        """Build normalized dictionary key for grouping shoes"""
        brand_key = (brand or "").strip().lower()
        model_key = (model or "").strip().lower()
        color_component = (color_key or "unknown").strip().lower()
        if not color_component:
            color_component = "unknown"
        return f"{brand_key}|{model_key}|{color_component}"

    def _compose_shoe_name(
        self, brand: str, model: str, color_description: str, fallback: str
    ) -> str:
        """Build a readable shoe name from parsed parts"""
        parts = [part for part in [brand, model] if part]
        composed = " ".join(parts).strip()

        if color_description:
            composed = f"{composed} {color_description}".strip()

        return composed if composed else fallback

    def _is_version_indicator(self, token: str) -> bool:
        """Check if token represents a version number or Roman numeral"""
        if not token:
            return False

        stripped = token.replace(".", "").replace("-", "")
        if not stripped:
            return False

        if stripped.isdigit():
            return True

        roman = stripped.upper()
        return all(ch in "IVXLCDM" for ch in roman)

    def _extract_image_urls(self, raw_image_value: str) -> List[str]:
        """Parse stored image field into a list of URLs"""
        if not raw_image_value:
            return []

        value = raw_image_value.strip()
        if not value:
            return []

        if value.startswith("[") and value.endswith("]"):
            try:
                urls = json.loads(value)
                return [
                    url for url in urls if isinstance(url, str) and url.strip()
                ]
            except json.JSONDecodeError:
                logger.debug("Failed to parse image JSON for shoe entry")
                return []

        return [value]

    def _format_group_image_urls(self, image_urls: List[str]) -> str:
        """Return JSON array string of deduplicated image URLs"""
        if not image_urls:
            return ""

        seen = set()
        game_photos = []
        other_photos = []

        for url in image_urls:
            if not url or url in seen:
                continue
            seen.add(url)
            if "/img/games/" in url:
                game_photos.append(url)
            else:
                other_photos.append(url)

        ordered_urls = game_photos + other_photos
        if not ordered_urls:
            return ""

        return json.dumps(ordered_urls)

    async def _get_kickscrew_enhanced_data(
        self, game_shoe: GameShoeData, kickscrew_service: KicksCrewService
    ):
        """Get KicksCrew data for enhanced information with error handling"""
        if not game_shoe.shoe_url:
            return None

        try:
            return await kickscrew_service.get_shoe_details_from_kixstats_url(
                game_shoe.shoe_url
            )
        except Exception as e:
            logger.debug(f"Could not get KicksCrew data for {game_shoe.shoe_url}: {e}")
            return None

    def _build_enhanced_pricing_data(
        self,
        kickscrew_data,
        shoe_name: str,
        kickscrew_url: str = None,
        brand: str = "",
        model: str = "",
        color_description: str = "",
        kickscrew_service: KicksCrewService = None,
    ) -> tuple:
        """Build release date, price, and shop links with KicksCrew enhancement"""
        release_date = ""
        price = ""
        shop_links = "[]"

        if kickscrew_data:
            # Use KicksCrew release date
            if kickscrew_data.release_date:
                release_date = kickscrew_data.release_date.isoformat()

            # Use KicksCrew retail price
            if kickscrew_data.retail_price:
                price = kickscrew_data.retail_price.value

            # Use direct KicksCrew purchase link
            if kickscrew_data.kickscrew_url:
                shop_links = json.dumps([kickscrew_data.kickscrew_url.value])
        elif kickscrew_url:
            # We have KicksCrew URL but no page data - still use the URL for shop_links
            shop_links = json.dumps([kickscrew_url])
        else:
            # Fallback to GOAT search link
            shop_links = json.dumps([self._build_goat_search_url(shoe_name)])

        return release_date, price, shop_links

    def _build_grouped_game_stats_json(
        self, games: List[GameShoeData]
    ) -> str:
        """Build aggregated game stats JSON for grouped shoes"""
        if not games:
            return json.dumps({"games": [], "summary": {}})

        games_sorted = sorted(games, key=lambda g: g.game_date)
        game_entries = [
            {
                "date": game.game_date.isoformat(),
                "points": game.points,
                "rebounds": game.rebounds,
                "assists": game.assists,
                "steals": game.steals,
                "blocks": game.blocks,
                "minutes": game.minutes,
                "opponent": game.opponent,
            }
            for game in games_sorted
        ]

        games_played = len(games_sorted)
        total_minutes = sum(game.minutes for game in games_sorted)
        total_points = sum(game.points for game in games_sorted)
        total_rebounds = sum(game.rebounds for game in games_sorted)
        total_assists = sum(game.assists for game in games_sorted)
        total_steals = sum(game.steals for game in games_sorted)
        total_blocks = sum(game.blocks for game in games_sorted)

        def average(total: int) -> float:
            return round(total / games_played, 1) if games_played else 0.0

        best_game = max(
            games_sorted,
            key=lambda g: (g.points, g.rebounds, g.assists, g.minutes, g.game_date),
        )

        summary = {
            "gamesPlayed": games_played,
            "totalMinutes": total_minutes,
            "pointsPerGame": average(total_points),
            "assistsPerGame": average(total_assists),
            "reboundsPerGame": average(total_rebounds),
            "stealsPerGame": average(total_steals),
            "blocksPerGame": average(total_blocks),
            "bestGame": {
                "date": best_game.game_date.isoformat(),
                "points": best_game.points,
                "rebounds": best_game.rebounds,
                "assists": best_game.assists,
                "minutes": best_game.minutes,
                "opponent": best_game.opponent,
            },
        }

        return json.dumps({"games": game_entries, "summary": summary})

    def _build_group_description(self, games: List[GameShoeData]) -> str:
        """Describe how often the shoe was worn"""
        if not games:
            return ""

        games_sorted = sorted(games, key=lambda g: g.game_date)
        if len(games_sorted) == 1:
            game = games_sorted[0]
            opponent = f" vs {game.opponent}" if game.opponent else ""
            return f"Worn in game on {game.game_date.isoformat()}{opponent}"

        start = games_sorted[0].game_date.isoformat()
        end = games_sorted[-1].game_date.isoformat()
        return f"Worn in {len(games_sorted)} games from {start} to {end}"

    def _parse_shoe_name(self, shoe_name: str) -> tuple:
        """Parse shoe name into brand, model, and color components"""
        # Examples:
        # "Nike Kobe 6 Sail All-Star" -> ("Nike", "Kobe 6", "Sail All-Star")
        # "Nike Book 1 1995 All-Star" -> ("Nike", "Book 1", "1995 All-Star")
        # "Nike Air Zoom G.T. Cut 3 Turbo" -> ("Nike", "Air Zoom G.T. Cut 3", "Turbo")

        parts = shoe_name.split()
        if len(parts) < 2:
            return shoe_name, "", ""

        brand = parts[0]

        # Dedicated handling for Kobe lines (numbers and Roman numerals)
        if len(parts) >= 3 and parts[1].lower() == "kobe":
            if parts[2] in ["V", "VI", "VIII", "5", "6", "8", "9", "10", "11"]:
                model = f"{parts[1]} {parts[2]}"
                remaining_parts = parts[3:]

                if remaining_parts and remaining_parts[0].lower() == "protro":
                    model = f"{model} Protro"
                    remaining_parts = remaining_parts[1:]

                color_description = " ".join(remaining_parts)
            else:
                model = parts[1]
                color_description = " ".join(parts[2:])
            return brand, model, color_description

        remaining_text = " ".join(parts[1:]).strip()
        if not remaining_text:
            return brand, "", ""

        book_match = BOOK_PATTERN.match(remaining_text)
        if book_match:
            version = book_match.group("version")
            color = (book_match.group("color") or "").strip()
            return brand, f"Book {version}".strip(), color

        gt_cut_match = GT_CUT_PATTERN.match(remaining_text)
        if gt_cut_match:
            model = gt_cut_match.group("model").strip()
            color = (gt_cut_match.group("color") or "").strip()
            return brand, model, color

        lebron_match = LEBRON_PATTERN.match(remaining_text)
        if lebron_match:
            version = lebron_match.group("version")
            color = (lebron_match.group("color") or "").strip()
            return brand, f"LeBron {version}".strip(), color

        # Fallback parsing
        model = parts[1]
        color_description = " ".join(parts[2:]) if len(parts) > 2 else ""

        color_parts = color_description.split()
        if color_parts and self._is_version_indicator(color_parts[0]):
            model = f"{model} {color_parts[0]}".strip()
            color_description = " ".join(color_parts[1:])

        return brand, model, color_description

    async def _parse_shoe_name_enhanced(self, game_shoe) -> tuple:
        """Parse shoe name with optional colorway enhancement"""
        # First try standard parsing
        brand, model, color_description = self._parse_shoe_name(game_shoe.shoe_name)

        # If no colorway found in title, use AI for simple color description
        if not color_description:
            try:
                ai_color_description = await self._get_simple_color_description(
                    game_shoe.image_url
                )
                if ai_color_description:
                    color_description = ai_color_description
                    logger.info(
                        f"AI color description for {brand} {model}: {color_description}"
                    )
                else:
                    logger.debug(
                        f"No AI color description available for {brand} {model}"
                    )
            except Exception as e:
                logger.debug(f"AI color description failed for {brand} {model}: {e}")
        else:
            logger.info(
                f"Using parsed colorway for {brand} {model}: {color_description}"
            )

        return brand, model, color_description

    async def _get_simple_color_description(self, image_url: str) -> Optional[str]:
        """Get simple 1-3 word color description from AI vision"""
        if not image_url:
            return None

        try:
            # Parse image URLs from JSON array if needed
            image_urls = []
            if image_url.startswith("[") and image_url.endswith("]"):
                import json

                image_urls = json.loads(image_url)
            else:
                image_urls = [image_url]

            if not image_urls:
                return None

            # Use centralized image selection logic
            best_image_url = _select_best_shoe_image(image_urls)

            if not best_image_url:
                logger.debug("No valid images available for color analysis")
                return None

            # Use OpenAI Vision API for simple color description
            import openai
            import base64
            import aiohttp

            # Download and encode image
            async with aiohttp.ClientSession() as session:
                async with session.get(best_image_url) as response:
                    if response.status != 200:
                        logger.debug(f"Failed to download image: {response.status}")
                        return None
                    image_data = await response.read()

            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Simple color description prompt
            client = openai.AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=20,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Describe the primary colors of this basketball shoe in 1-3 simple words.
                                Examples: 'White Black', 'Blue Yellow', 'Purple Gold', 'Multi-Color'
                                Focus on dominant colors visible in the image. Respond with only the color description.""",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
            )

            color_description = response.choices[0].message.content.strip()

            if color_description:
                logger.info(f"AI color description: {color_description}")
                return color_description
            else:
                logger.debug("No color description provided")
                return None

        except Exception as e:
            logger.debug(f"Error getting color description: {e}")
            return None

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

    def _build_group_additional_notes(
        self, games: List[GameShoeData], kickscrew_data
    ) -> str:
        """Build additional notes field for grouped game shoe data"""
        if not games:
            return ""

        games_sorted = sorted(games, key=lambda g: g.game_date)
        notes = []

        if len(games_sorted) == 1:
            game = games_sorted[0]
            notes.append(f"Game: {game.game_date.isoformat()}")
            notes.append(
                f"Stats: {game.points}pts, {game.rebounds}reb, {game.assists}ast"
            )
        else:
            notes.append(f"Games: {len(games_sorted)}")
            notes.append(
                f"Range: {games_sorted[0].game_date.isoformat()} → {games_sorted[-1].game_date.isoformat()}"
            )
            best_game = max(
                games_sorted,
                key=lambda g: (g.points, g.rebounds, g.assists, g.minutes, g.game_date),
            )
            notes.append(
                f"Best: {best_game.points}pts, {best_game.rebounds}reb, {best_game.assists}ast"
            )

        # Add data source
        notes.append("Source: KixStats game-by-game tracking")

        # Add KicksCrew enhancement info
        if kickscrew_data:
            if kickscrew_data.release_date:
                notes.append(f"Release: {kickscrew_data.release_date.isoformat()}")
            if kickscrew_data.retail_price:
                notes.append(f"Retail: {kickscrew_data.retail_price.value}")
            notes.append("Enhanced: KicksCrew data")
        else:
            notes.append("Enhanced: Limited data available")

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
