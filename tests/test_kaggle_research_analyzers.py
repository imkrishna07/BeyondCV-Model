"""Mocked Kaggle collector and deterministic research analyzer tests."""

from unittest import TestCase
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analyzers.kaggle.analyzer import (
    KaggleNetworkError,
    analyze_kaggle_username,
)
from app.analyzers.kaggle.scoring import score_kaggle_evidence
from app.analyzers.research.analyzer import analyze_research
from app.main import app
from app.schemas.kaggle import KaggleArtifact
from app.schemas.research import ResearchAnalysisRequest


client = TestClient(app)


class KaggleAnalyzerTests(TestCase):
    def _response(self, data):
        response = Mock(status_code=200)
        response.json.return_value = data
        return response

    def test_valid_profile_with_notebooks_and_datasets(self):
        notebook = [{"title": "Model exploration", "ref": "user/model-exploration", "language": "python", "tags": ["NLP"], "description": "A documented experiment", "lastUpdated": "2025-01-01"}]
        dataset = [{"title": "Text corpus", "ref": "user/text-corpus", "tags": ["text"]}]
        with patch("app.analyzers.kaggle.analyzer._auth", return_value=("bearer", "test-token")), patch(
            "app.analyzers.kaggle.analyzer.requests.get",
            side_effect=[self._response(notebook), self._response(dataset)],
        ) as get:
            result = analyze_kaggle_username("user")
        self.assertEqual(result.status, "available")
        self.assertEqual(result.username, "user")
        self.assertEqual(len(result.notebooks), 1)
        self.assertEqual(len(result.datasets), 1)
        self.assertIn("python", result.skills)
        self.assertIn("NLP", result.skills)
        self.assertIsNotNone(result.kaggle_score)
        self.assertEqual(get.call_count, 2)
        self.assertFalse(result.activity.profile_verified)
        self.assertEqual(result.competitions, [])

    def test_profile_with_competition_fields_unavailable(self):
        with patch("app.analyzers.kaggle.analyzer._auth", return_value=("bearer", "test-token")), patch(
            "app.analyzers.kaggle.analyzer.requests.get",
            side_effect=[self._response([]), self._response([])],
        ):
            result = analyze_kaggle_username("quiet_user")
        self.assertIsNone(result.activity.competitions)
        self.assertIn("competition participation/results", result.unavailable_fields)

    def test_empty_profile_search_is_not_claimed_as_nonexistent(self):
        with patch("app.analyzers.kaggle.analyzer._auth", return_value=("bearer", "test-token")), patch(
            "app.analyzers.kaggle.analyzer.requests.get",
            side_effect=[self._response([]), self._response([])],
        ):
            result = analyze_kaggle_username("quiet_user")
        self.assertEqual(result.status, "available")
        self.assertIsNone(result.kaggle_score)
        self.assertFalse(result.activity.profile_verified)
        self.assertEqual(result.strengths, [])

    def test_invalid_username(self):
        response = client.post("/analyze-kaggle", json={"username": "invalid user"})
        self.assertEqual(response.status_code, 422)

    def test_network_failure(self):
        with patch("app.analyzers.kaggle.analyzer._auth", return_value=("bearer", "test-token")), patch(
            "app.analyzers.kaggle.analyzer.requests.get", side_effect=requests.ConnectionError("offline")
        ):
            with self.assertRaises(KaggleNetworkError):
                analyze_kaggle_username("user")

    def test_missing_credentials_returns_unavailable_without_claiming_empty_profile(self):
        with patch("app.analyzers.kaggle.analyzer._auth", return_value=None):
            result = analyze_kaggle_username("user")
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.activity.notebooks)
        self.assertIsNone(result.kaggle_score)
        self.assertFalse(result.activity.profile_verified)

    def test_score_uses_metadata_and_diversity_not_raw_counts(self):
        notebook = KaggleArtifact(title="n", description="documented", url="https://example.test/n", topics=["ml"], last_updated="2025")
        self.assertEqual(score_kaggle_evidence([notebook], []), 90)
        self.assertEqual(score_kaggle_evidence([notebook], [notebook]), 100)
        self.assertIsNone(score_kaggle_evidence([], []))


class ResearchAnalyzerTests(TestCase):
    def test_one_publication_and_candidate_authorship(self):
        request = ResearchAnalysisRequest.model_validate({
            "candidate_name": "Ada Lovelace",
            "research": [{
                "title": "Deep learning for language understanding",
                "authors": ["Ada Lovelace", "Grace Hopper"],
                "venue": "Example Symposium",
                "year": 2026,
                "url": "https://example.org/paper",
                "abstract": "We study neural language models.",
                "role": "Implemented experiments",
                "project_connection": "Built as part of Example project",
            }],
        })
        result = analyze_research(request)
        self.assertEqual(result.publication_count, 1)
        self.assertEqual(result.publications[0].candidate_authorship, "listed_by_candidate")
        self.assertEqual(result.publications[0].verification_status, "not_verified")
        self.assertIn("artificial intelligence and machine learning", result.research_domains)
        self.assertEqual(result.research_score, 100)

    def test_multiple_publications(self):
        request = ResearchAnalysisRequest.model_validate({"research": [
            {"title": "A study of software testing", "authors": ["Person"], "year": 2024},
            {"title": "Security and privacy in networks", "authors": ["Other"], "year": 2025},
        ]})
        result = analyze_research(request)
        self.assertEqual(result.publication_count, 2)
        self.assertEqual(len(result.publications), 2)
        self.assertGreaterEqual(len(result.research_domains), 2)

    def test_empty_research_has_no_score(self):
        result = analyze_research(ResearchAnalysisRequest())
        self.assertEqual(result.publications, [])
        self.assertIsNone(result.research_score)
        self.assertIn("publication details", result.unavailable_fields)

    def test_missing_optional_fields_are_unavailable_not_invented(self):
        request = ResearchAnalysisRequest.model_validate({"research": [{"title": "Unclassified work"}]})
        result = analyze_research(request)
        publication = result.publications[0]
        self.assertEqual(publication.candidate_authorship, "unavailable")
        self.assertIsNone(publication.venue)
        self.assertIsNone(publication.stated_role)
        self.assertEqual(publication.project_connection_source, "unavailable")
        self.assertEqual(publication.research_domains, [])

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValidationError):
            ResearchAnalysisRequest.model_validate({"research": [{"title": "", "year": 2500}]})
        response = client.post("/analyze-research", json={"research": [{"title": "", "year": 2500}]})
        self.assertEqual(response.status_code, 422)
