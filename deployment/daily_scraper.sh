#!/usr/bin/env bash
# FanbaseHQ Scraper - Daily Automated Run
# Runs all scrapers for the last 24 hours and emails results

set -eo pipefail

# ==============================
# Setup & Environment
# ==============================

# Set timezone explicitly to prevent UTC offset issues
export TZ="America/Chicago"

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"
PYTHON="$PROJECT_ROOT/venv/bin/python"

# Logging (stored under project_root/logs)
mkdir -p "$PROJECT_ROOT/logs"
LOG_FILE="$PROJECT_ROOT/logs/scrape_$(date +%F).log"
exec > >(tee -a "$LOG_FILE") 2>&1

# ==============================
# Date Range (Last 24 Hours)
# ==============================
START=$(date -d "24 hours ago" +%Y-%m-%dT%H:%M:%S)
END=$(date +%Y-%m-%dT%H:%M:%S)

echo "========================================="
echo "FanbaseHQ Daily Scraper"
echo "Run Date: $(date)"
echo "Scraping range: $START → $END"
echo "========================================="
echo ""

# ==============================
# Scraper Function
# ==============================
run_scraper() {
    local SCRAPER_TYPE=$1
    echo "$(date '+%F %T') - Running $SCRAPER_TYPE scraper..."
    echo "-----------------------------------"

    if "$PYTHON" "$PROJECT_ROOT/main.py" \
        --player "caitlin clark" \
        --type "$SCRAPER_TYPE" \
        --start-date "$START" \
        --end-date "$END" \
        --limit 100; then
        echo "✓ $SCRAPER_TYPE scraper completed successfully"
    else
        echo "✗ $SCRAPER_TYPE scraper failed"
        return 1
    fi
    echo ""
}

# ==============================
# Run All Scrapers
# ==============================
declare -a FAILED_SCRAPERS=()

run_scraper "milestones" || FAILED_SCRAPERS+=("milestones")
run_scraper "shoes" || FAILED_SCRAPERS+=("shoes")
run_scraper "tunnel-fits" || FAILED_SCRAPERS+=("tunnel-fits")

# ==============================
# Summary
# ==============================
echo "========================================="
echo "Daily Scrape Complete"
echo "========================================="
echo ""

if [ ${#FAILED_SCRAPERS[@]} -eq 0 ]; then
    echo "✓ All scrapers completed successfully"
else
    echo "✗ Failed scrapers: ${FAILED_SCRAPERS[*]}"
    # Optional: Email or Telegram alert
    # echo "Failed scrapers: ${FAILED_SCRAPERS[*]}" | mail -s "FanbaseHQ Scraper Failures - $(date +%F)" you@example.com
    exit 1
fi
