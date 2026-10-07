"""Platform-specific transforms to bounded 0-100 competitive evidence features."""

import math

from app.schemas.coding import (
    CodeforcesProfile,
    LeetCodeProfile,
    NormalizedPlatformFeatures,
)


LEETCODE_RATING_REFERENCE = 3000
CODEFORCES_RATING_REFERENCE = 4000
PROBLEM_SOLVE_SATURATION = 2000
CONTEST_SATURATION = 30


def _bounded_linear(value: int | float | None, reference: int | float) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(100.0, float(value) / reference * 100)), 2)


def _log_count(value: int | None) -> float | None:
    if value is None:
        return None
    bounded = max(0, min(value, PROBLEM_SOLVE_SATURATION))
    return round(math.log1p(bounded) / math.log1p(PROBLEM_SOLVE_SATURATION) * 100, 2)


def _contest_count(value: int | None) -> float | None:
    if value is None:
        return None
    return round(max(0, min(value, CONTEST_SATURATION)) / CONTEST_SATURATION * 100, 2)


def normalize_leetcode(profile: LeetCodeProfile) -> NormalizedPlatformFeatures:
    """Normalize LeetCode measures using fixed LeetCode-specific reference values."""
    return NormalizedPlatformFeatures(
        rating=_bounded_linear(profile.rating, LEETCODE_RATING_REFERENCE),
        problem_solving=_log_count(profile.problems_solved),
        contest_participation=_contest_count(profile.contests_participated),
    )


def normalize_codeforces(profile: CodeforcesProfile) -> NormalizedPlatformFeatures:
    """Normalize Codeforces measures using fixed Codeforces-specific reference values."""
    return NormalizedPlatformFeatures(
        rating=_bounded_linear(profile.rating, CODEFORCES_RATING_REFERENCE),
        peak_rating=_bounded_linear(profile.max_rating, CODEFORCES_RATING_REFERENCE),
        problem_solving=_log_count(profile.problems_solved),
        contest_participation=_contest_count(profile.contests_participated),
    )
