"""Tests for deterministic resume extraction and the upload API."""

from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.analyzers.resume.extractor import (
    EmptyResume,
    InvalidResumePDF,
    analyze_resume_text,
    extract_pdf_text,
)
from app.main import app


SAMPLE_RESUME = """Jordan Lee
Skills
Python, Django; PostgreSQL
Education:
BSc Computer Science, Example University, 2021-2024
Experience
Backend Intern | Example Co | 2024
Built internal tools using Python.
Projects
Resume Matcher — Django application
Certifications
AWS Certified Cloud Practitioner
Achievements
Winner, Campus Hackathon
Research
Efficient Search in Graphs (student paper)
"""


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class ResumeTextExtractionTests(unittest.TestCase):
    def test_extracts_explicit_section_content(self) -> None:
        result = analyze_resume_text(SAMPLE_RESUME)

        self.assertEqual([skill.name for skill in result.skills], ["Python", "Django", "PostgreSQL"])
        self.assertEqual(result.education[0].details, "BSc Computer Science, Example University, 2021-2024")
        self.assertEqual(result.experience[0].details, "Backend Intern | Example Co | 2024")
        self.assertEqual(result.projects[0].details, "Resume Matcher — Django application")
        self.assertEqual(result.certifications[0].details, "AWS Certified Cloud Practitioner")
        self.assertEqual(result.achievements[0].details, "Winner, Campus Hackathon")
        self.assertEqual(result.research[0].details, "Efficient Search in Graphs (student paper)")

    def test_missing_sections_return_empty_lists(self) -> None:
        result = analyze_resume_text("Summary\nExperienced engineer.")

        self.assertEqual(result.model_dump(), {
            "skills": [], "education": [], "experience": [], "projects": [],
            "certifications": [], "achievements": [], "research": [],
        })

    def test_rejects_non_pdf_bytes(self) -> None:
        with self.assertRaises(InvalidResumePDF):
            extract_pdf_text(b"this is not a pdf")

    def test_rejects_valid_pdf_without_extractable_text(self) -> None:
        with self.assertRaises(EmptyResume):
            extract_pdf_text(_blank_pdf())

    def test_wraps_unexpected_pdf_parser_failure(self) -> None:
        with patch("app.analyzers.resume.extractor.PdfReader", side_effect=RuntimeError("parser failure")):
            from app.analyzers.resume.extractor import ResumeExtractionError

            with self.assertRaises(ResumeExtractionError):
                extract_pdf_text(b"%PDF-1.7\nmock")


class ResumeEndpointTests(unittest.TestCase):
    def test_endpoint_returns_structured_json(self) -> None:
        with patch("app.api.routes.extract_pdf_text", return_value=SAMPLE_RESUME):
            with TestClient(app) as client:
                response = client.post(
                    "/analyze-resume",
                    files={"file": ("resume.pdf", b"%PDF-mock", "application/pdf")},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["skills"][0], {"name": "Python"})
        self.assertEqual(payload["education"][0]["details"], "BSc Computer Science, Example University, 2021-2024")

    def test_invalid_pdf_returns_400(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/analyze-resume",
                files={"file": ("resume.pdf", b"not a pdf", "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)

    def test_empty_pdf_returns_422(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/analyze-resume",
                files={"file": ("empty.pdf", _blank_pdf(), "application/pdf")},
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
