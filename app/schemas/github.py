"""Typed request and response models for public GitHub evidence."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


GitHubUsername = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=39,
        pattern=r"^[A-Za-z0-9-]+$",
    ),
]


class GitHubAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: GitHubUsername

    @field_validator("username")
    @classmethod
    def validate_github_username(cls, value: str) -> str:
        if value.startswith("-") or value.endswith("-") or "--" in value:
            raise ValueError("GitHub username cannot start/end with a hyphen or contain consecutive hyphens.")
        return value


class GitHubTechnology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    repository_count: int
    percentage: float = Field(ge=0, le=100, description="Share of analyzed public repositories with this signal.")


class GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    full_name: str
    description: str | None = None
    url: str | None = None
    primary_language: str | None = None
    languages: dict[str, int] | None = None
    stars: int | None = None
    forks: int | None = None
    topics: list[str] = Field(default_factory=list)
    size_kb: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_fork: bool | None = None
    is_archived: bool | None = None
    has_readme: bool | None = None
    has_tests: bool | None = None
    has_ci_cd: bool | None = None
    has_docker: bool | None = None
    has_documentation: bool | None = None
    meaningful_structure: bool | None = None
    tree_truncated: bool | None = None


class GitHubActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commits: int | None = Field(default=None, description="Commit count observed in the sampled public events feed, not a lifetime total.")
    pull_requests: int | None = Field(default=None, description="Pull request events observed in the sampled public events feed.")
    issues: int | None = Field(default=None, description="Issue events observed in the sampled public events feed.")
    events_observed: int = 0
    source: str = "Recent public events feed; these are observed events, not lifetime totals."


class GitHubQualityIndicators(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documentation: int | None = Field(default=None, ge=0, le=100)
    testing: int | None = Field(default=None, ge=0, le=100)
    ci_cd: int | None = Field(default=None, ge=0, le=100)
    project_structure: int | None = Field(default=None, ge=0, le=100)
    repositories_evaluated: int = 0


class GitHubEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    finding: str
    repositories: list[str] = Field(default_factory=list)


class GitHubAnalysisResponse(BaseModel):
    """Observable public-profile and repository evidence; not a hiring decision."""

    model_config = ConfigDict(extra="forbid")

    username: str
    name: str | None = None
    bio: str | None = None
    company: str | None = None
    location: str | None = None
    blog: str | None = None
    profile_created_at: datetime | None = None
    public_repositories: int = 0
    analyzed_repositories: int = 0
    followers: int = 0
    following: int = 0
    repositories: list[GitHubRepository] = Field(default_factory=list)
    languages: list[GitHubTechnology] = Field(default_factory=list)
    technologies: list[GitHubTechnology] = Field(default_factory=list)
    activity: GitHubActivity
    quality_indicators: GitHubQualityIndicators
    github_score: int | None = Field(
        description="Evidence-coverage score only; it does not represent overall engineering ability."
    )
    score_weights: dict[str, int] = Field(default_factory=dict)
    evidence_level: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[GitHubEvidence] = Field(default_factory=list)
    not_assessed: list[str] = Field(
        default_factory=lambda: [
            "overall_engineering_ability", "originality", "student_authorship",
            "private_repository_work", "production_quality", "real_world_impact",
        ]
    )
    scoring_method: str = "Deterministic weighted average of documentation, testing, CI/CD, and project-structure coverage across inspected public repositories. Commit, repository, follower, star, and fork counts do not contribute to the score."
