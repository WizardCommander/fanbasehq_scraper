"""
Image Service for downloading and encoding images to base64
Follows existing async patterns and error handling in the codebase
"""

import asyncio
import base64
import logging
import aiohttp
from config.settings import TWITTER_API_TIMEOUT

logger = logging.getLogger(__name__)


class ImageService:
    """Service for downloading images and converting to base64 data URI format"""

    def __init__(self, timeout: int = TWITTER_API_TIMEOUT):
        self.timeout = timeout
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def download_and_encode_image(self, url: str) -> str:
        """
        Download image from URL and return as base64 data URI

        Args:
            url: Image URL (typically pbs.twimg.com URLs from Twitter)

        Returns:
            Base64 data URI string in format: "data:image/png;base64,{encoded_data}"
            Returns empty string on any error (graceful fallback)
        """
        if not url or not url.strip():
            return ""

        try:
            # Use existing session or create temporary one
            if self.session:
                return await self._download_with_session(self.session, url)
            else:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as session:
                    return await self._download_with_session(session, url)

        except Exception as e:
            logger.debug(f"Failed to download and encode image {url}: {e}")
            return ""

    async def _download_with_session(
        self, session: aiohttp.ClientSession, url: str
    ) -> str:
        """Download image using provided session"""
        try:
            # Add small delay to be respectful to image servers
            await asyncio.sleep(1)

            # Set realistic headers to avoid blocking
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            logger.debug(f"Downloading image: {url}")

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.debug(f"Image download failed: {response.status} for {url}")
                    return ""

                # Read image data
                image_data = await response.read()
                if not image_data:
                    logger.debug(f"No image data received for {url}")
                    return ""

                # Detect image format from content type or URL
                content_type = response.headers.get("content-type", "").lower()
                image_format = self._detect_image_format(url, content_type)

                # Encode to base64
                image_base64 = base64.b64encode(image_data).decode("utf-8")

                # Return data URI format
                data_uri = f"data:image/{image_format};base64,{image_base64}"

                logger.info(
                    f"Successfully encoded image {url} ({len(image_data)} bytes)"
                )
                return data_uri

        except asyncio.TimeoutError:
            logger.debug(f"Timeout downloading image: {url}")
            return ""
        except Exception as e:
            logger.debug(f"Error downloading image {url}: {e}")
            return ""

    def _detect_image_format(self, url: str, content_type: str) -> str:
        """
        Detect image format from URL or content type

        Args:
            url: Image URL
            content_type: HTTP content-type header

        Returns:
            Image format string ("png", "jpeg", "jpg", "gif", etc.)
        """
        # Check content type first
        if "image/" in content_type:
            format_part = content_type.split("image/")[1].split(";")[0]
            if format_part in ["png", "jpeg", "jpg", "gif", "webp"]:
                return format_part

        # Fall back to URL extension
        url_lower = url.lower()
        if url_lower.endswith(".png"):
            return "png"
        elif url_lower.endswith((".jpg", ".jpeg")):
            return "jpeg"
        elif url_lower.endswith(".gif"):
            return "gif"
        elif url_lower.endswith(".webp"):
            return "webp"

        # Default to PNG for Twitter images (most common)
        return "png"


# Convenience function for single image downloads
async def download_and_encode_image(url: str) -> str:
    """
    Convenience function to download and encode a single image

    Args:
        url: Image URL to download

    Returns:
        Base64 data URI string or empty string on error
    """
    async with ImageService() as service:
        return await service.download_and_encode_image(url)


# Convenience function for shoe images with array handling and game photo priority
async def download_and_encode_shoe_image(image_url: str) -> str:
    """
    Download and encode shoe image with support for JSON arrays and game photo priority

    Args:
        image_url: Single image URL or JSON array string containing multiple URLs

    Returns:
        Base64 data URI string or empty string on error

    Notes:
        - For JSON arrays, prioritizes second image (game photo) over first (product shot)
        - Falls back gracefully to single image URLs
        - Returns empty string on any parsing or download errors
    """
    if not image_url or not image_url.strip():
        return ""

    try:
        # Parse image URLs from JSON array if needed
        image_urls = []
        if image_url.startswith("[") and image_url.endswith("]"):
            import json

            image_urls = json.loads(image_url)
        else:
            image_urls = [image_url]

        if not image_urls:
            return ""

        # Select best image with game photo priority
        selected_url = _select_best_shoe_image(image_urls)

        if not selected_url:
            return ""

        # Download and encode the selected image
        async with ImageService() as service:
            return await service.download_and_encode_image(selected_url)

    except Exception as e:
        logger.debug(f"Failed to process shoe image {image_url}: {e}")
        return ""


def _select_best_shoe_image(image_urls: list) -> str:
    """
    Select the best image from a list with game photo priority

    Args:
        image_urls: List of image URLs (product shot, game photo)

    Returns:
        Selected image URL or empty string if none available
    """
    if not image_urls:
        return ""

    # Priority 1: Game photo (second image) if available
    if len(image_urls) >= 2:
        game_photo_url = image_urls[1]
        if _is_game_photo(game_photo_url):
            return game_photo_url

    # Priority 2: Product shot (first image) or any available image
    return image_urls[0] if image_urls else ""


def _is_game_photo(image_url: str) -> bool:
    """Check if image URL is a game photo based on URL pattern"""
    return "/img/games/" in image_url
