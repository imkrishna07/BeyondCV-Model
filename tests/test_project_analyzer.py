"""Coverage for static project analysis and unsafe archive handling."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import zipfile

from fastapi.testclient import TestClient

from app.analyzers.project.analyzer import analyze_project_directory, analyze_project_zip
from app.analyzers.project.file_scanner import InvalidProjectArchive
from app.main import app


def make_zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


class ProjectAnalyzerTests(unittest.TestCase):
    def test_simple_python_project(self) -> None:
        result = analyze_project_zip(make_zip({
            "main.py": "def greet(name):\n    try:\n        return f'Hello {name}'\n    except ValueError:\n        return 'Hello'\n",
            "requirements.txt": "fastapi==0.1\n",
        }))

        self.assertEqual(result.structure.source_files, 1)
        self.assertEqual(result.structure.languages, {"Python": 1})
        self.assertIn("Python", [item.name for item in result.technologies])
        self.assertIsNotNone(result.project_score)
        self.assertEqual(result.project_scale, "small")

    def test_frontend_backend_structure(self) -> None:
        result = analyze_project_zip(make_zip({
            "frontend/src/App.tsx": "export default function App() { return <main /> }",
            "frontend/package.json": '{"dependencies":{"react":"^18.0.0"}}',
            "backend/api/main.py": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/api/items')\ndef items(): return []\n",
        }))

        self.assertTrue(result.structure.frontend_present)
        self.assertTrue(result.structure.backend_present)
        self.assertIn("React", [item.name for item in result.technologies])
        self.assertGreaterEqual(result.architecture or 0, 60)

    def test_readme_documentation_signals(self) -> None:
        result = analyze_project_zip(make_zip({
            "README.md": "# Demo\n## Problem Statement\nA scheduling problem.\n## Setup\nRun pip install.\n## Architecture\nAPI and database.\n## Demo\n![screenshot](screen.png)\n",
            "src/main.py": "print('hello')\n",
        }))

        areas = {item.area for item in result.evidence}
        findings = " ".join(item.finding for item in result.evidence)
        self.assertIn("documentation", areas)
        self.assertIn("Setup instructions", findings)
        self.assertIn("Architecture explanation", findings)
        self.assertIn("Screenshots or demo", findings)

    def test_tests_and_docker_detected(self) -> None:
        result = analyze_project_zip(make_zip({
            "src/app.py": "def run():\n    return True\n",
            "tests/test_app.py": "def test_run():\n    assert True\n",
            "Dockerfile": "FROM python:3.13\nCMD ['python', 'src/app.py']\n",
            ".github/workflows/test.yml": "name: tests\n",
        }))

        self.assertEqual(result.structure.test_files, 1)
        self.assertIn("Docker configuration", " ".join(item.finding for item in result.evidence))
        self.assertEqual(result.deployment, 60)
        self.assertGreater(result.testing or 0, 0)

    def test_invalid_zip_is_rejected(self) -> None:
        with self.assertRaises(InvalidProjectArchive):
            analyze_project_zip(b"not a zip")

    def test_path_traversal_zip_is_rejected(self) -> None:
        with self.assertRaises(InvalidProjectArchive):
            analyze_project_zip(make_zip({"../outside.py": "print('unsafe')"}))

    def test_empty_project_has_insufficient_evidence_and_no_score(self) -> None:
        result = analyze_project_zip(make_zip({}))

        self.assertEqual(result.evidence_level, "insufficient")
        self.assertIsNone(result.project_score)
        self.assertEqual(result.structure.total_files, 0)

    def test_local_directory_interface_and_sensitive_file_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("API_TOKEN = 'not-to-be-returned'\n", encoding="utf-8")
            (root / ".env").write_text("API_TOKEN=must-not-be-read\n", encoding="utf-8")
            result = analyze_project_directory(root)

        self.assertEqual(result.structure.source_files, 1)
        serialized = result.model_dump_json()
        self.assertNotIn("must-not-be-read", serialized)
        self.assertNotIn("not-to-be-returned", serialized)
        self.assertTrue(any("secret" in item.finding.lower() for item in result.evidence))


class ProjectEndpointTests(unittest.TestCase):
    def test_zip_upload_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/analyze-project",
                files={"file": ("project.zip", make_zip({"README.md": "# App\n", "main.py": "print('ok')\n"}), "application/zip")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["structure"]["source_files"], 1)
        self.assertIn("project_score", response.json())

    def test_endpoint_rejects_invalid_zip(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/analyze-project",
                files={"file": ("project.zip", b"not a zip", "application/zip")},
            )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
