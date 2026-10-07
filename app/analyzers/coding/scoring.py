"""Deterministic competitive-programming evidence scoring, isolated from collection."""

from app.schemas.coding import NormalizedPlatformFeatures


SCORE_WEIGHTS = {
    "leetcode_rating": 50,
    "leetcode_problem_solving": 30,
    "leetcode_contest_participation": 20,
    "codeforces_rating": 40,
    "codeforces_peak_rating": 20,
    "codeforces_problem_solving": 25,
    "codeforces_contest_participation": 15,
}


def _weighted_platform_score(features: NormalizedPlatformFeatures, weights: dict[str, int]) -> float | None:
    values = {
        "rating": features.rating,
        "peak_rating": features.peak_rating,
        "problem_solving": features.problem_solving,
        "contest_participation": features.contest_participation,
    }
    available = [(values[key], weight) for key, weight in weights.items() if values.get(key) is not None]
    if not available:
        return None
    return round(sum(float(value) * weight for value, weight in available) / sum(weight for _, weight in available), 2)


def score_leetcode(features: NormalizedPlatformFeatures) -> NormalizedPlatformFeatures:
    """Score available normalized LeetCode features; renormalize for missing fields."""
    weights = {
        "rating": SCORE_WEIGHTS["leetcode_rating"],
        "problem_solving": SCORE_WEIGHTS["leetcode_problem_solving"],
        "contest_participation": SCORE_WEIGHTS["leetcode_contest_participation"],
    }
    return features.model_copy(update={"platform_score": _weighted_platform_score(features, weights)})


def score_codeforces(features: NormalizedPlatformFeatures) -> NormalizedPlatformFeatures:
    """Score available normalized Codeforces features; renormalize for missing fields."""
    weights = {
        "rating": SCORE_WEIGHTS["codeforces_rating"],
        "peak_rating": SCORE_WEIGHTS["codeforces_peak_rating"],
        "problem_solving": SCORE_WEIGHTS["codeforces_problem_solving"],
        "contest_participation": SCORE_WEIGHTS["codeforces_contest_participation"],
    }
    return features.model_copy(update={"platform_score": _weighted_platform_score(features, weights)})


def combine_platform_scores(
    leetcode: NormalizedPlatformFeatures | None,
    codeforces: NormalizedPlatformFeatures | None,
) -> int | None:
    """Average available platform scores so raw rating/problem scales are never added."""
    scores = [
        features.platform_score
        for features in (leetcode, codeforces)
        if features is not None and features.platform_score is not None
    ]
    return round(sum(scores) / len(scores)) if scores else None
