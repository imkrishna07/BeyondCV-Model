"""Public and internal schemas for project inspection results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    finding: str
    files: list[str] = Field(default_factory=list)


class ProjectTechnology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    evidence_files: list[str] = Field(default_factory=list)


class ProjectStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_files: int = 0
    source_files: int = 0
    documentation_files: int = 0
    test_files: int = 0
    configuration_files: int = 0
    skipped_binary_files: int = 0
    skipped_large_files: int = 0
    file_types: dict[str, int] = Field(default_factory=dict)
    languages: dict[str, int] = Field(default_factory=dict)
    component_count: int = 0
    source_directories: list[str] = Field(default_factory=list)
    frontend_present: bool = False
    backend_present: bool = False


class ProjectAnalysisResponse(BaseModel):
    """Transparent, evidence-based project analysis. Scores can be null when evidence is insufficient."""

    model_config = ConfigDict(extra="forbid")

    project_score: int | None = Field(description="Weighted deterministic score, or null if evidence is insufficient.")
    technical_complexity: int | None
    code_quality: int | None
    architecture: int | None
    documentation: int | None
    testing: int | None
    deployment: int | None
    security: int | None
    completeness: int | None
    evidence_level: Literal["insufficient", "limited", "moderate", "strong"]
    project_scale: Literal["insufficient_evidence", "small", "substantial"] = Field(
        description="Heuristic source-size classification; not a statement about production quality."
    )
    score_weights: dict[str, int] = Field(default_factory=dict)
    dimension_scoring: dict[str, str] = Field(default_factory=dict)
    structure: ProjectStructure
    technologies: list[ProjectTechnology] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[ProjectEvidence] = Field(default_factory=list)
    not_assessed: list[str] = Field(
        default_factory=lambda: [
            "originality", "student_authorship", "production_quality", "real_world_impact"
        ],
        description="Properties that cannot be reliably determined from a static project scan.",
    )
    scoring_method: str = "Deterministic static-evidence rubric; dimension scores are 0-100 and project_score is a weighted mean of available dimensions."


class ProjectInspection(BaseModel):
    """Internal facts gathered before scoring; contains no file contents in the API response."""

    file_paths: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    documentation_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    configuration_files: list[str] = Field(default_factory=list)
    skipped_binary_files: int = 0
    skipped_large_files: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    source_directories: list[str] = Field(default_factory=list)
    frontend_files: list[str] = Field(default_factory=list)
    backend_files: list[str] = Field(default_factory=list)
    dependency_files: list[str] = Field(default_factory=list)
    technologies: list[ProjectTechnology] = Field(default_factory=list)
    readme_files: list[str] = Field(default_factory=list)
    readme_headings: list[str] = Field(default_factory=list)
    documentation_signals: dict[str, list[str]] = Field(default_factory=dict)
    separation_directories: list[str] = Field(default_factory=list)
    api_files: list[str] = Field(default_factory=list)
    api_docs_files: list[str] = Field(default_factory=list)
    database_files: list[str] = Field(default_factory=list)
    auth_files: list[str] = Field(default_factory=list)
    integration_files: list[str] = Field(default_factory=list)
    algorithm_files: list[str] = Field(default_factory=list)
    deployment_files: list[str] = Field(default_factory=list)
    docker_files: list[str] = Field(default_factory=list)
    ci_files: list[str] = Field(default_factory=list)
    cloud_files: list[str] = Field(default_factory=list)
    coverage_files: list[str] = Field(default_factory=list)
    env_usage_files: list[str] = Field(default_factory=list)
    secret_pattern_files: list[str] = Field(default_factory=list)
    error_handling_files: list[str] = Field(default_factory=list)
    meaningful_code_lines: int = 0
    duplicate_line_count: int = 0
    naming_consistent_files: int = 0
