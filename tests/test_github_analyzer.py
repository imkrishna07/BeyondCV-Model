"""Mock-only tests for GitHub evidence collection and scoring."""

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from github.GithubException import GithubException, RateLimitExceededException
import requests

from app.analyzers.github.analyzer import (
    GitHubAPIError,
    GitHubNetworkError,
    GitHubProfileNotFound,
    GitHubRateLimitError,
    InvalidGitHubUsername,
    analyze_github_username,
)
from app.analyzers.github.scoring import score_github_evidence
from app.main import app
from app.schemas.github import GitHubRepository


def repo(name: str, *, stars: int = 0, paths: list[str] | None = None, language: str | None = "Python", topics: list[str] | None = None):
    item = SimpleNamespace(
        name=name,
        full_name=f"octocat/{name}",
        description=f"Demo {name}",
        html_url=f"https://github.com/octocat/{name}",
        language=language,
        stargazers_count=stars,
        forks_count=2,
        size=32,
        created_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        default_branch="main",
        fork=False,
        archived=False,
        private=False,
    )
    item.get_languages = Mock(return_value={language: 1200} if language else {})
    item.get_topics = Mock(return_value=topics or [])
    item.get_git_tree = Mock(return_value=SimpleNamespace(
        tree=[SimpleNamespace(path=path, type="blob") for path in (paths or [])],
        truncated=False,
    ))
    return item


def user_with_repositories(repositories, *, events=None):
    user = SimpleNamespace(
        login="octocat",
        name="Octo Cat",
        bio="Builds useful tools",
        company="Example",
        location="Remote",
        blog="https://example.test",
        created_at=datetime(2019, 1, 1, tzinfo=timezone.utc),
        public_repos=len(repositories),
        followers=50,
        following=35,
    )
    user.get_repos = Mock(return_value=repositories)
    user.get_events = Mock(return_value=events or [])
    return user


class GitHubAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.github_client = Mock()

    def analyze(self, user) -> object:
        self.github_client.get_user.return_value = user
        with patch("app.analyzers.github.analyzer.Github", return_value=self.github_client):
            return analyze_github_username("octocat")

    def test_normal_profile(self) -> None:
        project = repo("hello", stars=400, paths=["README.md", "src/app.py", "tests/test_app.py", ".github/workflows/ci.yml", "docs/design.md"])
        user = user_with_repositories([project], events=[
            SimpleNamespace(type="PushEvent", payload={"size": 3, "commits": [{}, {}, {}]}),
            SimpleNamespace(type="PullRequestEvent", payload={}),
            SimpleNamespace(type="IssuesEvent", payload={}),
        ])

        result = self.analyze(user)

        self.assertEqual(result.username, "octocat")
        self.assertEqual(result.public_repositories, 1)
        self.assertEqual(result.followers, 50)
        self.assertEqual(result.repositories[0].stars, 400)
        self.assertEqual(result.activity.commits, 3)
        self.assertEqual(result.activity.pull_requests, 1)
        self.assertEqual(result.activity.issues, 1)
        self.assertEqual(result.quality_indicators.documentation, 100)
        self.assertEqual(result.github_score, 100)
        self.github_client.close.assert_called_once()

    def test_multiple_repositories_and_technology_profile(self) -> None:
        projects = [
            repo("api", language="Python", topics=["fastapi", "docker"], paths=["README.md", "api/main.py"]),
            repo("web", language="TypeScript", topics=["react"], paths=["README.md", "src/App.tsx", "tests/App.test.tsx"]),
            repo("cli", language="Python", topics=["cli"], paths=["README.md", "src/main.py"]),
        ]
        result = self.analyze(user_with_repositories(projects))

        self.assertEqual(result.analyzed_repositories, 3)
        languages = {language.name: language.repository_count for language in result.languages}
        self.assertEqual(languages, {"Python": 2, "TypeScript": 1})
        technologies = {technology.name for technology in result.technologies}
        self.assertEqual(technologies, {"Docker", "FastAPI", "React"})

    def test_empty_profile_has_no_evidence_score(self) -> None:
        result = self.analyze(user_with_repositories([]))

        self.assertEqual(result.repositories, [])
        self.assertEqual(result.public_repositories, 0)
        self.assertIsNone(result.github_score)
        self.assertIsNone(result.quality_indicators.documentation)
        self.assertEqual(result.evidence_level, "insufficient")

    def test_invalid_username_is_rejected_before_api_call(self) -> None:
        with self.assertRaises(InvalidGitHubUsername):
            analyze_github_username("bad--name")
        self.github_client.get_user.assert_not_called()

    def test_unknown_username_maps_to_profile_not_found(self) -> None:
        self.github_client.get_user.side_effect = GithubException(404, {"message": "Not Found"})
        with patch("app.analyzers.github.analyzer.Github", return_value=self.github_client):
            with self.assertRaises(GitHubProfileNotFound):
                analyze_github_username("octocat")

    def test_api_failure_is_sanitized(self) -> None:
        self.github_client.get_user.side_effect = GithubException(500, {"message": "internal server error"})
        with patch("app.analyzers.github.analyzer.Github", return_value=self.github_client):
            with self.assertRaises(GitHubAPIError) as caught:
                analyze_github_username("octocat")
        self.assertNotIn("internal server error", str(caught.exception))

    def test_rate_limit_is_reported_without_provider_details(self) -> None:
        self.github_client.get_user.side_effect = RateLimitExceededException(403, {"message": "API rate limit exceeded"})
        with patch("app.analyzers.github.analyzer.Github", return_value=self.github_client):
            with self.assertRaises(GitHubRateLimitError) as caught:
                analyze_github_username("octocat")
        self.assertNotIn("ghp_secretvalue", str(caught.exception))

    def test_network_failure_is_sanitized(self) -> None:
        self.github_client.get_user.side_effect = requests.ConnectionError("connection details")
        with patch("app.analyzers.github.analyzer.Github", return_value=self.github_client):
            with self.assertRaises(GitHubNetworkError) as caught:
                analyze_github_username("octocat")
        self.assertNotIn("connection details", str(caught.exception))

    def test_authenticated_private_repository_is_never_inspected(self) -> None:
        private_repo = repo("private")
        private_repo.private = True
        user = user_with_repositories([private_repo])
        user.public_repos = 0
        result = self.analyze(user)
        self.assertEqual(result.public_repositories, 0)
        self.assertEqual(result.analyzed_repositories, 0)
        private_repo.get_topics.assert_not_called()

    def test_stars_and_repository_count_do_not_affect_quality_score(self) -> None:
        high_popularity = GitHubRepository(name="popular", full_name="a/popular", stars=10000, forks=200)
        no_popularity = GitHubRepository(name="quiet", full_name="b/quiet", stars=0, forks=0)
        high = score_github_evidence([high_popularity])
        low = score_github_evidence([no_popularity])
        self.assertEqual(high.github_score, low.github_score)


class GitHubEndpointTests(unittest.TestCase):
    def test_request_body_and_response(self) -> None:
        user = user_with_repositories([repo("demo", paths=["README.md", "src/app.py"])])
        github_client = Mock()
        github_client.get_user.return_value = user
        with patch("app.analyzers.github.analyzer.Github", return_value=github_client):
            with TestClient(app) as client:
                response = client.post("/analyze-github", json={"username": "octocat"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "octocat")
        self.assertIn("github_score", response.json())

    def test_endpoint_maps_not_found(self) -> None:
        github_client = Mock()
        github_client.get_user.side_effect = GithubException(404, {"message": "Not Found"})
        with patch("app.analyzers.github.analyzer.Github", return_value=github_client):
            with TestClient(app) as client:
                response = client.post("/analyze-github", json={"username": "octocat"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
