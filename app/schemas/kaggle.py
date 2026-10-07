"""Typed Kaggle evidence request and response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KaggleAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class KaggleArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str | None = None
    description: str | None = None
    last_updated: str | None = None
    topics: list[str] = Field(default_factory=list)
    language: str | None = None


class KaggleActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competitions: int | None = None
    medals: int | None = None
    notebooks: int | None = None
    datasets: int | None = None
    recent_activity_available: bool = False
    profile_verified: bool = False


class KaggleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    finding: str
    fields: list[str] = Field(default_factory=list)


class KaggleAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    status: Literal["available", "not_found", "unavailable", "rate_limited"]
    competitions: list[KaggleArtifact] = Field(default_factory=list)
    medals: list[str] = Field(default_factory=list)
    notebooks: list[KaggleArtifact] = Field(default_factory=list)
    datasets: list[KaggleArtifact] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    activity: KaggleActivity
    kaggle_score: int | None = Field(default=None, ge=0, le=100)
    score_method: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[KaggleEvidence] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)
