"""
Tunnel Fit Processing Service
Handles tunnel fit detection and validation from tweets
"""

import logging
from datetime import date
from typing import List, Optional
from dataclasses import dataclass

from utils.twitterapi_client import ScrapedTweet
from parsers.ai_parser import AIParser, TunnelFitData

logger = logging.getLogger(__name__)


@dataclass
class TunnelFitProcessingResult:
    """Result of tunnel fit processing"""

    tunnel_fits: List[TunnelFitData]
    tweets_processed: int
    tunnel_fits_found: int


class TunnelFitProcessingService:
    """Service for processing tweets into validated tunnel fits"""

    def __init__(self, ai_parser: AIParser = None):
        self.ai_parser = ai_parser or AIParser()

    async def process_tweets_to_tunnel_fits(
        self,
        tweets: List[ScrapedTweet],
        target_player: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> TunnelFitProcessingResult:
        """
        Process a list of tweets to extract tunnel fits

        Args:
            tweets: List of tweets to process
            target_player: The player we're looking for tunnel fits about
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            TunnelFitProcessingResult with tunnel fits found
        """
        logger.info(f"Processing {len(tweets)} tweets for {target_player} tunnel fits")

        tunnel_fits = []
        tweets_processed = 0

        for tweet in tweets:
            tweets_processed += 1
            logger.debug(
                f"Processing tweet {tweets_processed}/{len(tweets)}: {tweet.text[:100]}..."
            )

            try:
                # Parse tweet for tunnel fit information
                tunnel_fit = self.ai_parser.parse_tunnel_fit_tweet(
                    tweet_text=tweet.text,
                    target_player=target_player,
                    tweet_url=tweet.url,
                    tweet_id=tweet.id,
                    tweet_created_at=tweet.created_at,
                )

                if tunnel_fit and tunnel_fit.is_tunnel_fit:
                    # Apply date filtering inline
                    within_range = True
                    if tunnel_fit.date:
                        if start_date and tunnel_fit.date < start_date:
                            within_range = False
                        if end_date and tunnel_fit.date > end_date:
                            within_range = False

                    if within_range:
                        tunnel_fits.append(tunnel_fit)
                        logger.info(
                            f"Found tunnel fit: {tunnel_fit.event} on {tunnel_fit.date}"
                        )
                        logger.debug(
                            f"Outfit details: {len(tunnel_fit.outfit_details)} items"
                        )
                    else:
                        logger.debug(
                            f"Tunnel fit filtered out by date range: {tunnel_fit.date}"
                        )
                elif tunnel_fit:
                    # Not a tunnel fit, log for debugging
                    logger.debug(f"Tweet {tweet.id} determined to not be a tunnel fit")

            except Exception as e:
                logger.error(f"Error processing tweet {tweet.id}: {e}")
                continue

        logger.info(
            f"Processing complete: found {len(tunnel_fits)} tunnel fits from {tweets_processed} tweets"
        )

        return TunnelFitProcessingResult(
            tunnel_fits=tunnel_fits,
            tweets_processed=tweets_processed,
            tunnel_fits_found=len(tunnel_fits),
        )
