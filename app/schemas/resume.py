"""Typed output schemas for deterministic resume extraction."""

from pydantic import BaseModel, ConfigDict, Field


class ResumeFact(BaseModel):
    """Verbatim resume content associated with a recognized section."""

    model_config = ConfigDict(extra="forbid")

    details: str = Field(description="Text copied from the resume without inference.")


class ResumeSkill(BaseModel):
    """A skill explicitly listed in the resume's skills section."""

    model_config = ConfigDict(extra="forbid")

    name: str


class ResumeEducation(ResumeFact):
    """An explicitly stated education record."""


class ResumeExperience(ResumeFact):
    """An explicitly stated experience record."""


class ResumeProject(ResumeFact):
    """An explicitly stated project record."""


class ResumeCertification(ResumeFact):
    """An explicitly stated certification record."""


class ResumeAchievement(ResumeFact):
    """An explicitly stated achievement record."""


class ResumeResearch(ResumeFact):
    """An explicitly stated research record."""


class ResumeAnalysisResponse(BaseModel):
    """Structured resume facts grouped by recognized section."""

    model_config = ConfigDict(extra="forbid")

    skills: list[ResumeSkill] = Field(default_factory=list)
    education: list[ResumeEducation] = Field(default_factory=list)
    experience: list[ResumeExperience] = Field(default_factory=list)
    projects: list[ResumeProject] = Field(default_factory=list)
    certifications: list[ResumeCertification] = Field(default_factory=list)
    achievements: list[ResumeAchievement] = Field(default_factory=list)
    research: list[ResumeResearch] = Field(default_factory=list)
