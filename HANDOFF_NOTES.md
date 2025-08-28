# Caitlin Clark Scraper - Development Handoff Notes

## Current Status: ✅ COMPLETE MVP - Ready for Testing

### What's Built
- **Complete modular scraper** for Caitlin Clark milestone data from X.com
- **AI-powered parsing** using GPT-3.5-turbo to extract milestone data
- **FanbaseHQ CSV schema** matching exactly for Supabase import
- **Flexible CLI** with date ranges, player selection, output customization

### Project Structure
```
caitlin-clark-scraper/
├── config/           # All configuration (players, accounts, keywords, .env)
├── scrapers/         # milestone_scraper.py (main logic)
├── parsers/          # ai_parser.py (GPT) + csv_formatter.py 
├── utils/            # twitter_client.py (twscrape wrapper)
├── output/           # Generated CSV files
└── main.py           # CLI entry point
```

## Next Steps to Test/Deploy

### 1. Add Twitter Account to twscrape
```bash
cd caitlin-clark-scraper
twscrape add_account your_username your_password your_email your_email_password
twscrape login_accounts
```

### 2. Test the Scraper
```bash
# Small test run
python main.py --player "caitlin clark" --start-date 2024-08-01 --end-date 2024-08-27 --limit 10

# Full 4-month backfill
python main.py --player "caitlin clark" --start-date 2024-04-01 --end-date 2024-08-27 --limit 200
```

### 3. Key Configuration Files
- **`config/.env`** - OpenAI API key already configured ✅
- **`config/accounts.json`** - X.com accounts from Google Sheet ✅
- **`config/players.json`** - Caitlin Clark name variations ✅  
- **`config/keywords.json`** - Milestone detection keywords ✅

## Current Workflow
1. **Scrape tweets** from milestone accounts mentioning Caitlin Clark variations
2. **Pre-filter** using milestone keywords (saves GPT API costs)
3. **AI parsing** - GPT extracts structured milestone data as JSON
4. **CSV export** - Matches exact FanbaseHQ schema for import

## Dependencies Installed ✅
- twscrape (X.com scraping)
- openai (GPT parsing)
- python-dotenv (environment variables)
- pandas, requests, aiohttp

## Known Issues/Limitations
- **Twitter rate limits** - May need multiple accounts for large scrapes
- **Account bans** - Client doesn't care if personal account gets banned
- **Manual review needed** - CSV outputs marked as 'pending' status
- **Image processing** - Not downloading/encoding images yet (image_data field empty)

## Future Expansions (Not Implemented Yet)
- `shoe_scraper.py` - For shoe submissions
- `tunnel_scraper.py` - For tunnel fit submissions  
- Multiple player support
- Instagram scraping
- Image download and base64 encoding

## Testing Strategy
1. **Start small** - Test with 10-20 recent tweets
2. **Validate AI parsing** - Check that GPT correctly identifies milestones
3. **Schema validation** - Ensure CSV matches existing FanbaseHQ data
4. **Scale gradually** - Increase to full 4-month backfill

## Client Context
- **fanbasehq.ai** - User-generated WNBA content platform
- **Goal** - Backfill Caitlin Clark data from April 2024-present
- **Payment structure** - Get MVP working first, then potentially expand to full WNBA
- **Existing data** - CSV samples in `db_csvs/` folder show expected schema

## Error Handling
- All components have proper logging
- Graceful failure for individual tweet parsing
- Rate limiting with delays
- Duplicate detection via original_submission_id

## Ready for Production Testing! 🚀

The scraper is architecturally complete and ready for real-world testing with Twitter API credentials.