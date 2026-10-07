"""Typed request and response models for candidate-supplied achievements."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AchievementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    rank: str | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1800, le=2200)
    domain: str | None = Field(default=None, max_length=200)
    participants: int | None = Field(default=None, ge=1)


class AchievementAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    achievements: list[AchievementInput] = Field(default_factory=list, max_length=200)
    job_description: str | None = Field(default=None, max_length=20000)


RecognitionLevel = Literal["participation", "finalist", "ranked", "winner_award", "unspecified"]


class AchievementEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rank: str | None = None
    year: int | None = None
    domain: str | None = None
    participants: int | None = None
    recognition_level: RecognitionLevel
    relevance: Literal["relevant", "not_relevant", "not_assessed"]
    matched_terms: list[str] = Field(default_factory=list)


class AchievementEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str
    achievement_index: int | None = None
    fields: list[str] = Field(default_factory=list)


class AchievementAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    achievements: list[AchievementEvidenceItem] = Field(default_factory=list)
    achievement_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    evidence: list[AchievementEvidence] = Field(default_factory=list)
    score_method: str
    status: Literal["no_data", "available"]
