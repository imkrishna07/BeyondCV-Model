"""Request and response models for deterministic candidate ranking."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ranking.schemas import CandidateFeatureVector
from app.schemas.job import JobRequirementVector


class CandidateToRank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=200)
    candidate_features: CandidateFeatureVector


class RankCandidatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_requirements: JobRequirementVector
    candidates: list[CandidateToRank] = Field(min_length=1, max_length=500)

    @field_validator("candidates")
    @classmethod
    def candidate_ids_must_be_unique(cls, candidates: list[CandidateToRank]) -> list[CandidateToRank]:
        ids = [candidate.candidate_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique in a ranking request")
        return candidates


class ComponentScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None, ge=0, le=100)
    available: bool
    weight: float = Field(ge=0, le=1)
    effective_weight: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    reason: str

    @model_validator(mode="after")
    def availability_matches_score(self) -> "ComponentScore":
        if self.available != (self.score is not None):
            raise ValueError("component availability must match whether a score is present")
        return self


class RankingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str
    requirement: str | None = None
    source: str
    finding: str
    supports_match: bool | None = None


class RankedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    candidate_id: str
    overall_score: float | None = Field(default=None, ge=0, le=100)
    job_fit_score: float | None = Field(default=None, ge=0, le=100)
    data_coverage: float = Field(ge=0, le=1)
    job_fit_coverage: float = Field(ge=0, le=1)
    component_scores: dict[str, ComponentScore]
    matched_required_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    skill_evidence_available: bool
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[RankingEvidence] = Field(default_factory=list)
    explanation: str


class RankCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked_candidates: list[RankedCandidate]
    job_domain: str | None = None
    weight_profile: str
    scoring_method: str
    limitations: list[str] = Field(default_factory=list)
