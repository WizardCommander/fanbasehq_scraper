"""
Date utility functions for the scraper
"""

from datetime import datetime, date
from typing import Union


def parse_date(date_str: str, strict: bool = True) -> date:
    """
    Parse date string in various formats
    
    Args:
        date_str: Date string to parse
        strict: If True, only accept YYYY-MM-DD format. If False, try fuzzy parsing
        
    Returns:
        date object
        
    Raises:
        ValueError: If date format is invalid
    """
    import re
    from dateutil import parser as date_parser
    
    try:
        if strict:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            # Try YYYY-MM-DD first, then fallback to fuzzy parsing
            if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            parsed = date_parser.parse(date_str, fuzzy=True)
            return parsed.date()
    except Exception as e:
        if strict:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
        else:
            raise ValueError(f"Could not parse date: {date_str}. Error: {e}")


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
        raise ValueError(f"Start date {start_date} is too early. Use {earliest_date} or later")


def format_date_for_twitter(date_obj: date) -> str:
    """
    Format a date object for Twitter search queries
    
    Args:
        date_obj: Date to format
        
    Returns:
        Date string in format suitable for Twitter API
    """
    return date_obj.strftime('%Y-%m-%d')


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