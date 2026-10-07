"""Project inspection orchestration for local folders and uploaded ZIP files."""

from pathlib import Path, PurePosixPath
import re

from app.analyzers.project.code_metrics import inspect_code
from app.analyzers.project.dependency_detector import detect_dependencies
from app.analyzers.project.file_scanner import ScannedProject, scan_directory, scan_zip_bytes
from app.analyzers.project.language_detector import detect_languages, is_source_file
from app.analyzers.project.scoring import WEIGHTS, score_project
from app.schemas.project import (
    ProjectAnalysisResponse,
    ProjectEvidence,
    ProjectInspection,
    ProjectStructure,
    ProjectTechnology,
)


_DOC_EXTENSIONS = {".md", ".rst", ".adoc"}
_TEST_NAME = re.compile(r"(?:^|/)(?:tests?|specs?)(?:/|$)|(?:^|/)(?:test|spec)[^/]*\.(?:py|[cm]?[jt]sx?)$|\.(?:test|spec)\.[cm]?[jt]sx?$", re.I)
_CONFIG_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini", "package.json",
    "tsconfig.json", "webpack.config.js", "vite.config.js", "vite.config.ts", "babel.config.js",
    "makefile", "justfile", ".editorconfig", ".prettierrc", ".eslintrc", "eslint.config.js",
}
_DEPLOY_NAMES = {
    "procfile", "vercel.json", "netlify.toml", "render.yaml", "fly.toml", "railway.toml",
    "serverless.yml", "serverless.yaml", "terraform.tf", "main.tf", "app.yaml",
}
_SEPARATION_DIRS = {
    "api", "app", "apps", "components", "controllers", "models", "routes", "services",
    "repositories", "repository", "views", "utils", "frontend", "backend",
    "client", "server", "src",
}
_FRONTEND_EXTENSIONS = {".html", ".css", ".jsx", ".tsx", ".vue", ".svelte"}
_BACKEND_DIRS = {"backend", "server", "api"}
_FRONTEND_DIRS = {"frontend", "client", "web", "ui"}


