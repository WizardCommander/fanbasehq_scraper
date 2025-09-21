"""
Sneaker Database Service
Service for extracting colorway data from The Sneaker Database API
"""

import logging
import asyncio
import json
import os
from datetime import date
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv("config/.env")

logger = logging.getLogger(__name__)


@dataclass
class ColorwayData:
    """Colorway data from The Sneaker Database"""

    name: str
    colorway: str
    brand: str
    model: str
    release_date: Optional[date]
    image_url: str
    sku: str
    retail_price: Optional[float]
    stockx_link: str = ""


class SneakerDatabaseService:
    """Service for retrieving colorway data from The Sneaker Database API"""

    def __init__(self, api_key: Optional[str] = None, request_timeout: int = 30):
        self.base_url = "https://the-sneaker-database.p.rapidapi.com"
        self.api_key = api_key or os.getenv("SNEAKER_DATABASE_API_KEY")
        self.session = None
        self.request_timeout = request_timeout
        self._cache = {}  # Simple in-memory cache

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_colorways_for_model(
        self, brand: str, model: str
    ) -> List[ColorwayData]:
        """
        Get all available colorways for a specific shoe model

        Args:
            brand: Shoe brand (e.g., "Nike", "Adidas", "Jordan")
            model: Shoe model (e.g., "Kobe V", "Air Jordan 1", "Yeezy 350")

        Returns:
            List of ColorwayData objects for the specified model
        """
        cache_key = f"{brand.lower()}_{model.lower().replace(' ', '_')}"

        if cache_key in self._cache:
            logger.debug(f"Returning cached colorways for {brand} {model}")
            return self._cache[cache_key]

        try:
            if not self.session:
                async with aiohttp.ClientSession() as session:
                    return await self._fetch_colorways_with_session(
                        session, brand, model, cache_key
                    )
            else:
                return await self._fetch_colorways_with_session(
                    self.session, brand, model, cache_key
                )

        except Exception as e:
            logger.error(f"Error fetching colorways for {brand} {model}: {e}")
            return []

    async def _fetch_colorways_with_session(
        self, session: aiohttp.ClientSession, brand: str, model: str, cache_key: str
    ) -> List[ColorwayData]:
        """Internal method to fetch colorways with provided session - uses multiple calls for comprehensive results"""

        all_colorways = []
        seen_names = set()  # Track duplicates across pages
        page = 1
        max_pages = 5  # Limit to prevent excessive API calls

        while page <= max_pages:
            # Add respectful delay between calls
            if page > 1:
                await asyncio.sleep(1)

            headers = {}
            if self.api_key:
                headers["x-rapidapi-key"] = self.api_key
                headers["x-rapidapi-host"] = "the-sneaker-database.p.rapidapi.com"

            # Build API parameters with pagination
            params = {
                "limit": 100,  # Max limit per call
                "brand": brand.lower(),
                "name": model.lower(),
                "page": page,
            }

            url = f"{self.base_url}/sneakers"

            logger.info(f"Making API request to: {url} (page {page})")
            logger.info(f"Params: {params}")

            try:
                async with session.get(
                    url, headers=headers, params=params, timeout=self.request_timeout
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to fetch sneaker data: HTTP {response.status}"
                        )
                        break

                    data = await response.json()
                    page_colorways = self._parse_colorways(data, model)

                    # Add new colorways (deduplicate by name)
                    new_count = 0
                    for colorway in page_colorways:
                        if colorway.name not in seen_names:
                            all_colorways.append(colorway)
                            seen_names.add(colorway.name)
                            new_count += 1

                    logger.info(
                        f"Page {page}: Found {len(page_colorways)} colorways, {new_count} new"
                    )

                    # If we got fewer than 100 results, we've reached the end
                    if len(page_colorways) < 100:
                        logger.info(f"Reached end of results at page {page}")
                        break

                    page += 1

            except Exception as e:
                logger.warning(f"Page {page} failed: {e}")
                break

        # Sort by release date (newest first) when available
        all_colorways = self._sort_colorways_by_date(all_colorways)

        # Filter out placeholder images
        all_colorways = self._filter_valid_images(all_colorways)

        # Cache the comprehensive results
        self._cache[cache_key] = all_colorways

        logger.info(f"Total colorways found for {brand} {model}: {len(all_colorways)}")
        return all_colorways

    def _sort_colorways_by_date(
        self, colorways: List[ColorwayData]
    ) -> List[ColorwayData]:
        """Sort colorways by release date (newest first), then by name"""

        def sort_key(colorway):
            # Newest dates first (None goes to end)
            if colorway.release_date is None:
                return (1, colorway.name)  # No date - sort by name at end
            return (0, -colorway.release_date.toordinal())  # Negative for desc order

        return sorted(colorways, key=sort_key)

    def _filter_valid_images(self, colorways: List[ColorwayData]) -> List[ColorwayData]:
        """Filter out colorways with placeholder or missing images"""
        valid_colorways = []

        for colorway in colorways:
            # Skip placeholder images
            if (
                colorway.image_url
                and "missing.png" not in colorway.image_url
                and "placeholder" not in colorway.image_url.lower()
                and colorway.image_url.strip() != ""
            ):
                valid_colorways.append(colorway)
            else:
                logger.debug(
                    f"Filtered out colorway with invalid image: {colorway.name}"
                )

        return valid_colorways

    def _parse_colorways(
        self, api_response: Dict[str, Any], target_model: str
    ) -> List[ColorwayData]:
        """Parse API response and filter for target model"""

        colorways = []
        results = api_response.get("results", [])

        # Normalize target model for matching
        normalized_target = self._normalize_model_name(target_model)

        for item in results:
            name = item.get("name", "")

            # Check if this item matches our target model
            if not self._is_model_match(name, normalized_target):
                continue

            try:
                colorway_data = self._create_colorway_data(item)
                if colorway_data:
                    colorways.append(colorway_data)
            except Exception as e:
                logger.debug(f"Error parsing colorway item: {e}")
                continue

        return colorways

    def _normalize_model_name(self, model: str) -> str:
        """Normalize model name for consistent matching"""
        normalized = model.lower().strip()

        # Handle common variations for various brands
        replacements = {
            # Nike Kobe variations (order matters - longer patterns first)
            "kobe viii": "kobe 8",
            "kobe vi": "kobe 6",
            "kobe ix": "kobe 9",
            "kobe xi": "kobe 11",
            "kobe v": "kobe 5",
            # Jordan variations
            "air jordan": "jordan",
            "aj": "jordan",
            # LeBron variations
            "lebron james": "lebron",
            # Remove common prefixes/suffixes
            "nike ": "",
            "adidas ": "",
            " retro": "",
            " og": "",
        }

        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        return normalized.strip()

    def _is_model_match(self, name: str, target_model: str) -> bool:
        """Check if shoe name matches target model using regex patterns"""
        import re

        name_lower = name.lower()
        target_lower = target_model.lower()

        # Direct substring match first (fast path)
        if target_lower in name_lower:
            return True

        # Define regex patterns for common model types
        patterns = {
            "kobe": r"kobe\s+(v|vi|viii|ix|xi|5|6|8|9|10|11)(?:\s+protro)?",
            "jordan": r"(?:air\s+)?jordan\s+(\d+)",
            "lebron": r"lebron\s+(\d+)",
            "yeezy": r"yeezy\s+(?:boost\s+)?(\d+)",
            "air_max": r"air\s+max\s+(\d+)",
            "dunk": r"dunk\s+(low|high|sb)",
            "generic_numbered": r"(\w+)\s+(\d+)",
        }

        # Extract model info from both strings
        target_match = self._extract_model_info(target_lower, patterns)
        name_match = self._extract_model_info(name_lower, patterns)

        if target_match and name_match:
            return (
                target_match["model"] == name_match["model"]
                and target_match["number"] == name_match["number"]
            )

        # Fallback to partial matching for non-numbered models
        target_parts = target_lower.split()
        return all(part in name_lower for part in target_parts if len(part) > 2)

    def _extract_model_info(self, text: str, patterns: dict) -> Optional[dict]:
        """Extract model name and number using regex"""
        import re

        for model_type, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                if model_type == "kobe":
                    number = self._normalize_kobe_number(match.group(1))
                    return {"model": "kobe", "number": number}
                elif model_type in ["jordan", "lebron", "yeezy", "air_max"]:
                    return {"model": model_type, "number": match.group(1)}
                elif model_type == "dunk":
                    return {"model": "dunk", "number": match.group(1)}
                elif model_type == "generic_numbered":
                    return {"model": match.group(1), "number": match.group(2)}

        return None

    def _normalize_kobe_number(self, number_str: str) -> str:
        """Convert Roman numerals to numbers"""
        roman_to_num = {"v": "5", "vi": "6", "viii": "8", "ix": "9", "xi": "11"}
        return roman_to_num.get(number_str, number_str)

    def _create_colorway_data(self, item: Dict[str, Any]) -> Optional[ColorwayData]:
        """Create ColorwayData from API response item"""

        name = item.get("name", "")
        colorway = item.get("colorway", "")
        brand = item.get("brand", "")

        # Extract model from name
        model = self._extract_model_from_name(name, brand)

        # Parse release date
        release_date = None
        if item.get("releaseDate"):
            try:
                release_date = date.fromisoformat(item["releaseDate"])
            except (ValueError, TypeError):
                pass

        # Get image URL
        image_url = ""
        if isinstance(item.get("image"), dict):
            image_url = item["image"].get("original", "") or item["image"].get(
                "small", ""
            )
        elif isinstance(item.get("image"), str):
            image_url = item["image"]

        # Get retail price
        retail_price = None
        if item.get("retailPrice"):
            try:
                retail_price = float(item["retailPrice"])
            except (ValueError, TypeError):
                pass

        # Get StockX link
        stockx_link = ""
        if isinstance(item.get("links"), dict):
            stockx_link = item["links"].get("stockX", "")

        return ColorwayData(
            name=name,
            colorway=colorway or "Unknown",
            brand=brand,
            model=model,
            release_date=release_date,
            image_url=image_url,
            sku=item.get("sku", ""),
            retail_price=retail_price,
            stockx_link=stockx_link,
        )

    def _extract_model_from_name(self, name: str, brand: str) -> str:
        """Extract model name from full shoe name"""
        # Remove brand from name for cleaner model extraction
        name_without_brand = name
        if brand and brand.lower() in name.lower():
            name_without_brand = name.replace(brand, "").strip()

        # Split into parts
        parts = name_without_brand.split()

        if len(parts) >= 2:
            # For most shoes, first 2-3 parts are the model
            model_parts = parts[:3]

            # Handle common patterns like "Air Jordan 1" or "Kobe 5 Protro"
            model = " ".join(model_parts).strip()

            # Clean up common artifacts
            model = model.replace("  ", " ").strip()

            return model

        return name_without_brand or name  # Fallback to cleaned name or original

    async def match_colorway_by_vision(
        self, shoe_image_url: str, colorway_options: List[ColorwayData]
    ) -> Optional[ColorwayData]:
        """
        Use vision AI to match shoe image against colorway options

        Args:
            shoe_image_url: URL of the shoe image to analyze
            colorway_options: List of possible colorways to match against

        Returns:
            Best matching ColorwayData object or None if no good match
        """
        if not colorway_options:
            logger.debug("No colorway options provided for vision matching")
            return None

        try:
            # Import OpenAI here to avoid dependency issues if not available
            from openai import OpenAI

            client = OpenAI()

            # Build prompt with shoe options (use names, not just colorways)
            limited_options = colorway_options[
                :25
            ]  # Increased to top 25 for better matching
            shoe_names = [f"{i+1}. {c.name}" for i, c in enumerate(limited_options)]
            options_text = "\n".join(shoe_names)

            prompt = f"""
            Analyze this sneaker image and match it to the most similar shoe from the numbered list below.
            Pay close attention to:
            - Color scheme and color placement
            - Material textures (leather, mesh, suede, etc.)
            - Design elements (logos, patterns, overlays)
            - Overall silhouette and shape
            - Unique colorway-specific details

            Available shoes to match against:
            {options_text}

            Return only the number (1-{len(limited_options)}) of the shoe that best matches the image based on visual appearance, or "0" if none are visually similar enough.
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": shoe_image_url}},
                        ],
                    }
                ],
                max_tokens=50,
                temperature=0,
            )

            result = response.choices[0].message.content.strip()

            # Parse the number and return the corresponding ColorwayData object
            try:
                choice_num = int(result)
                if 1 <= choice_num <= len(limited_options):
                    matched_shoe = limited_options[choice_num - 1]
                    logger.info(f"Vision API matched shoe: {matched_shoe.name}")
                    return matched_shoe
                elif choice_num == 0:
                    logger.info("Vision API found no good match")
                    return None
                else:
                    logger.warning(f"Vision API returned invalid number: {result}")
                    return None
            except ValueError:
                logger.warning(f"Vision API returned non-numeric result: {result}")
                return None

        except Exception as e:
            logger.error(f"Error in vision colorway matching: {e}")
            return None
