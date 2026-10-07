"""Feature aggregation tests use analyzer response schemas, without network access."""

from unittest import TestCase

from fastapi.testclient import TestClient

from app.main import app
from app.ranking.feature_aggregator import aggregate_candidate
from app.ranking.normalization import normalize_count, normalize_rating, normalize_score, normalize_skill_name
from app.ranking.schemas import CandidateAnalysisInputs
from app.schemas.achievements import AchievementAnalysisResponse, AchievementEvidenceItem
from app.schemas.certifications import CertificationAnalysisResponse, CertificationEvidenceItem
from app.schemas.coding import (
    CodingAnalysisResponse,
    CodeforcesProfile,
    LeetCodeProfile,
    NormalizedCodingFeatures,
    NormalizedPlatformFeatures,
)
from app.schemas.github import GitHubActivity, GitHubAnalysisResponse, GitHubQualityIndicators, GitHubRepository, GitHubTechnology
from app.schemas.kaggle import KaggleActivity, KaggleAnalysisResponse, KaggleArtifact
from app.schemas.project import ProjectAnalysisResponse, ProjectEvidence, ProjectStructure, ProjectTechnology
from app.schemas.research import ResearchAnalysisResponse, ResearchPublicationEvidence
from app.schemas.resume import ResumeAnalysisResponse, ResumeExperience, ResumeSkill


client = TestClient(app)


def full_candidate() -> CandidateAnalysisInputs:
    resume = ResumeAnalysisResponse(
        skills=[ResumeSkill(name="python"), ResumeSkill(name="PYTHON"), ResumeSkill(name="TypeScript")],
        experience=[ResumeExperience(details="Software Intern at Example Co; built a Django service.")],
        education=[], projects=[], certifications=[], achievements=[], research=[],
    )
    project = ProjectAnalysisResponse(
        project_score=82,
        technical_complexity=75,
        code_quality=80,
        architecture=78,
        documentation=70,
        testing=60,
        deployment=50,
        security=55,
        completeness=84,
        evidence_level="moderate",
        project_scale="small",
        structure=ProjectStructure(total_files=40, source_files=25, component_count=3, languages={"Python": 10}),
        technologies=[ProjectTechnology(name="Django", category="framework", evidence_files=["requirements.txt"])],
        evidence=[ProjectEvidence(area="backend", finding="Django REST API with PostgreSQL.", files=["app/api.py"])],
    )
    github = GitHubAnalysisResponse(
        username="sample", public_repositories=2, analyzed_repositories=2, followers=12, following=20,
        repositories=[GitHubRepository(name="api", full_name="sample/api", description="Django API", primary_language="Python")],
        languages=[GitHubTechnology(name="Python", category="language", repository_count=2, percentage=100)],
        technologies=[GitHubTechnology(name="Django", category="framework", repository_count=1, percentage=50)],
        activity=GitHubActivity(commits=4, pull_requests=1, issues=0, events_observed=5),
        quality_indicators=GitHubQualityIndicators(documentation=80, testing=60, ci_cd=50, project_structure=70, repositories_evaluated=2),
        github_score=65, evidence_level="moderate",
    )
    coding = CodingAnalysisResponse(
        leetcode=LeetCodeProfile(username="lc", rating=1500, problems_solved=100, easy=30, medium=50, hard=20),
        leetcode_status="available",
        codeforces=CodeforcesProfile(username="cf", rating=2000, max_rating=2200, problems_solved=80),
        codeforces_status="available",
        normalized_features=NormalizedCodingFeatures(
            leetcode=NormalizedPlatformFeatures(rating=50, problem_solving=45, contest_participation=20, platform_score=40),
            codeforces=NormalizedPlatformFeatures(rating=50, peak_rating=55, problem_solving=40, contest_participation=30, platform_score=45),
            combined_score=43,
        ),
        coding_score=43,
    )
    kaggle = KaggleAnalysisResponse(
        username="sample", status="available", notebooks=[KaggleArtifact(title="Churn model", language="Python", topics=["ML"])],
        datasets=[KaggleArtifact(title="Churn data")], skills=["PYTHON", "Machine Learning"],
        activity=KaggleActivity(notebooks=1, datasets=1, profile_verified=False), kaggle_score=75,
        score_method="Kaggle evidence score.",
    )
    research = ResearchAnalysisResponse(
        publication_count=1,
        publications=[ResearchPublicationEvidence(
            title="ML for tabular data", authors=["Sample Candidate"], abstract_provided=True,
            research_domains=["artificial intelligence and machine learning"], domain_keywords=["ml"],
            candidate_authorship="listed_by_candidate", project_connection_source="unavailable",
        )],
        research_domains=["artificial intelligence and machine learning"], research_score=75,
        score_method="Research evidence completeness.",
    )
    certifications = CertificationAnalysisResponse(
        certifications=[CertificationEvidenceItem(name="AWS Cloud Practitioner", issuer="AWS", relevance="not_assessed")],
        certification_score=60, relevant_certifications=[], score_method="Certification evidence completeness.", status="available",
    )
    achievements = AchievementAnalysisResponse(
        achievements=[AchievementEvidenceItem(name="Hackathon", rank="Winner", year=2025, recognition_level="winner_award", relevance="not_assessed")],
        achievement_score=90, score_method="Achievement evidence.", status="available",
    )
    return CandidateAnalysisInputs(
        resume=resume, project=project, github=github, coding=coding, kaggle=kaggle,
        research=research, certifications=certifications, achievements=achievements,
    )


