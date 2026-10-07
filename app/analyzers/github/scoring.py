"""Deterministic scoring of observable GitHub repository evidence."""

from dataclasses import dataclass

from app.schemas.github import GitHubQualityIndicators, GitHubRepository


SCORE_WEIGHTS = {
    "documentation": 25,
    "testing": 30,
    "ci_cd": 25,
    "project_structure": 20,
}


@dataclass(frozen=True)
class GitHubEvidenceScore:
    quality_indicators: GitHubQualityIndicators
    github_score: int | None


def _coverage(repositories: list[GitHubRepository], attribute: str) -> int | None:
    observed = [getattr(repo, attribute) for repo in repositories if getattr(repo, attribute) is not None]
    if not observed:
        return None
    return round(sum(bool(value) for value in observed) / len(observed) * 100)


def score_github_evidence(repositories: list[GitHubRepository]) -> GitHubEvidenceScore:
    """Aggregate repository evidence coverage; popularity and activity are excluded."""
    quality = GitHubQualityIndicators(
        documentation=_coverage(repositories, "has_readme"),
        testing=_coverage(repositories, "has_tests"),
        ci_cd=_coverage(repositories, "has_ci_cd"),
        project_structure=_coverage(repositories, "meaningful_structure"),
        repositories_evaluated=len(repositories),
    )
    dimensions = quality.model_dump(exclude={"repositories_evaluated"})
    available = [(dimensions[key], weight) for key, weight in SCORE_WEIGHTS.items() if dimensions[key] is not None]
    score = round(sum(value * weight for value, weight in available) / sum(weight for _, weight in available)) if available else None
    return GitHubEvidenceScore(quality_indicators=quality, github_score=score)
