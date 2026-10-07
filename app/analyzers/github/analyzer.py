"""Collect public GitHub evidence with PyGithub and format a structured analysis."""

from datetime import datetime
from itertools import islice
import os
import re
from typing import Any

from dotenv import load_dotenv
from github import Github
from github.GithubException import GithubException, RateLimitExceededException
import requests

from app.analyzers.github.scoring import SCORE_WEIGHTS, score_github_evidence
from app.schemas.github import (
    GitHubActivity,
    GitHubAnalysisResponse,
    GitHubEvidence,
    GitHubRepository,
    GitHubTechnology,
)


MAX_REPOSITORIES = 15
MAX_ACTIVITY_EVENTS = 100
USERNAME_PATTERN = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$")
TECHNOLOGY_TOPICS = {
    "angular": "Angular", "aws": "AWS", "azure": "Azure", "docker": "Docker",
    "django": "Django", "express": "Express", "fastapi": "FastAPI",
    "firebase": "Firebase", "flask": "Flask", "gcp": "Google Cloud",
    "kubernetes": "Kubernetes", "mongodb": "MongoDB", "mysql": "MySQL",
    "nextjs": "Next.js", "postgresql": "PostgreSQL", "pytorch": "PyTorch",
    "react": "React", "redis": "Redis", "spring-boot": "Spring Boot",
    "tailwindcss": "Tailwind CSS", "tensorflow": "TensorFlow", "terraform": "Terraform",
    "vue": "Vue", "nodejs": "Node.js",
}
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{8,}['\"]?"),
)


class GitHubAnalyzerError(Exception):
    """Base class for safe, user-facing GitHub analyzer errors."""


class InvalidGitHubUsername(GitHubAnalyzerError):
    pass


class GitHubProfileNotFound(GitHubAnalyzerError):
    pass


class GitHubRateLimitError(GitHubAnalyzerError):
    pass


class GitHubAPIError(GitHubAnalyzerError):
    pass


class GitHubNetworkError(GitHubAnalyzerError):
    pass


def _redact_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None
    for pattern in _SECRET_TEXT_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def _is_rate_limit(exc: GithubException) -> bool:
    headers = {key.lower(): str(value) for key, value in (exc.headers or {}).items()}
    return (
        isinstance(exc, RateLimitExceededException)
        or headers.get("x-ratelimit-remaining") == "0"
        or "rate limit" in str(exc).lower()
    )


def _raise_api_error(exc: GithubException, *, profile_lookup: bool = False) -> None:
    if _is_rate_limit(exc):
        raise GitHubRateLimitError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.") from exc
    if profile_lookup and exc.status == 404:
        raise GitHubProfileNotFound("Public GitHub profile was not found or is unavailable.") from exc
    raise GitHubAPIError("GitHub API could not provide the requested public data.") from exc


def _iso(value: datetime | None) -> datetime | None:
    return value


def _repo_tree(repo: Any) -> tuple[set[str] | None, bool | None]:
    branch = getattr(repo, "default_branch", None)
    if not branch:
        return None, None
    try:
        tree = repo.get_git_tree(branch, recursive=True)
    except GithubException as exc:
        if _is_rate_limit(exc):
            raise GitHubRateLimitError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.") from exc
        if exc.status == 404:
            return None, None
        _raise_api_error(exc)
    paths = {
        element.path for element in tree.tree
        if getattr(element, "type", "blob") == "blob" and isinstance(getattr(element, "path", None), str)
    }
    return paths, bool(getattr(tree, "truncated", False))


