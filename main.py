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
import json
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


def load_all_players() -> list[str]:
    """
    Load all player names from config/players.json

    Returns:
        List of player names (lowercase keys from config)

    Raises:
        FileNotFoundError: If config/players.json doesn't exist
    """
    players_config_path = PROJECT_ROOT / "config" / "players.json"

    if not players_config_path.exists():
        raise FileNotFoundError(f"Players config not found: {players_config_path}")

    with open(players_config_path, "r", encoding="utf-8") as f:
        players_data = json.load(f)

    return list(players_data.keys())


def get_player_output_path(player_name: str, content_type: str) -> Path:
    """
    Generate output file path for a player

    Args:
        player_name: Player name (e.g., "Caitlin Clark")
        content_type: Content type (e.g., "milestones")

    Returns:
        Path object for output CSV file
    """
    # Normalize player name: lowercase, remove apostrophes, replace spaces with underscores
    normalized_name = player_name.lower().replace("'", "").replace(" ", "_")

    filename = f"{normalized_name}_{content_type}.csv"
    return PROJECT_ROOT / "output" / filename


def validate_player_args(player: str | None, all_players: bool) -> None:
    """
    Validate that either --player or --all-players is specified, but not both

    Args:
        player: Player name from --player argument
        all_players: Boolean from --all-players flag

    Raises:
        ValueError: If validation fails
    """
    if player and all_players:
        raise ValueError("Cannot specify both --player and --all-players")

    if not player and not all_players:
        raise ValueError("Must specify either --player or --all-players")


