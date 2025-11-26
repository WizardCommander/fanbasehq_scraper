"""
Monitoring Service
Tracks scraper metrics and health for production monitoring
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from config.settings import SCRAPER_TYPES

logger = logging.getLogger(__name__)


@dataclass
class ScraperRunMetrics:
    """Metrics for a single scraper run"""

    scraper_type: str  # milestones, shoes, tunnel-fits
    timestamp: str
    items_found: int
    posts_processed: int
    duration_seconds: float
    errors: List[str]
    success: bool
    output_file: str
    date_range: str  # "2024-01-01 to 2024-01-31"


class MonitoringService:
    """Service for tracking scraper metrics and health"""

    def __init__(self, metrics_file: Optional[Path] = None):
        self.metrics_file = metrics_file or Path("output/scraper_metrics.json")
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def log_scraper_run(
        self,
        scraper_type: str,
        items_found: int,
        posts_processed: int,
        duration_seconds: float,
        errors: List[str],
        success: bool,
        output_file: str,
        date_range: str = "",
    ) -> None:
        """
        Log metrics for a scraper run

        Args:
            scraper_type: Type of scraper (milestones, shoes, tunnel-fits)
            items_found: Number of items scraped
            posts_processed: Number of posts processed (Twitter + Instagram)
            duration_seconds: Duration of scraper run in seconds
            errors: List of error messages
            success: Whether the scraper succeeded
            output_file: Path to output CSV file
            date_range: Date range scraped (optional)
        """
        try:
            metrics = ScraperRunMetrics(
                scraper_type=scraper_type,
                timestamp=datetime.now().isoformat(),
                items_found=items_found,
                posts_processed=posts_processed,
                duration_seconds=duration_seconds,
                errors=errors,
                success=success,
                output_file=output_file,
                date_range=date_range,
            )

            # Load existing metrics
            all_metrics = self._load_metrics()

            # Append new metrics
            all_metrics.append(asdict(metrics))

            # Save metrics
            self._save_metrics(all_metrics)

            logger.info(
                f"Logged {scraper_type} scraper run: {items_found} items, {posts_processed} posts, {duration_seconds:.1f}s"
            )

        except Exception as e:
            logger.error(f"Failed to log scraper metrics: {e}")

    def get_daily_summary(self, date: Optional[datetime] = None) -> Dict:
        """
        Get summary of all scraper runs for a given date

        Args:
            date: Date to get summary for (defaults to today)

        Returns:
            Dictionary with daily summary metrics
        """
        if date is None:
            date = datetime.now()

        target_date = date.date()
        all_metrics = self._load_metrics()

        # Filter metrics for target date
        daily_metrics = []
        for metric in all_metrics:
            metric_date = datetime.fromisoformat(metric["timestamp"]).date()
            if metric_date == target_date:
                daily_metrics.append(metric)

        if not daily_metrics:
            return {
                "date": target_date.isoformat(),
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "total_items": 0,
                "total_posts": 0,
                "total_duration": 0,
                "scraper_types": {},
            }

        # Calculate summary statistics
        total_runs = len(daily_metrics)
        successful_runs = sum(1 for m in daily_metrics if m["success"])
        failed_runs = total_runs - successful_runs
        total_items = sum(m["items_found"] for m in daily_metrics)
        total_posts = sum(m["posts_processed"] for m in daily_metrics)
        total_duration = sum(m["duration_seconds"] for m in daily_metrics)

        # Group by scraper type
        scraper_types = {}
        for metric in daily_metrics:
            scraper_type = metric["scraper_type"]
            if scraper_type not in scraper_types:
                scraper_types[scraper_type] = {
                    "runs": 0,
                    "items": 0,
                    "posts": 0,
                    "success": 0,
                }

            scraper_types[scraper_type]["runs"] += 1
            scraper_types[scraper_type]["items"] += metric["items_found"]
            scraper_types[scraper_type]["posts"] += metric["posts_processed"]
            if metric["success"]:
                scraper_types[scraper_type]["success"] += 1

        return {
            "date": target_date.isoformat(),
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "total_items": total_items,
            "total_posts": total_posts,
            "total_duration": round(total_duration, 1),
            "scraper_types": scraper_types,
        }

    def check_health(self, days_threshold: int = 7) -> Dict:
        """
        Check scraper health and detect issues

        Args:
            days_threshold: Number of consecutive days with no results to trigger warning (default: 7)

        Returns:
            Dictionary with health status and warnings
        """
        all_metrics = self._load_metrics()

        if not all_metrics:
            return {
                "healthy": False,
                "warnings": ["No scraper metrics found - scrapers may not be running"],
                "last_successful_run": None,
            }

        # Get recent metrics (last 3 days for activity check)
        activity_cutoff = datetime.now() - timedelta(days=3)
        recent_metrics = [
            m
            for m in all_metrics
            if datetime.fromisoformat(m["timestamp"]) > activity_cutoff
        ]

        if not recent_metrics:
            return {
                "healthy": False,
                "warnings": [f"No scraper runs in the last 3 days - check cron jobs"],
                "last_successful_run": None,
            }

        # Find last successful run
        successful_runs = [m for m in recent_metrics if m["success"]]
        last_successful = None
        if successful_runs:
            last_successful = max(successful_runs, key=lambda m: m["timestamp"])[
                "timestamp"
            ]

        # Check for consecutive days with failed runs (not zero results)
        warnings = []
        consecutive_failure_days = self._check_consecutive_failed_runs(
            recent_metrics, days_threshold
        )

        if consecutive_failure_days >= days_threshold:
            warnings.append(
                f"{consecutive_failure_days} consecutive days with failed scraper runs - check scraper configuration"
            )

        # Check for high error rates
        error_rate = self._calculate_error_rate(recent_metrics)
        if error_rate > 0.5:  # More than 50% failures
            warnings.append(
                f"High error rate: {error_rate*100:.1f}% of runs failed in last 3 days"
            )

        # Check for specific scraper types not running
        scraper_types_seen = set(m["scraper_type"] for m in recent_metrics)
        expected_types = set(SCRAPER_TYPES)
        missing_types = expected_types - scraper_types_seen

        if missing_types:
            warnings.append(
                f"Missing scraper types: {', '.join(missing_types)} have not run in 3 days"
            )

        healthy = len(warnings) == 0

        # Count successful runs with zero items (normal behavior)
        successful_zero_items = [
            m for m in recent_metrics if m["success"] and m["items_found"] == 0
        ]

        return {
            "healthy": healthy,
            "warnings": warnings,
            "last_successful_run": last_successful,
            "recent_runs": len(recent_metrics),
            "error_rate": round(error_rate, 2),
            "successful_zero_item_runs": len(successful_zero_items),
            "note": "Zero items found in successful runs is normal when no new data is available",
        }

    def _load_metrics(self) -> List[Dict]:
        """Load metrics from JSON file"""
        if not self.metrics_file.exists():
            return []

        try:
            with open(self.metrics_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Corrupted metrics file: {self.metrics_file}")
            return []
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
            return []

    def _save_metrics(self, metrics: List[Dict]) -> None:
        """Save metrics to JSON file"""
        try:
            # Keep only last 90 days of metrics
            cutoff_date = datetime.now() - timedelta(days=90)
            filtered_metrics = [
                m
                for m in metrics
                if datetime.fromisoformat(m["timestamp"]) > cutoff_date
            ]

            with open(self.metrics_file, "w") as f:
                json.dump(filtered_metrics, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def _check_consecutive_failed_runs(
        self, metrics: List[Dict], threshold: int
    ) -> int:
        """Check for consecutive days with only failed runs (not zero results)"""
        # Group metrics by date and check if all runs failed
        dates_with_failures = {}
        for metric in metrics:
            metric_date = datetime.fromisoformat(metric["timestamp"]).date()
            if metric_date not in dates_with_failures:
                dates_with_failures[metric_date] = []
            dates_with_failures[metric_date].append(metric["success"])

        # Check consecutive days with all failed runs
        consecutive_failures = 0
        max_consecutive = 0

        # Check last N days
        for i in range(threshold + 1):
            check_date = (datetime.now() - timedelta(days=i)).date()
            if check_date in dates_with_failures:
                # Check if ALL runs on this day failed
                day_successes = dates_with_failures[check_date]
                if not any(day_successes):  # All runs failed
                    consecutive_failures += 1
                    max_consecutive = max(max_consecutive, consecutive_failures)
                else:
                    consecutive_failures = 0
            else:
                # No data for this day - treat as failure (scraper didn't run)
                consecutive_failures += 1
                max_consecutive = max(max_consecutive, consecutive_failures)

        return max_consecutive

    def _calculate_error_rate(self, metrics: List[Dict]) -> float:
        """Calculate error rate from metrics"""
        if not metrics:
            return 0.0

        total_runs = len(metrics)
        failed_runs = sum(1 for m in metrics if not m["success"])

        return failed_runs / total_runs if total_runs > 0 else 0.0
