#!/usr/bin/env bash
set -eo pipefail

# ==============================
# Setup & Environment
# ==============================

export TZ="America/Chicago"  # Lock to your local timezone

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_ROOT/venv/bin/activate"
PYTHON="$PROJECT_ROOT/venv/bin/python"

mkdir -p "$PROJECT_ROOT/logs"
LOG_FILE="$PROJECT_ROOT/logs/scrape_$(date +%F).log"
exec > >(tee -a "$LOG_FILE") 2>&1

# ==============================
# Date Range (full 48h overlap for safety)
# ==============================
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
TOMORROW=$(date -d "tomorrow" +%Y-%m-%d)

echo "========================================="
echo "FanbaseHQ Daily Scraper"
echo "Run Date: $(date)"
echo "Scraping range: $YESTERDAY → $TOMORROW"
echo "========================================="
echo ""

EMAIL_TO="you@example.com"
EMAIL_SUBJECT="FanbaseHQ Daily Report - $(date +%F)"

run_scraper() {
    local SCRAPER_TYPE=$1
    local TMP_OUT="/tmp/${SCRAPER_TYPE}_$(date +%s).txt"

    echo "$(date '+%F %T') - Running $SCRAPER_TYPE scraper..."
    echo "-----------------------------------"

    if "$PYTHON" "$PROJECT_ROOT/main.py" \
        --player "caitlin clark" \
        --type "$SCRAPER_TYPE" \
        --start-date "$YESTERDAY" \
        --end-date "$TOMORROW" \
        --limit 100 | tee "$TMP_OUT"; then
        echo "✓ $SCRAPER_TYPE scraper completed successfully"
    else
        echo "✗ $SCRAPER_TYPE scraper failed"
        return 1
    fi
    echo ""

    # If scraper produced meaningful output, send it by email
    if grep -qE '[A-Za-z0-9]' "$TMP_OUT"; then
        echo "📨 Sending email for $SCRAPER_TYPE (data found)"
        mail -s "$EMAIL_SUBJECT ($SCRAPER_TYPE)" "$EMAIL_TO" < "$TMP_OUT"
    else
        echo "No new data found for $SCRAPER_TYPE"
    fi

    rm -f "$TMP_OUT"
}

declare -a FAILED_SCRAPERS=()
run_scraper "milestones" || FAILED_SCRAPERS+=("milestones")
run_scraper "shoes" || FAILED_SCRAPERS+=("shoes")
run_scraper "tunnel-fits" || FAILED_SCRAPERS+=("tunnel-fits")

echo "========================================="
echo "Daily Scrape Complete"
echo "========================================="
echo ""

if [ ${#FAILED_SCRAPERS[@]} -eq 0 ]; then
    echo "✓ All scrapers completed successfully"
else
    echo "✗ Failed scrapers: ${FAILED_SCRAPERS[*]}"
    echo "Failed scrapers: ${FAILED_SCRAPERS[*]}" | mail -s "FanbaseHQ Scraper Failures - $(date +%F)" "$EMAIL_TO"
    exit 1
fi
