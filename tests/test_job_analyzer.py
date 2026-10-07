"""Rule-based job requirement extraction tests; no model or network access is needed."""

from unittest import TestCase
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.analyzers.job.analyzer import analyze_job_description
from app.main import app
from app.schemas.job import JobAnalysisRequest


client = TestClient(app)


class JobAnalyzerTests(TestCase):
    def analyze(self, text: str):
        return analyze_job_description(JobAnalysisRequest(job_description=text)).job_requirements

    def test_backend_developer_job(self):
        result = self.analyze(
            "Backend Developer Intern\n\n"
            "We are looking for a backend developer intern with experience in Python, Django, "
            "REST APIs, PostgreSQL and Docker. Candidates should understand databases, authentication "
            "and API development. Knowledge of AWS and Redis is preferred."
        )
        self.assertEqual(result.role, "Backend Developer Intern")
        self.assertEqual(result.domain, "Backend Development")
        self.assertTrue({"Python", "Django", "REST APIs", "PostgreSQL", "Docker", "Database Concepts", "Authentication", "API Development"}.issubset(result.required_skills))
        self.assertIn("AWS", result.preferred_skills)
        self.assertIn("Redis", result.preferred_skills)
        self.assertIn("Django", result.frameworks)
        self.assertIn("PostgreSQL", result.databases)
        self.assertIn("backend_projects", result.relevant_evidence)

    def test_ml_engineer_job(self):
        result = self.analyze("Machine Learning Engineer\nStrong knowledge of Python, PyTorch and scikit-learn. Experience with NLP and model evaluation required.")
        self.assertEqual(result.domain, "Machine Learning")
        self.assertIn("Python", result.programming_languages)
        self.assertIn("PyTorch", result.frameworks)
        self.assertIn("Natural Language Processing", result.technical_skills)
        self.assertIn("research_publications", result.relevant_evidence)
        self.assertIn("kaggle", result.relevant_evidence)

    def test_frontend_developer_job(self):
        result = self.analyze("Frontend Developer\nBuild interfaces using ReactJS, JS, Node and CSS. Strong communication and teamwork are required.")
        self.assertEqual(result.role, "Frontend Developer")
        self.assertEqual(result.domain, "Frontend Development")
        self.assertIn("React", result.frameworks)
        self.assertIn("JavaScript", result.programming_languages)
        self.assertIn("Node.js", result.frameworks)
        self.assertIn("Communication", result.soft_skills)
        self.assertIn("Teamwork", result.soft_skills)
        self.assertIn("frontend_projects", result.relevant_evidence)

    def test_competitive_programming_role(self):
        result = self.analyze("Competitive Programming Coach\nExperience with algorithms, data structures and Codeforces contests required.")
        self.assertEqual(result.domain, "Competitive Programming")
        self.assertIn("Competitive Programming", result.technical_skills)
        self.assertIn("Algorithms", result.technical_skills)
        self.assertIn("coding_profiles", result.relevant_evidence)

    def test_required_and_preferred_skills_are_distinct(self):
        result = self.analyze("Backend Engineer\nRequired: Python and Django. Preferred: AWS, familiarity with Redis, and Docker is a bonus.")
        self.assertIn("Python", result.required_skills)
        self.assertIn("Django", result.required_skills)
        self.assertNotIn("AWS", result.required_skills)
        self.assertNotIn("Redis", result.required_skills)
        self.assertNotIn("Docker", result.required_skills)
        self.assertIn("AWS", result.preferred_skills)
        self.assertIn("Redis", result.preferred_skills)
        self.assertIn("Docker", result.preferred_skills)
        self.assertEqual(result.skill_priorities["Python"], 1.0)
        self.assertEqual(result.skill_priorities["AWS"], 0.5)

    def test_experience_and_education_requirements_and_missing_sections(self):
        result = self.analyze("Software Engineer\nMust have 2-4 years of experience. Bachelor's degree in Computer Science preferred.")
        self.assertEqual(result.experience_requirements[0].minimum_years, 2)
        self.assertEqual(result.experience_requirements[0].maximum_years, 4)
        self.assertEqual(result.experience_requirements[0].requirement, "required")
        self.assertEqual(result.education_requirements[0].requirement, "preferred")
        no_optional_sections = self.analyze("Backend Developer\nBuild reliable services with Python.")
        self.assertEqual(no_optional_sections.experience_requirements, [])
        self.assertEqual(no_optional_sections.education_requirements, [])
        abbreviation = self.analyze("Data Engineer\nBS degree in Computer Science preferred.")
        self.assertEqual(abbreviation.education_requirements[0].requirement, "preferred")

    def test_role_can_be_extracted_from_prose(self):
        result = self.analyze("We are looking for a backend developer intern with experience in Python.")
        self.assertEqual(result.role, "Backend Developer Intern")

    def test_empty_job_description_returns_empty_vector(self):
        response = client.post("/analyze-job", json={"job_description": ""})
        self.assertEqual(response.status_code, 200)
        requirements = response.json()["job_requirements"]
        self.assertIsNone(requirements["role"])
        self.assertIsNone(requirements["domain"])
        self.assertEqual(requirements["technical_skills"], [])
        self.assertEqual(requirements["skill_priorities"], {})

    def test_skill_normalization_and_generic_words_are_not_technologies(self):
        result = self.analyze("Developer\nJS, Node, Postgres and ReactJS. We go to the office and use good judgment.")
        self.assertIn("JavaScript", result.programming_languages)
        self.assertIn("Node.js", result.frameworks)
        self.assertIn("PostgreSQL", result.databases)
        self.assertIn("React", result.frameworks)
        self.assertNotIn("Go", result.programming_languages)
        self.assertNotIn("Good", result.technical_skills)

    def test_optional_semantic_domain_matcher_is_isolated(self):
        matcher = Mock()
        matcher.enabled = True
        matcher.classify_domain.return_value = "Data Science"
        result = analyze_job_description("Research associate supporting analytics", semantic_matcher=matcher).job_requirements
        self.assertEqual(result.domain, "Data Science")
        self.assertEqual(result.extraction_method, "rules+semantic")

    def test_api_request_validation(self):
        response = client.post("/analyze-job", json={"unexpected": "field"})
        self.assertEqual(response.status_code, 422)
