#!/bin/bash
# FanbaseHQ Scraper - Daily Automated Run
# Orchestrates all 3 scrapers and emails results

set -e  # Exit on error

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Change to project directory
cd "$PROJECT_ROOT"

# Calculate date range (yesterday's data)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)

echo "========================================="
echo "FanbaseHQ Daily Scraper"
echo "Date: $TODAY"
echo "Scraping date range: $YESTERDAY to $YESTERDAY"
echo "========================================="
echo ""

# Function to run scraper with error handling
run_scraper() {
    SCRAPER_TYPE=$1
    echo "Running $SCRAPER_TYPE scraper..."
    echo "-----------------------------------"

    if python main.py \
        --player "caitlin clark" \
        --type "$SCRAPER_TYPE" \
        --start-date "$YESTERDAY" \
        --end-date "$YESTERDAY" \
        --limit 100; then
        echo "✓ $SCRAPER_TYPE scraper completed successfully"
    else
        echo "✗ $SCRAPER_TYPE scraper failed"
        return 1
    fi

    echo ""
}

# Track failures
FAILED_SCRAPERS=()

# Run all 3 scrapers
run_scraper "milestones" || FAILED_SCRAPERS+=("milestones")
run_scraper "shoes" || FAILED_SCRAPERS+=("shoes")
run_scraper "tunnel-fits" || FAILED_SCRAPERS+=("tunnel-fits")

# Summary
echo "========================================="
echo "Daily Scrape Complete"
echo "========================================="
echo ""

if [ ${#FAILED_SCRAPERS[@]} -eq 0 ]; then
    echo "✓ All scrapers completed successfully"
    exit 0
else
    echo "✗ Failed scrapers: ${FAILED_SCRAPERS[*]}"
    exit 1
fi
