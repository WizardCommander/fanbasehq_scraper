"""
Tunnel Fit Aggregation Service
Combines related outfit pieces into single complete outfits for JSONB storage
"""

import logging
from typing import List, Dict, Tuple
from dataclasses import dataclass
from collections import defaultdict

from parsers.ai_parser import TunnelFitData

logger = logging.getLogger(__name__)


@dataclass
class TunnelFitAggregationResult:
    """Result of tunnel fit aggregation"""

    tunnel_fits: List[TunnelFitData]
    original_count: int
    aggregated_count: int
    pieces_combined: int


class TunnelFitAggregationService:
    """Service for aggregating related outfit pieces into complete outfits"""

    def aggregate_outfit_pieces(
        self, tunnel_fits: List[TunnelFitData]
    ) -> TunnelFitAggregationResult:
        """
        Aggregate tunnel fits by grouping related outfit pieces into complete outfits

        Groups by: (event, date, player_name) combinations
        Combines: outfit_details arrays and selects best metadata

        Args:
            tunnel_fits: List of individual tunnel fit pieces

        Returns:
            TunnelFitAggregationResult with aggregated complete outfits
        """
        if not tunnel_fits:
            return TunnelFitAggregationResult(
                tunnel_fits=[], original_count=0, aggregated_count=0, pieces_combined=0
            )

        logger.info(
            f"Aggregating {len(tunnel_fits)} tunnel fit pieces into complete outfits"
        )

        # Group tunnel fits by outfit identifier
        grouped_outfits = self._group_tunnel_fits_by_outfit(tunnel_fits)

        # Combine each group into single outfit
        aggregated_outfits = []
        total_pieces_combined = 0

        for group_key, pieces in grouped_outfits.items():
            if len(pieces) == 1:
                # Single piece outfit - no aggregation needed
                aggregated_outfits.append(pieces[0])
            else:
                # Multiple pieces - combine into single outfit
                combined_outfit = self._combine_outfit_pieces(pieces)
                aggregated_outfits.append(combined_outfit)
                total_pieces_combined += len(pieces) - 1  # Count extra pieces combined
                logger.debug(f"Combined {len(pieces)} pieces for {group_key}")

        logger.info(
            f"Aggregation complete: {len(tunnel_fits)} → {len(aggregated_outfits)} outfits "
            f"({total_pieces_combined} pieces combined)"
        )

        return TunnelFitAggregationResult(
            tunnel_fits=aggregated_outfits,
            original_count=len(tunnel_fits),
            aggregated_count=len(aggregated_outfits),
            pieces_combined=total_pieces_combined,
        )

    def _group_tunnel_fits_by_outfit(
        self, tunnel_fits: List[TunnelFitData]
    ) -> Dict[Tuple[str, str, str], List[TunnelFitData]]:
        """Group tunnel fits by outfit identifier: (event, date, player)"""

        grouped = defaultdict(list)

        for tunnel_fit in tunnel_fits:
            # Create grouping key from event, date, and player
            date_str = tunnel_fit.date.isoformat() if tunnel_fit.date else "no-date"
            group_key = (
                tunnel_fit.event.strip(),
                date_str,
                tunnel_fit.player_name.strip(),
            )

            grouped[group_key].append(tunnel_fit)

        return dict(grouped)

    def _combine_outfit_pieces(self, pieces: List[TunnelFitData]) -> TunnelFitData:
        """Combine multiple tunnel fit pieces into single complete outfit"""

        if not pieces:
            raise ValueError("Cannot combine empty pieces list")

        if len(pieces) == 1:
            return pieces[0]

        # Select the best piece as the base (highest social engagement)
        base_piece = self._select_best_piece(pieces)

        # Combine all outfit_details arrays and deduplicate
        combined_outfit_details = []
        seen_items = set()

        for piece in pieces:
            if piece.outfit_details:
                for item in piece.outfit_details:
                    # Create a unique key for the item based on essential attributes
                    item_key = self._create_item_key(item)
                    if item_key not in seen_items:
                        seen_items.add(item_key)
                        combined_outfit_details.append(item)

        # Aggregate social stats (take maximum values)
        combined_social_stats = self._aggregate_social_stats(
            [p.social_stats for p in pieces]
        )

        # Determine highest fit confidence among pieces
        max_fit_confidence = max((p.fit_confidence for p in pieces), default=0.0)

        # Create new TunnelFitData with combined information
        return TunnelFitData(
            is_tunnel_fit=base_piece.is_tunnel_fit,
            event=base_piece.event,
            date=base_piece.date,
            type=base_piece.type,
            outfit_details=combined_outfit_details,
            location=base_piece.location,
            player_name=base_piece.player_name,
            source_tweet_id=base_piece.source_tweet_id,  # Use best piece's source
            social_stats=combined_social_stats,
            image_url=base_piece.image_url,
            date_confidence=base_piece.date_confidence,
            date_source=base_piece.date_source,
            fit_confidence=max_fit_confidence,
        )

    def _select_best_piece(self, pieces: List[TunnelFitData]) -> TunnelFitData:
        """Select the best piece to use as base (highest social engagement)"""

        def get_engagement_score(piece: TunnelFitData) -> int:
            """Calculate engagement score for piece selection"""
            if not piece.social_stats:
                return 0

            return (
                piece.social_stats.get("likes", 0) * 3  # Likes weighted highly
                + piece.social_stats.get("retweets", 0) * 5  # Retweets weighted highest
                + piece.social_stats.get("replies", 0)
                * 2  # Replies weighted moderately
                + piece.social_stats.get("views", 0)
                // 100  # Views weighted low (scaled down)
            )

        return max(pieces, key=get_engagement_score)

    def _aggregate_social_stats(self, stats_list: List[Dict]) -> Dict:
        """Aggregate social stats by taking maximum values"""

        if not stats_list:
            return {}

        # Filter out None/empty stats
        valid_stats = [stats for stats in stats_list if stats]
        if not valid_stats:
            return {}

        # Take maximum value for each metric across all pieces
        aggregated = {}
        all_keys = set()
        for stats in valid_stats:
            all_keys.update(stats.keys())

        for key in all_keys:
            values = [
                stats.get(key, 0) for stats in valid_stats if stats.get(key) is not None
            ]
            if values:
                aggregated[key] = max(values)  # Take highest engagement

        return aggregated

    def _create_item_key(self, item: Dict) -> str:
        """Create a unique key for an outfit item to enable deduplication"""
        # Normalize item name by removing common prefixes/infixes and standardizing
        item_name = str(item.get("item", "")).strip().lower()

        # Remove common words that don't change the core item identity
        # Handle both prefixes and infixes (words in middle)
        words_to_remove = [
            "women's",
            "womens",
            "men's",
            "mens",
            "nike",
            "adidas",
            "jordan",
            "the",
        ]

        # Split into words and remove common non-essential words
        words = item_name.split()
        filtered_words = []

        for word in words:
            # Remove common possessive/brand words
            if word not in words_to_remove:
                filtered_words.append(word)

        # Rejoin the essential words
        item_name = " ".join(filtered_words)

        # Normalize brand (though we're not using it in the key anymore)
        brand = str(item.get("brand", "")).strip().lower()
        if brand.startswith("@"):
            brand = brand[1:]

        # Use just the normalized item name as the key - brand is often inconsistent
        return item_name
