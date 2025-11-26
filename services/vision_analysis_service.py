"""
Vision Analysis Service
Uses GPT-4o-mini Vision API to identify outfit pieces, brands, and styling details
"""

import logging
import asyncio
from typing import List, Optional, Dict
from dataclasses import dataclass
from openai import AsyncOpenAI
from urllib.parse import urlparse
from collections import OrderedDict

from utils.image_service import download_and_encode_image

logger = logging.getLogger(__name__)

# Vision API parameters for pre-screening
PRESCREENING_MAX_TOKENS = 100  # Minimal tokens for yes/no classification
PRESCREENING_MIN_CONFIDENCE = (
    0.3  # Minimum confidence to consider outfit photo (lowered for inclusivity)
)
IMAGE_DOWNLOAD_RETRIES = 3


@dataclass
class OutfitItem:
    """Single outfit item identified from vision analysis"""

    item_type: str  # "jacket", "pants", "shoes", "bag", "jewelry", etc.
    brand: str  # Brand name if identifiable
    description: str  # Detailed description (color, style, material)
    confidence: float  # 0.0-1.0 confidence score
    price_estimate: Optional[str] = None  # "$100-$200" range if AI can estimate
    is_accessory: bool = False  # True for jewelry, bags, hats, etc.


@dataclass
class OutfitAnalysis:
    """Complete outfit analysis result"""

    items: List[OutfitItem]
    overall_style: str  # "casual", "formal", "athleisure", "streetwear", etc.
    color_palette: List[str]  # Dominant colors
    confidence: float  # Overall confidence (0.0-1.0)
    is_tunnel_fit: bool  # Is this actually a tunnel/arrival photo?
    notes: str  # Additional AI observations


class VisionAnalysisService:
    """Service for analyzing outfit photos using GPT-4o-mini Vision API"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Initialize vision analysis service

        Args:
            api_key: OpenAI API key
            model: Vision model to use (default: gpt-4o-mini for cost efficiency)
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = 1500  # Enough for detailed outfit analysis
        self.temperature = 0.1  # Low temperature for consistent analysis
        self._image_payload_cache: "OrderedDict[str, str]" = OrderedDict()
        self._cache_limit = 128

    async def analyze_outfit_image(
        self,
        image_url: str,
        player_name: str,
        event_context: Optional[str] = None,
    ) -> Optional[OutfitAnalysis]:
        """
        Analyze an outfit image to identify clothing items and brands

        Args:
            image_url: URL of the image to analyze
            player_name: Name of the player in the photo
            event_context: Optional context (e.g., "Fever vs Sky pregame")

        Returns:
            OutfitAnalysis object or None if analysis fails
        """
        try:
            logger.info(f"Analyzing outfit image for {player_name}: {image_url}")

            # Build context-aware prompt
            prompt = self._build_analysis_prompt(player_name, event_context)
            image_content = await self._build_image_content(image_url)
            if not image_content:
                logger.warning(f"Unable to prepare image for analysis: {image_url}")
                return None

            # Call GPT-4o-mini Vision API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            image_content,
                        ],
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            # Parse the response
            analysis_text = response.choices[0].message.content

            if not analysis_text:
                logger.error("Empty response from Vision API")
                return None

            # Convert AI response to structured OutfitAnalysis
            outfit_analysis = self._parse_analysis_response(analysis_text)

            logger.info(
                f"Vision analysis complete: {len(outfit_analysis.items)} items identified "
                f"(confidence: {outfit_analysis.confidence:.2f})"
            )

            return outfit_analysis

        except Exception as e:
            logger.error(f"Error analyzing outfit image: {e}")
            return None

    async def is_outfit_photo(
        self, image_url: str, player_name: str
    ) -> tuple[bool, float]:
        """
        Quick pre-screening to determine if photo shows a full-body outfit

        This is a lightweight check before expensive full analysis.
        Uses minimal tokens for cost efficiency (~$0.001 per image).

        Args:
            image_url: URL of the image to check
            player_name: Name of the player

        Returns:
            Tuple of (is_outfit: bool, confidence: float)
        """
        try:
            prompt = f"""Look at this photo of {player_name}.

Is this a photo where {player_name} is showing off an outfit, clothing, or fashion look?

Answer with ONLY a JSON response:
{{
  "is_outfit_photo": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}}

