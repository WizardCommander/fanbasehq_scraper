"""
KicksCrew Service
Web scraping service for extracting shoe release dates and prices from KicksCrew.com
"""

import logging
import asyncio
import json
import urllib.parse
from datetime import date, datetime
from typing import Optional
from dataclasses import dataclass
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class KicksCrewShoeData:
    """Shoe data extracted from KicksCrew"""

    release_date: Optional[date]
    retail_price: Optional[str]
    kickscrew_url: str
    product_name: str = ""


class KicksCrewService:
    """Service for extracting shoe data from KicksCrew.com using Playwright"""

    def __init__(self, request_timeout: int = 30):
        self.base_url = "https://www.kickscrew.com"
        self.playwright = None
        self.browser = None
        self.request_timeout = request_timeout * 1000  # Playwright uses milliseconds

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_shoe_details_from_kixstats_url(
        self, kixstats_shoe_url: str
    ) -> Optional[KicksCrewShoeData]:
        """
        Get shoe details by first extracting KicksCrew URL from KixStats shoe page

        Args:
            kixstats_shoe_url: URL to KixStats shoe detail page

        Returns:
            KicksCrewShoeData object or None if not found
        """
        try:
            # First extract KicksCrew URL from KixStats page
            kickscrew_url = await self._extract_kickscrew_url_from_kixstats(
                kixstats_shoe_url
            )
            if not kickscrew_url:
                logger.debug(f"No KicksCrew URL found for {kixstats_shoe_url}")
                return None

            # Then get shoe details from KicksCrew
            return await self.get_shoe_details_from_kickscrew_url(kickscrew_url)

        except Exception as e:
            logger.error(
                f"Error getting shoe details from KixStats URL {kixstats_shoe_url}: {e}"
            )
            return None

    async def get_shoe_details_from_kickscrew_url(
        self, kickscrew_url: str
    ) -> Optional[KicksCrewShoeData]:
        """
        Get shoe details directly from KicksCrew URL

        Args:
            kickscrew_url: Direct URL to KicksCrew product page

        Returns:
            KicksCrewShoeData object or None if not found
        """
        try:
            if not self.browser:
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    try:
                        return await self._scrape_kickscrew_with_browser(
                            browser, kickscrew_url
                        )
                    finally:
                        await browser.close()
            else:
                return await self._scrape_kickscrew_with_browser(
                    self.browser, kickscrew_url
                )

        except Exception as e:
            logger.error(
                f"Error getting shoe details from KicksCrew URL {kickscrew_url}: {e}"
            )
            return None

    async def _extract_kickscrew_url_from_kixstats(
        self, kixstats_shoe_url: str
    ) -> Optional[str]:
        """Extract KicksCrew URL from KixStats shoe detail page"""

        try:
            # Use aiohttp for KixStats - it works fine and is much faster
            async with aiohttp.ClientSession() as session:
                return await self._extract_with_session(session, kixstats_shoe_url)

        except Exception as e:
            logger.error(
                f"Error extracting KicksCrew URL from {kixstats_shoe_url}: {e}"
            )
            return None

    async def _extract_with_session(
        self, session: aiohttp.ClientSession, kixstats_shoe_url: str
    ) -> Optional[str]:
        """Extract KicksCrew URL from KixStats using aiohttp (fast and works)"""

        # Small delay to be respectful
        await asyncio.sleep(1)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        }

        async with session.get(kixstats_shoe_url, headers=headers) as response:
            if response.status != 200:
                logger.warning(f"Failed to fetch KixStats shoe page: {kixstats_shoe_url}")
                return None

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            # Find KicksCrew link in store boxes
            store_boxes = soup.find_all("div", class_="store-box")
            for box in store_boxes:
                kickscrew_links = box.find_all(
                    "a", href=lambda href: href and "kickscrew" in href
                )
                for link in kickscrew_links:
                    affiliate_url = link.get("href", "")
                    if affiliate_url:
                        # Decode the affiliate URL to get clean KicksCrew URL
                        clean_url = self._decode_kickscrew_affiliate_url(affiliate_url)
                        if clean_url:
                            logger.debug(f"Found KicksCrew URL: {clean_url}")
                            return clean_url

            logger.debug(f"No KicksCrew URL found for shoe: {kixstats_shoe_url}")
            return None


    async def _scrape_kickscrew_with_browser(
        self, browser, kickscrew_url: str
    ) -> Optional[KicksCrewShoeData]:
        """Scrape KicksCrew data using provided browser"""

        # Add respectful delay to avoid being blocked
        await asyncio.sleep(3)

        page = await browser.new_page()
        try:
            await self._setup_page_and_navigate(page, kickscrew_url)
            retail_price = await self._extract_price_with_playwright(page)
            html = await page.content()
            shoe_data = self._parse_kickscrew_page(html, kickscrew_url)

            # Override price with Playwright-extracted price if found
            if retail_price and shoe_data:
                shoe_data.retail_price = retail_price

            return shoe_data

        except Exception as e:
            logger.warning(f"Failed to fetch KicksCrew page: {kickscrew_url} - {e}")
            return None
        finally:
            await page.close()

    async def _setup_page_and_navigate(self, page, kickscrew_url: str) -> None:
        """Setup page headers and navigate to URL"""
        try:
            # Set realistic headers
            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9"
            })

            logger.info(f"Fetching KicksCrew page: {kickscrew_url}")
            await page.goto(kickscrew_url, timeout=self.request_timeout)

            # Wait for page content to load
            logger.info("Waiting 10 seconds for page to load...")
            await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Failed to navigate to KicksCrew page: {e}")
            raise

    async def _extract_price_with_playwright(self, page) -> Optional[str]:
        """Extract price using multiple Playwright selector strategies"""
        price_selectors = [
            "h1 ~ * span:has-text('$')",  # Span with $ near the title
            ".price span:has-text('$')",  # Price class with span
            "[class*='price'] span:has-text('$')",  # Any price-related class
            "[data-price] span:has-text('$')",  # Data-price attribute
            "span:has-text('$')",  # Last resort - any span with $
        ]

        for selector in price_selectors:
            try:
                price_element = await page.query_selector(selector)
                if price_element:
                    text_content = await price_element.text_content()
                    if text_content and text_content.strip().startswith("$"):
                        retail_price = text_content.strip()
                        logger.info(f"Extracted price using selector '{selector}': {retail_price}")
                        return retail_price

            except TimeoutError as e:
                logger.debug(f"Timeout with selector '{selector}': {e}")
                continue
            except Exception as e:
                logger.debug(f"Error with selector '{selector}': {e}")
                continue

        logger.debug("No price found with any selector strategy")
        return None

    def _parse_kickscrew_page(
        self, html: str, kickscrew_url: str
    ) -> Optional[KicksCrewShoeData]:
        """Parse KicksCrew page for shoe metadata (release date and product name)"""

        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")

        release_date = None
        product_name = ""

        for script in scripts:
            try:
                parsed_data = self._parse_json_ld_script(script)
                if parsed_data:
                    release_date = parsed_data.get('release_date') or release_date
                    product_name = parsed_data.get('product_name') or product_name

            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Error parsing JSON-LD script: {e}")
                continue

        # Create result if we found any useful data
        if release_date or product_name:
            return KicksCrewShoeData(
                release_date=release_date,
                retail_price=None,  # Price handled by Playwright
                kickscrew_url=kickscrew_url,
                product_name=product_name,
            )

        logger.debug(f"No structured data found in KicksCrew page: {kickscrew_url}")
        return None

    def _parse_json_ld_script(self, script) -> Optional[dict]:
        """Parse individual JSON-LD script for product data"""
        try:
            data = json.loads(script.string)
            data_items = self._normalize_json_ld_structure(data)

            for item in data_items:
                if self._is_product_item(item):
                    return self._extract_product_metadata(item)

        except json.JSONDecodeError:
            return None

        return None

    def _normalize_json_ld_structure(self, data) -> list:
        """Normalize JSON-LD data structure to a list of items"""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            if "@graph" in data:
                return data["@graph"]
            else:
                return [data]
        return []

    def _is_product_item(self, item: dict) -> bool:
        """Check if JSON-LD item represents a product"""
        return isinstance(item, dict) and item.get("@type") in ["ProductGroup", "Product"]

    def _extract_product_metadata(self, item: dict) -> dict:
        """Extract release date and product name from product JSON-LD item"""
        result = {}

        # Extract release date
        if "releaseDate" in item:
            try:
                result['release_date'] = datetime.strptime(
                    item["releaseDate"], "%Y-%m-%d"
                ).date()
            except ValueError:
                logger.warning(f"Invalid release date format: {item['releaseDate']}")

        # Extract product name
        if "name" in item:
            result['product_name'] = item["name"]

        return result

    def _decode_kickscrew_affiliate_url(self, affiliate_url: str) -> Optional[str]:
        """Decode KicksCrew affiliate URL to get clean product URL"""

        try:
            # Parse the affiliate URL
            parsed = urllib.parse.urlparse(affiliate_url)
            query_params = urllib.parse.parse_qs(parsed.query)

            # Look for the 'u' parameter which contains the encoded clean URL
            if "u" in query_params:
                encoded_url = query_params["u"][0]
                # URL decode the clean KicksCrew URL
                clean_url = urllib.parse.unquote(encoded_url)
                if "kickscrew.com" in clean_url:
                    return clean_url

            # If we can't decode, return the original URL if it's already a KicksCrew URL
            if "kickscrew.com" in affiliate_url:
                return affiliate_url

            return None

        except Exception as e:
            logger.error(f"Error decoding affiliate URL {affiliate_url}: {e}")
            # If we can't decode but it's a KicksCrew URL, return it
            if "kickscrew.com" in affiliate_url:
                return affiliate_url
            return None