async def scrape_single_player(
    player_name: str,
    content_type: str,
    start_date: date,
    end_date: date,
    output_file: Path,
    limit: int,
    email_service: EmailService,
    monitoring_service: MonitoringService,
    email_recipient: str | None,
    should_send_email: bool,
) -> dict:
    """
    Scrape data for a single player

    Args:
        player_name: Player name to scrape
        content_type: Type of content ("milestones", "shoes", "tunnel-fits")
        start_date: Start date for scraping
        end_date: End date for scraping
        output_file: Output CSV file path
        limit: Maximum number of posts to process
        email_service: Email service instance
        monitoring_service: Monitoring service instance
        email_recipient: Email recipient for notifications
        should_send_email: Whether to send email notifications

    Returns:
        Dictionary with scraping results and metadata
    """
    start_time = time.time()
    errors = []
    success = False

    try:
        logger.info(f"Scraping {content_type} for {player_name}...")

        if content_type == "milestones":
            scraper = MilestoneScraper.create_from_legacy_params(
                player=player_name,
                start_date=start_date,
                end_date=end_date,
                output_file=str(output_file),
                limit=limit,
            )
            results = await scraper.scrape_milestones()
            success = True
            items_found = results["milestones_found"]

        elif content_type == "shoes":
            from scrapers.shoe_scraper import ShoeScraper

            scraper = ShoeScraper.create_from_legacy_params(
                player=player_name,
                start_date=start_date,
                end_date=end_date,
                output_file=str(output_file),
                limit=limit,
            )
            results = await scraper.run()
            success = True
            items_found = results["shoes_found"]

        elif content_type == "tunnel-fits":
            from scrapers.tunnel_fit_scraper import TunnelFitScraper

            scraper = TunnelFitScraper.create_from_legacy_params(
                player=player_name,
                start_date=start_date,
                end_date=end_date,
                output_file=str(output_file),
                limit=limit,
            )
            results = await scraper.run()
            success = True
            items_found = results["tunnel_fits_found"]

        duration = time.time() - start_time

        # Log metrics
        items_key = {
            "milestones": "milestones_found",
            "shoes": "shoes_found",
            "tunnel-fits": "tunnel_fits_found",
        }.get(content_type, "items_found")

        monitoring_service.log_scraper_run(
            scraper_type=content_type,
            items_found=results.get(items_key, 0),
            tweets_processed=results.get("tweets_processed", 0),
            duration_seconds=duration,
            errors=errors,
            success=success,
            output_file=str(output_file),
            date_range=f"{start_date} to {end_date}",
        )

        # Send email if configured and items found
        if should_send_email and success and items_found > 0:
            logger.info(f"Sending results email to {email_recipient}")
            metrics = {
                "Player": player_name,
                "Scraper Type": content_type,
                "Items Found": items_found,
                "Tweets Processed": results.get("tweets_processed", 0),
                "Duration": f"{duration:.1f}s",
            }

            email_service.send_daily_results(
                csv_files=[output_file],
                metrics=metrics,
                recipient=email_recipient,
            )

        return {
            "player": player_name,
            "success": success,
            "items_found": items_found,
            "duration": duration,
            "output_file": str(output_file),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error scraping {player_name}: {e}")
        errors.append(str(e))
        duration = time.time() - start_time

        monitoring_service.log_scraper_run(
            scraper_type=content_type,
            items_found=0,
            tweets_processed=0,
            duration_seconds=duration,
            errors=errors,
            success=False,
            output_file=str(output_file),
            date_range=f"{start_date} to {end_date}",
        )

        return {
            "player": player_name,
            "success": False,
            "items_found": 0,
            "duration": duration,
            "output_file": str(output_file),
            "errors": errors,
        }


async def scrape_all_players(
    content_type: str,
    start_date: date,
    end_date: date,
    limit: int,
    email_service: EmailService,
    monitoring_service: MonitoringService,
    email_recipient: str | None,
    should_send_email: bool,
) -> list[dict]:
    """
    Scrape data for all players sequentially

    Args:
        content_type: Type of content to scrape
        start_date: Start date for scraping
        end_date: End date for scraping
        limit: Maximum number of posts to process per player
        email_service: Email service instance
        monitoring_service: Monitoring service instance
        email_recipient: Email recipient for notifications
        should_send_email: Whether to send email notifications

    Returns:
        List of result dictionaries for each player
    """
    players = load_all_players()
    results = []

    logger.info(f"Starting sequential scraping for {len(players)} players...")

    for player_name in players:
        output_file = get_player_output_path(player_name, content_type)

        result = await scrape_single_player(
            player_name=player_name,
            content_type=content_type,
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            email_service=email_service,
            monitoring_service=monitoring_service,
            email_recipient=email_recipient,
            should_send_email=should_send_email,
        )

        results.append(result)

    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Scrape WNBA player data for FanbaseHQ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single player
  python main.py --player "caitlin clark" --type milestones
  python main.py --player "paige bueckers" --type shoes --start-date 2024-04-01

  # All players
  python main.py --all-players --type milestones
  python main.py --all-players --type shoes --start-date 2024-04-01 --end-date 2024-08-27
        """,
    )

    # Player selection (either --player or --all-players required)
    parser.add_argument(
        "--player", help='Player name to scrape (e.g., "caitlin clark")'
    )

    parser.add_argument(
        "--all-players",
        action="store_true",
        help="Scrape all players from config/players.json sequentially",
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

    # Validate player arguments
    try:
        validate_player_args(player=args.player, all_players=args.all_players)
    except ValueError as e:
        logger.error(f"Argument validation error: {e}")
        parser.print_help()
        return 1

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

    if args.all_players:
        logger.info("Mode: All players (sequential)")
        logger.info(f"Type: {args.type}")
        logger.info(f"Date range: {args.start_date} to {args.end_date}")
        logger.info(f"Limit: {args.limit} posts per player")
    else:
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

    try:
        if args.all_players:
            # Multi-player mode
            results_list = await scrape_all_players(
                content_type=args.type,
                start_date=start_date,
                end_date=end_date,
                limit=args.limit,
                email_service=email_service,
                monitoring_service=monitoring_service,
                email_recipient=email_recipient,
                should_send_email=should_send_email,
            )

            # Print summary
            logger.info("\n" + "=" * 60)
            logger.info("ALL PLAYERS SCRAPING SUMMARY")
            logger.info("=" * 60)

            total_items = 0
            successful = 0
            failed = 0

            for result in results_list:
                status = "✓" if result["success"] else "✗"
                logger.info(
                    f"{status} {result['player']}: {result['items_found']} items "
                    f"({result['duration']:.1f}s) - {result['output_file']}"
                )

                if result["success"]:
                    successful += 1
                    total_items += result["items_found"]
                else:
                    failed += 1
                    if result["errors"]:
                        logger.error(f"  Errors: {', '.join(result['errors'])}")

            logger.info("=" * 60)
            logger.info(f"Total: {successful} successful, {failed} failed")
            logger.info(f"Total items found: {total_items}")
            logger.info("=" * 60)

            return 0 if failed == 0 else 1

        else:
            # Single player mode (existing logic)
            output_file = Path(args.output)

            result = await scrape_single_player(
                player_name=args.player,
                content_type=args.type,
                start_date=start_date,
                end_date=end_date,
                output_file=output_file,
                limit=args.limit,
                email_service=email_service,
                monitoring_service=monitoring_service,
                email_recipient=email_recipient,
                should_send_email=should_send_email,
            )

            if result["success"]:
                logger.info(
                    f"Successfully scraped {result['items_found']} items for {args.player}"
                )
                logger.info(f"Results saved to: {args.output}")
                return 0
            else:
                logger.error(f"Scraping failed for {args.player}")
                if result["errors"]:
                    logger.error(f"Errors: {', '.join(result['errors'])}")

                # Send error alert email if configured
                if should_send_email:
                    logger.info(f"Sending error alert email to {email_recipient}")
                    email_service.send_error_alert(
                        error=Exception("; ".join(result["errors"])),
                        scraper_type=args.type,
                        recipient=email_recipient,
                        additional_context={
                            "Player": args.player,
                            "Date Range": f"{args.start_date} to {args.end_date}",
                            "Output File": str(args.output),
                        },
                    )

                return 1

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"Error during scraping: {e}")

        # Send error alert email if configured
        if should_send_email and not args.all_players:
            logger.info(f"Sending error alert email to {email_recipient}")
            email_service.send_error_alert(
                error=e,
                scraper_type=args.type,
                recipient=email_recipient,
                additional_context={
                    "Player": args.player if args.player else "All players",
                    "Date Range": f"{args.start_date} to {args.end_date}",
                    "Output File": (
                        str(args.output) if args.output else "Multiple files"
                    ),
                },
            )

        return 1


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sys.exit(asyncio.run(main()))
