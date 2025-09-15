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
            return self._parse_games_table(html, player_name)

    def _parse_games_table(self, html: str, player_name: str) -> List[GameShoeData]:
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
                game_data = self._parse_game_row(row, player_name)
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
            kickstats_links = images_cell.find_all("a", href=lambda href: href and "kickstats" in href)
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
                game_photo_links = game_photo_cell.find_all("a", href=lambda href: href and "/img/games/" in str(href))
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
