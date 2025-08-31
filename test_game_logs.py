#!/usr/bin/env python3
"""
Quick test script to debug the game log service
"""

import asyncio
import logging
from utils.player_game_logs import PlayerGameLogService

# Set up logging to see debug info
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test_game_logs():
    service = PlayerGameLogService()
    
    print("Testing Caitlin Clark game logs...")
    
    # Clear cache to force fresh data
    service.cache = {'last_updated': 0, 'players': {}}
    
    # Test 2025 season with fresh data
    print("\n=== Testing 2025 season (fresh data) ===")
    game_dates_2025 = await service.get_player_game_dates("Caitlin Clark", 2025)
    print(f"2025 games: {game_dates_2025}")
    print(f"Total 2025 games: {len(game_dates_2025)}")
    if game_dates_2025:
        print(f"Most recent game: {max(game_dates_2025)}")
        print(f"Should be around 2025-07-15 based on your screenshot")

if __name__ == "__main__":
    asyncio.run(test_game_logs())