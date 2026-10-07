"""Deterministic ranking tests built from normalized feature and job vectors."""

from unittest import TestCase

from fastapi.testclient import TestClient

from app.main import app
from app.ranking.ranker import rank_candidates
from app.ranking.ranking_schemas import RankCandidatesRequest
from app.ranking.schemas import CandidateFeatureVector, FeatureDatum, FeatureGroup, SkillFeature
from app.ranking.weights import select_weight_profile
from app.schemas.job import JobRequirementVector, ExperienceRequirement, EducationRequirement


client = TestClient(app)


def _group(source: str, values: dict[str, object] | None = None, available: bool = True) -> FeatureGroup:
    features = {}
    for name, value in (values or {}).items():
        features[name] = FeatureDatum(
            value=value,
            normalized_value=None,
            available=value is not None,
            source=source,
            evidence=[f"{source} evidence: {name} = {value}"],
        )
    return FeatureGroup(available=available, sources=[source] if available else [], features=features)


def _candidate(
    skills: list[str] | None = None,
    *,
    project: float | None = None,
    github: float | None = None,
    coding: float | None = None,
    kaggle: float | None = None,
    research: float | None = None,
    research_domains: list[str] | None = None,
    certifications: list[dict] | None = None,
    achievements: list[dict] | None = None,
    experience: list[str] | None = None,
    education: list[str] | None = None,
) -> CandidateFeatureVector:
    def one_score(source: str, key: str, score: float | None, extra: dict | None = None) -> FeatureGroup:
        values = dict(extra or {})
        if score is not None:
            values[key] = score
        return _group(source, values, available=score is not None or bool(extra))

    return CandidateFeatureVector(
        technical_skills=[SkillFeature(name=item, normalized_key=item.casefold(), sources=["resume_analyzer"], evidence=[f"Resume lists {item}."]) for item in (skills or [])],
        project_features=one_score("project_analyzer", "project_score", project, {"project_evidence": ["Backend API built with Django and PostgreSQL."]} if project is not None else None),
        github_features=one_score("github_analyzer", "github_score", github, {"technologies": [{"name": "Python"}]} if github is not None else None),
        coding_features=one_score("coding_analyzer", "coding_score", coding),
        kaggle_features=one_score("kaggle_analyzer", "kaggle_score", kaggle),
        research_features=one_score("research_analyzer", "research_score", research, {"domains": research_domains or [], "publications": [{"title": "Research paper", "verification_status": "not_verified"}]} if research is not None or research_domains is not None else None),
        certification_features=_group("certifications_analyzer", {"records": certifications or []}) if certifications is not None else FeatureGroup(available=False),
        achievement_features=_group("achievements_analyzer", {"records": achievements or []}) if achievements is not None else FeatureGroup(available=False),
        experience_features=_group("resume_analyzer", {
            **({"experience_records": experience} if experience is not None else {}),
            **({"education_records": education} if education is not None else {}),
        }) if experience is not None or education is not None else FeatureGroup(available=False),
    )


def _job(domain: str, skills: list[str], **kwargs) -> JobRequirementVector:
    return JobRequirementVector(
        role=kwargs.pop("role", domain),
        domain=domain,
        required_skills=kwargs.pop("required_skills", skills),
        preferred_skills=kwargs.pop("preferred_skills", []),
        technical_skills=skills,
        skill_priorities={skill: 1.0 for skill in skills},
        **kwargs,
    )


def _rank(job: JobRequirementVector, candidates: list[tuple[str, CandidateFeatureVector]]):
    return rank_candidates({
        "job_requirements": job.model_dump(mode="json"),
        "candidates": [{"candidate_id": identifier, "candidate_features": vector.model_dump(mode="json")} for identifier, vector in candidates],
    })


