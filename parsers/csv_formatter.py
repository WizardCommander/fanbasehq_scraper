"""
CSV formatter to match FanbaseHQ milestone schema with intelligent date resolution
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import MilestoneData
from parsers.date_resolver import create_date_resolver
from utils.image_service import download_and_encode_image
from config.settings import (
    CSV_ENCODING,
    CLIENT_SUBMITTER_NAME,
    CLIENT_SUBMITTER_EMAIL,
    CLIENT_USER_ID,
    CLIENT_ORIGINAL_SUBMISSION_ID,
)


logger = logging.getLogger(__name__)


class MilestoneCSVFormatter:
    """Format milestone data to match FanbaseHQ CSV schema"""

    # CSV columns based on existing milestone CSV schema
    CSV_COLUMNS = [
        "id",
        "player_name",
        "title",
        "date",
        "value",
        "categories",
        "previous_record",
        "description",
        "submitter_name",
        "user_id",
        "status",
        "created_at",
        "updated_at",
        "submitter_email",
        "article_url",
        "original_submission_id",
        "is_award",
        "image_url",
        "image_data",
        "is_featured",
    ]

    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    async def format_milestone_to_csv_row(
        self,
        milestone: MilestoneData,
        tweet: ScrapedTweet,
        player_name: str,
        submission_id: int = None,
    ) -> Dict[str, str]:
        """
        Convert milestone and tweet data to CSV row format with intelligent date resolution

        Args:
            milestone: Parsed milestone data
            tweet: Original tweet data
            player_name: Player name for date resolution
            submission_id: Optional ID for the submission

        Returns:
            Dictionary representing CSV row
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f%z")

        # Resolve the actual milestone date using intelligent date resolution
        try:
            date_resolver = create_date_resolver()
            resolved_date, date_source, date_confidence = (
                await date_resolver.resolve_milestone_date(
                    milestone, tweet.created_at, player_name
                )
            )

            # Log the date resolution for debugging
            if resolved_date:
                logger.info(
                    f"Date resolution: {tweet.created_at.strftime('%Y-%m-%d')} -> {resolved_date} "
                    f"(source: {date_source}, confidence: {date_confidence:.2f})"
                )
            else:
                logger.info(
                    f"Date resolution: {tweet.created_at.strftime('%Y-%m-%d')} -> BLANK "
                    f"(source: {date_source}, confidence: {date_confidence:.2f})"
                )

        except Exception as e:
            logger.warning(f"Date resolution failed, leaving date blank: {e}")
            resolved_date = None
            date_source = "error"
            date_confidence = 0.0

        # Format categories as JSON array string
        categories_json = (
            json.dumps(milestone.categories) if milestone.categories else "[]"
        )

        # Determine if this is an award-type milestone
        is_award = any(
            cat.lower() in ["award", "honor", "recognition"]
            for cat in milestone.categories
        )

        # Handle blank dates conservatively
        date_string = resolved_date.strftime("%Y-%m-%d") if resolved_date else ""

        return {
            "id": submission_id or "",
            "player_name": milestone.player_name or player_name,
            "title": milestone.title,
            "date": date_string,  # Use resolved date or blank if uncertain
            "value": milestone.value,
            "categories": categories_json,
            "previous_record": milestone.previous_record,
            "description": milestone.description or tweet.text,
            "submitter_name": CLIENT_SUBMITTER_NAME,
            "user_id": CLIENT_USER_ID,
            "status": (
                "pending" if resolved_date else "needs_date_review"
            ),  # Flag uncertain dates for review
            "created_at": timestamp,
            "updated_at": timestamp,
            "submitter_email": CLIENT_SUBMITTER_EMAIL,
            "article_url": tweet.url,
            "original_submission_id": CLIENT_ORIGINAL_SUBMISSION_ID,
            "is_award": "TRUE" if is_award else "FALSE",
            "image_url": (
                tweet.images[0] if tweet.images else ""
            ),  # Real pbs.twimg.com URLs via universal image extraction system
            "image_data": (
                await download_and_encode_image(tweet.images[0]) if tweet.images else ""
            ),
            "is_featured": "FALSE",
        }

    async def write_milestones_to_csv(
        self,
        milestones: List[MilestoneData],
        tweets: List[ScrapedTweet],
        player_name: str,
    ) -> None:
        """
        Write milestones to CSV file with intelligent date resolution

        Args:
            milestones: List of parsed milestone data
            tweets: List of corresponding tweet data
            player_name: Player name for date resolution
        """
        if len(milestones) != len(tweets):
            raise ValueError("Milestones and tweets lists must have same length")

        rows = []
        for i, (milestone, tweet) in enumerate(zip(milestones, tweets), 1):
            row = await self.format_milestone_to_csv_row(
                milestone, tweet, player_name, submission_id=i
            )
            rows.append(row)

        # Write to CSV
        with open(self.output_file, "w", newline="", encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        logger.info(f"Wrote {len(rows)} milestones to {self.output_file}")

    async def append_milestones_to_csv(
        self,
        milestones: List[MilestoneData],
        tweets: List[ScrapedTweet],
        player_name: str,
    ) -> None:
        """
        Append milestones to existing CSV file with intelligent date resolution

        Args:
            milestones: List of parsed milestone data
            tweets: List of corresponding tweet data
            player_name: Player name for date resolution
        """
        if len(milestones) != len(tweets):
            raise ValueError("Milestones and tweets lists must have same length")

        # Check if file exists and has header
        file_exists = self.output_file.exists()

        # Get the next ID number by counting existing records
        existing_count = len(self.read_existing_csv()) if file_exists else 0

        rows = []
        for i, (milestone, tweet) in enumerate(zip(milestones, tweets), 1):
            submission_id = existing_count + i
            row = await self.format_milestone_to_csv_row(
                milestone, tweet, player_name, submission_id=submission_id
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

        logger.info(f"Appended {len(rows)} milestones to {self.output_file}")

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
