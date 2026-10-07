"""Structured job requirements extracted from natural-language descriptions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(max_length=50000)


class SkillEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    requirement: Literal["required", "preferred"]
    priority: float = Field(ge=0, le=1)
    category: str
    excerpt: str
    cue: str | None = None


class ExperienceRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    minimum_years: int | None = None
    maximum_years: int | None = None
    requirement: Literal["required", "preferred", "unspecified"]


class EducationRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    level: str | None = None
    requirement: Literal["required", "preferred", "unspecified"]


class JobRequirementVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    domain: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    cloud_technologies: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    skill_priorities: dict[str, float] = Field(default_factory=dict)
    skill_evidence: list[SkillEvidence] = Field(default_factory=list)
    experience_requirements: list[ExperienceRequirement] = Field(default_factory=list)
    education_requirements: list[EducationRequirement] = Field(default_factory=list)
    relevant_evidence: list[str] = Field(default_factory=list)
    extraction_method: Literal["rules", "rules+semantic"] = "rules"
    role_evidence: str | None = None
    domain_evidence: str | None = None


class JobAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_requirements: JobRequirementVector
