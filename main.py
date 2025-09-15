#!/usr/bin/env python3
"""
Caitlin Clark Data Scraper for FanbaseHQ
Modular scraper for WNBA player milestones, shoes, and tunnel fits
"""

import argparse
import asyncio
import sys
import logging
from datetime import date
from pathlib import Path

# Add the project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Fix Python 3.12 compatibility for aiohttp
import fix_collections

from scrapers.milestone_scraper import MilestoneScraper
from utils.date_utils import parse_date, validate_date_range

# Set up logging
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Scrape WNBA player data for FanbaseHQ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --player "caitlin clark" --type milestones
  python main.py --player "caitlin clark" --start-date 2024-04-01 --end-date 2024-08-27
  python main.py --player "caitlin clark" --type milestones --output custom_output.csv
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--player', 
        required=True,
        help='Player name to scrape (e.g., "caitlin clark")'
    )
    
    # Optional arguments with defaults
    parser.add_argument(
        '--type',
        choices=['milestones', 'shoes', 'tunnel-fits'],
        default='milestones',
        help='Type of content to scrape (default: milestones)'
    )
    
    parser.add_argument(
        '--start-date',
        help='Start date for scraping (YYYY-MM-DD, default: 2024-04-01)'
    )
    
    parser.add_argument(
        '--end-date',
        help='End date for scraping (YYYY-MM-DD, default: today)'
    )
    
    parser.add_argument(
        '--output',
        help='Output CSV file path (default: output/{type}.csv)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum number of posts to process (default: 100)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be scraped without actually scraping'
    )
    
    args = parser.parse_args()
    
    # Set default dates
    if not args.start_date:
        args.start_date = '2024-04-01'
    if not args.end_date:
        args.end_date = date.today().isoformat()
    
    # Validate dates
    try:
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date)
        validate_date_range(start_date, end_date)
    except ValueError as e:
        logger.error(f"Date validation error: {e}")
        return 1
    
    # Set default output path
    if not args.output:
        output_dir = PROJECT_ROOT / 'output'
        output_dir.mkdir(exist_ok=True)
        args.output = output_dir / f"{args.type.replace('-', '_')}.csv"
    
    logger.info("FanbaseHQ Scraper Starting...")
    logger.info(f"Player: {args.player}")
    logger.info(f"Type: {args.type}")
    logger.info(f"Date range: {args.start_date} to {args.end_date}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Limit: {args.limit} posts")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No actual scraping will occur")
        return 0
    
    try:
        if args.type == 'milestones':
            scraper = MilestoneScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit
            )
            results = scraper.run()
            logger.info(f"Successfully scraped {results['milestones_found']} milestones")
            logger.info(f"Results saved to: {args.output}")
            
        elif args.type == 'shoes':
            from scrapers.shoe_scraper import ShoeScraper
            scraper = ShoeScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit
            )
            results = await scraper.run()
            logger.info(f"Successfully scraped {results['shoes_found']} shoes")
            logger.info(f"Results saved to: {args.output}")
            
        elif args.type == 'tunnel-fits':
            from scrapers.tunnel_fit_scraper import TunnelFitScraper
            scraper = TunnelFitScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit
            )
            results = await scraper.run()
            logger.info(f"Successfully scraped {results['tunnel_fits_found']} tunnel fits")
            logger.info(f"Results saved to: {args.output}")
            
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    sys.exit(asyncio.run(main()))