"""Typed request and response models for candidate-supplied research evidence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ResearchPublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=100)
    venue: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1800, le=2200)
    url: HttpUrl | None = None
    abstract: str | None = Field(default=None, max_length=20000)
    role: str | None = Field(default=None, max_length=1000)
    project_connection: str | None = Field(default=None, max_length=1000)


class ResearchAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str | None = Field(default=None, max_length=300)
    research: list[ResearchPublicationInput] = Field(default_factory=list, max_length=100)


class ResearchPublicationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    authors: list[str]
    venue: str | None = None
    year: int | None = None
    url: str | None = None
    abstract_provided: bool
    research_domains: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    candidate_authorship: Literal["listed_by_candidate", "not_listed", "unavailable"]
    stated_role: str | None = None
    project_connection: str | None = None
    project_connection_source: Literal["candidate_supplied", "unavailable"]
    verification_status: Literal["not_verified"] = "not_verified"


class ResearchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str
    publication_index: int | None = None
    fields: list[str] = Field(default_factory=list)


class ResearchAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_count: int
    publications: list[ResearchPublicationEvidence] = Field(default_factory=list)
    research_domains: list[str] = Field(default_factory=list)
    research_score: int | None = Field(default=None, ge=0, le=100)
    score_method: str
    strengths: list[str] = Field(default_factory=list)
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)
