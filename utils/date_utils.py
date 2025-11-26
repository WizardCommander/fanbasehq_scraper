"""
Date utility functions for the scraper
"""

from datetime import datetime, date
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def parse_flexible_date(date_str: str, fuzzy: bool = True) -> Optional[date]:
    """
    Parse date string in various common formats

    Consolidated date parsing function that handles all formats found across the codebase.
    Tries formats in order of most common to least common, with fuzzy parsing as fallback.

    Args:
        date_str: Date string to parse
        fuzzy: Whether to use fuzzy parsing as fallback (default: True)

    Returns:
        Parsed date object or None if parsing fails

    Formats supported (in order):
        1. YYYY-MM-DD (ISO format with dashes)
        2. MM/DD/YYYY (US format with slashes)
        3. MM-DD-YYYY (US format with dashes)
        4. YYYY/MM/DD (ISO format with slashes)
        5. Full month names with comma (January 15, 2024)
        6. Full month names without comma (January 15 2024)
        7. Short month names with comma (Jan 15, 2024)
        8. Short month names without comma (Jan 15 2024)
        9. Fuzzy parsing fallback (if enabled)
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # List of format strings to try in order
    date_formats = [
        "%Y-%m-%d",  # ISO format (most common)
        "%m/%d/%Y",  # US format with slashes
        "%m-%d-%Y",  # US format with dashes
        "%Y/%m/%d",  # ISO format with slashes
        "%B %d, %Y",  # Full month with comma (January 15, 2024)
        "%B %d %Y",  # Full month without comma (January 15 2024)
        "%b %d, %Y",  # Short month with comma (Jan 15, 2024)
        "%b %d %Y",  # Short month without comma (Jan 15 2024)
    ]

    # Try each format
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt).date()
            logger.debug(f"Parsed '{date_str}' using format '{fmt}'")
            return parsed_date
        except ValueError:
            continue

    # Fallback to fuzzy parsing if enabled
    if fuzzy:
        try:
            from dateutil import parser as date_parser

            parsed = date_parser.parse(date_str, fuzzy=True)
            logger.debug(f"Parsed '{date_str}' using fuzzy parsing")
            return parsed.date()
        except Exception as e:
            logger.debug(f"Fuzzy parsing failed for '{date_str}': {e}")
            return None

    logger.debug(f"Could not parse date: {date_str}")
    return None


def parse_date(date_str: str, strict: bool = True) -> date:
    """
    Parse date string in various formats

    Backward-compatible wrapper around parse_flexible_date().

    Args:
        date_str: Date string to parse
        strict: If True, only accept YYYY-MM-DD format. If False, try all formats with fuzzy parsing

    Returns:
        date object

    Raises:
        ValueError: If date format is invalid
    """
    if strict:
        # Strict mode: only accept YYYY-MM-DD
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
    else:
        # Non-strict mode: try all formats
        parsed = parse_flexible_date(date_str, fuzzy=True)
        if parsed is None:
            raise ValueError(f"Could not parse date: {date_str}")
        return parsed


def validate_date_range(start_date: date, end_date: date) -> None:
    """
    Validate that start_date is before end_date and both are reasonable

    Args:
        start_date: Start date
        end_date: End date

    Raises:
        ValueError: If date range is invalid
    """
    if start_date > end_date:
        raise ValueError(f"Start date {start_date} cannot be after end date {end_date}")

    # Check if dates are too far in the future
    today = date.today()
    if start_date > today:
        raise ValueError(f"Start date {start_date} cannot be in the future")

    if end_date > today:
        raise ValueError(f"End date {end_date} cannot be in the future")

    # Check if dates are too far in the past (before WNBA season)
    earliest_date = date(2024, 1, 1)  # Adjust based on WNBA season
    if start_date < earliest_date:
        raise ValueError(
            f"Start date {start_date} is too early. Use {earliest_date} or later"
        )


def format_date_for_twitter(date_obj: date) -> str:
    """
    Format a date object for Twitter search queries

    Args:
        date_obj: Date to format

    Returns:
        Date string in format suitable for Twitter API
    """
    return date_obj.strftime("%Y-%m-%d")


def get_date_range_days(start_date: date, end_date: date) -> int:
    """
    Get the number of days between two dates

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        Number of days between the dates
    """
    return (end_date - start_date).days
