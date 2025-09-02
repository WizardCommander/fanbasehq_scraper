"""
Text processing utilities for semantic milestone deduplication
Provides content hashing and similarity matching without API costs
"""

import re
import hashlib
import logging
from typing import List, Dict, Set, Optional
from fuzzywuzzy import fuzz
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DuplicationResult:
    """Result of duplication detection between two milestones"""

    is_duplicate: bool
    similarity_score: float
    match_type: str  # "exact", "fuzzy_title", "fuzzy_content", "category_stats"


class MilestoneDeduplicator:
    """Semantic deduplication for milestones using local text processing"""

    def __init__(self, similarity_threshold: float = 85.0):
        """
        Initialize deduplicator

        Args:
            similarity_threshold: Minimum similarity score (0-100) to consider duplicates
        """
        self.similarity_threshold = similarity_threshold

    def generate_content_hash(
        self, title: str, categories: List[str], value: str
    ) -> str:
        """
        Generate semantic hash from milestone content

        Args:
            title: Milestone title
            categories: List of categories
            value: Milestone value

        Returns:
            Hex hash string for content fingerprinting
        """
        # Normalize text content
        normalized_title = self._normalize_text(title)
        normalized_value = self._normalize_text(value)
        sorted_categories = sorted([cat.lower().strip() for cat in categories])

        # Create content string for hashing
        content = f"{normalized_title}|{normalized_value}|{','.join(sorted_categories)}"

        # Generate hash
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]

    def check_duplication(
        self, milestone1: Dict[str, any], milestone2: Dict[str, any]
    ) -> DuplicationResult:
        """
        Check if two milestones are semantic duplicates

        Args:
            milestone1: First milestone dict with title, categories, value, etc.
            milestone2: Second milestone dict

        Returns:
            DuplicationResult with similarity assessment
        """
        # Quick exact hash check
        if milestone1.get("content_hash") == milestone2.get("content_hash"):
            return DuplicationResult(True, 100.0, "exact")

        # Category overlap check - must have some common categories
        cats1 = set(cat.lower() for cat in milestone1.get("categories", []))
        cats2 = set(cat.lower() for cat in milestone2.get("categories", []))

        if not cats1.intersection(cats2):
            return DuplicationResult(False, 0.0, "no_category_overlap")

        # Title similarity check
        title1 = milestone1.get("title", "")
        title2 = milestone2.get("title", "")
        title_similarity = fuzz.token_sort_ratio(title1, title2)

        if title_similarity >= self.similarity_threshold:
            return DuplicationResult(True, title_similarity, "fuzzy_title")

        # Content similarity check (title + value combined)
        content1 = f"{title1} {milestone1.get('value', '')}"
        content2 = f"{title2} {milestone2.get('value', '')}"
        content_similarity = fuzz.token_set_ratio(content1, content2)

        if content_similarity >= self.similarity_threshold:
            return DuplicationResult(True, content_similarity, "fuzzy_content")

        # Special case: statistical milestones with similar numbers
        if self._are_similar_stats(milestone1, milestone2):
            return DuplicationResult(True, 80.0, "category_stats")

        return DuplicationResult(
            False, max(title_similarity, content_similarity), "no_match"
        )

    def find_best_milestone(self, duplicates: List[Dict[str, any]]) -> Dict[str, any]:
        """
        Select the best milestone from a group of duplicates

        Args:
            duplicates: List of duplicate milestone dicts

        Returns:
            The highest quality milestone from the group
        """
        if not duplicates:
            return None

        if len(duplicates) == 1:
            return duplicates[0]

        # Score each milestone
        scored = []
        for milestone in duplicates:
            score = self._calculate_quality_score(milestone)
            scored.append((score, milestone))

        # Return highest scored milestone
        scored.sort(reverse=True, key=lambda x: x[0])
        best_milestone = scored[0][1]

        logger.debug(
            "Selected best duplicate: %s (score: %.2f) over %d alternatives",
            best_milestone.get("title", "Unknown")[:50],
            scored[0][0],
            len(duplicates) - 1,
        )

        return best_milestone

    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent comparison"""
        if not text:
            return ""

        # Convert to lowercase
        normalized = text.lower()

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        # Remove punctuation except numbers and basic separators
        normalized = re.sub(r"[^\w\s\.\,\-\+]", "", normalized)

        # Standardize common statistical abbreviations
        stat_replacements = {
            "ppg": "points per game",
            "rpg": "rebounds per game",
            "apg": "assists per game",
            "spg": "steals per game",
            "bpg": "blocks per game",
            "pts": "points",
            "reb": "rebounds",
            "ast": "assists",
            "stl": "steals",
            "blk": "blocks",
        }

        for abbr, full in stat_replacements.items():
            normalized = re.sub(rf"\b{abbr}\b", full, normalized)

        return normalized.strip()

    def _are_similar_stats(
        self, milestone1: Dict[str, any], milestone2: Dict[str, any]
    ) -> bool:
        """Check if milestones represent similar statistical achievements"""
        # Both must have statistical categories
        cats1 = set(cat.lower() for cat in milestone1.get("categories", []))
        cats2 = set(cat.lower() for cat in milestone2.get("categories", []))

        stat_categories = {"scoring", "assists", "rebounding", "steals", "blocks"}

        if not (
            cats1.intersection(stat_categories) and cats2.intersection(stat_categories)
        ):
            return False

        # Extract numbers from values
        value1 = milestone1.get("value", "")
        value2 = milestone2.get("value", "")

        numbers1 = self._extract_numbers(value1)
        numbers2 = self._extract_numbers(value2)

        # If both have numbers, check if they're in similar ranges
        if numbers1 and numbers2:
            # Simple heuristic: if any numbers are within 20% of each other
            for n1 in numbers1:
                for n2 in numbers2:
                    if n1 > 0 and n2 > 0:
                        ratio = min(n1, n2) / max(n1, n2)
                        if ratio >= 0.8:  # Within 20% of each other
                            return True

        return False

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract all numbers from text"""
        if not text:
            return []

        # Find all decimal numbers
        numbers = re.findall(r"\d+\.?\d*", text)
        return [float(n) for n in numbers if float(n) > 0]

    def _calculate_quality_score(self, milestone: Dict[str, any]) -> float:
        """Calculate quality score for milestone selection"""
        score = 0.0

        # Source reliability (if available)
        source_reliability = milestone.get("source_reliability", 0.5)
        score += source_reliability * 40  # Up to 40 points

        # Title specificity (longer, more detailed titles score higher)
        title_length = len(milestone.get("title", ""))
        score += min(title_length / 10, 20)  # Up to 20 points

        # Value specificity (more detailed values score higher)
        value_length = len(milestone.get("value", ""))
        score += min(value_length / 20, 20)  # Up to 20 points

        # Description completeness
        description_length = len(milestone.get("description", ""))
        score += min(description_length / 50, 10)  # Up to 10 points

        # Prefer official-sounding sources
        tweet_url = milestone.get("source_tweet_url", "")
        if any(official in tweet_url.lower() for official in ["wnba", "espn", "fever"]):
            score += 10  # Official source bonus

        return score
