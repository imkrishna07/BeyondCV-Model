"""Unit and route tests for candidate-supplied certification and achievement evidence."""

from unittest import TestCase

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analyzers.achievements.analyzer import analyze_achievements
from app.analyzers.certifications.analyzer import analyze_certifications
from app.main import app
from app.schemas.achievements import AchievementAnalysisRequest
from app.schemas.certifications import CertificationAnalysisRequest


client = TestClient(app)


class CertificationAnalyzerTests(TestCase):
    def test_multiple_certifications_and_job_relevance(self):
        request = CertificationAnalysisRequest.model_validate({
            "job_description": "Cloud security engineer with AWS experience",
            "certifications": [
                {"name": "AWS Cloud Practitioner", "issuer": "Amazon Web Services", "date": "2026-05-10", "url": "https://example.org/aws", "domain": "Cloud Computing"},
                {"name": "First Aid", "issuer": "Example Safety", "date": "2024-01-01"},
            ],
        })
        response = analyze_certifications(request)
        self.assertEqual(len(response.certifications), 2)
        self.assertEqual(response.certifications[0].date.isoformat(), "2026-05-10")
        self.assertEqual(response.certifications[0].relevance, "relevant")
        self.assertEqual(len(response.relevant_certifications), 1)
        self.assertEqual(response.status, "available")

    def test_single_certification(self):
        response = analyze_certifications(CertificationAnalysisRequest.model_validate({
            "certifications": [{"name": "Cloud Practitioner", "issuer": "Provider"}],
        }))
        self.assertEqual(len(response.certifications), 1)
        self.assertEqual(response.certifications[0].relevance, "not_assessed")

    def test_empty_certification_list(self):
        response = analyze_certifications(CertificationAnalysisRequest())
        self.assertEqual(response.status, "no_data")
        self.assertEqual(response.certification_score, 0)
        self.assertEqual(response.certifications, [])

    def test_missing_optional_certification_fields(self):
        response = analyze_certifications(CertificationAnalysisRequest.model_validate({
            "certifications": [{"name": "  Example Credential  "}],
        }))
        certification = response.certifications[0]
        self.assertEqual(certification.name, "Example Credential")
        self.assertIsNone(certification.issuer)
        self.assertIsNone(certification.date)
        self.assertIsNone(certification.domain)
        self.assertIsNone(certification.url)

    def test_invalid_certification_input(self):
        with self.assertRaises(ValidationError):
            CertificationAnalysisRequest.model_validate({"certifications": [{"name": "", "date": "not-a-date"}]})
        response = client.post("/analyze-certifications", json={"certifications": [{"name": "", "date": "not-a-date"}]})
        self.assertEqual(response.status_code, 422)


class AchievementAnalyzerTests(TestCase):
    def _analyze(self, achievement):
        return analyze_achievements(AchievementAnalysisRequest.model_validate({"achievements": [achievement]}))

    def test_winner(self):
        result = self._analyze({"name": "Smart India Hackathon", "rank": "Winner", "year": 2026, "domain": "Software Development", "participants": 1000})
        self.assertEqual(result.achievements[0].recognition_level, "winner_award")
        self.assertGreater(result.achievement_score, 50)

    def test_finalist(self):
        result = self._analyze({"name": "University Hackathon", "rank": "Finalist", "year": 2025})
        self.assertEqual(result.achievements[0].recognition_level, "finalist")
        self.assertEqual(result.achievement_score, 60)

    def test_participation_is_not_treated_as_a_major_achievement(self):
        result = self._analyze({"name": "Coding Contest", "rank": "Participant"})
        self.assertEqual(result.achievements[0].recognition_level, "participation")
        self.assertEqual(result.achievement_score, 15)
        self.assertEqual(result.strengths, [])

    def test_participant_count_is_reported_without_increasing_score(self):
        without_count = self._analyze({"name": "Coding Contest", "rank": "Participant"})
        with_count = self._analyze({"name": "Coding Contest", "rank": "Participant", "participants": 5000})
        self.assertEqual(with_count.achievements[0].participants, 5000)
        self.assertEqual(with_count.achievement_score, without_count.achievement_score)

    def test_multiple_achievements(self):
        result = analyze_achievements(AchievementAnalysisRequest.model_validate({"achievements": [
            {"name": "Contest A", "rank": "Winner"},
            {"name": "Contest B", "rank": "Runner-up"},
            {"name": "Contest C", "rank": "Participant"},
        ]}))
        self.assertEqual(len(result.achievements), 3)
        self.assertEqual([item.recognition_level for item in result.achievements], ["winner_award", "ranked", "participation"])

    def test_empty_achievement_list(self):
        result = analyze_achievements(AchievementAnalysisRequest())
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.achievement_score, 0)
        self.assertEqual(result.achievements, [])

    def test_missing_optional_achievement_fields(self):
        result = self._analyze({"name": "Academic Achievement"})
        item = result.achievements[0]
        self.assertEqual(item.recognition_level, "unspecified")
        self.assertIsNone(item.rank)
        self.assertIsNone(item.year)
        self.assertIsNone(item.domain)
        self.assertIsNone(item.participants)
        self.assertEqual(item.relevance, "not_assessed")

    def test_invalid_achievement_input(self):
        with self.assertRaises(ValidationError):
            AchievementAnalysisRequest.model_validate({"achievements": [{"name": "", "year": 2500, "participants": 0}]})
        response = client.post("/analyze-achievements", json={"achievements": [{"name": "", "year": 2500}]})
        self.assertEqual(response.status_code, 422)

    def test_relevance_only_assessed_when_job_description_is_supplied(self):
        request = AchievementAnalysisRequest.model_validate({
            "job_description": "Machine learning engineer",
            "achievements": [{"name": "ML Challenge", "rank": "Winner", "domain": "Machine Learning"}],
        })
        result = analyze_achievements(request)
        self.assertEqual(result.achievements[0].relevance, "relevant")
