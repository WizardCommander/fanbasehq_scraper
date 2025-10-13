#!/bin/bash
# FanbaseHQ Scraper - Production Setup Script
# One-command setup for DigitalOcean droplet

set -e  # Exit on error

echo "========================================="
echo "FanbaseHQ Scraper - Production Setup"
echo "========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: Check prerequisites
echo "Step 1: Checking prerequisites..."
echo "-----------------------------------"

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then
   echo -e "${YELLOW}Warning: Running as root. Consider using a non-root user with sudo.${NC}"
fi

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Installing...${NC}"
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}✓ Python version: $(python3 --version)${NC}"

# Check if virtualenv exists and is valid
if [ ! -d "$PROJECT_ROOT/venv" ] || [ ! -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    if [ -d "$PROJECT_ROOT/venv" ]; then
        echo -e "${YELLOW}⚠ Removing incomplete virtual environment...${NC}"
        rm -rf "$PROJECT_ROOT/venv"
    fi
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_ROOT/venv"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Step 2: Install dependencies
echo ""
echo "Step 2: Installing Python dependencies..."
echo "-----------------------------------"

source "$PROJECT_ROOT/venv/bin/activate"

pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"

echo -e "${GREEN}✓ Python dependencies installed${NC}"

# Step 3: Install Playwright browsers
echo ""
echo "Step 3: Installing Playwright browsers..."
echo "-----------------------------------"

playwright install chromium
playwright install-deps chromium

echo -e "${GREEN}✓ Playwright browsers installed${NC}"

# Step 4: Setup configuration
echo ""
echo "Step 4: Setting up configuration..."
echo "-----------------------------------"

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/config/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.production.example" ]; then
        echo "Copying .env.production.example to config/.env..."
        cp "$SCRIPT_DIR/.env.production.example" "$PROJECT_ROOT/config/.env"
        echo -e "${YELLOW}⚠ IMPORTANT: Edit config/.env with your API keys!${NC}"
        echo "   - OPENAI_API_KEY"
        echo "   - TWITTER_API_KEY"
        echo "   - SMTP credentials"
    else
        echo -e "${YELLOW}⚠ No .env.production.example found. Please create config/.env manually.${NC}"
    fi
else
    echo -e "${GREEN}✓ config/.env already exists${NC}"
fi

# Create output directory
mkdir -p "$PROJECT_ROOT/output"
echo -e "${GREEN}✓ Output directory created${NC}"

# Step 5: Test email delivery
echo ""
echo "Step 5: Testing email configuration..."
echo "-----------------------------------"

read -p "Do you want to test email delivery? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Attempting to send test email..."
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from services.email_service import EmailService
from config.settings import NOTIFICATION_EMAIL

email_service = EmailService()
if NOTIFICATION_EMAIL:
    result = email_service.send_test_email()
    if result:
        print('✓ Test email sent successfully to $NOTIFICATION_EMAIL')
    else:
        print('✗ Failed to send test email - check SMTP settings in config/.env')
else:
    print('⚠ NOTIFICATION_EMAIL not configured in config/.env')
"
fi

# Step 6: Setup cron jobs
echo ""
echo "Step 6: Setting up cron jobs..."
echo "-----------------------------------"

read -p "Do you want to install cron jobs for automatic daily scraping? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Add cron jobs
    CRON_FILE="$SCRIPT_DIR/cron_schedule"

    if [ -f "$CRON_FILE" ]; then
        # Read existing crontab
        crontab -l > /tmp/current_crontab 2>/dev/null || true

        # Check if our cron jobs already exist
        if grep -q "fanbasehq-scraper" /tmp/current_crontab 2>/dev/null; then
            echo -e "${YELLOW}⚠ Cron jobs already installed${NC}"
        else
            # Replace PROJECT_ROOT placeholder with actual path
            sed "s|PROJECT_ROOT|$PROJECT_ROOT|g" "$CRON_FILE" >> /tmp/current_crontab

            # Install new crontab
            crontab /tmp/current_crontab

            echo -e "${GREEN}✓ Cron jobs installed${NC}"
            echo "Cron schedule:"
            grep "fanbasehq-scraper" /tmp/current_crontab
        fi

        rm /tmp/current_crontab
    else
        echo -e "${YELLOW}⚠ cron_schedule file not found${NC}"
    fi
fi

# Step 7: Run test scrape
echo ""
echo "Step 7: Running test scrape..."
echo "-----------------------------------"

read -p "Do you want to run a test scrape (last 7 days, milestones)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SEVEN_DAYS_AGO=$(date -d "7 days ago" +%Y-%m-%d)
    TODAY=$(date +%Y-%m-%d)

    echo "Running: python main.py --player 'caitlin clark' --type milestones --start-date $SEVEN_DAYS_AGO --end-date $TODAY --limit 20"

    cd "$PROJECT_ROOT"
    source venv/bin/activate
    python main.py --player "caitlin clark" --type milestones --start-date "$SEVEN_DAYS_AGO" --end-date "$TODAY" --limit 20

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Test scrape completed successfully${NC}"
    else
        echo -e "${RED}✗ Test scrape failed - check logs above${NC}"
    fi
fi

# Final summary
echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next Steps:"
echo "1. Edit config/.env with your API keys"
echo "2. Test email delivery: python -c 'from services.email_service import EmailService; EmailService().send_test_email()'"
echo "3. Run manual scrape: python main.py --player 'caitlin clark' --type milestones"
echo "4. Check cron jobs: crontab -l"
echo ""
echo "For more information, see PRODUCTION_GUIDE.md"
echo ""