class FeatureAggregatorTests(TestCase):
    def test_complete_candidate_with_all_data(self):
        result = aggregate_candidate(full_candidate())
        self.assertEqual(len(result.technical_skills), 4)
        self.assertTrue(result.project_features.available)
        self.assertTrue(result.github_features.available)
        self.assertTrue(result.coding_features.available)
        self.assertTrue(result.kaggle_features.available)
        self.assertTrue(result.research_features.available)
        self.assertTrue(result.certification_features.available)
        self.assertTrue(result.achievement_features.available)
        self.assertTrue(result.experience_features.available)
        self.assertEqual(result.coding_features.features["leetcode_rating"].normalized_value, 0.5)
        self.assertEqual(result.coding_features.features["codeforces_peak_rating"].normalized_value, 0.55)
        self.assertNotIn("overall_score", result.model_dump())

    def test_candidate_missing_github_keeps_github_unavailable(self):
        inputs = full_candidate().model_copy(update={"github": None})
        result = aggregate_candidate(inputs)
        self.assertFalse(result.github_features.available)
        self.assertIsNone(result.github_features.features["github_score"].value)
        self.assertFalse(result.github_features.features["github_score"].available)
        self.assertTrue(result.project_features.available)

    def test_candidate_with_no_coding_profiles_keeps_platform_metrics_unavailable(self):
        coding = CodingAnalysisResponse(
            leetcode_status="not_provided", codeforces_status="not_provided",
            normalized_features=NormalizedCodingFeatures(), coding_score=None,
        )
        result = aggregate_candidate({"coding": coding})
        self.assertTrue(result.coding_features.available)
        self.assertIsNone(result.coding_features.features["leetcode_rating"].value)
        self.assertFalse(result.coding_features.features["leetcode_rating"].available)
        self.assertEqual(result.coding_features.features["leetcode_status"].value, "not_provided")

    def test_candidate_with_no_research_is_known_empty_not_a_missing_analyzer(self):
        research = ResearchAnalysisResponse(publication_count=0, research_score=None, score_method="No publications submitted.")
        result = aggregate_candidate({"research": research})
        self.assertTrue(result.research_features.available)
        self.assertEqual(result.research_features.features["publication_count"].value, 0)
        self.assertTrue(result.research_features.features["publication_count"].available)
        self.assertFalse(result.research_features.features["research_score"].available)

    def test_partial_candidate_only_populates_submitted_sources(self):
        result = aggregate_candidate({"resume": ResumeAnalysisResponse(skills=[ResumeSkill(name="Python")])})
        self.assertEqual([skill.name for skill in result.technical_skills], ["Python"])
        self.assertFalse(result.project_features.features["project_score"].available)
        self.assertTrue(result.experience_features.available)
        self.assertFalse(result.kaggle_features.available)

    def test_normalization_preserves_missingness_and_uses_separate_scales(self):
        self.assertEqual(normalize_score(82), 0.82)
        self.assertEqual(normalize_rating(2000, 4000), 0.5)
        self.assertEqual(normalize_count(0, 1000), 0)
        self.assertIsNone(normalize_score(None))
        self.assertIsNone(normalize_count(None, 1000))

    def test_skill_normalization_unifies_case_and_common_aliases(self):
        result = aggregate_candidate({"resume": ResumeAnalysisResponse(skills=[
            ResumeSkill(name="Python"), ResumeSkill(name="python"), ResumeSkill(name=" PYTHON "),
            ResumeSkill(name="Postgres"), ResumeSkill(name="PostgreSQL"),
        ])})
        self.assertEqual([skill.name for skill in result.technical_skills], ["PostgreSQL", "Python"])
        self.assertEqual(normalize_skill_name("PYTHON"), "Python")
        self.assertEqual(result.technical_skills[-1].sources, ["resume_analyzer"])

    def test_evidence_and_source_payloads_are_preserved(self):
        result = aggregate_candidate(full_candidate())
        project_feature = result.project_features.features["project_evidence"]
        self.assertIn("Django REST API with PostgreSQL.", project_feature.evidence[0])
        self.assertEqual(project_feature.source, "project_analyzer")
        self.assertEqual(result.project_features.source_payloads["project_analyzer"]["evidence"][0]["finding"], "Django REST API with PostgreSQL.")
        self.assertTrue(any(item["feature"] == "github_features.commits_observed" and item["source"] == "github_analyzer" for item in result.evidence_vector))

    def test_missing_data_is_explicit_in_vector(self):
        result = aggregate_candidate({})
        missing = result.github_features.features["github_score"]
        self.assertIsNone(missing.value)
        self.assertIsNone(missing.normalized_value)
        self.assertFalse(missing.available)
        self.assertEqual(missing.source, "not_provided")

    def test_aggregate_candidate_api(self):
        response = client.post("/aggregate-candidate", json={"resume": {"skills": [{"name": "python"}]}})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["technical_skills"][0]["name"], "Python")
        self.assertFalse(body["github_features"]["available"])