Consider TRUE if:
- ANY shot clearly showing clothing/outfit (full body, upper body, or detail shots)
- Mirror selfie showing outfit
- Fashion/style photo (tunnel walk, arrival, pregame, event)
- Dressed up or showing intentional style/fashion
- Multiple clothing items visible OR focus on specific outfit piece

Consider FALSE if:
- Basketball action shot IN UNIFORM during game
- Extreme close-up headshot with no outfit visible
- Photo where outfit is completely obscured
- Screenshot or non-photo content"""

            image_content = await self._build_image_content(image_url)
            if not image_content:
                logger.warning(f"Unable to prepare image for outfit check: {image_url}")
                return False, 0.0

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            image_content,
                        ],
                    }
                ],
                max_tokens=PRESCREENING_MAX_TOKENS,
                temperature=0.1,
            )

            result_text = response.choices[0].message.content

            # Parse JSON response
            import json

            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1

            if json_start == -1:
                logger.warning(f"No JSON in pre-screening response: {result_text}")
                return False, 0.0

            result = json.loads(result_text[json_start:json_end])

            is_outfit = result.get("is_outfit_photo", False)
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "")

            logger.debug(
                f"Pre-screening result: {is_outfit} (confidence: {confidence:.2f}) - {reason}"
            )

            return is_outfit, confidence

        except Exception as e:
            logger.error(f"Error in outfit photo pre-screening: {e}")
            return False, 0.0

    def _build_analysis_prompt(
        self, player_name: str, event_context: Optional[str]
    ) -> str:
        """Build the prompt for vision analysis"""

        base_prompt = f"""You are a fashion expert analyzing {player_name}'s outfit in this photo.

TASK: Identify all visible clothing items, accessories, and brands worn by {player_name}.

Provide your analysis in the following JSON format:
{{
  "is_tunnel_fit": true/false,  // Is this a tunnel/arrival/pregame photo?
  "overall_style": "streetwear/casual/formal/athleisure/etc",
  "color_palette": ["color1", "color2", ...],
  "items": [
    {{
      "item_type": "jacket/pants/shoes/bag/jewelry/etc",
      "brand": "Brand Name or Unknown",
      "description": "Detailed description with color, style, material",
      "confidence": 0.0-1.0,  // Your confidence in this identification
      "price_estimate": "$100-$200 or null",  // Optional price range
      "is_accessory": true/false
    }},
    ...
  ],
  "notes": "Any additional observations about the outfit"
}}

