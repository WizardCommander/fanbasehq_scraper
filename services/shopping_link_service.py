"""
Shopping Link Service
Uses Oxylabs Google Lens to find product links via reverse image search
"""

import logging
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProductLink:
    """Product link found via reverse image search"""

    product_name: str
    shop_url: str
    price: Optional[str] = None  # "$XX.XX" or price range
    retailer: str = "Unknown"  # Store name
    similarity_score: float = 0.0  # How well it matches the image (0.0-1.0)
    is_exact_match: bool = False  # True if exact product found
    is_affiliate_eligible: bool = False  # Potential for affiliate links


class ShoppingLinkService:
    """Service for finding product shop links using Oxylabs Google Lens"""

    def __init__(self, username: str, password: str, rate_limit_delay: float = 1.0):
        """
        Initialize shopping link service

        Args:
            username: Oxylabs API username
            password: Oxylabs API password
            rate_limit_delay: Seconds to wait between API calls (default: 1.0)
        """
        self.username = username
        self.password = password
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    async def __aenter__(self):
        """Async context manager entry"""
        # Initialize Oxylabs AsyncClient when entering context
        from oxylabs import AsyncClient

        self.client = AsyncClient(self.username, self.password)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Oxylabs client doesn't require explicit cleanup
        self.client = None

    async def find_product_links(
        self,
        image_url: str,
        item_description: Optional[str] = None,
        max_results: int = 5,
    ) -> List[ProductLink]:
        """
        Find product shop links for an image using Google Lens

        Args:
            image_url: URL of the product image
            item_description: Optional text description (not used by Oxylabs Lens API)
            max_results: Maximum number of product links to return

        Returns:
            List of ProductLink objects sorted by similarity score
        """
        try:
            logger.info(f"Finding product links for image: {image_url}")

            # Rate limiting
            await self._rate_limit()

            # Call Oxylabs Google Lens
            results = await self._call_oxylabs_google_lens(image_url)

            if not results:
                logger.warning(f"No results from Oxylabs for image: {image_url}")
                return []

            # Parse results into ProductLink objects
            product_links = self._parse_oxylabs_results(results, max_results)

            logger.info(
                f"Found {len(product_links)} product links for image: {image_url}"
            )

            return product_links

        except Exception as e:
            logger.error(f"Error finding product links for {image_url}: {e}")
            return []

    async def batch_find_links(
        self,
        items: List[
            tuple[str, str, Optional[str]]
        ],  # (item_id, image_url, description)
        max_concurrent: int = 2,
    ) -> Dict[str, List[ProductLink]]:
        """
        Find product links for multiple items concurrently

        Args:
            items: List of (item_id, image_url, description) tuples
            max_concurrent: Maximum concurrent API calls (default: 2 for rate limits)

        Returns:
            Dictionary mapping item_id to list of ProductLink objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def find_with_semaphore(item_id: str, url: str, desc: Optional[str]):
            async with semaphore:
                links = await self.find_product_links(url, desc)
                return item_id, links

        tasks = [
            find_with_semaphore(item_id, url, desc) for item_id, url, desc in items
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dictionary
        result_dict = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Batch find error: {result}")
                continue

            item_id, links = result
            result_dict[item_id] = links

        return result_dict

    async def _rate_limit(self):
        """Enforce rate limiting between API calls"""
        import time

        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self.rate_limit_delay:
            wait_time = self.rate_limit_delay - time_since_last
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)

        self._last_request_time = time.time()

    async def _call_oxylabs_google_lens(self, image_url: str) -> Optional[Dict]:
        """
        Call Oxylabs Google Lens API

        Documentation: https://developers.oxylabs.io/

        Args:
            image_url: Image URL to search

        Returns:
            API response dictionary or None on error
        """
        try:
            from oxylabs import AsyncClient

            # Create client if not in context manager
            if not hasattr(self, "client") or self.client is None:
                client = AsyncClient(self.username, self.password)
            else:
                client = self.client

            # Call Google Lens API
            # Note: Oxylabs returns a response object, not a dict directly
            response = await client.google.scrape_lens(
                image_url,
                parse=True,  # Get structured parsed data
                timeout=30,  # 30 second timeout
            )

            # Extract results from response
            # Oxylabs response has .results attribute containing list of result objects
            if not response or not response.results:
                logger.warning(f"No results from Oxylabs for image: {image_url}")
                return None

            # Get the first result's content (parsed data)
            if len(response.results) > 0:
                result = response.results[0]
                if hasattr(result, "content"):
                    # Oxylabs content structure: { "results": {...}, "parse_status_code": ... }
                    # Extract the inner "results" dict for parsing
                    content = result.content
                    if isinstance(content, dict) and "results" in content:
                        return content["results"]
                    # Fallback: return content as-is for backward compatibility with tests
                    return content
                else:
                    logger.warning("Oxylabs response missing content field, using raw")
                    return result.raw if hasattr(result, "raw") else None

            return None

        except Exception as e:
            logger.error(f"Error calling Oxylabs Google Lens: {e}")
            return None

    def _parse_oxylabs_results(
        self, results: Dict, max_results: int
    ) -> List[ProductLink]:
        """
        Parse Oxylabs Google Lens response into ProductLink objects

        Handles both actual Oxylabs format and test mock format for scalability:
        - Oxylabs format: results.organic[] and results.exact_match[]
        - Test mock format: results.shopping_results[] and results.visual_matches[]

        Args:
            results: Oxylabs response dictionary
            max_results: Maximum results to return

        Returns:
            List of ProductLink objects
        """
        product_links = []

        try:
            # Handle actual Oxylabs Google Lens response structure
            # Oxylabs returns: { "organic": [...], "exact_match": [...] }
            exact_matches = results.get("exact_match", [])
            organic_results = results.get("organic", [])

            # Also handle test mock format for backward compatibility
            # Test mocks use: { "shopping_results": [...], "visual_matches": [...] }
            shopping_results = results.get("shopping_results", [])
            visual_matches = results.get("visual_matches", [])

            # Process high-confidence results first (exact_match or shopping_results)
            high_confidence = exact_matches or shopping_results
            for result in high_confidence[:max_results]:
                product_link = self._parse_shopping_result(result)
                if product_link:
                    product_links.append(product_link)

            # If we need more results, add organic/visual matches
            remaining = max_results - len(product_links)
            if remaining > 0:
                lower_confidence = organic_results or visual_matches
                for result in lower_confidence[:remaining]:
                    product_link = self._parse_visual_match(result)
                    if product_link:
                        product_links.append(product_link)

            # Sort by similarity score (descending)
            product_links.sort(key=lambda x: x.similarity_score, reverse=True)

            return product_links[:max_results]

        except Exception as e:
            logger.error(f"Error parsing Oxylabs results: {e}")
            return []

    def _parse_shopping_result(self, result: Dict) -> Optional[ProductLink]:
        """Parse a shopping result from Oxylabs"""
        try:
            return ProductLink(
                product_name=result.get("title", "Unknown Product"),
                shop_url=result.get("link", ""),
                price=result.get("price"),
                retailer=result.get("source", "Unknown"),
                similarity_score=0.9,  # Shopping results are high confidence
                is_exact_match=True,
                is_affiliate_eligible=self._check_affiliate_eligible(
                    result.get("source", "")
                ),
            )
        except Exception as e:
            logger.error(f"Error parsing shopping result: {e}")
            return None

    def _parse_visual_match(self, result: Dict) -> Optional[ProductLink]:
        """
        Parse a visual match from Oxylabs

        Handles both Oxylabs format (url, domain) and test mock format (link)
        """
        try:
            # Handle both Oxylabs 'url' field and test mock 'link' field
            shop_url = result.get("link") or result.get("url", "")

            # Extract retailer from domain if available, otherwise from URL
            retailer = result.get("domain")
            if not retailer and shop_url:
                retailer = self._extract_retailer_from_url(shop_url)

            # Visual matches/organic results don't always have prices
            return ProductLink(
                product_name=result.get("title", "Unknown Product"),
                shop_url=shop_url,
                price=result.get("price"),  # May be None
                retailer=retailer or "Unknown",
                similarity_score=0.7,  # Visual matches are medium confidence
                is_exact_match=False,
                is_affiliate_eligible=False,  # Unknown for visual matches
            )
        except Exception as e:
            logger.error(f"Error parsing visual match: {e}")
            return None

    def _extract_retailer_from_url(self, url: str) -> str:
        """Extract retailer name from URL"""
        try:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc
            # Remove www. and .com/etc
            retailer = domain.replace("www.", "").split(".")[0]
            return retailer.title()
        except Exception:
            return "Unknown"

    def _check_affiliate_eligible(self, retailer: str) -> bool:
        """
        Check if retailer is commonly affiliate-program eligible

        Args:
            retailer: Retailer name

        Returns:
            True if likely affiliate-eligible
        """
        # Common retailers with affiliate programs
        affiliate_retailers = {
            "amazon",
            "nike",
            "adidas",
            "nordstrom",
            "zappos",
            "saks",
            "bloomingdales",
            "macys",
            "revolve",
            "shopbop",
            "farfetch",
            "ssense",
            "net-a-porter",
            "stockx",
            "goat",
            "stadium goods",
        }

        retailer_lower = retailer.lower()
        return any(name in retailer_lower for name in affiliate_retailers)

    def filter_by_price_range(
        self,
        product_links: List[ProductLink],
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> List[ProductLink]:
        """
        Filter product links by price range

        Args:
            product_links: List of ProductLink objects
            min_price: Minimum price (inclusive)
            max_price: Maximum price (inclusive)

        Returns:
            Filtered list of product links
        """
        if not min_price and not max_price:
            return product_links

        filtered = []
        for link in product_links:
            if not link.price:
                continue

            # Extract numeric price from string (e.g., "$199.99" -> 199.99)
            try:
                price_str = link.price.replace("$", "").replace(",", "")
                price = float(price_str.split("-")[0].strip())  # Handle ranges

                if min_price and price < min_price:
                    continue
                if max_price and price > max_price:
                    continue

                filtered.append(link)

            except ValueError:
                continue  # Skip if price parsing fails

        return filtered
