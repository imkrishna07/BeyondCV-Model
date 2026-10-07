"""Typed request and response models for candidate-supplied certifications."""

from __future__ import annotations

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CertificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    issuer: str | None = Field(default=None, max_length=200)
    date: Date | None = None
    url: HttpUrl | None = None
    domain: str | None = Field(default=None, max_length=200)


class CertificationAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certifications: list[CertificationInput] = Field(default_factory=list, max_length=200)
    job_description: str | None = Field(default=None, max_length=20000)


class CertificationEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    issuer: str | None = None
    date: Date | None = None
    domain: str | None = None
    url: str | None = None
    relevance: Literal["relevant", "not_relevant", "not_assessed"]
    matched_terms: list[str] = Field(default_factory=list)


class CertificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str
    certification_index: int | None = None
    fields: list[str] = Field(default_factory=list)


class CertificationAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certifications: list[CertificationEvidenceItem] = Field(default_factory=list)
    certification_score: int = Field(ge=0, le=100)
    relevant_certifications: list[CertificationEvidenceItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    evidence: list[CertificationEvidence] = Field(default_factory=list)
    score_method: str
    status: Literal["no_data", "available"]
