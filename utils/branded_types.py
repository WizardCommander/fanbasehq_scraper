"""
Branded types for type safety following CLAUDE.md C-5 requirement
"""

from typing import TypeVar, Generic

# Base branded type implementation
T = TypeVar("T")
Brand = TypeVar("Brand")


class BrandedType(Generic[T, Brand]):
    """Base class for branded types to prevent type confusion"""

    def __init__(self, value: T):
        self._value = value

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._value!r})"

    @property
    def value(self) -> T:
        return self._value

    def __eq__(self, other) -> bool:
        if isinstance(other, BrandedType):
            return self._value == other._value
        return self._value == other

    def __hash__(self) -> int:
        return hash(self._value)


# Specific branded types for our domain
class TweetId(BrandedType[str, "TweetId"]):
    """Branded type for Tweet IDs to prevent confusion with other string IDs"""

    pass


class SubmissionId(BrandedType[int, "SubmissionId"]):
    """Branded type for Submission IDs to prevent confusion with other integers"""

    pass


class PlayerId(BrandedType[str, "PlayerId"]):
    """Branded type for Player IDs to prevent confusion with player names"""

    pass


class TeamId(BrandedType[str, "TeamId"]):
    """Branded type for Team IDs"""

    pass


class ShoeBrand(BrandedType[str, "ShoeBrand"]):
    """Branded type for shoe brand names to prevent confusion with other strings"""

    pass


class ShoeModel(BrandedType[str, "ShoeModel"]):
    """Branded type for shoe model names to prevent confusion with other strings"""

    pass


class ImageUrl(BrandedType[str, "ImageUrl"]):
    """Branded type for image URLs to prevent confusion with other URLs"""

    pass


class KicksCrewUrl(BrandedType[str, "KicksCrewUrl"]):
    """Branded type for KicksCrew URLs to prevent confusion with other URLs"""

    pass


class SearchUrl(BrandedType[str, "SearchUrl"]):
    """Branded type for search URLs to prevent confusion with product URLs"""

    pass


class Price(BrandedType[str, "Price"]):
    """Branded type for price strings to prevent confusion with other strings"""

    pass


# Convenience constructors
def tweet_id(value: str) -> TweetId:
    """Create a TweetId from string"""
    return TweetId(value)


def submission_id(value: int) -> SubmissionId:
    """Create a SubmissionId from int"""
    return SubmissionId(value)


def player_id(value: str) -> PlayerId:
    """Create a PlayerId from string"""
    return PlayerId(value)


def team_id(value: str) -> TeamId:
    """Create a TeamId from string"""
    return TeamId(value)


def shoe_brand(value: str) -> ShoeBrand:
    """Create a ShoeBrand from string"""
    return ShoeBrand(value)


def shoe_model(value: str) -> ShoeModel:
    """Create a ShoeModel from string"""
    return ShoeModel(value)


def image_url(value: str) -> ImageUrl:
    """Create an ImageUrl from string"""
    return ImageUrl(value)


def kickscrew_url(value: str) -> KicksCrewUrl:
    """Create a KicksCrewUrl from string"""
    return KicksCrewUrl(value)


def search_url(value: str) -> SearchUrl:
    """Create a SearchUrl from string"""
    return SearchUrl(value)


def price(value: str) -> Price:
    """Create a Price from string"""
    return Price(value)
