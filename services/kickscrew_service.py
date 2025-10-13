"""
KicksCrew Service
Web scraping service for extracting shoe release dates and prices from KicksCrew.com
Rebuilt from historical implementation with enhancements for smart colorway integration
"""

import logging
import asyncio
import urllib.parse
from datetime import date, datetime
from typing import Optional
from dataclasses import dataclass
from utils.branded_types import KicksCrewUrl, SearchUrl, Price
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class KicksCrewShoeData:
    """Shoe data extracted from KicksCrew"""

    release_date: Optional[date]
    retail_price: Optional[Price]
    kickscrew_url: KicksCrewUrl
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
        self.browser = await self.playwright.chromium.launch(headless=True)
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
                logger.warning(
                    f"Failed to fetch KixStats shoe page: {kixstats_shoe_url}"
                )
                return None

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            # Find KicksCrew link in store boxes
            store_boxes = soup.find_all("div", class_="store-box")
            for box in store_boxes:
                kickscrew_links = box.find_all(
                    "a", href=lambda href: href and "kickscrew" in href
                )
                if kickscrew_links:
                    kickscrew_url = kickscrew_links[0]["href"]
                    logger.info(f"Found KicksCrew URL: {kickscrew_url}")
                    return kickscrew_url

            logger.debug(f"No KicksCrew link found in {kixstats_shoe_url}")
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
            await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})

            logger.info(f"Fetching KicksCrew page: {kickscrew_url}")
            await page.goto(kickscrew_url, timeout=self.request_timeout)

            # Wait for page content to load
            logger.info("Waiting 10 seconds for page to load...")
            await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Failed to navigate to KicksCrew page: {e}")
            raise

    async def _extract_price_with_playwright(self, page) -> Optional[Price]:
        """Extract price using multiple Playwright selector strategies"""
        price_selectors = self._get_price_selectors()

        for selector in price_selectors:
            price = await self._try_price_selector(page, selector)
            if price:
                return price

        logger.debug("No price found with any selector")
        return None

    def _get_price_selectors(self) -> list[str]:
        """Get list of price selectors in priority order"""
        return [
            "h1 ~ * span:has-text('$')",  # Span with $ near the title
            ".price span:has-text('$')",  # Price class with span
            "[data-price] span:has-text('$')",  # Data price attribute
            "span:has-text('$'):near(h1)",  # Span with $ near h1
            "span:has-text('$')",  # Any span with $
        ]

    async def _try_price_selector(self, page, selector: str) -> Optional[Price]:
        """Try a single price selector and return price if found"""
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                price = await self._extract_price_from_element(element)
                if price:
                    logger.info(f"Found price using selector '{selector}': {price}")
                    return price
        except Exception as e:
            logger.debug(f"Selector '{selector}' failed: {e}")

        return None

    async def _extract_price_from_element(self, element) -> Optional[Price]:
        """Extract price from a single page element"""
        try:
            text = await element.text_content()
            if text and "$" in text:
                return self._extract_price_from_text(text.strip())
        except Exception as e:
            logger.debug(f"Failed to extract text from element: {e}")

        return None

    def _extract_price_from_text(self, text: str) -> Optional[Price]:
        """Extract price from text using regex"""
        import re

        # Look for patterns like $123.45, $123, etc.
        price_patterns = [
            r"\$(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)",  # $123.45, $1,234.56
            r"USD\s*(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)",  # USD 123.45
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                price_value = match.group(1).replace(",", "")
                return Price(f"${price_value}")

        return None

    def _parse_kickscrew_page(
        self, html: str, kickscrew_url: str
    ) -> Optional[KicksCrewShoeData]:
        """Parse KicksCrew page HTML for product information"""

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Extract product name
            product_name = self._extract_product_name(soup)

            # Extract release date
            release_date = self._extract_release_date(soup)

            # Note: price will be overridden by Playwright extraction
            return KicksCrewShoeData(
                release_date=release_date,
                retail_price=None,  # Will be set by Playwright
                kickscrew_url=KicksCrewUrl(kickscrew_url),
                product_name=product_name,
            )

        except Exception as e:
            logger.error(f"Error parsing KicksCrew page: {e}")
            return None

    def _extract_product_name(self, soup: BeautifulSoup) -> str:
        """Extract product name from page"""
        selectors = ["h1", ".product-title", ".title", "title"]

        for selector in selectors:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                return element.get_text(strip=True)

        return ""

    def _extract_release_date(self, soup: BeautifulSoup) -> Optional[date]:
        """Extract release date from page"""
        import re

        # Look for release date patterns in text
        text_content = soup.get_text()
        date_patterns = [
            r"Release Date:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            r"Released:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            r"(\d{4}-\d{2}-\d{2})",  # ISO format
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    # Try to parse the date
                    if "/" in date_str:
                        parsed_date = datetime.strptime(date_str, "%m/%d/%Y").date()
                    elif "-" in date_str and len(date_str) == 10:
                        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    else:
                        continue

                    return parsed_date
                except ValueError:
                    continue

        return None

    def build_search_url(self, brand: str, model: str, colorway: str = "") -> SearchUrl:
        """
        Build KicksCrew search URL using shoe details
        Enhanced with smart colorway integration
        """
        search_terms = [brand, model]
        if colorway:
            search_terms.append(colorway)

        query = " ".join(search_terms)
        encoded_query = urllib.parse.quote(query)
        return SearchUrl(f"{self.base_url}/search?q={encoded_query}")

    def build_goat_search_url(self, shoe_name: str) -> SearchUrl:
        """Build GOAT search URL from shoe name"""
        query = urllib.parse.quote(shoe_name)
        return SearchUrl(f"https://www.goat.com/search?query={query}")

    def build_stockx_search_url(self, shoe_name: str) -> SearchUrl:
        """Build StockX search URL from shoe name"""
        query = urllib.parse.quote(shoe_name)
        return SearchUrl(f"https://stockx.com/search?s={query}")
