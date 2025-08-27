"""
Date utility functions for the scraper
"""

from datetime import datetime, date
from typing import Union


def parse_date(date_str: str) -> date:
    """
    Parse a date string in YYYY-MM-DD format to a date object
    
    Args:
        date_str: Date string in format YYYY-MM-DD
        
    Returns:
        date object
        
    Raises:
        ValueError: If date format is invalid
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")


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