def _tree_signals(paths: set[str] | None, truncated: bool | None) -> dict[str, bool | None]:
    if paths is None:
        return {
            "has_readme": None, "has_tests": None, "has_ci_cd": None,
            "has_docker": None, "has_documentation": None, "meaningful_structure": None,
        }
    lowered_paths = {path.lower() for path in paths}
    readme = any(path.rsplit("/", 1)[-1].startswith("readme") for path in lowered_paths)
    tests = any(
        re.search(r"(?:^|/)(?:tests?|specs?)(?:/|$)", path)
        or re.search(r"(?:^|/)(?:test|spec)[^/]*\.(?:py|[cm]?[jt]sx?)$", path)
        or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", path)
        for path in lowered_paths
    )
    ci = any(
        ".github/workflows/" in path or ".gitlab-ci" in path
        or path.endswith(("/.travis.yml", "/jenkinsfile", "/azure-pipelines.yml", "/bitbucket-pipelines.yml"))
        or path in {".travis.yml", "jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml"}
        for path in lowered_paths
    )
    docker = any(path.rsplit("/", 1)[-1] in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"} for path in lowered_paths)
    documentation = any(
        path.startswith("docs/") or "/docs/" in path
        or path.endswith((".md", ".rst", ".adoc"))
        for path in lowered_paths
    )
    organization_markers = {"src", "app", "lib", "packages", "frontend", "backend", "api", "tests", "docs"}
    organized = len({part for path in lowered_paths for part in path.split("/")[:-1] if part in organization_markers}) >= 2
    values: dict[str, bool | None] = {
        "has_readme": readme,
        "has_tests": tests,
        "has_ci_cd": ci,
        "has_docker": docker,
        "has_documentation": documentation,
        "meaningful_structure": organized,
    }
    if truncated:
        return {key: value if value else None for key, value in values.items()}
    return values


def _repository_data(repo: Any) -> tuple[GitHubRepository, dict[str, int] | None, list[str]]:
    try:
        languages = repo.get_languages()
    except GithubException as exc:
        if _is_rate_limit(exc):
            raise GitHubRateLimitError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.") from exc
        if exc.status == 404:
            languages = None
        else:
            _raise_api_error(exc)
    try:
        topics = repo.get_topics()
    except GithubException as exc:
        if _is_rate_limit(exc):
            raise GitHubRateLimitError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.") from exc
        if exc.status == 404:
            topics = []
        else:
            _raise_api_error(exc)

    paths, truncated = _repo_tree(repo)
    signals = _tree_signals(paths, truncated)
    repository = GitHubRepository(
        name=_redact_sensitive_text(repo.name) or "[redacted]",
        full_name=_redact_sensitive_text(getattr(repo, "full_name", repo.name)) or "[redacted]",
        description=_redact_sensitive_text(getattr(repo, "description", None)),
        url=_redact_sensitive_text(getattr(repo, "html_url", None)),
        primary_language=getattr(repo, "language", None),
        languages=languages,
        stars=getattr(repo, "stargazers_count", None),
        forks=getattr(repo, "forks_count", None),
        topics=sorted({_redact_sensitive_text(topic) or "[redacted]" for topic in (topics or [])}),
        size_kb=getattr(repo, "size", None),
        created_at=_iso(getattr(repo, "created_at", None)),
        updated_at=_iso(getattr(repo, "updated_at", None)),
        is_fork=getattr(repo, "fork", None),
        is_archived=getattr(repo, "archived", None),
        tree_truncated=truncated,
        **signals,
    )
    return repository, languages, topics or []


def _activity(user: Any) -> GitHubActivity:
    try:
        events = list(islice(user.get_events(), MAX_ACTIVITY_EVENTS))
    except GithubException as exc:
        if _is_rate_limit(exc):
            raise GitHubRateLimitError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.") from exc
        if exc.status in {403, 404}:
            return GitHubActivity(
                commits=None, pull_requests=None, issues=None, events_observed=0,
                source="Recent public events were unavailable; activity counts are not inferred.",
            )
        _raise_api_error(exc)

    if not events:
        return GitHubActivity(
            commits=None, pull_requests=None, issues=None, events_observed=0,
            source="No recent public events were returned; lifetime activity is not inferred.",
        )

    commits = pull_requests = issues = 0
    for event in events:
        event_type = getattr(event, "type", None)
        payload = getattr(event, "payload", {}) or {}
        if not isinstance(payload, dict):
            payload = {}
        if event_type == "PushEvent":
            commits += int(payload.get("size") or len(payload.get("commits", [])))
        elif event_type == "PullRequestEvent":
            pull_requests += 1
        elif event_type == "IssuesEvent":
            issues += 1
    return GitHubActivity(
        commits=commits,
        pull_requests=pull_requests,
        issues=issues,
        events_observed=len(events),
    )


def _technology_profiles(
    repositories: list[GitHubRepository], language_maps: list[dict[str, int] | None], topic_lists: list[list[str]]
) -> tuple[list[GitHubTechnology], list[GitHubTechnology]]:
    denominator = len(repositories)
    if not denominator:
        return [], []
    language_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    for language_map in language_maps:
        for language in (language_map or {}):
            language_counts[language] = language_counts.get(language, 0) + 1
    for topics in topic_lists:
        for topic in set(topics):
            topic_counts[topic.lower()] = topic_counts.get(topic.lower(), 0) + 1
    languages = [
        GitHubTechnology(name=name, category="language", repository_count=count, percentage=round(count / denominator * 100, 1))
        for name, count in sorted(language_counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    technologies = [
        GitHubTechnology(
            name=TECHNOLOGY_TOPICS[topic], category="repository topic",
            repository_count=count, percentage=round(count / denominator * 100, 1),
        )
        for topic, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))
        if topic in TECHNOLOGY_TOPICS
    ]
    return languages, technologies


def _build_evidence(repositories: list[GitHubRepository], activity: GitHubActivity) -> list[GitHubEvidence]:
    evidence: list[GitHubEvidence] = []
    signals = (
        ("documentation", "README", "has_readme"),
        ("testing", "tests", "has_tests"),
        ("CI/CD", "CI/CD workflow", "has_ci_cd"),
        ("deployment", "Docker configuration", "has_docker"),
        ("documentation", "documentation files", "has_documentation"),
        ("project structure", "meaningful source directories", "meaningful_structure"),
    )
    for category, label, attribute in signals:
        names = [repo.full_name for repo in repositories if getattr(repo, attribute) is True]
        if names:
            evidence.append(GitHubEvidence(category=category, finding=f"{label} detected in {len(names)} inspected public repositories.", repositories=names[:20]))
    language_names = sorted({repo.primary_language for repo in repositories if repo.primary_language})
    if language_names:
        evidence.append(GitHubEvidence(category="languages", finding="Repository language metadata reports: " + ", ".join(language_names) + "."))
    if activity.events_observed:
        evidence.append(GitHubEvidence(
            category="activity",
            finding=f"Observed {activity.events_observed} recent public events; event-derived counts are not lifetime totals.",
        ))
    return evidence


def analyze_github_username(username: str) -> GitHubAnalysisResponse:
    """Analyze public GitHub profile evidence. No private repositories are included."""
    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise InvalidGitHubUsername("GitHub username must be 1-39 letters, numbers, or single hyphens.")

    load_dotenv()
    token = os.getenv("GITHUB_TOKEN", "").strip() or None
    client = Github(login_or_token=token, timeout=10, per_page=100, retry=0)
    try:
        try:
            user = client.get_user(username)
            # Read the profile's public count separately; private repos returned
            # by an authenticated owner's listing are filtered before inspection.
            public_repositories = int(getattr(user, "public_repos", 0) or 0)
            repos = []
            for repo in islice(user.get_repos(type="owner", sort="updated"), MAX_REPOSITORIES):
                # If visibility metadata is missing, fail closed rather than
                # risk inspecting a private repository on an authenticated client.
                if getattr(repo, "private", None) is not False:
                    continue
                repos.append(repo)
            repository_data: list[GitHubRepository] = []
            language_maps: list[dict[str, int] | None] = []
            topic_lists: list[list[str]] = []
            for repo in repos:
                repository, languages, topics = _repository_data(repo)
                repository_data.append(repository)
                language_maps.append(languages)
                topic_lists.append(topics)
            activity = _activity(user)
        except GithubException as exc:
            _raise_api_error(exc, profile_lookup=exc.status == 404)
        except (requests.exceptions.RequestException, TimeoutError, OSError) as exc:
            raise GitHubNetworkError("Could not connect to GitHub. Try again later.") from exc
    finally:
        client.close()

    score = score_github_evidence(repository_data)
    languages, technologies = _technology_profiles(repository_data, language_maps, topic_lists)
    evidence = _build_evidence(repository_data, activity)
    strengths: list[str] = []
    weaknesses: list[str] = []
    for label, value in (
        ("README documentation", score.quality_indicators.documentation),
        ("test files", score.quality_indicators.testing),
        ("CI/CD workflows", score.quality_indicators.ci_cd),
        ("organized repository structure", score.quality_indicators.project_structure),
    ):
        if value is not None and value >= 70:
            strengths.append(f"{value}% of inspected public repositories showed {label} evidence.")
        elif value is not None and value < 30:
            weaknesses.append(f"{value}% of inspected public repositories showed {label} evidence.")
    if public_repositories > len(repository_data):
        weaknesses.append(
            f"Inspected {len(repository_data)} public repositories; the profile reports {public_repositories} in total."
        )
    if not repository_data:
        weaknesses.append("No public repositories were available for repository-quality inspection.")

    if not repository_data:
        evidence_level = "insufficient"
    elif len(repository_data) < 3:
        evidence_level = "limited"
    elif len(repository_data) < 10:
        evidence_level = "moderate"
    else:
        evidence_level = "strong"

    return GitHubAnalysisResponse(
        username=getattr(user, "login", username),
        name=_redact_sensitive_text(getattr(user, "name", None)),
        bio=_redact_sensitive_text(getattr(user, "bio", None)),
        company=_redact_sensitive_text(getattr(user, "company", None)),
        location=_redact_sensitive_text(getattr(user, "location", None)),
        blog=_redact_sensitive_text(getattr(user, "blog", None)),
        profile_created_at=getattr(user, "created_at", None),
        public_repositories=public_repositories,
        analyzed_repositories=len(repository_data),
        followers=int(getattr(user, "followers", 0) or 0),
        following=int(getattr(user, "following", 0) or 0),
        repositories=repository_data,
        languages=languages,
        technologies=technologies,
        activity=activity,
        quality_indicators=score.quality_indicators,
        github_score=score.github_score,
        score_weights=SCORE_WEIGHTS,
        evidence_level=evidence_level,
        strengths=strengths,
        weaknesses=weaknesses,
        evidence=evidence,
    )