IMPORTANT GUIDELINES:
1. Only identify items you can clearly see in the photo
2. For brands: Use "Unknown" if you cannot confidently identify the brand
3. Confidence scores: 0.9+ = very certain, 0.7-0.9 = likely, 0.5-0.7 = unsure, <0.5 = guess
4. Include ALL visible items: clothing, shoes, bags, jewelry, hats, sunglasses, etc.
5. Be specific in descriptions: exact colors, patterns, materials, style details
6. For shoes: Include model name if identifiable (e.g., "Nike Air Jordan 1")
7. is_tunnel_fit should be true only if this appears to be a tunnel/arrival/pregame photo
"""

        if event_context:
            base_prompt += f"\n\nCONTEXT: This photo is from {event_context}"

        return base_prompt

    def _parse_analysis_response(self, response_text: str) -> OutfitAnalysis:
        """
        Parse the AI response into structured OutfitAnalysis object

        Args:
            response_text: Raw JSON response from GPT-4 Vision

        Returns:
            OutfitAnalysis object
        """
        import json

        try:
            # Extract JSON from response (may have markdown code blocks)
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)

            # Parse outfit items
            items = []
            for item_data in data.get("items", []):
                item = OutfitItem(
                    item_type=item_data.get("item_type", "unknown"),
                    brand=item_data.get("brand", "Unknown"),
                    description=item_data.get("description", ""),
                    confidence=float(item_data.get("confidence", 0.0)),
                    price_estimate=item_data.get("price_estimate"),
                    is_accessory=item_data.get("is_accessory", False),
                )
                items.append(item)

            # Calculate overall confidence (average of item confidences)
            overall_confidence = (
                sum(item.confidence for item in items) / len(items) if items else 0.0
            )

            return OutfitAnalysis(
                items=items,
                overall_style=data.get("overall_style", "unknown"),
                color_palette=data.get("color_palette", []),
                confidence=overall_confidence,
                is_tunnel_fit=data.get("is_tunnel_fit", False),
                notes=data.get("notes", ""),
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}\nResponse: {response_text}")
            # Return minimal analysis on parse failure
            return OutfitAnalysis(
                items=[],
                overall_style="unknown",
                color_palette=[],
                confidence=0.0,
                is_tunnel_fit=False,
                notes=f"Failed to parse response: {e}",
            )
        except Exception as e:
            logger.error(f"Error parsing analysis response: {e}")
            return OutfitAnalysis(
                items=[],
                overall_style="unknown",
                color_palette=[],
                confidence=0.0,
                is_tunnel_fit=False,
                notes=f"Parsing error: {e}",
            )

    async def batch_analyze_outfits(
        self,
        images: List[tuple[str, str, Optional[str]]],  # (url, player, context)
        max_concurrent: int = 3,
    ) -> List[Optional[OutfitAnalysis]]:
        """
        Analyze multiple outfit images concurrently

        Args:
            images: List of (image_url, player_name, event_context) tuples
            max_concurrent: Maximum concurrent API calls to avoid rate limits

        Returns:
            List of OutfitAnalysis objects (None for failed analyses)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_semaphore(url: str, player: str, context: Optional[str]):
            async with semaphore:
                return await self.analyze_outfit_image(url, player, context)

        tasks = [
            analyze_with_semaphore(url, player, ctx) for url, player, ctx in images
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None
        return [
            result if not isinstance(result, Exception) else None for result in results
        ]

    def filter_high_confidence_items(
        self, outfit_analysis: OutfitAnalysis, min_confidence: float = 0.7
    ) -> List[OutfitItem]:
        """
        Filter outfit items by confidence threshold

        Args:
            outfit_analysis: Complete outfit analysis
            min_confidence: Minimum confidence score (0.0-1.0)

        Returns:
            Filtered list of high-confidence items
        """
        return [
            item for item in outfit_analysis.items if item.confidence >= min_confidence
        ]

    async def _build_image_content(self, image_url: str) -> Optional[dict]:
        """Prepare image payload for OpenAI Vision API by downloading when needed"""
        if not image_url:
            return None

        cached = self._image_payload_cache.get(image_url)
        if cached:
            return {"type": "image_url", "image_url": {"url": cached}}

        if image_url.startswith("data:"):
            self._cache_image_payload(image_url, image_url)
            return {"type": "image_url", "image_url": {"url": image_url}}

        try:
            encoded = await self._download_image_with_retry(image_url)
            if encoded:
                self._cache_image_payload(image_url, encoded)
                return {"type": "image_url", "image_url": {"url": encoded}}
        except Exception as exc:
            logger.debug(f"Failed to download image {image_url}: {exc}")

        if not self._is_instagram_host(image_url):
            # For non-Instagram hosts, let OpenAI fetch directly as fallback
            return {"type": "image_url", "image_url": {"url": image_url}}

        logger.warning(f"Instagram image inaccessible for Vision API: {image_url}")
        return None

    def _is_instagram_host(self, image_url: str) -> bool:
        """Check if the host is Instagram-related (which usually blocks OpenAI)"""
        try:
            host = urlparse(image_url).netloc.lower()
        except Exception:
            return False

        blocked_hosts = ["instagram.com", "cdninstagram.com", "fbcdn.net"]
        return any(blocked in host for blocked in blocked_hosts)

    def _cache_image_payload(self, key: str, value: str) -> None:
        """Store encoded image data with simple LRU eviction"""
        if not key or not value:
            return

        if key in self._image_payload_cache:
            # Move to end (most recently used)
            self._image_payload_cache.move_to_end(key)
        self._image_payload_cache[key] = value

        if len(self._image_payload_cache) > self._cache_limit:
            self._image_payload_cache.popitem(last=False)

    async def _download_image_with_retry(self, image_url: str) -> Optional[str]:
        """Download and encode image with retry/backoff strategy"""
        last_exception = None
        for attempt in range(IMAGE_DOWNLOAD_RETRIES):
            if attempt > 0:
                await asyncio.sleep(attempt)  # simple linear backoff
            try:
                encoded = await download_and_encode_image(image_url)
                if encoded:
                    return encoded
            except Exception as exc:
                last_exception = exc
                logger.debug(
                    "Image download attempt %d failed for %s: %s",
                    attempt + 1,
                    image_url,
                    exc,
                )

        if last_exception:
            logger.warning(
                "Failed to download image %s after %d attempts: %s",
                image_url,
                IMAGE_DOWNLOAD_RETRIES,
                last_exception,
            )
        return None
