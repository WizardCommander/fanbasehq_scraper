"""
Tunnel Fit CSV formatter to match FanbaseHQ tunnel fit schema
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import TunnelFitData
from utils.image_service import download_and_encode_image
from config.settings import (
    CSV_ENCODING,
    CLIENT_SUBMITTER_NAME,
    CLIENT_SUBMITTER_EMAIL,
    CLIENT_USER_ID,
    CLIENT_ORIGINAL_SUBMISSION_ID,
)
from utils.branded_types import SubmissionId, submission_id


logger = logging.getLogger(__name__)


class TunnelFitCSVFormatter:
    """Format tunnel fit data to match FanbaseHQ CSV schema"""

    # CSV columns based on existing tunnel fit CSV schema
    CSV_COLUMNS = [
        "id",
        "player_name",
        "event",
        "date",
        "type",
        "image_url",
        "image_data",
        "outfit_details",
        "social_stats",
        "source",
        "source_link",
        "photographer",
        "photographer_link",
        "additional_notes",
        "submitter_name",
        "user_id",
        "status",
        "created_at",
        "updated_at",
        "original_submission_id",
        "location",
        "style_category",
        "submitter_email",
    ]

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    async def format_tunnel_fit_to_csv_row(
        self,
        tunnel_fit: TunnelFitData,
        tweet: ScrapedTweet,
        player_name: str,
        submission_id: Optional[SubmissionId] = None,
    ) -> Dict[str, str]:
        """
        Convert tunnel fit and tweet data to CSV row format

        Args:
            tunnel_fit: Parsed tunnel fit data
            tweet: Original tweet data
            player_name: Player name
            submission_id: Optional ID for the submission

        Returns:
            Dictionary representing CSV row
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f%z")

        # Format outfit details as JSON string
        outfit_details_json = (
            json.dumps(tunnel_fit.outfit_details) if tunnel_fit.outfit_details else "[]"
        )

        # Format social stats as JSON string
        social_stats_json = (
            json.dumps(tunnel_fit.social_stats) if tunnel_fit.social_stats else "{}"
        )

        # Handle date formatting
        date_string = tunnel_fit.date.strftime("%Y-%m-%d") if tunnel_fit.date else ""

        image_url = tunnel_fit.image_url or (tweet.images[0] if tweet.images else "")

        return {
            "id": str(submission_id.value) if submission_id else "",
            "player_name": tunnel_fit.player_name or player_name,
            "event": tunnel_fit.event,
            "date": date_string,
            "type": tunnel_fit.type,
            "image_url": image_url,
            "image_data": (
                await download_and_encode_image(image_url) if image_url else ""
            ),
            "outfit_details": outfit_details_json,
            "social_stats": social_stats_json,
            "source": tweet.author_handle,  # Twitter account name (e.g. @caitlinclarksty)
            "source_link": tweet.url,
            "photographer": "",
            "photographer_link": "",
            "additional_notes": "",
            "submitter_name": CLIENT_SUBMITTER_NAME,
            "user_id": CLIENT_USER_ID,
            "status": "pending",
            "created_at": timestamp,
            "updated_at": timestamp,
            "original_submission_id": CLIENT_ORIGINAL_SUBMISSION_ID,
            "location": tunnel_fit.location,
            "style_category": "",  # Could be populated from outfit analysis
            "submitter_email": CLIENT_SUBMITTER_EMAIL,
        }

    async def _format_tunnel_fit_from_sources(
        self,
        tunnel_fit: TunnelFitData,
        player_name: str,
        tweet_sources: Dict[str, Dict[str, str]],
        submission_id: Optional[SubmissionId] = None,
    ) -> Dict[str, str]:
        """
        Convert tunnel fit to CSV row using tweet_sources dict (for multi-source flow)

        Args:
            tunnel_fit: Parsed tunnel fit data
            player_name: Player name
            tweet_sources: Dict mapping photo_id -> metadata dict (handle/post_url/image_url)
            submission_id: Optional ID for the submission

        Returns:
            Dictionary representing CSV row
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f%z")

        # Format outfit details as JSON string
        outfit_details_json = (
            json.dumps(tunnel_fit.outfit_details) if tunnel_fit.outfit_details else "[]"
        )

        # Format social stats as JSON string
        social_stats_json = (
            json.dumps(tunnel_fit.social_stats) if tunnel_fit.social_stats else "{}"
        )

        # Handle date formatting
        date_string = tunnel_fit.date.strftime("%Y-%m-%d") if tunnel_fit.date else ""

        source_info = tweet_sources.get(tunnel_fit.source_tweet_id.value)
        if not source_info:
            logger.warning(
                "Missing source metadata for tunnel fit photo %s",
                tunnel_fit.source_tweet_id.value,
            )
            source_info = {}
        raw_handle = (
            source_info.get("handle")
            or tunnel_fit.source_handle
            or ""
        ).strip()
        if raw_handle and not raw_handle.startswith("@"):
            source = f"@{raw_handle}"
        else:
            source = raw_handle
        if not source:
            logger.warning(
                "Missing source handle metadata for tunnel fit photo %s",
                tunnel_fit.source_tweet_id.value,
            )

        source_link = source_info.get("post_url") or tunnel_fit.source_post_url or ""
        if not source_link:
            logger.warning(
                "Missing post_url metadata for tunnel fit photo %s",
                tunnel_fit.source_tweet_id.value,
            )

        image_url = tunnel_fit.image_url or source_info.get("image_url", "")
        if not image_url:
            logger.warning(
                "Missing image_url for tunnel fit photo %s",
                tunnel_fit.source_tweet_id.value,
            )
        image_data = (
            await download_and_encode_image(image_url) if image_url else ""
        )

        return {
            "id": str(submission_id.value) if submission_id else "",
            "player_name": tunnel_fit.player_name or player_name,
            "event": tunnel_fit.event,
            "date": date_string,
            "type": tunnel_fit.type,
            "image_url": image_url,
            "image_data": image_data,
            "outfit_details": outfit_details_json,
            "social_stats": social_stats_json,
            "source": source,
            "source_link": source_link,
            "photographer": "",
            "photographer_link": "",
            "additional_notes": f"Source: {tunnel_fit.date_source}, Fit confidence: {tunnel_fit.fit_confidence:.2f}",
            "submitter_name": CLIENT_SUBMITTER_NAME,
            "user_id": CLIENT_USER_ID,
            "status": "pending",
            "created_at": timestamp,
            "updated_at": timestamp,
            "original_submission_id": CLIENT_ORIGINAL_SUBMISSION_ID,
            "location": tunnel_fit.location,
            "style_category": "",  # Could be populated from outfit analysis
            "submitter_email": CLIENT_SUBMITTER_EMAIL,
        }

    async def write_tunnel_fits_to_csv(
        self,
        tunnel_fits: List[TunnelFitData],
        tweets: Optional[List[ScrapedTweet]] = None,
        player_name: str = "",
        tweet_sources: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        """
        Write tunnel fits to CSV file

        Args:
            tunnel_fits: List of parsed tunnel fit data
            tweets: List of corresponding tweet data (optional for backward compatibility)
            player_name: Player name
            tweet_sources: Dict mapping photo_id -> metadata dict (multi-source flow)
        """
        # Validate mutually exclusive parameters
        if tweets is not None and tweet_sources is not None:
            raise ValueError(
                "Cannot provide both 'tweets' and 'tweet_sources'. "
                "Use 'tweets' for Twitter-only flow or 'tweet_sources' for multi-source flow."
            )
        if tweets is None and tweet_sources is None:
            raise ValueError(
                "Must provide either 'tweets' (Twitter flow) or 'tweet_sources' (multi-source flow)."
            )

        # Backward compatibility: if tweets provided, use them
        if tweets is not None:
            if len(tunnel_fits) != len(tweets):
                raise ValueError("Tunnel fits and tweets lists must have same length")

            rows = []
            for i, (tunnel_fit, tweet) in enumerate(zip(tunnel_fits, tweets), 1):
                row = await self.format_tunnel_fit_to_csv_row(
                    tunnel_fit, tweet, player_name, submission_id=submission_id(i)
                )
                rows.append(row)
        else:
            # Multi-source flow: use tweet_sources dict
            if tweet_sources is None:
                tweet_sources = {}

            rows = []
            for i, tunnel_fit in enumerate(tunnel_fits, 1):
                row = await self._format_tunnel_fit_from_sources(
                    tunnel_fit,
                    player_name,
                    tweet_sources,
                    submission_id=submission_id(i),
                )
                rows.append(row)

        # Write to CSV
        with open(self.output_file, "w", newline="", encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Wrote {len(rows)} tunnel fits to {self.output_file}")

    async def append_tunnel_fits_to_csv(
        self,
        tunnel_fits: List[TunnelFitData],
        tweets: List[ScrapedTweet],
        player_name: str,
    ) -> None:
        """
        Append tunnel fits to existing CSV file

        Args:
            tunnel_fits: List of parsed tunnel fit data
            tweets: List of corresponding tweet data
            player_name: Player name
        """
        if len(tunnel_fits) != len(tweets):
            raise ValueError("Tunnel fits and tweets lists must have same length")

        # Check if file exists and has header
        file_exists = self.output_file.exists()

        # Get the next ID number by counting existing records
        existing_count = len(self.read_existing_csv()) if file_exists else 0

        rows = []
        for i, (tunnel_fit, tweet) in enumerate(zip(tunnel_fits, tweets), 1):
            sub_id = existing_count + i
            row = await self.format_tunnel_fit_to_csv_row(
                tunnel_fit, tweet, player_name, submission_id=submission_id(sub_id)
            )
            rows.append(row)

        # Append to CSV
        mode = "a" if file_exists else "w"
        with open(self.output_file, mode, newline="", encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)

            # Write header if new file
            if not file_exists:
                writer.writeheader()

            writer.writerows(rows)

        logger.info(f"Appended {len(rows)} tunnel fits to {self.output_file}")

    def read_existing_csv(self) -> List[Dict[str, str]]:
        """
        Read existing CSV file to avoid duplicates

        Returns:
            List of existing CSV rows as dictionaries
        """
        if not self.output_file.exists():
            return []

        existing_rows = []
        with open(self.output_file, "r", encoding=CSV_ENCODING) as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)

        logger.info(
            f"Found {len(existing_rows)} existing records in {self.output_file}"
        )
        return existing_rows

    def get_existing_submission_ids(self) -> List[str]:
        """
        Get list of existing submission IDs to avoid duplicates

        Returns:
            List of original_submission_id values from existing CSV
        """
        existing_rows = self.read_existing_csv()
        return [row.get("original_submission_id", "") for row in existing_rows]
