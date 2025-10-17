# WNBA Scraper - Setup Guide

Once set up, you'll receive **daily emails at 3:00 AM** with:
- ✅ **milestones.csv** - Records, achi
evements, stat milestones
- ✅ **shoes.csv** - Game shoes with performance stats and prices
- ✅ **tunnel_fits.csv** - Outfit details with shopping links
- ✅ **Summary report** - How many items found, processing time

**Cost**: ~$30-50/month (server + AI processing)
**Time to set up**: 30-45 minutes
**Technical level**: Beginner-friendly with copy/paste commands

---

## Table of Contents

1. [Prerequisites & What You Need](#1-prerequisites--what-you-need)
2. [Server Setup](#2-server-setup-digitalocean)
3. [Install & Configure](#3-install--configure)
4. [Daily Operations](#4-daily-operations)
5. [Monitoring & Troubleshooting](#5-monitoring--troubleshooting)
6. [Architecture Overview](#6-architecture-overview)
7. [Cost Breakdown](#7-cost-breakdown)
8. [Adding New Players/Content](#8-adding-new-playerscontent)

---

## Prerequisites & What You Need

### What You Need (Get These First)

1. **DigitalOcean Account** - Create server ($12/month)
   - Sign up at https://digitalocean.com
   - Credit card required for server hosting

2. **OpenAI API Key** - For AI data processing (~$15-30/month)
   - Sign up at https://platform.openai.com
   - Add payment method, get API key

3. **TwitterAPI.io Key** - For social media access (free tier available)
   - Sign up at https://twitterapi.io
   - Get API key (free tier = 1 request per 5 seconds)

4. **Email Service** - For daily email delivery
   - **Option A**: SendGrid (free tier: 100 emails/day) - **Recommended**
   - **Option B**: Gmail (free) - Use existing Gmail + app password
   - **Option C**: Any SMTP provider (Mailgun, etc.)

### Steps

1. **Create a server** on DigitalOcean (Section 2)
2. **Install the scraper** with one command (Section 3)
3. **Add your API keys** to configuration file (Section 3)
4. **Test everything works** and set up daily automation (Section 3)

---

## Server Setup (DigitalOcean)

### Step 1: Create Droplet

1. **Log in to DigitalOcean** → Create → Droplets
2. **Choose Image**: Ubuntu 22.04 LTS
3. **Choose Size**: Basic plan, $12/month (2 GB RAM, 1 vCPU)
4. **Choose Region**: Closest to you
5. **Authentication**: SSH key (recommended) or password
6. **Hostname**: `fanbasehq-scraper`
7. **Click "Create Droplet"**

### Step 2: Initial Server Configuration

```bash
# SSH into server
ssh root@<your-droplet-ip>

# Update system
apt-get update && apt-get upgrade -y

# Install prerequisites
apt-get install -y git python3 python3-pip python3-venv

```

## 3. Install & Configure

**Now that you have a server, let's install the scraper:**

```bash
# Clone the repository
cd /opt

git clone https://github.com/WizardCommander/fanbasehq_scraper /opt/fanbasehq-scraper
cd /opt/fanbasehq-scraper

# Run setup script
chmod +x deployment/daily_scraper.sh
chmod +x deployment/setup.sh
./deployment/setup.sh
```

**Note**: Running as root is acceptable for server setup. For production, consider creating a dedicated user with sudo privileges.

The setup script will:
- ✅ Install Python dependencies
- ✅ Install Playwright browsers
- ✅ Create config/.env from template
- ✅ Test email delivery
- ✅ Install cron jobs (optional)
- ✅ Run test scrape (optional)

### 3.2 Environment Variables

**File Location**: `config/.env`

```bash
# Copy template
cp deployment/.env.production.example config/.env

# Edit with your values
nano config/.env
```

**Required Variables**:

```bash
# OpenAI API Key
OPENAI_API_KEY=sk-your-openai-api-key-here

# TwitterAPI.io Key
TWITTER_API_KEY=your-twitterapi-key-here

# SMTP Settings (sendgrid example)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM_EMAIL=your-verified-sender@domain.com

# Notification Email
NOTIFICATION_EMAIL=recipient@example.com

# Monitoring Settings
ENABLE_EMAIL_DELIVERY=true
ENABLE_ERROR_ALERTS=true
HEALTH_CHECK_DAYS=3
```

### 3.3 Email Service Setup

**Option A: SendGrid (Recommended - Free & Reliable)**

1. Sign up at https://sendgrid.com (free tier: 100 emails/day)
2. Go to Settings → API Keys → Create API Key
3. Copy the API key
4. In `config/.env` use:
   ```bash
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USER=apikey
   SMTP_PASSWORD=your-sendgrid-api-key-here
   SMTP_FROM_EMAIL=your-verified-sender@domain.com
   ```

**Option B: Gmail (Alternative)**

Gmail users MUST use an app-specific password:
1. Enable 2FA on your Google account
2. Visit: https://myaccount.google.com/apppasswords
3. Create new app password for "Mail"
4. In `config/.env` use:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-specific-password
   SMTP_FROM_EMAIL=your-email@gmail.com
   ```

### 3.4 Player Configuration

**File Location**: `config/players.json`

Current configuration for Caitlin Clark:

```json
{
  "caitlin clark": {
    "full_name": "Caitlin Clark",
    "team": "Indiana Fever",
    "team_id": "11",
    "variations": [
      "Caitlin Clark",
      "caitlin clark",
      "CC",
      "Clark",
      "@CaitlinClark22"
    ],
    "twitter_handle": "@CaitlinClark22"
  }
}
```

### 3.5 Twitter Accounts

**File Location**: `config/accounts.json`

Configure which Twitter accounts to scrape:

```json
{
  "twitter_accounts": {
    "milestone_accounts": [
      "@PolymarketHoops",
      "@FeverStats"
    ],
    "shoe_accounts": [
      "@nicekicks",
      "@nikebasketball"
    ],
    "tunnel_fit_accounts": [
      "@caitlinclarksty"
    ]
  }
}
```

---

## 4. Daily Operations

### 4.1 Automatic Daily Scraping

**Cron Schedule** (configured by setup.sh):

```cron
# Daily scraper runs at 3 AM UTC
0 3 * * * cd /opt/fanbasehq-scraper && ./deployment/daily_scraper.sh >> /var/log/fanbasehq-scraper.log 2>&1

# Health check runs at 5 AM UTC
0 5 * * * cd /opt/fanbasehq-scraper && ./venv/bin/python -c "..." >> /var/log/fanbasehq-scraper.log 2>&1
```

**What Happens Daily**:
1. **3:00 AM**: daily_scraper.sh runs all 3 scrapers sequentially
   - Milestones scraper (5-10 min)
   - Shoes scraper (5-10 min)
   - Tunnel fits scraper (5-10 min)
2. **3:30 AM** (approx): Email sent with CSV attachments
3. **5:00 AM**: Health check verifies scraping succeeded

### 4.2 Manual Scraping

Run scrapers manually when needed:

```bash
cd /opt/fanbasehq-scraper
# Virtual environment is automatically managed - no need to activate manually!
# The scraper will automatically:
# ✅ Detect if venv is active
# ✅ Activate venv if needed
# ✅ Install missing dependencies
# ✅ Restart with proper environment

# Scrape yesterday's milestones
python main.py --player "caitlin clark" --type milestones \
  --start-date $(date -d "yesterday" +%Y-%m-%d) \
  --end-date $(date -d "yesterday" +%Y-%m-%d)

# Scrape specific date range
python main.py --player "caitlin clark" --type shoes \
  --start-date 2024-09-01 --end-date 2024-09-30

# Send email with results
python main.py --player "caitlin clark" --type tunnel-fits \
  --start-date 2024-09-26 --end-date 2024-09-26 \
  --email your-email@example.com
```

### 4.3 Email Notifications

**Daily Results Email** includes:
- Summary metrics (items found, tweets processed, duration)
- CSV file attachments for all 3 scrapers
- Date range scraped

**Error Alert Email** includes:
- Error type and message
- Scraper that failed
- Context information (date range, player, etc.)

**Disable Email**:
```bash
# Temporarily disable for one run
python main.py --player "caitlin clark" --type milestones --no-email

# Disable in config
# Edit config/.env and set:
ENABLE_EMAIL_DELIVERY=false
```

### 4.4 Output Files

**Location**: `output/`

```
output/
├── milestones.csv
├── shoes.csv
├── tunnel_fits.csv
└── scraper_metrics.json  # Monitoring data
```

**CSV Files are overwritten daily** - make sure to import them into your database before the next run, or update the scripts to use timestamped filenames.

---

## 5. Monitoring & Troubleshooting

### 5.1 Check Cron Jobs

```bash
# View installed cron jobs
crontab -l

# Check cron logs
tail -f /var/log/fanbasehq-scraper.log

# Check system cron logs
grep CRON /var/log/syslog
```

### 5.2 Check Scraper Metrics

```bash
cd /opt/fanbasehq-scraper
# Virtual environment automatically managed - no manual activation needed!

python -c "
from services.monitoring_service import MonitoringService
import json

m = MonitoringService()

# Get today's summary
summary = m.get_daily_summary()
print(json.dumps(summary, indent=2))

# Check health
health = m.check_health()
print(json.dumps(health, indent=2))
"
```

### 5.3 Test Email Delivery

```bash
cd /opt/fanbasehq-scraper
# Virtual environment automatically managed - no manual activation needed!

python -c "
from services.email_service import EmailService
from config.settings import NOTIFICATION_EMAIL

email_service = EmailService()
result = email_service.send_test_email(NOTIFICATION_EMAIL)

if result:
    print('✓ Test email sent successfully')
else:
    print('✗ Failed to send test email')
"
```

### 5.4 Common Issues

#### Issue: No email received

**Check**:
```bash
# Verify SMTP settings
cat config/.env | grep SMTP

# Test SMTP connection
python -c "
import smtplib
from config.settings import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

try:
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    print('✓ SMTP connection successful')
    server.quit()
except Exception as e:
    print(f'✗ SMTP connection failed: {e}')
"
```

#### Issue: Cron job not running

**Check**:
```bash
# Verify cron service is running
systemctl status cron

# Check if jobs are installed
crontab -l | grep fanbasehq

# Check cron logs
tail -50 /var/log/syslog | grep CRON
```

#### Issue: Scraper fails with API errors

**Check**:
```bash
# Verify API keys
cat config/.env | grep API_KEY

# Check API rate limits
# TwitterAPI.io: Check dashboard at https://twitterapi.io/dashboard
# OpenAI: Check usage at https://platform.openai.com/usage

# Run scraper manually with full logs
python main.py --player "caitlin clark" --type milestones \
  --start-date $(date -d "yesterday" +%Y-%m-%d) \
  --end-date $(date -d "yesterday" +%Y-%m-%d)
```

#### Issue: Playwright browser not found

**Fix**:
```bash
source venv/bin/activate
playwright install chromium
playwright install-deps chromium
```

### 5.5 Health Check Alerts

If you receive a health check alert email, it means:

**Possible Issues**:
- ❌ No scraper runs in last 3 days → Check cron jobs
- ❌ 3+ consecutive days with failed scraper runs → Check API keys and logs
- ❌ High error rate (>50%) → Check API keys and logs
- ❌ Specific scraper type not running → Check cron schedule

**Note**: Successful runs with 0 items found are normal when no new data is available and will NOT trigger health alerts.

---

## 6. Architecture Overview

### 6.1 System Components

```
┌─────────────────────────────────────────┐
│         main.py (CLI Entry Point)       │
└───────────────┬─────────────────────────┘
                │
        ┌───────┴───────┐
        │   Scrapers    │
        │  (Orchestrate)│
        └───────┬───────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼────┐  ┌──▼────┐  ┌───▼──────┐
│Milestone│  │Tunnel │  │  Shoe    │
│Scraper │  │  Fit  │  │ Scraper  │
└───┬────┘  └───┬───┘  └───┬──────┘
    │           │           │
    └───────────┼───────────┘
                │
        ┌───────▼────────┐
        │    Services    │
        │  (Reusable)    │
        └───────┬────────┘
                │
    ┌───────────┼────────────┐
    │           │            │
┌───▼──────┐ ┌─▼────────┐ ┌─▼────────┐
│Twitter   │ │Content   │ │Email &   │
│Search    │ │Processing│ │Monitoring│
└──────────┘ └──────────┘ └──────────┘
```

### 6.2 Service Layer

**ContentProcessingService** (Consolidated):
- Replaces MilestoneProcessingService + TunnelFitProcessingService
- Generic tweet → content item processing
- Handles quality filtering and post-processing
- ~150 lines

**TwitterSearchService**:
- Searches Twitter via TwitterAPI.io
- Handles rate limiting and pagination
- Returns structured tweet data

**EmailService**:
- Sends daily CSV results
- Sends error alerts
- HTML email templates

**MonitoringService**:
- Tracks scraper metrics (items found, duration, errors)
- Health checks for production monitoring
- Stores metrics in JSON file

**KixStatsService**:
- Scrapes game-by-game shoe data from KixStats.com
- Provides real game stats (points, rebounds, assists)

**KicksCrewService**:
- Scrapes shoe prices and release dates from KicksCrew.com
- Uses Playwright for dynamic content

### 6.3 Data Flow

```
1. TwitterAPI.io → Raw tweets
2. ContentProcessingService → AI parsing (OpenAI GPT)
3. AggregationService → Deduplication
4. CSVFormatter → FanbaseHQ schema
5. EmailService → Daily email with CSVs
6. MonitoringService → Track metrics
```

### 6.4 Key Files

**Configuration**:
- `config/.env` - Environment variables
- `config/settings.py` - Loads and validates configuration
- `config/players.json` - Player variations for search
- `config/accounts.json` - Twitter accounts to scrape

**Services**:
- `services/content_processing_service.py` - Generic content processing
- `services/email_service.py` - Email delivery
- `services/monitoring_service.py` - Metrics tracking
- `services/twitter_search_service.py` - Twitter API client
- `services/kixstats_service.py` - Shoe data scraping
- `services/kickscrew_service.py` - Shoe pricing

**Scrapers**:
- `scrapers/milestone_scraper.py` - Milestone orchestrator
- `scrapers/shoe_scraper.py` - Shoe orchestrator
- `scrapers/tunnel_fit_scraper.py` - Tunnel fit orchestrator

**Deployment**:
- `deployment/setup.sh` - One-command setup
- `deployment/daily_scraper.sh` - Daily automation script
- `deployment/cron_schedule` - Cron job configuration
- `deployment/.env.production.example` - Environment template

---

## 7. Cost Breakdown

### Monthly Costs (Estimated)

| Service | Cost | Notes |
|---------|------|-------|
| **DigitalOcean Droplet** | $12-24/month | 2GB RAM recommended |
| **OpenAI API (GPT-4o-mini)** | $15-30/month | ~300 tweets/day processed |
| **TwitterAPI.io** | $0-15/month | Free tier usually sufficient |
| **Email (Gmail)** | $0 | Free with app-specific password |
| **Total** | **$27-69/month** | |

### Cost Optimization Tips

1. **OpenAI**:
   - Already using cheapest model (gpt-4o-mini)
   - Could reduce `limit` parameter to process fewer tweets
   - Monitor usage at https://platform.openai.com/usage

2. **TwitterAPI.io**:
   - Free tier = 1 request per 5 seconds (sufficient for daily scraping)
   - Pro tier ($15/month) = faster rate limits if needed

3. **Server**:
   - 2GB RAM droplet is sufficient
   - Could use 1GB if running only scrapers (no other services)

### Monitor Costs

```bash
# Check OpenAI usage
# Visit: https://platform.openai.com/usage

# Check TwitterAPI.io usage
# Visit: https://twitterapi.io/dashboard

# Check DigitalOcean billing
# Visit: https://cloud.digitalocean.com/billing
```

---

## 8. Adding New Players/Content

### 8.1 Add New Player

**Step 1**: Update `config/players.json`

```json
{
  "angel reese": {
    "full_name": "Angel Reese",
    "team": "Chicago Sky",
    "team_id": "5",
    "variations": [
      "Angel Reese",
      "angel reese",
      "Reese",
      "@angelreese"
    ],
    "twitter_handle": "@angelreese"
  }
}
```

**Step 2**: Update `config/accounts.json`

```json
{
  "twitter_accounts": {
    "milestone_accounts": [
      "@PolymarketHoops",
      "@ChicagoBulls"
    ]
  }
}
```

**Step 3**: Run scraper

```bash
python main.py --player "angel reese" --type milestones \
  --start-date 2024-09-01 --end-date 2024-09-30
```

### 8.2 Add New Content Type

To add a new content type (e.g., "injuries", "awards"):

1. **Create dataclass** in `parsers/ai_parser.py`:
   ```python
   @dataclass
   class InjuryData:
       is_injury: bool
       injury_type: str
       expected_return: str
       # ... other fields
   ```

2. **Add parser method** in `AIParser`:
   ```python
   def parse_injury_tweet(self, tweet_text: str, ...):
       # Use OpenAI to parse injury information
   ```

3. **Add to ContentType enum** in `services/content_processing_service.py`:
   ```python
   class ContentType(Enum):
       MILESTONE = "milestone"
       TUNNEL_FIT = "tunnel_fit"
       INJURY = "injury"  # NEW
   ```

4. **Create CSV formatter** in `parsers/`:
   ```python
   class InjuryCSVFormatter:
       def format_injuries_to_csv(self, injuries: List[InjuryData]):
           # Format to CSV matching your schema
   ```

5. **Create scraper** in `scrapers/`:
   ```python
   class InjuryScraper:
       # Follow existing scraper patterns
   ```

6. **Update main.py** to include new type:
   ```python
   parser.add_argument('--type',
       choices=['milestones', 'shoes', 'tunnel-fits', 'injuries'])
   ```

---

## Appendix: Quick Reference

### Common Commands

```bash
# Start scraper manually (venv automatically managed)
cd /opt/fanbasehq-scraper
python main.py --player "caitlin clark" --type milestones

# Check logs
tail -f /var/log/fanbasehq-scraper.log

# View cron jobs
crontab -l

# Test email (venv automatically managed)
python -c "from services.email_service import EmailService; EmailService().send_test_email()"

# Check health (venv automatically managed)
python -c "from services.monitoring_service import MonitoringService; print(MonitoringService().check_health())"
```

### Important Paths

| Path | Description |
|------|-------------|
| `/opt/fanbasehq-scraper/` | Project root (git repository) |
| `config/.env` | Environment variables |
| `output/` | CSV output files |
| `deployment/` | Deployment scripts |
| `/var/log/fanbasehq-scraper.log` | Cron job logs |

### Support Resources

- **OpenAI API**: https://platform.openai.com/docs
- **TwitterAPI.io**: https://twitterapi.io/docs
- **Gmail App Passwords**: https://support.google.com/accounts/answer/185833
- **DigitalOcean**: https://docs.digitalocean.com

---

**Last Updated**: 2025-10-16
**Virtual Environment**: Now automatically managed by VenvManager system
