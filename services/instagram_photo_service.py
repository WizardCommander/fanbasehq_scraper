"""
Instagram Photo Service
Fetches tunnel fit photos from Instagram using Scrape Creators API
"""

import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import hashlib
import re

logger = logging.getLogger(__name__)


@dataclass
class InstagramPost:
    """Instagram post data"""

    post_id: str
    image_url: str
    caption: str
    posted_at: datetime
    likes: int
    comments: int
    instagram_handle: str
    is_tunnel_fit_candidate: bool = False
    confidence_score: float = 0.0
    post_url: str = ""


class InstagramPhotoService:
    """Service for fetching tunnel fit photos from Instagram via Scrape Creators API"""

    def __init__(self, api_key: str, cache_hours: int = 6):
        """
        Initialize Instagram photo service

        Args:
            api_key: Scrape Creators API key
            cache_hours: Hours to cache Instagram data
        """
        self.api_key = api_key
        self.cache_hours = cache_hours
        self.base_url = "https://api.scrapecreators.com/v2/instagram/user/posts"
        self.cache: Dict[str, tuple[datetime, List[InstagramPost]]] = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def get_recent_posts(
        self, instagram_handle: str, limit: int = 50, since_days: int = 30
    ) -> List[InstagramPost]:
        """
        Get recent Instagram posts from a player's account

        Args:
            instagram_handle: Instagram handle (e.g., "caitlinclark22")
            limit: Maximum number of posts to fetch
            since_days: Only fetch posts from last N days

        Returns:
            List of InstagramPost objects
        """
        # Check cache first
        cache_key = f"{instagram_handle}_{limit}_{since_days}"
        if cache_key in self.cache:
            cached_time, cached_posts = self.cache[cache_key]
            if datetime.now() - cached_time < timedelta(hours=self.cache_hours):
                logger.info(
                    f"Using cached Instagram data for @{instagram_handle} "
                    f"({len(cached_posts)} posts)"
                )
                return cached_posts

        try:
            logger.info(f"Fetching Instagram posts for @{instagram_handle}...")

            # Clean handle (remove @ if present)
            handle_clean = instagram_handle.lstrip("@")

            # Fetch from Scrape Creators API
            posts = await self._fetch_from_scrape_creators(
                handle_clean, limit, since_days
            )

            # Cache the results
            self.cache[cache_key] = (datetime.now(), posts)

            logger.info(f"Fetched {len(posts)} Instagram posts for @{instagram_handle}")
            return posts

        except Exception as e:
            logger.error(f"Error fetching Instagram posts for @{instagram_handle}: {e}")
            return []

    async def _fetch_from_scrape_creators(
        self, handle: str, limit: int, since_days: int
    ) -> List[InstagramPost]:
        """
        Fetch posts from Scrape Creators API

        Args:
            handle: Instagram handle without @
            limit: Maximum posts to fetch
            since_days: Only posts from last N days

        Returns:
            List of InstagramPost objects
        """
        if not self.session:
            async with aiohttp.ClientSession() as session:
                return await self._make_api_request(session, handle, limit, since_days)
        else:
            return await self._make_api_request(self.session, handle, limit, since_days)

    async def _make_api_request(
        self, session: aiohttp.ClientSession, handle: str, limit: int, since_days: int
    ) -> List[InstagramPost]:
        """Make the actual Scrape Creators API request"""

        # Calculate date threshold
        date_threshold = datetime.now(timezone.utc) - timedelta(days=since_days)

        headers = {"x-api-key": self.api_key}

        all_posts = []
        cursor = None
        pages_fetched = 0
        max_pages = 5  # Reasonable limit to prevent infinite loops

        try:
            while len(all_posts) < limit and pages_fetched < max_pages:
                # Build request params
                params = {"handle": handle, "limit": min(50, limit - len(all_posts))}

                if cursor:
                    params["after"] = cursor

                logger.info(
                    f"Fetching page {pages_fetched + 1} for @{handle} (cursor: {cursor[:20] if cursor else 'None'}...)"
                )

                async with session.get(
                    self.base_url, headers=headers, params=params, timeout=30
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"Scrape Creators API error: HTTP {response.status} - {error_text}"
                        )
                        break

                    data = await response.json()

                    # Extract posts from response
                    items = data.get("items", [])
                    if not items:
                        logger.info("No more posts available")
                        break

                    logger.info(
                        f"Retrieved {len(items)} posts from page {pages_fetched + 1}"
                    )

                    # Convert and filter posts
                    for item in items:
                        post = self._convert_to_instagram_post(item, handle)
                        if post and post.posted_at >= date_threshold:
                            all_posts.append(post)

                        # Stop if we've hit the limit
                        if len(all_posts) >= limit:
                            break

                    # Check if there are more pages
                    more_available = data.get("more_available", False)
                    if not more_available:
                        logger.info("No more pages available")
                        break

                    # Get next cursor for pagination
                    cursor = data.get("next_cursor")
                    if not cursor:
                        logger.info("No next cursor available")
                        break

                    pages_fetched += 1

                    # Rate limiting - be respectful
                    await asyncio.sleep(0.5)

            logger.info(
                f"Fetched {len(all_posts)} total posts for @{handle} "
                f"across {pages_fetched} pages"
            )
            return all_posts[:limit]

        except asyncio.TimeoutError:
            logger.error("Scrape Creators API request timeout")
            return all_posts
        except Exception as e:
            logger.error(f"Error making Scrape Creators request: {e}")
            return all_posts

    def _convert_to_instagram_post(
        self, item: Dict, handle: str
    ) -> Optional[InstagramPost]:
        """Convert Scrape Creators post data to InstagramPost object"""
        try:
            # Extract post ID
            post_id = item.get("pk") or item.get("id", "")
            if not post_id:
                logger.warning("Skipping post without ID")
                return None

            # Filter out videos/reels - we only want photos
            media_type = item.get("media_type", 1)
            # Media type: 1 = photo, 2 = video, 8 = carousel
            if media_type == 2:
                logger.debug(f"Skipping video post {post_id}")
                return None

            # Extract image URL
            image_url = self._extract_image_url(item)
            if not image_url:
                logger.warning(f"Skipping post {post_id} - no image URL found")
                return None

            # Extract caption
            caption_data = item.get("caption", {})
            if isinstance(caption_data, dict):
                caption = caption_data.get("text", "")
            elif isinstance(caption_data, str):
                caption = caption_data
            else:
                caption = ""

            # Extract timestamp
            taken_at = item.get("taken_at")
            if taken_at:
                posted_at = datetime.fromtimestamp(taken_at, tz=timezone.utc)
            else:
                logger.warning(f"Post {post_id} missing timestamp, using current time")
                posted_at = datetime.now(timezone.utc)

            # Extract engagement metrics
            likes = item.get("like_count", 0)
            comments = item.get("comment_count", 0)

            # Build post URL
            code = item.get("code") or item.get("shortcode", "")
            post_url = f"https://www.instagram.com/p/{code}/" if code else ""

            return InstagramPost(
                post_id=str(post_id),
                image_url=image_url,
                caption=caption,
                posted_at=posted_at,
                likes=likes,
                comments=comments,
                instagram_handle=f"@{handle}",
                post_url=post_url,
            )

        except Exception as e:
            logger.error(f"Error converting Instagram post: {e}")
            logger.debug(
                f"Post data keys: {item.keys() if isinstance(item, dict) else 'not a dict'}"
            )
            return None

    def _extract_image_url(self, item: Dict) -> Optional[str]:
        """Extract the best quality image URL from post data"""
        # Try direct image URL fields first
        direct_fields = [
            "display_url",
            "image_url",
            "thumbnail_url",
        ]

        for field in direct_fields:
            url = item.get(field)
            if url and isinstance(url, str) and self._looks_like_image_url(url):
                return url

        # Try image_versions2.candidates (array of different resolutions)
        image_versions = item.get("image_versions2", {})
        if isinstance(image_versions, dict):
            candidates = image_versions.get("candidates", [])
            if isinstance(candidates, list) and candidates:
                # First candidate is usually highest quality
                first_candidate = candidates[0]
                if isinstance(first_candidate, dict):
                    url = first_candidate.get("url")
                    if url and isinstance(url, str):
                        return url

        # Try carousel_media for multi-image posts
        carousel_media = item.get("carousel_media", [])
        if isinstance(carousel_media, list) and carousel_media:
            first_item = carousel_media[0]
            if isinstance(first_item, dict):
                # Recursively extract from first carousel item
                return self._extract_image_url(first_item)

        # Fallback: search recursively
        return self._find_image_url_recursive(item)

    def _looks_like_image_url(self, url: str) -> bool:
        """Check if URL appears to be a direct image link"""
        if not isinstance(url, str):
            return False

        lower_url = url.lower()
        if not lower_url.startswith("http"):
            return False

        # Check for image extensions
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        if lower_url.endswith(image_exts):
            return True

        # Check for Instagram CDN indicators
        cdn_indicators = [
            "cdninstagram",
            "fbcdn",
            "scontent",
            "instagram",
        ]
        return any(indicator in lower_url for indicator in cdn_indicators)

    def _find_image_url_recursive(self, data: Any) -> Optional[str]:
        """Recursively search for a direct image URL"""
        if isinstance(data, str):
            if self._looks_like_image_url(data):
                return data
            return None

        if isinstance(data, dict):
            for value in data.values():
                result = self._find_image_url_recursive(value)
                if result:
                    return result

        if isinstance(data, list):
            for item in data:
                result = self._find_image_url_recursive(item)
                if result:
                    return result

        return None

    def filter_tunnel_fit_candidates(
        self, posts: List[InstagramPost], keywords: Optional[List[str]] = None
    ) -> List[InstagramPost]:
        """
        Filter posts that are likely tunnel fit photos

        Args:
            posts: List of InstagramPost objects
            keywords: Keywords to search for in captions (default: tunnel fit related)

        Returns:
            Filtered list with is_tunnel_fit_candidate=True and confidence scores
        """
        if keywords is None:
            keywords = [
                "tunnel",
                "pregame",
                "gameday",
                "game day",
                "arrival",
                "fit",
                "outfit",
                "ootd",
                "fashion",
                "style",
                "wearing",
            ]

        for post in posts:
            caption_lower = post.caption.lower()

            # Count keyword matches
            matches = sum(1 for keyword in keywords if keyword in caption_lower)

            # Calculate confidence based on keyword matches
            confidence = min(matches * 0.25, 1.0)  # 0.25 per keyword match, max 1.0

            post.confidence_score = confidence
            post.is_tunnel_fit_candidate = confidence > 0

        tagged_count = len([p for p in posts if p.is_tunnel_fit_candidate])
        logger.info(
            f"Tagged {tagged_count}/{len(posts)} Instagram posts with tunnel fit keywords"
        )
        return posts

    @staticmethod
    def get_image_hash(image_url: str) -> str:
        """
        Generate a hash for image URL for deduplication

        Args:
            image_url: Image URL

        Returns:
            MD5 hash of the URL
        """
        return hashlib.md5(image_url.encode()).hexdigest()