class RankingEngineTests(TestCase):
    def test_backend_developer_ranking_prefers_matching_skills_and_projects(self):
        job = _job("Backend Development", ["Python", "Django", "REST APIs", "PostgreSQL"])
        strong = _candidate(["python", "Django", "REST APIs", "Postgres"], project=88, github=80)
        partial = _candidate(["Python"], project=55, github=50)
        result = _rank(job, [("partial", partial), ("strong", strong)])
        self.assertEqual(result.weight_profile, "backend")
        self.assertEqual(result.ranked_candidates[0].candidate_id, "strong")
        self.assertEqual(result.ranked_candidates[0].matched_required_skills, job.required_skills)
        self.assertEqual(result.ranked_candidates[1].missing_required_skills, ["Django", "REST APIs", "PostgreSQL"])

    def test_ml_research_profile_weights_research_and_kaggle_more(self):
        job = _job("Machine Learning", ["Python", "PyTorch", "Machine Learning"], role="ML Research Engineer")
        profile, weights = select_weight_profile(job)
        self.assertEqual(profile, "ml_research")
        self.assertGreater(weights["research"], weights["github"])
        researcher = _candidate(["Python", "PyTorch", "Machine Learning"], project=70, research=80, research_domains=["Artificial Intelligence and Machine Learning"], kaggle=75)
        github_only = _candidate(["Python", "PyTorch", "Machine Learning"], project=70, github=95)
        result = _rank(job, [("github", github_only), ("research", researcher)])
        self.assertEqual(result.ranked_candidates[0].candidate_id, "research")
        self.assertGreater(result.ranked_candidates[0].component_scores["research"].score, 0)

    def test_frontend_role_uses_frontend_weights(self):
        job = _job("Frontend Development", ["React", "JavaScript", "CSS"], role="Frontend Developer")
        profile, weights = select_weight_profile(job)
        self.assertEqual(profile, "frontend")
        self.assertGreater(weights["skills"], weights["coding"])
        result = _rank(job, [("web", _candidate(["React", "JavaScript", "CSS"], project=80))])
        self.assertEqual(result.ranked_candidates[0].matched_required_skills, job.required_skills)

    def test_competitive_programming_role_emphasizes_coding_profiles(self):
        job = _job("Competitive Programming", ["Algorithms", "Data Structures and Algorithms"], role="Competitive Programmer")
        profile, weights = select_weight_profile(job)
        self.assertEqual(profile, "competitive_programming")
        self.assertGreater(weights["coding"], weights["projects"])
        coder = _candidate(["Algorithms", "Data Structures and Algorithms"], coding=92)
        project_candidate = _candidate(["Algorithms", "Data Structures and Algorithms"], project=95)
        result = _rank(job, [("project", project_candidate), ("coder", coder)])
        self.assertEqual(result.ranked_candidates[0].candidate_id, "coder")

    def test_required_skills_dominate_preferred_skills(self):
        job = _job("Backend Development", ["Python", "Django"], required_skills=["Python"], preferred_skills=["Django", "AWS"])
        candidate = _candidate(["Python"])
        scored = _rank(job, [("candidate", candidate)]).ranked_candidates[0]
        self.assertEqual(scored.matched_required_skills, ["Python"])
        self.assertEqual(scored.missing_required_skills, [])
        self.assertEqual(scored.matched_preferred_skills, [])
        self.assertGreaterEqual(scored.component_scores["skills"].score, 70)

    def test_missing_data_is_not_treated_as_zero_and_weights_renormalize(self):
        job = _job("Backend Development", ["Python", "Django"])
        candidate = _candidate(["Python"], project=80)
        result = _rank(job, [("candidate", candidate)]).ranked_candidates[0]
        github = result.component_scores["github"]
        self.assertFalse(github.available)
        self.assertIsNone(github.score)
        self.assertIsNone(github.effective_weight)
        self.assertLess(result.data_coverage, 1.0)
        self.assertIn("github", result.explanation)

    def test_multiple_candidate_ranking_assigns_unique_ranks(self):
        job = _job("Backend Development", ["Python", "Django"])
        result = _rank(job, [
            ("candidate-c", _candidate(["Python"], project=50)),
            ("candidate-b", _candidate(["Python", "Django"], project=60)),
            ("candidate-a", _candidate(["Python", "Django"], project=90)),
        ])
        self.assertEqual([item.rank for item in result.ranked_candidates], [1, 2, 3])
        self.assertEqual([item.candidate_id for item in result.ranked_candidates], ["candidate-a", "candidate-b", "candidate-c"])

    def test_skill_normalization_matches_case_and_aliases(self):
        job = _job("Backend Development", ["JavaScript", "Node.js", "PostgreSQL"])
        result = _rank(job, [("candidate", _candidate(["JS", "Node", "Postgres"]))]).ranked_candidates[0]
        self.assertEqual(result.matched_required_skills, job.required_skills)

    def test_scores_remain_within_bounds(self):
        job = _job("Backend Development", ["Python"])
        result = _rank(job, [("candidate", _candidate(["Python"], project=150, github=-5))]).ranked_candidates[0]
        self.assertTrue(0 <= result.overall_score <= 100)
        self.assertTrue(0 <= result.job_fit_score <= 100)
        for score in result.component_scores.values():
            if score.score is not None:
                self.assertTrue(0 <= score.score <= 100)

    def test_results_are_deterministic(self):
        job = _job("Frontend Development", ["React", "TypeScript"])
        candidates = [("x", _candidate(["React"], project=70)), ("y", _candidate(["React", "TypeScript"], project=60))]
        first = _rank(job, candidates).model_dump(mode="json")
        second = _rank(job, candidates).model_dump(mode="json")
        self.assertEqual(first, second)

    def test_explanations_and_evidence_are_traceable(self):
        job = _job("Backend Development", ["Python", "Django"])
        result = _rank(job, [("candidate", _candidate(["Python"], project=85))]).ranked_candidates[0]
        self.assertIn("Matched required skills: Python", result.explanation)
        self.assertTrue(any(item.component == "skills" and item.source == "resume_analyzer" for item in result.evidence))
        self.assertTrue(any("project_score" in item for item in result.component_scores["projects"].evidence))

    def test_api_endpoint(self):
        job = _job("Backend Development", ["Python"])
        candidate = _candidate(["Python"], project=80)
        response = client.post("/rank-candidates", json={
            "job_requirements": job.model_dump(mode="json"),
            "candidates": [{"candidate_id": "candidate-1", "candidate_features": candidate.model_dump(mode="json")}],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["ranked_candidates"][0]["rank"], 1)
