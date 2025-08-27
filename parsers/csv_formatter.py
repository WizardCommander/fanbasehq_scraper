"""
CSV formatter to match FanbaseHQ milestone schema
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import asdict

from utils.twitter_client import ScrapedTweet
from parsers.ai_parser import MilestoneData
from config.settings import CSV_ENCODING


logger = logging.getLogger(__name__)


class MilestoneCSVFormatter:
    """Format milestone data to match FanbaseHQ CSV schema"""
    
    # CSV columns based on existing milestone CSV schema
    CSV_COLUMNS = [
        'id',
        'player_name', 
        'title',
        'date',
        'value',
        'categories',
        'previous_record',
        'description', 
        'submitter_name',
        'user_id',
        'status',
        'created_at',
        'updated_at',
        'submitter_email',
        'article_url',
        'original_submission_id',
        'is_award',
        'image_url',
        'image_data',
        'is_featured'
    ]
    
    def __init__(self, output_file: str):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
    def format_milestone_to_csv_row(
        self, 
        milestone: MilestoneData,
        tweet: ScrapedTweet,
        submission_id: int = None
    ) -> Dict[str, str]:
        """
        Convert milestone and tweet data to CSV row format
        
        Args:
            milestone: Parsed milestone data
            tweet: Original tweet data
            submission_id: Optional ID for the submission
            
        Returns:
            Dictionary representing CSV row
        """
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S.%f%z')
        
        # Format categories as JSON array string
        categories_json = json.dumps(milestone.categories) if milestone.categories else '[]'
        
        # Determine if this is an award-type milestone
        is_award = any(cat.lower() in ['award', 'honor', 'recognition'] for cat in milestone.categories)
        
        return {
            'id': submission_id or '',
            'player_name': milestone.player_name or 'Caitlin Clark',
            'title': milestone.title,
            'date': tweet.created_at.strftime('%Y-%m-%d'),
            'value': milestone.value,
            'categories': categories_json,
            'previous_record': milestone.previous_record,
            'description': milestone.description or tweet.text,
            'submitter_name': 'scraper_bot',  # Bot identifier
            'user_id': 'automated_scraper',
            'status': 'pending',  # Needs manual review
            'created_at': timestamp,
            'updated_at': timestamp,
            'submitter_email': 'scraper@fanbasehq.ai',
            'article_url': tweet.url,
            'original_submission_id': tweet.id,
            'is_award': 'TRUE' if is_award else 'FALSE',
            'image_url': tweet.images[0] if tweet.images else '',
            'image_data': '',  # Would need to download and encode images
            'is_featured': 'FALSE'
        }
    
    def write_milestones_to_csv(
        self,
        milestones: List[MilestoneData], 
        tweets: List[ScrapedTweet]
    ) -> None:
        """
        Write milestones to CSV file
        
        Args:
            milestones: List of parsed milestone data
            tweets: List of corresponding tweet data
        """
        if len(milestones) != len(tweets):
            raise ValueError("Milestones and tweets lists must have same length")
        
        rows = []
        for i, (milestone, tweet) in enumerate(zip(milestones, tweets), 1):
            row = self.format_milestone_to_csv_row(milestone, tweet, submission_id=i)
            rows.append(row)
        
        # Write to CSV
        with open(self.output_file, 'w', newline='', encoding=CSV_ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            
        logger.info(f"Wrote {len(rows)} milestones to {self.output_file}")
        
    def append_milestones_to_csv(
        self,
        milestones: List[MilestoneData],
        tweets: List[ScrapedTweet]
    ) -> None:
        """
        Append milestones to existing CSV file
        
        Args:
            milestones: List of parsed milestone data  
            tweets: List of corresponding tweet data
        """
        if len(milestones) != len(tweets):
            raise ValueError("Milestones and tweets lists must have same length")
            
        # Check if file exists and has header
        file_exists = self.output_file.exists()
        
        rows = []
        for milestone, tweet in zip(milestones, tweets):
            row = self.format_milestone_to_csv_row(milestone, tweet)
            rows.append(row)
            
        # Append to CSV
        mode = 'a' if file_exists else 'w'
        with open(self.output_file, mode, newline='', encoding=CSV_ENCODING) as f:
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
        with open(self.output_file, 'r', encoding=CSV_ENCODING) as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
            
        logger.info(f"Found {len(existing_rows)} existing records in {self.output_file}")
        return existing_rows
        
    def get_existing_submission_ids(self) -> List[str]:
        """
        Get list of existing submission IDs to avoid duplicates
        
        Returns:
            List of original_submission_id values from existing CSV
        """
        existing_rows = self.read_existing_csv()
        return [row.get('original_submission_id', '') for row in existing_rows]


def create_sample_csv_output(output_file: str) -> None:
    """
    Create a sample CSV file with the correct schema for testing
    
    Args:
        output_file: Path to output CSV file
    """
    formatter = MilestoneCSVFormatter(output_file)
    
    # Sample data
    sample_milestone = MilestoneData(
        is_milestone=True,
        title="Sample Milestone for Testing",
        value="Test value",
        categories=["scoring", "league"],
        description="This is a test milestone to verify CSV schema",
        previous_record="Previous test record",
        player_name="Caitlin Clark",
        date_context="2024-08-27",
        source_reliability=0.9
    )
    
    sample_tweet = ScrapedTweet(
        id="test123",
        text="Sample test tweet",
        author="Test Author", 
        author_handle="@testauthor",
        created_at=datetime.now(),
        retweet_count=0,
        like_count=0,
        reply_count=0,
        quote_count=0,
        view_count=0,
        url="https://twitter.com/test/status/123",
        images=[],
        is_retweet=False,
        is_quote=False
    )
    
    formatter.write_milestones_to_csv([sample_milestone], [sample_tweet])
    logger.info(f"Created sample CSV at {output_file}")