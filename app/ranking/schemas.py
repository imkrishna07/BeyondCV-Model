"""API input and output schemas for normalized candidate evidence vectors."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.achievements import AchievementAnalysisResponse
from app.schemas.certifications import CertificationAnalysisResponse
from app.schemas.coding import CodingAnalysisResponse
from app.schemas.github import GitHubAnalysisResponse
from app.schemas.kaggle import KaggleAnalysisResponse
from app.schemas.project import ProjectAnalysisResponse
from app.schemas.research import ResearchAnalysisResponse
from app.schemas.resume import ResumeAnalysisResponse


class CandidateAnalysisInputs(BaseModel):
    """Existing analyzer responses; omitted analyzers remain unavailable in the vector."""

    model_config = ConfigDict(extra="forbid")

    resume: ResumeAnalysisResponse | None = None
    project: ProjectAnalysisResponse | None = None
    github: GitHubAnalysisResponse | None = None
    coding: CodingAnalysisResponse | None = None
    kaggle: KaggleAnalysisResponse | None = None
    research: ResearchAnalysisResponse | None = None
    certifications: CertificationAnalysisResponse | None = None
    achievements: AchievementAnalysisResponse | None = None


class FeatureDatum(BaseModel):
    """A single preserved value with explicit availability, provenance, and optional normalization."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    normalized_value: float | None = None
    available: bool
    source: str
    evidence: list[str] = Field(default_factory=list)
    normalization: str | None = None

    @model_validator(mode="after")
    def normalized_value_requires_available_data(self) -> "FeatureDatum":
        if self.normalized_value is not None and not self.available:
            raise ValueError("normalized_value cannot be set when feature data is unavailable")
        return self


class FeatureGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    sources: list[str] = Field(default_factory=list)
    features: dict[str, FeatureDatum] = Field(default_factory=dict)
    source_payloads: dict[str, Any] = Field(default_factory=dict)


class SkillFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    normalized_key: str
    sources: list[str]
    evidence: list[str]


class CandidateFeatureVector(BaseModel):
    """Normalized evidence representation; it deliberately has no overall candidate score."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    technical_skills: list[SkillFeature] = Field(default_factory=list)
    project_features: FeatureGroup
    github_features: FeatureGroup
    coding_features: FeatureGroup
    kaggle_features: FeatureGroup
    research_features: FeatureGroup
    certification_features: FeatureGroup
    achievement_features: FeatureGroup
    experience_features: FeatureGroup
    evidence_vector: list[dict[str, Any]] = Field(default_factory=list)