def _readme_features(files: dict[str, str], readme_paths: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    headings: set[str] = set()
    features = {
        "readme": list(readme_paths),
        "problem_statement": [],
        "setup_instructions": [],
        "architecture_explanation": [],
        "api_documentation": [],
        "screenshots_or_demo": [],
    }
    for path in readme_paths:
        content = files[path]
        headings.update(
            re.sub(r"[^a-z0-9 ]", "", line.lstrip("#").strip().lower())
            for line in content.splitlines() if line.lstrip().startswith("#")
        )
        lowered = content.lower()
        if re.search(r"problem statement|problem this project|problem it solves|\bwhy this project\b", lowered):
            features["problem_statement"].append(path)
        if re.search(r"\b(installation|setup|getting started|how to run|usage)\b", lowered):
            features["setup_instructions"].append(path)
        if re.search(r"\b(architecture|system design|technical design)\b", lowered):
            features["architecture_explanation"].append(path)
        if re.search(r"\b(api documentation|api reference|swagger|openapi|endpoints)\b", lowered):
            features["api_documentation"].append(path)
        if re.search(r"\b(screenshot|demo|live demo|video walkthrough)\b|!\[[^]]*\]\([^)]*\)", lowered):
            features["screenshots_or_demo"].append(path)
    return sorted(headings), features


def _inspect(scanned: ScannedProject) -> ProjectInspection:
    files = scanned.files
    paths = sorted(files)
    source_files = sorted(path for path in paths if is_source_file(path))
    documentation_files = sorted(
        path for path in paths
        if PurePosixPath(path).suffix.lower() in _DOC_EXTENSIONS
        or "docs" in {part.lower() for part in PurePosixPath(path).parts[:-1]}
    )
    readme_files = sorted(
        path for path in paths
        if PurePosixPath(path).name.lower().startswith("readme")
        and PurePosixPath(path).suffix.lower() in {".md", ".rst", ".txt", ".adoc", ""}
    )
    test_files = sorted(path for path in paths if _TEST_NAME.search(path))
    dependency_files, dependency_technologies = detect_dependencies(files)
    languages = detect_languages(files)
    language_technologies = [
        ProjectTechnology(
            name=language, category="programming language",
            evidence_files=sorted(path for path in source_files if detect_languages({path: files[path]}).get(language)),
        )
        for language in languages
    ]
    technologies = { (tech.name, tech.category): tech for tech in language_technologies + dependency_technologies }
    technologies_list = [technologies[key] for key in sorted(technologies)]

    metrics = inspect_code(files)
    implementation_files = [path for path in source_files if path not in test_files]
    source_dirs = sorted({
        "/".join(PurePosixPath(path).parts[:-1])
        for path in implementation_files if len(PurePosixPath(path).parts) > 1
    })
    frontend_files = sorted(path for path in source_files if (
        PurePosixPath(path).suffix.lower() in _FRONTEND_EXTENSIONS
        or bool(set(part.lower() for part in PurePosixPath(path).parts[:-1]) & _FRONTEND_DIRS)
    ))
    backend_files = sorted(path for path in source_files if (
        bool(set(part.lower() for part in PurePosixPath(path).parts[:-1]) & _BACKEND_DIRS)
        or path in metrics.api_files
        or (PurePosixPath(path).suffix.lower() in {".py", ".java", ".go", ".rs", ".php", ".rb"}
            and any(tech.name in {"FastAPI", "Django", "Flask", "Express", "Spring Boot", "Laravel", "Ruby on Rails"} for tech in technologies_list))
    ))

    config_files = sorted(path for path in paths if (
        PurePosixPath(path).name.lower() in _CONFIG_NAMES
        or PurePosixPath(path).suffix.lower() in {".toml", ".yaml", ".yml", ".ini", ".cfg"}
        or path in dependency_files
    ))
    docker_files = sorted(path for path in paths if PurePosixPath(path).name.lower() in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})
    ci_files = sorted(path for path in paths if (
        ".github/workflows/" in path.lower() or ".gitlab-ci" in PurePosixPath(path).name.lower()
        or PurePosixPath(path).name.lower() in {"jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml"}
    ))
    cloud_files = sorted(path for path in paths if (
        "terraform" in path.lower() or "cloudformation" in path.lower()
        or PurePosixPath(path).name.lower() in {"serverless.yml", "serverless.yaml", "app.yaml"}
    ))
    deployment_files = sorted(set(docker_files + [path for path in paths if PurePosixPath(path).name.lower() in _DEPLOY_NAMES]))
    api_docs_files = sorted(path for path in documentation_files if (
        any(term in path.lower() for term in ("api", "swagger", "openapi"))
        or re.search(r"(?i)\b(?:swagger|openapi|api reference|api documentation)\b", files[path])
    ))
    coverage_files = sorted(path for path in paths if PurePosixPath(path).name.lower() in {
        ".coveragerc", "coverage.xml", "lcov.info", "codecov.yml", "codecov.yaml"
    })
    readme_headings, doc_signals = _readme_features(files, readme_files)
    if api_docs_files:
        doc_signals["api_documentation"].extend(api_docs_files)
    for path in documentation_files:
        if "screenshot" in path.lower() or "demo" in path.lower():
            doc_signals["screenshots_or_demo"].append(path)
    doc_signals = {key: sorted(set(value)) for key, value in doc_signals.items()}
    separation_dirs = sorted({
        part.lower()
        for path in implementation_files for part in PurePosixPath(path).parts[:-1]
        if part.lower() in _SEPARATION_DIRS
    })

    inspection = ProjectInspection(
        file_paths=paths,
        source_files=source_files,
        documentation_files=documentation_files,
        test_files=test_files,
        configuration_files=config_files,
        skipped_binary_files=scanned.skipped_binary_files,
        skipped_large_files=scanned.skipped_large_files,
        languages=languages,
        source_directories=source_dirs,
        frontend_files=frontend_files,
        backend_files=backend_files,
        dependency_files=dependency_files,
        technologies=technologies_list,
        readme_files=readme_files,
        readme_headings=readme_headings,
        documentation_signals=doc_signals,
        separation_directories=separation_dirs,
        api_files=metrics.api_files,
        api_docs_files=api_docs_files,
        database_files=metrics.database_files,
        auth_files=metrics.auth_files,
        integration_files=metrics.integration_files,
        algorithm_files=metrics.algorithm_files,
        deployment_files=deployment_files,
        docker_files=docker_files,
        ci_files=ci_files,
        cloud_files=cloud_files,
        coverage_files=coverage_files,
        env_usage_files=metrics.env_usage_files,
        secret_pattern_files=metrics.secret_pattern_files,
        error_handling_files=metrics.error_handling_files,
        meaningful_code_lines=metrics.meaningful_lines,
        duplicate_line_count=metrics.duplicate_line_count,
        naming_consistent_files=metrics.naming_consistent_files,
    )
    return inspection


