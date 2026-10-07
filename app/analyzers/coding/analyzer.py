"""Orchestrate the two competitive-programming providers and shape their evidence."""

from app.analyzers.coding.codeforces import fetch_codeforces_profile
from app.analyzers.coding.errors import (
    CodingAPIError,
    CodingNetworkError,
    CodingProfileNotFound,
    CodingRateLimitError,
    InvalidCodingUsername,
)
from app.analyzers.coding.leetcode import fetch_leetcode_profile
from app.analyzers.coding.normalizer import normalize_codeforces, normalize_leetcode
from app.analyzers.coding.scoring import (
    SCORE_WEIGHTS,
    combine_platform_scores,
    score_codeforces,
    score_leetcode,
)
from app.schemas.coding import (
    CodingAnalysisResponse,
    CodingEvidence,
    CodeforcesProfile,
    LeetCodeProfile,
    NormalizedCodingFeatures,
    NormalizedPlatformFeatures,
)


def _collect(username: str | None, fetcher):
    if username is None or not username.strip():
        return None, "not_provided"
    try:
        return fetcher(username), "available"
    except InvalidCodingUsername:
        raise
    except CodingProfileNotFound:
        return None, "not_found"
    except CodingRateLimitError:
        return None, "rate_limited"
    except (CodingAPIError, CodingNetworkError):
        return None, "unavailable"


def _evidence(leetcode: LeetCodeProfile | None, codeforces: CodeforcesProfile | None) -> list[CodingEvidence]:
    evidence: list[CodingEvidence] = []
    if leetcode:
        fields: list[str] = []
        if leetcode.rating is not None:
            fields.append("rating")
        if leetcode.problems_solved is not None:
            fields.append("problems_solved")
        if leetcode.contests_participated is not None:
            fields.append("contests_participated")
        if fields:
            evidence.append(CodingEvidence(
                platform="leetcode",
                finding="LeetCode public profile exposed " + ", ".join(fields) + ".",
                fields=fields,
            ))
        if leetcode.recent_activity_available:
            evidence.append(CodingEvidence(
                platform="leetcode",
                finding=f"Recent accepted-submission activity is available ({len(leetcode.recent_activity)} entries).",
                fields=["recent_activity"],
            ))
    if codeforces:
        fields = []
        if codeforces.rating is not None:
            fields.append("rating")
        if codeforces.max_rating is not None:
            fields.append("max_rating")
        if codeforces.contests_participated is not None:
            fields.append("contests_participated")
        if codeforces.problems_solved is not None:
            fields.append("problems_solved_sample")
        if fields:
            evidence.append(CodingEvidence(
                platform="codeforces",
                finding="Codeforces public profile exposed " + ", ".join(fields) + ".",
                fields=fields,
            ))
        if codeforces.recent_contests:
            evidence.append(CodingEvidence(
                platform="codeforces",
                finding=f"Recent rated contest history is available ({len(codeforces.recent_contests)} entries shown).",
                fields=["recent_contests"],
            ))
    return evidence


def analyze_coding_profiles(
    leetcode_username: str | None = None,
    codeforces_username: str | None = None,
) -> CodingAnalysisResponse:
    """Fetch and normalize public coding-profile evidence independently by platform."""
    leetcode, leetcode_status = _collect(leetcode_username, fetch_leetcode_profile)
    codeforces, codeforces_status = _collect(codeforces_username, fetch_codeforces_profile)

    leetcode_features: NormalizedPlatformFeatures | None = None
    if leetcode is not None:
        leetcode_features = score_leetcode(normalize_leetcode(leetcode))
    codeforces_features: NormalizedPlatformFeatures | None = None
    if codeforces is not None:
        codeforces_features = score_codeforces(normalize_codeforces(codeforces))

    coding_score = combine_platform_scores(leetcode_features, codeforces_features)
    strengths: list[str] = []
    weaknesses: list[str] = []
    available_scores = [
        (platform, features.platform_score)
        for platform, features in (("LeetCode", leetcode_features), ("Codeforces", codeforces_features))
        if features is not None and features.platform_score is not None
    ]
    for platform, score in available_scores:
        if score >= 75:
            strengths.append(f"{platform} competitive-programming evidence scored {score:.0f}/100 on the available-data rubric.")
        elif score < 35:
            weaknesses.append(f"{platform} competitive-programming evidence is limited on the available-data rubric ({score:.0f}/100); this does not measure general software-engineering ability.")
    if not available_scores:
        if leetcode_status == "not_provided" and codeforces_status == "not_provided":
            weaknesses.append("No coding-profile usernames were provided; no performance score was calculated.")
        else:
            weaknesses.append("No usable competitive-programming data was available; no performance score was calculated.")

    normalized = NormalizedCodingFeatures(
        leetcode=leetcode_features,
        codeforces=codeforces_features,
        combined_score=float(coding_score) if coding_score is not None else None,
    )
    return CodingAnalysisResponse(
        leetcode=leetcode,
        leetcode_status=leetcode_status,
        codeforces=codeforces,
        codeforces_status=codeforces_status,
        normalized_features=normalized,
        coding_score=coding_score,
        score_weights=SCORE_WEIGHTS,
        strengths=strengths,
        weaknesses=weaknesses,
        evidence=_evidence(leetcode, codeforces),
    )
