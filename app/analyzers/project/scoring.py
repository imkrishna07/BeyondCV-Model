"""Transparent deterministic rubric, kept separate from project inspection."""

from dataclasses import dataclass

from app.schemas.project import ProjectInspection


@dataclass(frozen=True)
class ProjectScores:
    project_score: int | None
    technical_complexity: int | None
    code_quality: int | None
    architecture: int | None
    documentation: int | None
    testing: int | None
    deployment: int | None
    security: int | None
    completeness: int | None
    evidence_level: str
    project_scale: str


WEIGHTS = {
    "technical_complexity": 18,
    "code_quality": 16,
    "architecture": 16,
    "documentation": 10,
    "testing": 10,
    "deployment": 10,
    "security": 10,
    "completeness": 10,
}


def _score(value: float) -> int:
    return max(0, min(100, round(value)))


def score_project(inspection: ProjectInspection) -> ProjectScores:
    """Score only detectable static signals; never evaluate originality or impact."""
    has_project_files = bool(inspection.file_paths)
    has_source = bool(inspection.source_files)

    if not has_project_files:
        return ProjectScores(None, None, None, None, None, None, None, None, None, "insufficient", "insufficient_evidence")

    docs = inspection.documentation_signals
    docs_points = sum(bool(docs.get(key)) for key in (
        "readme", "problem_statement", "setup_instructions", "architecture_explanation",
        "api_documentation", "screenshots_or_demo",
    ))
    documentation = _score(docs_points / 6 * 100)

    testing = None
    if has_source:
        testing = _score(
            (55 if inspection.test_files else 0)
            + (20 if any(t.category == "test framework" for t in inspection.technologies) else 0)
            + (25 if inspection.coverage_files else 0)
        )

    deployment = _score(
        (30 if inspection.docker_files else 0)
        + (30 if inspection.ci_files else 0)
        + (20 if inspection.cloud_files else 0)
        + (20 if any(path not in inspection.docker_files and path not in inspection.cloud_files for path in inspection.deployment_files) else 0)
    )

    security = None
    if has_source:
        security = _score(
            30
            + (20 if inspection.env_usage_files else 0)
            + (20 if inspection.auth_files else 0)
            + (15 if inspection.dependency_files else 0)
            - min(60, 60 * len(inspection.secret_pattern_files))
        )

    architecture = None
    complexity = None
    code_quality = None
    if has_source:
        architecture = _score(
            35
            + min(40, len(inspection.separation_directories) * 10)
            + (25 if inspection.frontend_files and inspection.backend_files else 0)
        )
        complexity_signals = (
            bool(inspection.frontend_files and inspection.backend_files),
            bool(inspection.database_files),
            bool(inspection.auth_files),
            bool(inspection.api_files),
            bool(inspection.integration_files),
            bool(inspection.algorithm_files),
            bool(inspection.deployment_files or inspection.ci_files or inspection.cloud_files),
            len(inspection.languages) > 1,
        )
        complexity = _score(sum(complexity_signals) / len(complexity_signals) * 100)

        source_count = len(inspection.source_files)
        naming_ratio = inspection.naming_consistent_files / source_count if source_count else 0
        duplicate_penalty = min(35, inspection.duplicate_line_count * 3)
        code_quality = _score(
            35
            + (15 if len(inspection.source_directories) > 1 else 0)
            + 20 * naming_ratio
            + (15 if inspection.error_handling_files else 0)
            + (15 if inspection.meaningful_code_lines >= 10 else 0)
            - duplicate_penalty
        )

    completeness = _score(
        (30 if has_source else 0)
        + (20 if docs.get("readme") else 0)
        + (15 if inspection.test_files else 0)
        + (10 if inspection.dependency_files else 0)
        + (10 if inspection.deployment_files or inspection.ci_files or inspection.cloud_files else 0)
        + (10 if inspection.frontend_files and inspection.backend_files else 0)
        + (5 if len(inspection.source_directories) > 1 else 0)
    )

    dimensions = {
        "technical_complexity": complexity,
        "code_quality": code_quality,
        "architecture": architecture,
        "documentation": documentation,
        "testing": testing,
        "deployment": deployment,
        "security": security,
        "completeness": completeness,
    }
    available = [(value, WEIGHTS[name]) for name, value in dimensions.items() if value is not None]
    project_score = _score(sum(value * weight for value, weight in available) / sum(weight for _, weight in available))

    evidence_categories = sum((
        bool(inspection.source_files), bool(inspection.documentation_files),
        bool(inspection.test_files), bool(inspection.configuration_files),
    ))
    if len(inspection.file_paths) >= 20 and evidence_categories >= 3:
        evidence_level = "strong"
    elif len(inspection.file_paths) >= 5 and evidence_categories >= 2:
        evidence_level = "moderate"
    else:
        evidence_level = "limited"

    project_scale = (
        "substantial"
        if len(inspection.source_files) >= 8 and inspection.meaningful_code_lines >= 200
        else "small" if has_source else "insufficient_evidence"
    )
    return ProjectScores(
        project_score, complexity, code_quality, architecture, documentation,
        testing, deployment, security, completeness, evidence_level, project_scale,
    )
