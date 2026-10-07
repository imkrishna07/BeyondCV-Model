"""Typed request and response models for competitive-programming evidence."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PlatformStatus = Literal["not_provided", "available", "not_found", "unavailable", "rate_limited"]


class CodingAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leetcode_username: str | None = Field(default=None, min_length=1, max_length=100)
    codeforces_username: str | None = Field(default=None, min_length=1, max_length=100)


class CodingActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str | None = None
    timestamp: datetime | None = None
    verdict: str | None = None


class LeetCodeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    rating: float | None = None
    profile_rank: int | None = None
    contest_rank: int | None = None
    contest_top_percentile: float | None = None
    contests_participated: int | None = None
    problems_solved: int | None = Field(
        default=None,
        description="Total accepted problems reported by LeetCode across difficulty bands.",
    )
    easy: int | None = None
    medium: int | None = None
    hard: int | None = None
    recent_activity: list[CodingActivityItem] = Field(default_factory=list)
    recent_activity_available: bool = False


class ProblemDifficultyCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: str
    count: int


class CodeforcesContest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rank: int | None = None
    old_rating: int | None = None
    new_rating: int | None = None
    date: datetime | None = None


class CodeforcesProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    rating: int | None = None
    max_rating: int | None = None
    rank: str | None = None
    max_rank: str | None = None
    contests_participated: int | None = None
    problems_solved: int | None = Field(
        default=None,
        description="Unique accepted problems found among the most recent sampled submissions; may undercount lifetime solves.",
    )
    problem_difficulty_distribution: list[ProblemDifficultyCount] = Field(default_factory=list)
    recent_contests: list[CodeforcesContest] = Field(default_factory=list)
    recent_activity: list[CodingActivityItem] = Field(default_factory=list)
    submissions_sampled: int = 0
    problem_count_scope: str = "Unique accepted problems among the most recent bounded submission sample; not a lifetime total."


class NormalizedPlatformFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: float | None = Field(default=None, ge=0, le=100)
    peak_rating: float | None = Field(default=None, ge=0, le=100)
    problem_solving: float | None = Field(default=None, ge=0, le=100)
    contest_participation: float | None = Field(default=None, ge=0, le=100)
    platform_score: float | None = Field(default=None, ge=0, le=100)


class NormalizedCodingFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leetcode: NormalizedPlatformFeatures | None = None
    codeforces: NormalizedPlatformFeatures | None = None
    combined_score: float | None = Field(default=None, ge=0, le=100)
    method: str = "Ratings are linearly scaled to 0-100 using LeetCode 3000 and Codeforces 4000 reference ceilings; solved counts use log1p with a 2000-problem cap; contest counts scale linearly to 30 contests. These are fixed heuristics, not cross-platform percentiles."


class CodingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["leetcode", "codeforces"]
    finding: str
    fields: list[str] = Field(default_factory=list)


class CodingAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leetcode: LeetCodeProfile | None = None
    leetcode_status: PlatformStatus
    codeforces: CodeforcesProfile | None = None
    codeforces_status: PlatformStatus
    normalized_features: NormalizedCodingFeatures
    coding_score: int | None = Field(
        description="Competitive-programming evidence score only; null when neither profile has usable evidence."
    )
    score_weights: dict[str, int] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[CodingEvidence] = Field(default_factory=list)
    scoring_method: str = "LeetCode platform score weights: rating 50%, problem-solving 30%, contests 20%. Codeforces: rating 40%, peak rating 20%, problem-solving 25%, contests 15%. Missing features are omitted and remaining weights renormalized. coding_score is the arithmetic mean of available platform scores, never a sum of raw counts or ratings. This measures competitive-programming evidence only."
