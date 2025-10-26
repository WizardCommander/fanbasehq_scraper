#!/usr/bin/env python3
"""
Caitlin Clark Data Scraper for FanbaseHQ
Modular scraper for WNBA player milestones, shoes, and tunnel fits
"""

import argparse
import asyncio
import sys
import logging
import os
from datetime import date
from pathlib import Path

# Add the project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import VenvManager after path setup
from utils.venv_manager import VenvManager

# Ensure virtual environment is ready before proceeding
try:
    venv_manager = VenvManager(project_root=PROJECT_ROOT)
    venv_manager.ensure_venv_ready()
except Exception as e:
    print(f"ERROR: Virtual environment setup failed: {e}")
    sys.exit(1)

# Fix Python 3.12 compatibility for aiohttp
import fix_collections

from scrapers.milestone_scraper import MilestoneScraper
from services.email_service import EmailService
from services.monitoring_service import MonitoringService
from utils.date_utils import parse_date, validate_date_range
from config.settings import ENABLE_EMAIL_DELIVERY, NOTIFICATION_EMAIL, SCRAPER_TYPES
import time

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
        """,
    )

    # Required arguments
    parser.add_argument(
        "--player", required=True, help='Player name to scrape (e.g., "caitlin clark")'
    )

    # Optional arguments with defaults
    parser.add_argument(
        "--type",
        choices=SCRAPER_TYPES,
        default="milestones",
        help="Type of content to scrape (default: milestones)",
    )

    parser.add_argument(
        "--start-date", help="Start date for scraping (YYYY-MM-DD, default: 2024-04-01)"
    )

    parser.add_argument(
        "--end-date", help="End date for scraping (YYYY-MM-DD, default: today)"
    )

    parser.add_argument(
        "--output", help="Output CSV file path (default: output/{type}.csv)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of posts to process (default: 100)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be scraped without actually scraping",
    )

    parser.add_argument(
        "--email", help="Email address to send results to (overrides config)"
    )

    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Disable email delivery even if configured",
    )

    args = parser.parse_args()

    # Set default dates
    if not args.start_date:
        args.start_date = "2024-04-01"
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
        output_dir = PROJECT_ROOT / "output"
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

    # Initialize services for email and monitoring
    email_service = EmailService()
    monitoring_service = MonitoringService()

    # Determine email recipient
    email_recipient = args.email or NOTIFICATION_EMAIL if not args.no_email else None
    should_send_email = ENABLE_EMAIL_DELIVERY and email_recipient and not args.no_email

    # Track scraping duration
    start_time = time.time()
    errors = []
    success = False

    try:
        if args.type == "milestones":
            scraper = MilestoneScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit,
            )
            results = await scraper.scrape_milestones()
            success = True
            logger.info(
                f"Successfully scraped {results['milestones_found']} milestones"
            )
            logger.info(f"Results saved to: {args.output}")

        elif args.type == "shoes":
            from scrapers.shoe_scraper import ShoeScraper

            scraper = ShoeScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit,
            )
            results = await scraper.run()
            success = True
            logger.info(f"Successfully scraped {results['shoes_found']} shoes")
            logger.info(f"Results saved to: {args.output}")

        elif args.type == "tunnel-fits":
            from scrapers.tunnel_fit_scraper import TunnelFitScraper

            scraper = TunnelFitScraper.create_from_legacy_params(
                player=args.player,
                start_date=start_date,
                end_date=end_date,
                output_file=str(args.output),
                limit=args.limit,
            )
            results = await scraper.run()
            success = True
            logger.info(
                f"Successfully scraped {results['tunnel_fits_found']} tunnel fits"
            )
            logger.info(f"Results saved to: {args.output}")

        # Calculate duration
        duration = time.time() - start_time

        # Log metrics to monitoring service
        items_key = {
            "milestones": "milestones_found",
            "shoes": "shoes_found",
            "tunnel-fits": "tunnel_fits_found",
        }.get(args.type, "items_found")

        monitoring_service.log_scraper_run(
            scraper_type=args.type,
            items_found=results.get(items_key, 0),
            tweets_processed=results.get("tweets_processed", 0),
            duration_seconds=duration,
            errors=errors,
            success=success,
            output_file=str(args.output),
            date_range=f"{args.start_date} to {args.end_date}",
        )

        # Send email with results if configured and items were found
        items_found = results.get(items_key, 0)
        if should_send_email and success and items_found > 0:
            logger.info(f"Sending results email to {email_recipient}")
            metrics = {
                "Scraper Type": args.type,
                "Items Found": items_found,
                "Tweets Processed": results.get("tweets_processed", 0),
                "Duration": f"{duration:.1f}s",
                "Date Range": f"{args.start_date} to {args.end_date}",
            }

            email_sent = email_service.send_daily_results(
                csv_files=[Path(args.output)],
                metrics=metrics,
                recipient=email_recipient,
            )

            if email_sent:
                logger.info("Results email sent successfully")
            else:
                logger.warning("Failed to send results email")
        elif should_send_email and success and items_found == 0:
            logger.info(f"No items found - skipping email delivery")

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        errors.append("Interrupted by user")

        # Log failed run
        duration = time.time() - start_time
        monitoring_service.log_scraper_run(
            scraper_type=args.type,
            items_found=0,
            tweets_processed=0,
            duration_seconds=duration,
            errors=errors,
            success=False,
            output_file=str(args.output),
            date_range=f"{args.start_date} to {args.end_date}",
        )
        return 1

    except Exception as e:
        logger.error(f"Error during scraping: {e}")
        errors.append(str(e))

        # Log failed run
        duration = time.time() - start_time
        monitoring_service.log_scraper_run(
            scraper_type=args.type,
            items_found=0,
            tweets_processed=0,
            duration_seconds=duration,
            errors=errors,
            success=False,
            output_file=str(args.output),
            date_range=f"{args.start_date} to {args.end_date}",
        )

        # Send error alert email if configured
        if should_send_email:
            logger.info(f"Sending error alert email to {email_recipient}")
            email_service.send_error_alert(
                error=e,
                scraper_type=args.type,
                recipient=email_recipient,
                additional_context={
                    "Player": args.player,
                    "Date Range": f"{args.start_date} to {args.end_date}",
                    "Output File": str(args.output),
                },
            )

        return 1

    return 0


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sys.exit(asyncio.run(main()))