def _build_response(inspection: ProjectInspection, scanned: ScannedProject) -> ProjectAnalysisResponse:
    scores = score_project(inspection)
    structure = ProjectStructure(
        total_files=scanned.total_files_seen,
        source_files=len(inspection.source_files),
        documentation_files=len(inspection.documentation_files),
        test_files=len(inspection.test_files),
        configuration_files=len(inspection.configuration_files),
        skipped_binary_files=inspection.skipped_binary_files,
        skipped_large_files=inspection.skipped_large_files,
        file_types=dict(sorted(scanned.file_types.items())),
        languages=inspection.languages,
        component_count=len(inspection.source_directories) or int(bool(inspection.source_files)),
        source_directories=inspection.source_directories,
        frontend_present=bool(inspection.frontend_files),
        backend_present=bool(inspection.backend_files),
    )
    evidence: list[ProjectEvidence] = []

    def add(area: str, message: str, files: list[str]) -> None:
        if files:
            evidence.append(ProjectEvidence(area=area, finding=message, files=files[:20]))

    add("structure", f"Inspected {scanned.total_files_seen} files; identified {len(inspection.source_files)} source files.", inspection.file_paths)
    add("documentation", "README/documentation file detected.", inspection.readme_files)
    for label, key in (
        ("Problem statement documented", "problem_statement"),
        ("Setup instructions documented", "setup_instructions"),
        ("Architecture explanation documented", "architecture_explanation"),
        ("API documentation detected", "api_documentation"),
        ("Screenshots or demo information detected", "screenshots_or_demo"),
    ):
        add("documentation", label + ".", inspection.documentation_signals.get(key, []))
    add("testing", "Test files detected.", inspection.test_files)
    add("testing", "Coverage configuration/artifact detected.", inspection.coverage_files)
    add("deployment", "Docker configuration detected.", inspection.docker_files)
    add("deployment", "CI/CD configuration detected.", inspection.ci_files)
    add("deployment", "Cloud or infrastructure configuration detected.", inspection.cloud_files)
    add("security", "Environment-variable access pattern detected in source.", inspection.env_usage_files)
    add("security", "Authentication-related code pattern detected; behavior was not executed or validated.", inspection.auth_files)
    add("security", "Potential hardcoded secret pattern detected; values are suppressed.", inspection.secret_pattern_files)
    add("architecture", "Frontend and backend source indicators are both present.", inspection.frontend_files + inspection.backend_files)
    add("architecture", "Common separation-of-concerns directories detected: " + ", ".join(inspection.separation_directories) + ".", inspection.source_files)
    add("code_quality", "Error-handling syntax indicators detected.", inspection.error_handling_files)
    add("code_quality", f"Repeated nontrivial source lines detected: {inspection.duplicate_line_count}.", inspection.source_files if inspection.duplicate_line_count else [])
    for technology in inspection.technologies:
        add("technologies", f"Detected {technology.category}: {technology.name}.", technology.evidence_files)

    strengths: list[str] = []
    weaknesses: list[str] = []
    if inspection.source_files:
        strengths.append(f"Static scan identified {len(inspection.source_files)} source files across {len(inspection.languages)} programming language(s).")
    if inspection.frontend_files and inspection.backend_files:
        strengths.append("Both frontend and backend source indicators were found.")
    if inspection.test_files:
        strengths.append(f"Test files were found ({len(inspection.test_files)}).")
    if inspection.readme_files and inspection.documentation_signals.get("setup_instructions"):
        strengths.append("A README with setup instructions was found.")
    if inspection.deployment_files or inspection.ci_files or inspection.cloud_files:
        strengths.append("Deployment or CI configuration was found.")
    if not inspection.source_files:
        weaknesses.append("No recognized source-code files were found; project quality and complexity scores are unavailable.")
    if not inspection.readme_files:
        weaknesses.append("No README file was detected.")
    if inspection.source_files and not inspection.test_files:
        weaknesses.append("No test files were detected in inspected paths.")
    if inspection.source_files and not (inspection.deployment_files or inspection.ci_files or inspection.cloud_files):
        weaknesses.append("No deployment, CI/CD, or cloud configuration was detected.")
    if inspection.secret_pattern_files:
        weaknesses.append("Potential hardcoded secret patterns need manual review; the scanner does not reveal matched values.")
    if inspection.duplicate_line_count:
        weaknesses.append("Repeated nontrivial lines were found; this is a basic duplication signal, not a semantic clone check.")

    return ProjectAnalysisResponse(
        project_score=scores.project_score,
        technical_complexity=scores.technical_complexity,
        code_quality=scores.code_quality,
        architecture=scores.architecture,
        documentation=scores.documentation,
        testing=scores.testing,
        deployment=scores.deployment,
        security=scores.security,
        completeness=scores.completeness,
        evidence_level=scores.evidence_level,
        project_scale=scores.project_scale,
        score_weights=WEIGHTS,
        dimension_scoring={
            "technical_complexity": "Eight detectable engineering signals, equally weighted: full stack, database, auth, API, integrations, algorithms, deployment/configuration, and multiple languages.",
            "code_quality": "Starts at 35; adds modularity, naming consistency, error-handling syntax, and source size signals; subtracts a capped repeated-line penalty.",
            "architecture": "Starts at 35; adds up to 40 for detected separation-of-concerns directories and 25 for both frontend and backend indicators.",
            "documentation": "Six binary checks, equally weighted: README, problem statement, setup, architecture explanation, API docs, and screenshots/demo information.",
            "testing": "55 for test files, 20 for a detected test framework, and 25 for coverage configuration/artifacts.",
            "deployment": "30 Docker, 30 CI/CD, 20 cloud/infrastructure, and 20 other deployment configuration; each category contributes at most once.",
            "security": "Starts at 30; adds environment access, auth indicators, and dependency manifests; subtracts up to 60 per file with a possible hardcoded-secret pattern.",
            "completeness": "30 source, 20 README, 15 tests, 10 dependencies, 10 deployment/CI/cloud, 10 full-stack indicators, and 5 multiple source directories.",
        },
        structure=structure,
        technologies=inspection.technologies,
        strengths=strengths,
        weaknesses=weaknesses,
        evidence=evidence,
    )


def analyze_scanned_project(scanned: ScannedProject) -> ProjectAnalysisResponse:
    inspection = _inspect(scanned)
    return _build_response(inspection, scanned)


def analyze_project_directory(directory: str | Path) -> ProjectAnalysisResponse:
    """Analyze a local project directory without executing any project code."""
    return analyze_scanned_project(scan_directory(directory))


def analyze_project_zip(archive_bytes: bytes) -> ProjectAnalysisResponse:
    """Analyze a ZIP byte payload without extracting or executing it."""
    return analyze_scanned_project(scan_zip_bytes(archive_bytes))
