"""
Tunnel Fit scraper for WNBA data - Following Existing Architecture
"""

import json
import logging
from datetime import date
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.photo_aggregation_service import PhotoAggregationService
    from services.vision_analysis_service import VisionAnalysisService
    from services.shopping_link_service import ShoppingLinkService

from config.settings import PLAYERS_FILE, TWITTER_ACCOUNTS_FILE
from services.scraper_config import ScraperConfig
from services.twitter_search_service import TwitterSearchService
from services.content_processing_service import ContentProcessingService, ContentType
from services.tunnel_fit_aggregation_service import TunnelFitAggregationService
from parsers.ai_parser import TunnelFitData
from parsers.tunnel_fit_csv_formatter import TunnelFitCSVFormatter


logger = logging.getLogger(__name__)


class TunnelFitScraper:
    """Main scraper orchestrator for tunnel fits - coordinates services to perform tunnel fit scraping"""

    def __init__(
        self,
        config: ScraperConfig,
        twitter_service: Optional[TwitterSearchService] = None,
        processing_service: Optional[ContentProcessingService] = None,
        aggregation_service: Optional[TunnelFitAggregationService] = None,
        csv_formatter: Optional[TunnelFitCSVFormatter] = None,
        # New services for multi-source flow
        photo_aggregation_service: Optional["PhotoAggregationService"] = None,
        vision_analysis_service: Optional["VisionAnalysisService"] = None,
        shopping_link_service: Optional["ShoppingLinkService"] = None,
    ):
        # Validate and store configuration
        config.validate()
        self.config = config

        # Initialize services with dependency injection
        self.twitter_service = twitter_service or TwitterSearchService()
        self.processing_service = processing_service or ContentProcessingService()
        self.aggregation_service = aggregation_service or TunnelFitAggregationService()
        self.csv_formatter = csv_formatter or TunnelFitCSVFormatter(config.output_file)

        # Initialize multi-source services (lazy initialization)
        self.photo_aggregation_service = photo_aggregation_service
        self.vision_analysis_service = vision_analysis_service
        self.shopping_link_service = shopping_link_service

    @classmethod
    def create_from_legacy_params(
        cls,
        player: str,
        start_date: date,
        end_date: date,
        output_file: str,
        limit: int = 100,
    ) -> "TunnelFitScraper":
        """Factory method for backward compatibility with legacy constructor"""

        # Load configurations the same way as milestone scraper
        player_config = cls._load_player_config(player.lower())
        accounts_config = cls._load_accounts_config()

        # Create config object - use tunnel_fit_accounts for target_accounts
        config = ScraperConfig(
            player=player.lower(),
            player_display_name=player.title(),
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
            limit=limit,
            player_variations=player_config.get("variations", []),
            target_accounts=accounts_config.get("twitter_accounts", {}).get(
                "tunnel_fit_accounts", []
            ),
        )

        return cls(config)

    @staticmethod
    def _load_player_config(player: str) -> Dict:
        """Load player configuration"""
        with open(PLAYERS_FILE, "r") as f:
            players = json.load(f)

        if player not in players:
            raise ValueError(f"Player '{player}' not found in {PLAYERS_FILE}")

        return players[player]

    @staticmethod
    def _load_accounts_config() -> Dict:
        """Load accounts configuration"""
        with open(TWITTER_ACCOUNTS_FILE, "r") as f:
            return json.load(f)

    @staticmethod
    def _load_tunnel_fit_sources() -> Dict:
        """Load tunnel fit sources configuration"""
        from pathlib import Path

        sources_file = (
            Path(__file__).parent.parent / "config" / "tunnel_fit_sources.json"
        )
        with open(sources_file, "r") as f:
            return json.load(f)

    async def scrape_tunnel_fits(self) -> Dict:
        """
        Orchestrate tunnel fit scraping using service layer architecture

        Returns:
            Dictionary with scraping results
        """
        logger.info(f"Starting tunnel fit scrape for {self.config.player_display_name}")
        logger.info(f"Date range: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Output: {self.config.output_file}")

        # Search Twitter for tweets using tunnel fit accounts
        logger.info(
            f"Searching across {len(self.config.target_accounts)} tunnel fit accounts with {len(self.config.player_variations)} variations"
        )
        search_results = await self.twitter_service.search_tweets_for_player(
            accounts=self.config.target_accounts,
            variations=self.config.player_variations,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            limit=self.config.limit,
        )

        if not search_results:
            logger.warning("No tweets found across all searches")
            await self._write_empty_results()
            return self._create_results_summary(0, 0, [])

        # Process tweets into tunnel fits
        tunnel_fit_batches = []
        total_posts_processed = 0

        for search_result in search_results:
            logger.info(
                f"Processing {len(search_result.tweets)} tweets from {search_result.account} × {search_result.variation}"
            )

            processing_result = await self.processing_service.process_tweets(
                tweets=search_result.tweets,
                content_type=ContentType.TUNNEL_FIT,
                target_player=self.config.player_display_name,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                quality_filter=self._is_quality_tunnel_fit,
                post_processor=self._override_social_stats,
            )

            if processing_result.content_items:
                tunnel_fit_batches.append(
                    (processing_result.content_items, search_result.tweets)
                )
                logger.info(f"Found {processing_result.items_found} tunnel fits")

            total_posts_processed += processing_result.posts_processed

        # Combine all tunnel fits from different searches and match with source tweets
        if tunnel_fit_batches:
            all_tunnel_fits = []
            all_source_tweets = []

            # Create a lookup of all tweets by ID
            tweet_lookup = {}
            for tunnel_fits, tweets in tunnel_fit_batches:
                for tweet in tweets:
                    tweet_lookup[tweet.id] = tweet

            # Collect tunnel fits and their corresponding source tweets
            for tunnel_fits, tweets in tunnel_fit_batches:
                for tunnel_fit in tunnel_fits:
                    source_tweet = tweet_lookup.get(tunnel_fit.source_tweet_id.value)
                    if source_tweet:
                        all_tunnel_fits.append(tunnel_fit)
                        all_source_tweets.append(source_tweet)
                    else:
                        logger.warning(
                            f"Could not find source tweet for tunnel fit: {tunnel_fit.event}"
                        )

            # Aggregate related outfit pieces into complete outfits
            logger.info(
                f"Aggregating {len(all_tunnel_fits)} tunnel fit pieces into complete outfits"
            )
            aggregation_result = self.aggregation_service.aggregate_outfit_pieces(
                all_tunnel_fits
            )

            # Update tunnel fits with aggregated results
            all_tunnel_fits = aggregation_result.tunnel_fits

            # Rebuild source tweets mapping for aggregated tunnel fits
            aggregated_source_tweets = []
            for tunnel_fit in all_tunnel_fits:
                source_tweet = tweet_lookup.get(tunnel_fit.source_tweet_id.value)
                if source_tweet:
                    aggregated_source_tweets.append(source_tweet)
                else:
                    logger.warning(
                        f"Could not find source tweet for aggregated tunnel fit: {tunnel_fit.event}"
                    )

            logger.info(
                f"Aggregation complete: {aggregation_result.original_count} pieces → "
                f"{aggregation_result.aggregated_count} complete outfits "
                f"({aggregation_result.pieces_combined} pieces combined)"
            )

            # Write results to CSV
            await self.csv_formatter.write_tunnel_fits_to_csv(
                tunnel_fits=all_tunnel_fits,
                tweets=aggregated_source_tweets,
                player_name=self.config.player_display_name,
            )

            logger.info(f"Scraping complete: {len(all_tunnel_fits)} tunnel fits found")

            return self._create_results_summary(
                len(all_tunnel_fits),
                total_posts_processed,
                all_tunnel_fits,
            )
        else:
            logger.warning("No tunnel fits found after processing")
            await self._write_empty_results()
            return self._create_results_summary(0, total_posts_processed, [])

    def _is_quality_tunnel_fit(self, tunnel_fit: TunnelFitData) -> bool:
        """
        Validate tunnel fit data quality to filter out low-value records

        Args:
            tunnel_fit: TunnelFitData object to validate

        Returns:
            True if tunnel fit meets quality standards, False otherwise
        """
        # Filter out empty outfit details
        if not tunnel_fit.outfit_details or len(tunnel_fit.outfit_details) == 0:
            return False

        # Filter out single item with null shop link
        if len(tunnel_fit.outfit_details) == 1:
            item = tunnel_fit.outfit_details[0]
            if item.get("shopLink") is None:
                return False

        return True

    def _override_social_stats(self, tunnel_fit: TunnelFitData, tweet) -> TunnelFitData:
        """
        Override AI-extracted social stats with real Twitter metrics

        Args:
            tunnel_fit: TunnelFitData object
            tweet: Source ScrapedTweet object

        Returns:
            TunnelFitData with updated social stats
        """
        tunnel_fit.social_stats = {
            "views": tweet.view_count,
            "likes": tweet.like_count,
            "retweets": tweet.retweet_count,
            "replies": tweet.reply_count,
            "quotes": tweet.quote_count,
        }
        return tunnel_fit

    async def _write_empty_results(self) -> None:
        """Write empty CSV when no results found"""
        try:
            await self.csv_formatter.write_tunnel_fits_to_csv(
                tunnel_fits=[], tweets=[], player_name=self.config.player_display_name
            )
            logger.info("Empty results written to CSV")
        except Exception as e:
            logger.error(f"Error writing empty results: {e}")

    def _create_results_summary(
        self, tunnel_fits_count: int, posts_processed: int, tunnel_fits: List
    ) -> Dict:
        """Create results summary dictionary"""
        return {
            "player": self.config.player_display_name,
            "date_range": f"{self.config.start_date} to {self.config.end_date}",
            "tunnel_fits_found": tunnel_fits_count,
            "posts_processed": posts_processed,
            "output_file": self.config.output_file,
            "tunnel_fits": tunnel_fits,
        }

    def _initialize_multi_source_services(self) -> None:
        """
        Initialize multi-source services (Instagram, Vision, Shopping) if not provided

        Lazy initialization pattern - only creates services when needed for multi-source flow
        """
        if not self.photo_aggregation_service:
            from services.photo_aggregation_service import PhotoAggregationService
            from services.instagram_photo_service import InstagramPhotoService
            from config.settings import SCRAPE_CREATORS_API_KEY

            instagram_service = InstagramPhotoService(api_key=SCRAPE_CREATORS_API_KEY)
            self.photo_aggregation_service = PhotoAggregationService(
                instagram_service=instagram_service,
                twitter_client=self.twitter_service.client,
            )

        if not self.vision_analysis_service:
            from services.vision_analysis_service import VisionAnalysisService
            from config.settings import OPENAI_API_KEY

            self.vision_analysis_service = VisionAnalysisService(api_key=OPENAI_API_KEY)

        if not self.shopping_link_service:
            from services.shopping_link_service import ShoppingLinkService
            from config.settings import OXYLABS_USERNAME, OXYLABS_PASSWORD

            self.shopping_link_service = ShoppingLinkService(
                username=OXYLABS_USERNAME, password=OXYLABS_PASSWORD
            )

    async def scrape_tunnel_fits_multi_source(self) -> Dict:
        """
        Orchestrate tunnel fit scraping using multi-source flow (Instagram + Twitter)

        Flow:
        1. Use PhotoAggregationService to get UnifiedPhotos from all sources
        2. Use VisionAnalysisService to analyze outfit images
        3. Use ShoppingLinkService to find product links for each outfit item
        4. Use AIParser to create TunnelFitData from vision analysis results
        5. Format and save to CSV using tweet_sources dict

        Returns:
            Dictionary with scraping results
        """
        logger.info(
            f"Starting multi-source tunnel fit scrape for {self.config.player_display_name}"
        )

        # Load source configuration
        sources_config = self._load_tunnel_fit_sources()
        player_sources = sources_config.get(self.config.player.lower())

        if not player_sources:
            logger.error(f"No tunnel fit sources configured for {self.config.player}")
            await self._write_empty_results()
            return self._create_results_summary(0, 0, [])

        # Initialize services if not provided (lazy initialization)
        self._initialize_multi_source_services()

        # Step 1: Aggregate photos from all sources
        instagram_handle = player_sources.get("instagram_handle")
        twitter_accounts = player_sources.get("twitter_style_accounts", [])

        logger.info(
            f"Fetching photos from Instagram: {instagram_handle}, Twitter: {twitter_accounts}"
        )

        unified_photos = await self.photo_aggregation_service.get_all_tunnel_photos(
            player_name=self.config.player_display_name,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            instagram_handle=instagram_handle,
            twitter_accounts=twitter_accounts,
            limit_per_source=self.config.limit,
        )

        if not unified_photos:
            logger.warning("No photos found from any source")
            await self._write_empty_results()
            return self._create_results_summary(0, 0, [])

        logger.info(f"Found {len(unified_photos)} candidate photos to analyze")

        # Build source metadata dict for CSV formatter
        tweet_sources = {
            photo.photo_id: {
                "handle": photo.source_handle,
                "post_url": photo.post_url,
                "image_url": photo.image_url,
                "source": photo.source,
            }
            for photo in unified_photos
        }

        # Step 2: Analyze outfits using Vision API
        tunnel_fits = []
        photos_processed = 0

        for photo in unified_photos:
            photos_processed += 1

            try:
                # Step 2a: Quick pre-screening to filter out non-outfit photos
                # This saves expensive Vision API calls on action shots, selfies, etc.
                is_outfit, screening_confidence = (
                    await self.vision_analysis_service.is_outfit_photo(
                        image_url=photo.image_url,
                        player_name=self.config.player_display_name,
                    )
                )

                # Import threshold from vision service
                from services.vision_analysis_service import PRESCREENING_MIN_CONFIDENCE

                if not is_outfit or screening_confidence < PRESCREENING_MIN_CONFIDENCE:
                    logger.info(
                        f"Photo {photo.photo_id[:8]} pre-screened out - not an outfit photo "
                        f"(confidence: {screening_confidence:.2f})"
                    )
                    continue

                logger.info(
                    f"Photo {photo.photo_id[:8]} passed pre-screening "
                    f"(confidence: {screening_confidence:.2f}) - analyzing outfit details..."
                )

                # Step 2b: Full outfit analysis (expensive - only on pre-screened photos)
                outfit_analysis = (
                    await self.vision_analysis_service.analyze_outfit_image(
                        image_url=photo.image_url,
                        player_name=self.config.player_display_name,
                        event_context=photo.caption[:100] if photo.caption else None,
                    )
                )

                if not outfit_analysis or not outfit_analysis.is_tunnel_fit:
                    logger.info(
                        f"Photo {photo.photo_id[:8]} not a tunnel fit after full analysis "
                        f"(confidence: {outfit_analysis.confidence if outfit_analysis else 0})"
                    )
                    continue

                # Step 3: Find shopping links for high-confidence items
                items_with_links = []
                high_confidence_items = (
                    self.vision_analysis_service.filter_high_confidence_items(
                        outfit_analysis, min_confidence=0.7
                    )
                )

                for item in high_confidence_items:
                    # Try to find product links
                    product_links = await self.shopping_link_service.find_product_links(
                        image_url=photo.image_url,
                        item_description=f"{item.brand} {item.description}",
                        max_results=3,
                    )

                    # Use best product link if found
                    best_link = product_links[0] if product_links else None

                    items_with_links.append(
                        {
                            "item": item.description,
                            "brand": item.brand,
                            "price": (
                                best_link.price if best_link else item.price_estimate
                            ),
                            "shopLink": best_link.shop_url if best_link else None,
                            "affiliate": (
                                best_link.is_affiliate_eligible if best_link else False
                            ),
                        }
                    )

                # Step 4: Create TunnelFitData from vision analysis
                from parsers.ai_parser import AIParser

                tunnel_fit = AIParser.create_tunnel_fit_from_vision_analysis(
                    vision_analysis=outfit_analysis,
                    unified_photo=photo,
                    player_name=self.config.player_display_name,
                    outfit_items_with_links=items_with_links,
                )

                tunnel_fits.append(tunnel_fit)
                logger.info(
                    f"Created tunnel fit from {photo.source} photo: {tunnel_fit.event}"
                )

            except Exception as e:
                logger.error(f"Error processing photo {photo.photo_id}: {e}")
                continue

        # Step 5: Write results to CSV using tweet_sources dict
        if tunnel_fits:
            await self.csv_formatter.write_tunnel_fits_to_csv(
                tunnel_fits=tunnel_fits,
                player_name=self.config.player_display_name,
                tweet_sources=tweet_sources,
            )

            logger.info(
                f"Multi-source scraping complete: {len(tunnel_fits)} tunnel fits found"
            )
            return self._create_results_summary(
                len(tunnel_fits), photos_processed, tunnel_fits
            )
        else:
            logger.warning("No tunnel fits found after vision analysis")
            await self._write_empty_results()
            return self._create_results_summary(0, photos_processed, [])

    async def run(self) -> Dict:
        """
        Run the scraper asynchronously - routes to appropriate flow based on player config

        Returns:
            Scraping results dictionary
        """
        # Load tunnel fit sources config to determine flow
        try:
            sources_config = self._load_tunnel_fit_sources()
            player_sources = sources_config.get(self.config.player.lower())

            if player_sources and player_sources.get("priority") == "instagram":
                # Use new multi-source flow for Instagram-priority players
                logger.info(
                    f"Using multi-source flow for {self.config.player_display_name}"
                )
                return await self.scrape_tunnel_fits_multi_source()
            else:
                # Use existing Twitter-only flow for Twitter-priority players
                logger.info(f"Using Twitter flow for {self.config.player_display_name}")
                return await self.scrape_tunnel_fits()

        except FileNotFoundError:
            # Fallback to Twitter flow if config not found
            logger.warning("tunnel_fit_sources.json not found, using Twitter flow")
            return await self.scrape_tunnel_fits()


# Test functions removed for production - see development branch for testing utilities
